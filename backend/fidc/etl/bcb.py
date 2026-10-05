"""Séries do Banco Central (SGS) para contexto setorial e CDI.

API: https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json
Às vezes devolve HTML de erro em vez de JSON: tentamos de novo. Falha numa série
não derruba o ETL (fica o último download bom em disco).
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date

import httpx
import pandas as pd
import yaml

from .. import config

log = logging.getLogger(__name__)
CFG = config.TAXONOMY_FILE.parent / "setor_bcb.yaml"
DIR = config.DATA_DIR / "bcb"
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{c}/dados?formato=json&dataInicial=01/01/2013"


def load_cfg() -> dict:
    return yaml.safe_load(open(CFG, encoding="utf-8"))


def download() -> list[int]:
    DIR.mkdir(parents=True, exist_ok=True)
    ok = []
    with httpx.Client(timeout=60) as c:
        for code in load_cfg()["series"]:
            for i in range(3):
                try:
                    r = c.get(URL.format(c=code))
                    data = r.json()
                    if not isinstance(data, list):
                        raise ValueError("resposta inesperada")
                    (DIR / f"{code}.json").write_text(json.dumps(data))
                    ok.append(code)
                    break
                except Exception as e:  # noqa: BLE001
                    if i == 2:
                        log.warning("BCB %s falhou: %s", code, e)
                    time.sleep(2 ** i)
    return ok


def build_table(con) -> None:
    cfg = load_cfg()
    rows = []
    today = date.today()
    for code, meta in cfg["series"].items():
        f = DIR / f"{code}.json"
        if not f.exists():
            continue
        for p in json.loads(f.read_text()):
            d = pd.to_datetime(p["data"], dayfirst=True).date()
            if d > today:
                continue
            try:
                v = float(p["valor"])
            except (TypeError, ValueError):
                continue
            rows.append((int(code), meta["nome"], meta["unidade"], meta["metrica"], d, v))
    df = pd.DataFrame(rows, columns=["codigo", "nome", "unidade", "metrica", "data", "valor"])
    con.register("_bcb", df)
    # data mensal do SGS = 1º dia do mês; normalizamos para o fim do mês (igual ao informe CVM)
    con.execute("""CREATE OR REPLACE TABLE bcb_serie AS
                   SELECT codigo, nome, unidade, metrica, CAST(last_day(data) AS DATE) AS dt, valor FROM _bcb""")
    con.unregister("_bcb")
    cat = [(k, int(c)) for k, codes in cfg["categorias"].items() for c in codes]
    con.register("_bc", pd.DataFrame(cat, columns=["categoria", "codigo"]))
    con.execute("CREATE OR REPLACE TABLE bcb_categoria AS SELECT * FROM _bc")
    con.unregister("_bc")
    # CDI 12m por mês (para retorno em % do CDI); o mês corrente parcial é descartado
    con.execute("""
        CREATE OR REPLACE TABLE cdi_mes AS
        WITH c AS (SELECT dt, valor FROM bcb_serie WHERE codigo = 4391 AND dt < CAST(last_day(current_date) AS DATE))
        SELECT dt, valor / 100 AS cdi_mes,
               exp(sum(ln(1 + valor / 100)) OVER (ORDER BY dt ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)) - 1 AS cdi_12m
        FROM c
    """)
