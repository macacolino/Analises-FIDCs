"""Converte os zips da CVM em parquet (um arquivo por tabela por zip).

Os CSVs vêm em latin-1, separados por ';'. Guardamos tudo como texto e
fazemos a tipagem/harmonização no build — assim mudanças de layout da CVM
(ex.: CNPJ_FUNDO -> CNPJ_FUNDO_CLASSE com a Res. CVM 175) não quebram a carga.
"""
from __future__ import annotations

import logging
import re
import tempfile
import zipfile
from collections import defaultdict
from pathlib import Path

import duckdb

from .. import config

log = logging.getLogger(__name__)

_CSV = re.compile(r"inf_mensal_fidc_tab_(.+)_(\d{6})\.csv$")

# Tabelas que usamos. VIII (lista de valores sem descrição útil) fica de fora.
TABLES = ["I", "II", "III", "IV", "V", "VI", "VII", "IX", "X",
          "X_1", "X_1_1", "X_2", "X_3", "X_4", "X_5", "X_6", "X_7"]


def zip_to_parquet(zip_path: Path) -> None:
    stem = zip_path.stem
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(zip_path) as zf:
        groups: dict[str, list[str]] = defaultdict(list)
        for name in zf.namelist():
            m = _CSV.search(name)
            if m and m.group(1) in TABLES:
                # latin-1 decodifica qualquer byte; regravamos em utf-8 para o DuckDB
                dest = Path(tmp) / Path(name).name
                dest.write_text(zf.read(name).decode("latin-1"), encoding="utf-8")
                groups[m.group(1)].append(str(dest))
        con = duckdb.connect()
        for tab, files in groups.items():
            out_dir = config.PARQUET_DIR / tab
            out_dir.mkdir(parents=True, exist_ok=True)
            out = out_dir / f"{stem}.parquet"
            con.execute(
                f"""COPY (
                      SELECT *, '{stem}' AS _src
                      FROM read_csv(?, delim=';', header=true, all_varchar=true,
                                    union_by_name=true,
                                    ignore_errors=true, quote='"')
                    ) TO '{out}' (FORMAT parquet, COMPRESSION zstd)""",
                [files],
            )
        con.close()
    log.info("convertido %s (%d tabelas)", zip_path.name, len(groups))


def convert(names: list[str] | None = None) -> None:
    """Converte os zips indicados (ou todos os que ainda não têm parquet)."""
    zips = sorted(config.RAW_DIR.glob("inf_mensal_fidc_*.zip"))
    for z in zips:
        done = (config.PARQUET_DIR / "I" / f"{z.stem}.parquet").exists()
        if (names is not None and z.name in names) or (names is None and not done):
            zip_to_parquet(z)
