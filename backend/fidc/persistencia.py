"""Guarda o app.sqlite (carteira, watchlist, notas, checklist de DD...) num bucket do Cloud Storage.

O disco do Cloud Run é apagado quando a instância desliga ou sai versão nova. Com FIDC_BUCKET definido:
- na subida, baixa a última cópia do bucket antes de qualquer acesso ao app.sqlite;
- a cada sessão que grava algo, envia uma cópia consistente (API de backup do SQLite) em segundo plano.
O serviço roda com no máximo 1 instância, então não há duas cópias divergindo. Credencial: a conta de serviço da
instância, pelo servidor de metadados (sem chave). Sem FIDC_BUCKET (uso local) nada disso roda.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from urllib.parse import quote

import httpx

from . import config

log = logging.getLogger(__name__)
OBJETO = "app.sqlite"
_TOKEN_URL = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
_lock = threading.Lock()
_pendente = threading.Event()
_token: dict = {"v": None, "ate": 0.0}
ESTADO = {"ativo": False, "ultimo_envio": None, "erro": None, "bloqueado": False}


def bucket() -> str | None:
    return os.environ.get("FIDC_BUCKET") or None


def _cabecalho() -> dict:
    if time.time() > _token["ate"] - 60:
        r = httpx.get(_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=10)
        r.raise_for_status()
        j = r.json()
        _token.update(v=j["access_token"], ate=time.time() + j.get("expires_in", 300))
    return {"Authorization": f"Bearer {_token['v']}"}


def baixar() -> str:
    """Restaura o app.sqlite do bucket. Retorna 'restaurado', 'vazio' (primeira vez) ou 'desligado'."""
    b = bucket()
    if not b:
        return "desligado"
    ESTADO["ativo"] = True
    url = f"https://storage.googleapis.com/storage/v1/b/{b}/o/{quote(OBJETO, safe='')}?alt=media"
    try:
        r = httpx.get(url, headers=_cabecalho(), timeout=60)
    except httpx.HTTPError as e:
        ESTADO.update(erro=f"falha ao baixar: {e}", bloqueado=True)   # não sobrescreve a cópia boa do bucket
        log.error("persistência: %s", ESTADO["erro"])
        return "erro"
    if r.status_code == 404:
        return "vazio"
    if r.status_code >= 400:
        ESTADO.update(erro=f"bucket respondeu {r.status_code}: {r.text[:200]}", bloqueado=True)
        log.error("persistência: %s", ESTADO["erro"])
        return "erro"
    Path(config.APP_DB_PATH).write_bytes(r.content)
    return "restaurado"


def _enviar() -> None:
    b = bucket()
    with _lock:                       # um envio por vez; sempre manda o estado mais recente
        _pendente.clear()
        with tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False) as f:
            tmp = Path(f.name)
        try:
            src, dst = sqlite3.connect(config.APP_DB_PATH), sqlite3.connect(tmp)
            src.backup(dst)
            src.close()
            dst.close()
            url = f"https://storage.googleapis.com/upload/storage/v1/b/{b}/o?uploadType=media&name={quote(OBJETO, safe='')}"
            r = httpx.post(url, content=tmp.read_bytes(), timeout=60,
                           headers={**_cabecalho(), "Content-Type": "application/x-sqlite3"})
            r.raise_for_status()
            ESTADO.update(ultimo_envio=time.strftime("%Y-%m-%d %H:%M:%S"), erro=None)
        except Exception as e:  # noqa: BLE001 - não derruba a requisição do usuário
            ESTADO["erro"] = f"falha ao salvar: {e}"
            log.error("persistência: %s", ESTADO["erro"])
        finally:
            tmp.unlink(missing_ok=True)


def alterou() -> None:
    """Chamado depois de um commit que mudou algo. Envia em segundo plano (vários cliques seguidos = 1-2 envios)."""
    if not bucket() or ESTADO["bloqueado"] or _pendente.is_set():
        return
    _pendente.set()
    threading.Thread(target=_enviar, daemon=True).start()
