"""Pipeline completo: baixa o que mudou na CVM, converte e reconstrói a base."""
from __future__ import annotations

import logging
import threading

from . import build, cvm_cadastro, cvm_download, cvm_load

log = logging.getLogger(__name__)
_lock = threading.Lock()


def run(download: bool = True) -> dict:
    """Executa o ETL. Seguro para chamar de várias threads (uma execução por vez)."""
    if not _lock.acquire(blocking=False):
        return {"status": "ja_em_execucao"}
    try:
        changed: list[str] = []
        if download:
            changed = cvm_download.download()
            try:
                cvm_cadastro.download()
            except Exception as e:  # noqa: BLE001 - cadastro é complementar
                log.warning("falha ao baixar cadastro CVM: %s", e)
        cvm_load.convert(changed or None)
        build.build()
        return {"status": "ok", "arquivos_atualizados": changed}
    finally:
        _lock.release()


def rebuild_only() -> dict:
    """Reconstrói a base sem baixar nada (ex.: depois de ajustar a taxonomia)."""
    return run(download=False)
