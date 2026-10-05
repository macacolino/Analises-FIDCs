"""Estado do app (SQLite): carteira, watchlist, notas e ajustes manuais de categoria.

Fica separado da base analítica porque a base é reconstruída a cada ETL e
isto aqui é o que os usuários editam.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS lista (
    cnpj        TEXT NOT NULL,
    tipo        TEXT NOT NULL CHECK (tipo IN ('carteira', 'watchlist')),
    adicionado_em TEXT NOT NULL DEFAULT (datetime('now')),
    adicionado_por TEXT,
    tese        TEXT,
    PRIMARY KEY (cnpj, tipo)
);
CREATE TABLE IF NOT EXISTS nota (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    cnpj        TEXT NOT NULL,
    texto       TEXT NOT NULL,
    autor       TEXT,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS nota_cnpj ON nota (cnpj);
CREATE TABLE IF NOT EXISTS override_categoria (
    cnpj        TEXT PRIMARY KEY,
    categoria   TEXT NOT NULL,
    autor       TEXT,
    motivo      TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    con = sqlite3.connect(path or config.APP_DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    return con


@contextmanager
def session(path: Path | None = None):
    con = connect(path)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def overrides(path: Path | None = None) -> dict[str, str]:
    with session(path) as con:
        return {r["cnpj"]: r["categoria"] for r in con.execute("SELECT cnpj, categoria FROM override_categoria")}
