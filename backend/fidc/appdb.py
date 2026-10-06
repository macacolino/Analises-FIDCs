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
CREATE TABLE IF NOT EXISTS grupo_pares (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT NOT NULL UNIQUE,
    descricao   TEXT,
    uma_por_gestora INTEGER NOT NULL DEFAULT 1,
    criado_por  TEXT,
    criado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS grupo_pares_membro (
    grupo_id    INTEGER NOT NULL REFERENCES grupo_pares(id) ON DELETE CASCADE,
    cnpj        TEXT NOT NULL,
    incluir     INTEGER NOT NULL DEFAULT 1,
    motivo      TEXT,
    PRIMARY KEY (grupo_id, cnpj)
);
-- dados que o informe não traz: regulamento, rating, relatório do gestor (com fonte e data-base)
CREATE TABLE IF NOT EXISTS fundo_param (
    cnpj        TEXT NOT NULL,
    chave       TEXT NOT NULL,
    competencia TEXT NOT NULL DEFAULT '',   -- '' = valor estático (ex.: regulamento); 'AAAA-MM' = mensal
    valor_num   REAL,
    valor_txt   TEXT,
    fonte       TEXT,
    data_base   TEXT,
    autor       TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cnpj, chave, competencia)
);
CREATE TABLE IF NOT EXISTS dd_resposta (
    cnpj        TEXT NOT NULL,
    pergunta_id TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente', 'ok', 'atencao', 'red_flag', 'nao_se_aplica')),
    resposta    TEXT,
    fonte       TEXT,
    autor       TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (cnpj, pergunta_id)
);
CREATE TABLE IF NOT EXISTS cnpj_nome (
    cnpj        TEXT PRIMARY KEY,
    nome        TEXT,
    detalhe     TEXT,
    consultado_em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS categoria_ref (   -- referência de estrutura por categoria (ex.: subordinação mínima típica)
    categoria   TEXT NOT NULL,
    chave       TEXT NOT NULL,
    valor_num   REAL,
    fonte       TEXT,
    autor       TEXT,
    atualizado_em TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (categoria, chave)
);
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
    con.execute("PRAGMA foreign_keys = ON")
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
