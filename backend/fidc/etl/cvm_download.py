"""Download incremental dos informes mensais de FIDC do Portal de Dados Abertos da CVM.

Fonte: https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/DADOS/
- HIST/inf_mensal_fidc_AAAA.zip  -> anos fechados
- inf_mensal_fidc_AAAAMM.zip     -> meses recentes (a CVM republica quando há reenvio)

Um manifesto guarda a data de modificação de cada zip; só baixamos o que mudou.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

from .. import config

log = logging.getLogger(__name__)

MANIFEST = config.RAW_DIR / "manifest.json"
_LINE = re.compile(r'href="(inf_mensal_fidc_\d+\.zip)">[^<]*</a>\s+(\S+ \S+)\s+(\S+)')


def _listing(client: httpx.Client, url: str) -> dict[str, str]:
    html = client.get(url).text
    return {m.group(1): f"{m.group(2)}|{m.group(3)}" for m in _LINE.finditer(html)}


def remote_files(client: httpx.Client) -> dict[str, tuple[str, str]]:
    """{nome_zip: (url, versao)} para histórico + meses recentes."""
    out: dict[str, tuple[str, str]] = {}
    for name, ver in _listing(client, f"{config.CVM_BASE}/HIST/").items():
        out[name] = (f"{config.CVM_BASE}/HIST/{name}", ver)
    for name, ver in _listing(client, f"{config.CVM_BASE}/").items():
        out[name] = (f"{config.CVM_BASE}/{name}", ver)
    return out


def load_manifest() -> dict[str, str]:
    return json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}


def download(force: bool = False) -> list[str]:
    """Baixa zips novos ou alterados. Retorna a lista de nomes atualizados."""
    manifest = load_manifest()
    changed: list[str] = []
    with httpx.Client(timeout=config.HTTP_TIMEOUT, follow_redirects=True) as client:
        for name, (url, ver) in sorted(remote_files(client).items()):
            dest = config.RAW_DIR / name
            if not force and manifest.get(name) == ver and dest.exists():
                continue
            log.info("baixando %s", name)
            with client.stream("GET", url) as r:
                r.raise_for_status()
                tmp = dest.with_suffix(".part")
                with tmp.open("wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
                tmp.replace(dest)
            manifest[name] = ver
            changed.append(name)
            MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return changed
