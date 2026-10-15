"""Resumo por fundo para filtros (Pesquisa) e para a visão por gestora/administradora.

fundo_resumo (último informe de cada fundo):
- pl_medio_12m: PL médio dos últimos 12 informes;
- cotistas_senior / _mezanino / _subordinada: soma de cotistas das séries de cada classe (Tab. X, último mês);
- taxa_desconto_aa: taxa média ponderada das aquisições em 12m (Tab. IX), em % a.a.;
- taxa_administracao / taxa_gestao / sub_min_senior: regulamento (regras + IA);
- estrutura: "classes" (sênior/mezanino/subordinada) ou "classe única" (sem subordinação a medir);
- rentab_*_12m e cdi_12m: rentabilidade composta em 12 meses (só com 12 meses informados e sem mês implausível);
  rentab_*_pct_cdi (último mês) e rentab_*_12m_pct_cdi: a mesma rentabilidade como % do CDI do período;
  spread_*_aa: "CDI + x% a.a." estimado pelo excesso mensal MEDIANO sobre o CDI nos últimos 12 meses (>= 6 meses com cota andando),
  anualizado - a mediana ignora os meses de amortização, em que a cota cai sem perda e a rentabilidade informada
  sai negativa. É estimativa da remuneração efetiva, não o benchmark do regulamento.

gestor_resumo / admin_resumo: AuM, fundos ativos e medianas por casa (fundos ativos, último informe).
"""
from __future__ import annotations

import re

ATIVO = "f.ultimo_informe >= (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 3 MONTH"


_MIN = re.compile(r"m[íi]nim[oa]s?\b(?P<per>[^R$;]{0,40}?)R\$\s*(?P<v>\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)\s*(?P<mil>mil\b)?",
                  re.I)


def minimo_mensal(txt: str | None) -> float | None:
    """Piso da taxa em R$ por mês, do texto do regulamento ("mínimo mensal de R$ 15.000,00", "mínimo de R$ 8 mil
    por mês"). Com escalonamento, fica o primeiro valor citado; mínimo anual vira mensal (/12)."""
    m = _MIN.search(txt or "")
    if not m:
        return None
    v = float(m["v"].replace(".", "").replace(",", ".")) * (1000 if m["mil"] else 1)
    resto = (m["per"] + (txt or "")[m.end():m.end() + 30]).lower()
    return v / 12 if re.search(r"\banua", resto) and not re.search(r"mensa|m[êe]s", resto) else v


def _minimos(con) -> None:
    import pandas as pd
    rows = con.execute("""SELECT cnpj, campo, valor_txt FROM regulamento_param
                          WHERE campo IN ('taxa_administracao', 'taxa_gestao') AND valor_txt IS NOT NULL""").fetchall()
    d = {}
    for c, campo, t in rows:
        v = minimo_mensal(t)
        if v is not None and v > 0:
            d.setdefault(c, {})[campo] = max(v, d.get(c, {}).get(campo, 0))
    df = pd.DataFrame([{"cnpj": c, "adm": x.get("taxa_administracao"), "gest": x.get("taxa_gestao")} for c, x in d.items()],
                      columns=["cnpj", "adm", "gest"]).astype({"adm": "float64", "gest": "float64"})
    con.register("_mn", df)
    con.execute("""
        ALTER TABLE fundo_resumo ADD COLUMN taxa_administracao_min_mes DOUBLE;
        ALTER TABLE fundo_resumo ADD COLUMN taxa_gestao_min_mes DOUBLE;
        UPDATE fundo_resumo r SET taxa_administracao_min_mes = m.adm, taxa_gestao_min_mes = m.gest FROM _mn m
        WHERE m.cnpj = r.cnpj""")
    con.unregister("_mn")


