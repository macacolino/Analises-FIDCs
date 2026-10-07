"""Ofertas públicas de cotas de FIDC registradas na CVM (Res. CVM 160 e regime anterior).

Fonte: https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip (atualização diária)
- oferta_resolucao_160.csv: requerimento, registro, encerramento, status, valor registrado, público-alvo
- oferta_distribuicao.csv: ofertas do regime anterior (ICVM 400/476), até 2025

O CNPJ do emissor pode ser o da classe ou o do fundo; a tabela `oferta` traz o CNPJ como informado e o CNPJ
da classe usado no informe mensal (`cnpj`), mapeado pelo cadastro quando necessário.
"""
from __future__ import annotations

import logging
import zipfile

import httpx

from .. import config

log = logging.getLogger(__name__)

URL = "https://dados.cvm.gov.br/dados/OFERTA/DISTRIB/DADOS/oferta_distribuicao.zip"
ZIP = config.RAW_DIR / "oferta_distribuicao.zip"

VAZIA = """CREATE OR REPLACE TABLE oferta (cnpj VARCHAR, cnpj_emissor VARCHAR, nome_emissor VARCHAR, regime VARCHAR,
  data_requerimento DATE, data_registro DATE, data_inicio DATE, data_encerramento DATE, status VARCHAR,
  valor_registrado DOUBLE, publico_alvo VARCHAR, tipo_oferta VARCHAR, emissao VARCHAR, lider VARCHAR,
  gestor_oferta VARCHAR, rito VARCHAR)"""


def download() -> None:
    with httpx.Client(timeout=config.HTTP_TIMEOUT, follow_redirects=True) as c:
        r = c.get(URL)
        r.raise_for_status()
        tmp = ZIP.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(ZIP)


def build_table(con) -> None:
    if not ZIP.exists():
        log.warning("ofertas CVM ausentes; rode o download")
        con.execute(VAZIA)
        return
    import io

    import pandas as pd
    partes = []
    with zipfile.ZipFile(ZIP) as zf:
        if "oferta_resolucao_160.csv" in zf.namelist():
            o = pd.read_csv(io.BytesIO(zf.read("oferta_resolucao_160.csv")), sep=";", encoding="latin-1", dtype=str)
            o = o[o.Valor_Mobiliario.str.contains("FIDC", case=False, na=False)]
            partes.append(pd.DataFrame({
                "cnpj_emissor": o.CNPJ_Emissor.str.replace(r"\D", "", regex=True), "nome_emissor": o.Nome_Emissor,
                "regime": "RCVM 160", "data_requerimento": o.Data_requerimento, "data_registro": o.Data_Registro,
                "data_inicio": o.Data_Registro, "data_encerramento": o.Data_Encerramento,
                "status": o.Status_Requerimento, "valor_registrado": o.Valor_Total_Registrado,
                "publico_alvo": o.Publico_alvo, "tipo_oferta": o.Tipo_Oferta, "emissao": o.Emissao,
                "lider": o.Nome_Lider, "gestor_oferta": o.Gestor, "rito": o.Rito_Requerimento}))
        if "oferta_distribuicao.csv" in zf.namelist():
            o = pd.read_csv(io.BytesIO(zf.read("oferta_distribuicao.csv")), sep=";", encoding="latin-1", dtype=str)
            o = o[o.Tipo_Ativo.str.contains("FIDC|Direitos Credit", case=False, na=False)]
            partes.append(pd.DataFrame({
                "cnpj_emissor": o.CNPJ_Emissor.str.replace(r"\D", "", regex=True), "nome_emissor": o.Nome_Emissor,
                "regime": "ICVM 400/476", "data_requerimento": o.Data_Protocolo, "data_registro": o.Data_Registro_Oferta,
                "data_inicio": o.Data_Inicio_Oferta, "data_encerramento": o.Data_Encerramento_Oferta,
                "status": o.Data_Encerramento_Oferta.map(lambda x: "Oferta Encerrada" if isinstance(x, str) else "Registrada"),
                "valor_registrado": o.Valor_Total, "publico_alvo": None, "tipo_oferta": o.Tipo_Oferta,
                "emissao": o.Emissao, "lider": o.Nome_Lider, "gestor_oferta": None, "rito": o.Rito_Oferta}))
    d = pd.concat(partes, ignore_index=True)
    for c in ("data_requerimento", "data_registro", "data_inicio", "data_encerramento"):
        d[c] = pd.to_datetime(d[c], errors="coerce").dt.date
    d["valor_registrado"] = pd.to_numeric(d.valor_registrado, errors="coerce")
    con.register("_ofd", d.astype(object).where(d.notna(), None))
    con.execute("""CREATE OR REPLACE TABLE _of AS SELECT cnpj_emissor, nome_emissor, regime,
        CAST(data_requerimento AS DATE) AS data_requerimento, CAST(data_registro AS DATE) AS data_registro,
        CAST(data_inicio AS DATE) AS data_inicio, CAST(data_encerramento AS DATE) AS data_encerramento, status,
        CAST(valor_registrado AS DOUBLE) AS valor_registrado, publico_alvo, tipo_oferta, emissao, lider,
        gestor_oferta, rito FROM _ofd""")
    con.unregister("_ofd")
    # CNPJ da classe usado no informe: direto, ou via cnpj_fundo do cadastro (uma classe -> mantém)
    con.execute("""
        CREATE OR REPLACE TABLE oferta AS
        WITH info AS (SELECT DISTINCT cnpj FROM fundo_mes),
        mapa AS (
          SELECT k.cnpj_fundo, any_value(k.cnpj) AS cnpj_classe, count(*) AS n
          FROM cadastro k JOIN info i ON i.cnpj = k.cnpj WHERE k.cnpj_fundo IS NOT NULL GROUP BY k.cnpj_fundo)
        SELECT CASE WHEN o.cnpj_emissor IN (SELECT cnpj FROM info) THEN o.cnpj_emissor
                    WHEN m.n = 1 THEN m.cnpj_classe END AS cnpj, o.*
        FROM _of o LEFT JOIN mapa m ON m.cnpj_fundo = o.cnpj_emissor""")
    con.execute("DROP TABLE _of")
