"""Cadastro de fundos e classes da CVM (gestor, administrador, custodiante, datas).

Fonte: https://dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip
O CNPJ do informe mensal pode ser o da classe (pós Res. CVM 175) ou o do fundo;
a tabela `cadastro` tem uma linha por CNPJ em qualquer dos dois casos.
"""
from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

import httpx

from .. import config

log = logging.getLogger(__name__)

ZIP = config.RAW_DIR / "registro_fundo_classe.zip"


def download() -> None:
    with httpx.Client(timeout=config.HTTP_TIMEOUT, follow_redirects=True) as c:
        r = c.get(config.CVM_CAD_URL)
        r.raise_for_status()
        tmp = ZIP.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(ZIP)


def build_table(con) -> None:
    if not ZIP.exists():
        log.warning("cadastro CVM ausente; rode o download")
        con.execute("CREATE TABLE cadastro (cnpj VARCHAR, gestor VARCHAR, cnpj_gestor VARCHAR, "
                    "administrador VARCHAR, custodiante VARCHAR, auditor VARCHAR, data_inicio DATE, "
                    "situacao VARCHAR, publico_alvo VARCHAR, condominio VARCHAR, exclusivo VARCHAR, "
                    "data_registro DATE, cnpj_fundo VARCHAR)")
        return
    with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(ZIP) as zf:
        paths = {}
        for n in ("registro_fundo.csv", "registro_classe.csv"):
            p = Path(tmp) / n
            p.write_text(zf.read(n).decode("latin-1"), encoding="utf-8")
            paths[n] = str(p)
        rf = f"read_csv('{paths['registro_fundo.csv']}', delim=';', header=true, all_varchar=true)"
        rc = f"read_csv('{paths['registro_classe.csv']}', delim=';', header=true, all_varchar=true)"
        con.execute(f"""
            CREATE TABLE cadastro AS
            WITH f AS (SELECT * FROM {rf}),
            classes AS (
              SELECT c.CNPJ_Classe AS cnpj, f.Gestor AS gestor, f.CPF_CNPJ_Gestor AS cnpj_gestor,
                     f.Administrador AS administrador, c.Custodiante AS custodiante, c.Auditor AS auditor,
                     TRY_CAST(coalesce(c.Data_Inicio, c.Data_Constituicao) AS DATE) AS data_inicio,
                     c.Situacao AS situacao, c.Publico_Alvo AS publico_alvo,
                     c.Forma_Condominio AS condominio, c.Exclusivo AS exclusivo,
                     TRY_CAST(c.Data_Registro AS DATE) AS data_registro, f.CNPJ_Fundo AS cnpj_fundo, 1 AS prio
              FROM {rc} c LEFT JOIN f USING (ID_Registro_Fundo)
              WHERE c.Tipo_Classe ILIKE '%FIDC%'
            ),
            fundos AS (
              SELECT CNPJ_Fundo AS cnpj, Gestor, CPF_CNPJ_Gestor, Administrador, NULL, NULL,
                     TRY_CAST(Data_Constituicao AS DATE), Situacao, NULL, NULL, NULL,
                     TRY_CAST(Data_Registro AS DATE), CNPJ_Fundo, 2
              FROM f WHERE Tipo_Fundo ILIKE 'FIDC%'
            )
            SELECT * EXCLUDE (prio) FROM (SELECT * FROM classes UNION ALL SELECT * FROM fundos)
            QUALIFY row_number() OVER (
              PARTITION BY cnpj
              ORDER BY prio, (situacao ILIKE '%normal%') DESC, data_registro DESC NULLS LAST) = 1
        """)
