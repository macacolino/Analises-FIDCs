"""Pipeline completo: baixa o que mudou na CVM, converte e reconstrói a base."""
from __future__ import annotations

import logging
import threading

from . import bcb, build, cvm_cadastro, cvm_download, cvm_load, cvm_ofertas

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
                bcb.download()
            except Exception as e:  # noqa: BLE001 - contexto setorial é complementar
                log.warning("falha ao baixar séries do BCB: %s", e)
            try:
                cvm_cadastro.download()
            except Exception as e:  # noqa: BLE001 - cadastro é complementar
                log.warning("falha ao baixar cadastro CVM: %s", e)
            try:
                cvm_ofertas.download()
            except Exception as e:  # noqa: BLE001 - complementar
                log.warning("falha ao baixar ofertas CVM: %s", e)
            try:  # regulamentos de fundos ainda não lidos (limitado por execução; o lote completo é manual)
                from .. import config, regulamentos
                if config.DB_PATH.exists():
                    itens = regulamentos.fila(regulamentos.LIMITE_DIARIO)
                    if itens:
                        log.info("regulamentos novos: %s", regulamentos.rodar(itens, workers=2))
            except Exception as e:  # noqa: BLE001 - complementar
                log.warning("falha ao ler regulamentos do FNET: %s", e)
        cvm_load.convert(changed or None)
        build.build()
        return {"status": "ok", "arquivos_atualizados": changed}
    finally:
        _lock.release()


def rebuild_only() -> dict:
    """Reconstrói a base sem baixar nada (ex.: depois de ajustar a taxonomia)."""
    return run(download=False)