def build_table(con) -> None:
    con.execute(f"""
        CREATE OR REPLACE TABLE fundo_resumo AS
        WITH ult AS (SELECT f.cnpj, f.ultimo_informe AS dt FROM fundo f),
        pl12 AS (
            SELECT m.cnpj, avg(m.pl) AS pl_medio_12m
            FROM metricas_mes m JOIN ult u ON u.cnpj = m.cnpj AND m.dt > u.dt - INTERVAL 12 MONTH AND m.dt <= u.dt
            GROUP BY m.cnpj),
        cot AS (
            SELECT s.cnpj,
                   sum(s.nr_cotistas) FILTER (WHERE s.tipo = 'senior') AS cotistas_senior,
                   sum(s.nr_cotistas) FILTER (WHERE s.tipo = 'mezanino') AS cotistas_mezanino,
                   sum(s.nr_cotistas) FILTER (WHERE s.tipo = 'subordinada') AS cotistas_subordinada
            FROM serie_mes s JOIN ult u ON u.cnpj = s.cnpj AND s.dt = u.dt
            WHERE coalesce(s.pl_serie, 0) > 0
            GROUP BY s.cnpj),
        r12 AS (
            SELECT m.cnpj, count(*) AS n,
                   exp(sum(ln(1 + m.rentab_senior / 100))) - 1 AS rentab_senior_12m,
                   count(m.rentab_senior) AS n_sr, max(abs(m.rentab_senior)) AS max_sr,
                   exp(sum(ln(1 + m.rentab_mezanino / 100))) - 1 AS rentab_mezanino_12m,
                   count(m.rentab_mezanino) AS n_mz, max(abs(m.rentab_mezanino)) AS max_mz,
                   exp(sum(ln(1 + m.rentab_subordinada / 100))) - 1 AS rentab_subordinada_12m,
                   count(m.rentab_subordinada) AS n_sb, max(abs(m.rentab_subordinada)) AS max_sb,
                   exp(sum(ln(1 + c.cdi_mes))) - 1 AS cdi_12m,
                   -- excesso mensal mediano sobre o CDI: robusto a meses de amortização (cota cai sem perda)
                   -- (meses com rentabilidade exatamente zero = cota parada/série encerrada, fora)
                   median(m.rentab_senior / 100 - c.cdi_mes) FILTER (WHERE m.rentab_senior <> 0) AS exc_sr,
                   count(*) FILTER (WHERE m.rentab_senior <> 0) AS n_sr_ok,
                   median(m.rentab_mezanino / 100 - c.cdi_mes) FILTER (WHERE m.rentab_mezanino <> 0) AS exc_mz,
                   count(*) FILTER (WHERE m.rentab_mezanino <> 0) AS n_mz_ok
            FROM metricas_mes m JOIN ult u ON u.cnpj = m.cnpj AND m.dt > u.dt - INTERVAL 12 MONTH AND m.dt <= u.dt
            JOIN cdi_mes c ON c.dt = m.dt
            WHERE coalesce(m.rentab_senior, 0) > -99 AND coalesce(m.rentab_mezanino, 0) > -99
              AND coalesce(m.rentab_subordinada, 0) > -99
            GROUP BY m.cnpj),
        reg AS (
            SELECT cnpj,
                   max(valor_num) FILTER (WHERE campo = 'taxa_administracao') AS taxa_administracao,
                   max(valor_num) FILTER (WHERE campo = 'taxa_gestao') AS taxa_gestao,
                   max(valor_num) FILTER (WHERE campo = 'sub_min_senior') AS sub_min_senior
            FROM regulamento_param GROUP BY cnpj)
        SELECT f.cnpj, p.pl_medio_12m,
               c.cotistas_senior, c.cotistas_mezanino, c.cotistas_subordinada,
               k.m22_taxa_ix_aa AS taxa_desconto_aa,
               g.taxa_administracao, g.taxa_gestao, g.sub_min_senior,
               CASE WHEN m.n_series > 1 THEN 'classes' WHEN m.n_series = 1 THEN 'classe única' END AS estrutura,
               CASE WHEN r.n = 12 AND r.n_sr = 12 AND r.max_sr <= 15 THEN r.rentab_senior_12m END AS rentab_senior_12m,
               CASE WHEN r.n = 12 AND r.n_mz = 12 AND r.max_mz <= 15 THEN r.rentab_mezanino_12m END AS rentab_mezanino_12m,
               -- subordinada oscila mais: aceita até 30% num mês antes de considerar o dado implausível
               CASE WHEN r.n = 12 AND r.n_sb = 12 AND r.max_sb <= 30 AND m.n_series > 1 THEN r.rentab_subordinada_12m END
                   AS rentab_subordinada_12m,
               CASE WHEN r.n = 12 THEN r.cdi_12m END AS cdi_12m,
               cm.cdi_mes,
               -- % do CDI do último mês (rentabilidade informada / CDI do mês); só com CDI do mês positivo
               CASE WHEN cm.cdi_mes > 0 THEN m.rentab_senior / 100 / cm.cdi_mes END AS rentab_senior_pct_cdi,
               CASE WHEN cm.cdi_mes > 0 THEN m.rentab_mezanino / 100 / cm.cdi_mes END AS rentab_mezanino_pct_cdi,
               CASE WHEN cm.cdi_mes > 0 THEN m.rentab_subordinada / 100 / cm.cdi_mes END AS rentab_subordinada_pct_cdi,
               -- só com sênior de verdade (mais de uma classe): na classe única o rótulo "sênior" é a cota toda
               CASE WHEN r.n_sr_ok >= 6 AND m.n_series > 1 THEN r.exc_sr END AS exc_sr,
               CASE WHEN r.n_mz_ok >= 6 AND m.n_series > 1 THEN r.exc_mz END AS exc_mz
        FROM fundo f
        LEFT JOIN metricas_mes m ON m.cnpj = f.cnpj AND m.dt = f.ultimo_informe
        LEFT JOIN pl12 p ON p.cnpj = f.cnpj LEFT JOIN cot c ON c.cnpj = f.cnpj
        LEFT JOIN casa_mes k ON k.cnpj = f.cnpj AND k.dt = f.ultimo_informe
        LEFT JOIN r12 r ON r.cnpj = f.cnpj LEFT JOIN reg g ON g.cnpj = f.cnpj
        LEFT JOIN cdi_mes cm ON cm.dt = f.ultimo_informe""")
    con.execute("""
        ALTER TABLE fundo_resumo ADD COLUMN spread_senior_aa DOUBLE;
        ALTER TABLE fundo_resumo ADD COLUMN spread_mezanino_aa DOUBLE;
        UPDATE fundo_resumo SET spread_senior_aa = (1 + exc_sr) ^ 12 - 1, spread_mezanino_aa = (1 + exc_mz) ^ 12 - 1;
        ALTER TABLE fundo_resumo DROP COLUMN exc_sr; ALTER TABLE fundo_resumo DROP COLUMN exc_mz;
        ALTER TABLE fundo_resumo ADD COLUMN rentab_senior_12m_pct_cdi DOUBLE;
        ALTER TABLE fundo_resumo ADD COLUMN rentab_mezanino_12m_pct_cdi DOUBLE;
        ALTER TABLE fundo_resumo ADD COLUMN rentab_subordinada_12m_pct_cdi DOUBLE;
        UPDATE fundo_resumo SET rentab_senior_12m_pct_cdi = rentab_senior_12m / nullif(cdi_12m, 0),
                                rentab_mezanino_12m_pct_cdi = rentab_mezanino_12m / nullif(cdi_12m, 0),
                                rentab_subordinada_12m_pct_cdi = rentab_subordinada_12m / nullif(cdi_12m, 0)""")
    _minimos(con)
    for nome, col in (("gestor_resumo", "gestor"), ("admin_resumo", "admin")):
        con.execute(f"""
            CREATE OR REPLACE TABLE {nome} AS
            SELECT f.{col} AS casa, count(*) AS fundos, sum(f.pl) AS pl, median(f.pl) AS pl_mediano,
                   count(DISTINCT f.categoria) AS categorias, mode(f.categoria_nome) AS categoria_principal,
                   median(m.inad_90) AS inad_90_mediana, median(m.pdd_carteira) AS pdd_carteira_mediana,
                   median(m.subordinacao) AS subordinacao_mediana,
                   median(r.spread_senior_aa) AS spread_senior_mediano,
                   sum(r.spread_senior_aa * f.pl) / nullif(sum(f.pl) FILTER (WHERE r.spread_senior_aa IS NOT NULL), 0)
                       AS spread_senior_ponderado,
                   count(r.spread_senior_aa) AS fundos_com_senior,
                   median(r.spread_mezanino_aa) AS spread_mezanino_mediano,
                   sum(r.spread_mezanino_aa * f.pl) / nullif(sum(f.pl) FILTER (WHERE r.spread_mezanino_aa IS NOT NULL), 0)
                       AS spread_mezanino_ponderado,
                   count(r.spread_mezanino_aa) AS fundos_com_mezanino,
                   median(r.taxa_gestao) AS taxa_gestao_mediana, median(r.taxa_administracao) AS taxa_administracao_mediana,
                   median(r.taxa_desconto_aa) AS taxa_desconto_mediana
            FROM fundo f LEFT JOIN metricas_mes m ON m.cnpj = f.cnpj AND m.dt = f.ultimo_informe
            LEFT JOIN fundo_resumo r ON r.cnpj = f.cnpj
            WHERE {ATIVO.replace('f.', 'f.')} AND f.{col} IS NOT NULL
            GROUP BY f.{col}""")
