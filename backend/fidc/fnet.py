"""Cliente do FNET (B3), onde os administradores publicam os documentos dos fundos.

A API de busca não é documentada oficialmente; usamos o mesmo endpoint da tela
pública "Gerenciador de Documentos". Por isso:
- toda chamada tem timeout, retry e cache em disco;
- falha do FNET nunca derruba o app (retorna lista vazia + aviso).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime

import httpx

from . import config

log = logging.getLogger(__name__)

SEARCH = f"{config.FNET_BASE}/pesquisarGerenciadorDocumentosDados"
CACHE_TTL = 6 * 3600
HEADERS = {"X-Requested-With": "XMLHttpRequest", "Accept": "application/json",
           "User-Agent": "Mozilla/5.0 (analisador-fidc)"}

# Categorias de documento que viram "evento" na linha do tempo da lâmina
EVENTOS = {"Fato Relevante", "Assembleia", "Comunicado ao Mercado", "Aviso aos Cotistas",
           "Relatórios", "Regulamento", "Atos de Deliberação do Administrador",
           "Oferta Pública de Distribuição de Cotas"}


def link(doc_id: int) -> str:
    return f"{config.FNET_BASE}/exibirDocumento?id={doc_id}&cvm=true"


def _get(params: dict, tries: int = 3) -> dict:
    last: Exception | None = None
    for i in range(tries):
        try:
            with httpx.Client(timeout=60, headers=HEADERS) as c:
                r = c.get(SEARCH, params=params)
                r.raise_for_status()
                return r.json()
        except Exception as e:  # noqa: BLE001 - FNET falha de vários jeitos
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"FNET indisponível: {last}")


def _parse(r: dict) -> dict:
    def dt(s, fmt):
        try:
            return datetime.strptime(s, fmt).isoformat()
        except (TypeError, ValueError):
            return None
    return {
        "id": r.get("id"),
        "data_entrega": dt(r.get("dataEntrega"), "%d/%m/%Y %H:%M"),
        "data_referencia": r.get("dataReferencia"),
        "categoria": (r.get("categoriaDocumento") or "").strip(),
        "tipo": (r.get("tipoDocumento") or "").strip(),
        "especie": (r.get("especieDocumento") or "").strip(),
        "fundo": r.get("descricaoFundo"),
        "status": r.get("descricaoStatus"),
        "link": link(r["id"]) if r.get("id") else None,
    }


def documentos(cnpj: str, limite: int = 200, use_cache: bool = True) -> dict:
    """Documentos de um fundo no FNET, do mais recente para o mais antigo."""
    cnpj = "".join(ch for ch in cnpj if ch.isdigit()).zfill(14)
    cache = config.FNET_CACHE_DIR / f"{cnpj}.json"
    if use_cache and cache.exists() and time.time() - cache.stat().st_mtime < CACHE_TTL:
        return json.loads(cache.read_text())
    try:
        docs: list[dict] = []
        start = 0
        while len(docs) < limite:
            page = _get({"d": 1, "s": start, "l": min(100, limite - len(docs)),
                         "o[0][dataEntrega]": "desc", "cnpjFundo": cnpj})
            rows = page.get("data") or []
            docs += [_parse(r) for r in rows]
            start += len(rows)
            if not rows or start >= (page.get("recordsTotal") or 0):
                break
        out = {"cnpj": cnpj, "ok": True, "atualizado_em": datetime.now().isoformat(), "documentos": docs}
        cache.write_text(json.dumps(out, ensure_ascii=False))
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("FNET falhou para %s: %s", cnpj, e)
        if cache.exists():  # cache vencido é melhor que nada
            out = json.loads(cache.read_text())
            out["aviso"] = "FNET indisponível; exibindo cache anterior"
            return out
        return {"cnpj": cnpj, "ok": False, "aviso": str(e), "documentos": []}


def eventos(cnpj: str) -> list[dict]:
    """Documentos relevantes para a linha do tempo (exclui informes periódicos de rotina)."""
    return [d for d in documentos(cnpj)["documentos"] if d["categoria"] in EVENTOS]
