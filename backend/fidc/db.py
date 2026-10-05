"""Conexão com a base analítica (somente leitura).

O ETL grava um arquivo novo e troca atomicamente; aqui detectamos a troca
pelo mtime e reabrimos a conexão.
"""
from __future__ import annotations

import threading

import duckdb
import pandas as pd

from . import config

_lock = threading.Lock()
_con: duckdb.DuckDBPyConnection | None = None
_mtime: float | None = None


def con() -> duckdb.DuckDBPyConnection:
    global _con, _mtime
    path = config.DB_PATH
    if not path.exists():
        raise RuntimeError("Base ainda não construída. Rode: python -m fidc.etl")
    m = path.stat().st_mtime
    with _lock:
        if _con is None or m != _mtime:
            # não fechamos a conexão antiga: requisições em andamento ainda podem usá-la
            _con = duckdb.connect(str(path), read_only=True)
            _mtime = m
        return _con.cursor()


def df(sql: str, params: list | None = None) -> pd.DataFrame:
    return con().execute(sql, params or []).df()


def one(sql: str, params: list | None = None):
    return con().execute(sql, params or []).fetchone()
