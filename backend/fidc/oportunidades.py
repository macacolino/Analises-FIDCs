"""Novas oportunidades: como o mercado está captando (por categoria) e quais fundos estão captando ou são novos.

Captação/resgate/amortização: Tab. X.4 do informe mensal, somando todas as classes de cota. Registros em que a
captação do mês passa de 1,5x o PL (maior entre o mês e o anterior) mais resgates e amortizações são tratados
como erro de preenchimento e ficam fora (ex.: R$ 121 bi informados por um fundo de R$ 0,13 bi).
"""
from __future__ import annotations

import pandas as pd

from .db import df

FLUXO_SQL = """
WITH f AS (
  SELECT cnpj, dt, sum(coalesce(captacoes, 0)) AS cap, sum(coalesce(resgates, 0)) AS resg,
         sum(coalesce(amortizacoes, 0)) AS amort,
         sum(coalesce(captacoes, 0)) FILTER (WHERE tipo = 'senior') AS cap_senior,
         sum(coalesce(captacoes, 0)) FILTER (WHERE tipo = 'mezanino') AS cap_mezanino,
         sum(coalesce(captacoes, 0)) FILTER (WHERE tipo = 'subordinada') AS cap_sub
  FROM fluxo_mes GROUP BY ALL),
p AS (SELECT cnpj, dt, pl, lag(pl) OVER (PARTITION BY cnpj ORDER BY dt) AS pl_ant FROM metricas_mes),
ini AS (SELECT cnpj, min(dt) AS primeiro_informe FROM metricas_mes WHERE pl > 0 GROUP BY cnpj)
SELECT f.*, p.pl, p.pl_ant, c.categoria, c.categoria_nome, c.grupo, ini.primeiro_informe,
       f.cap <= 1.5 * greatest(coalesce(p.pl, 0), coalesce(p.pl_ant, 0)) + f.resg + f.amort + 1e6 AS valido
FROM f LEFT JOIN p USING (cnpj, dt) LEFT JOIN classificacao c USING (cnpj) LEFT JOIN ini USING (cnpj)
WHERE f.dt <= (SELECT ultimo_mes_completo FROM _meta)
"""


def _fluxo(meses: int) -> pd.DataFrame:
    d = df(FLUXO_SQL + " AND f.dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL (?) MONTH", [meses])
    d["dt"] = pd.to_datetime(d.dt)
    return d


def mercado(meses: int = 24) -> dict:
    d = _fluxo(meses + 12)
    erros = d[~d.valido.fillna(True)]
    d = d[d.valido.fillna(True)]
    d["novo"] = d.primeiro_informe.notna() & (pd.to_datetime(d.primeiro_informe) == d.dt)
    g = d.groupby(["dt", "categoria", "categoria_nome", "grupo"]).agg(
        captacao=("cap", "sum"), resgates=("resg", "sum"), amortizacoes=("amort", "sum"),
        n_captando=("cap", lambda x: int((x > 0).sum())), n_novos=("novo", "sum")).reset_index()
    g["liquida"] = g.captacao - g.resgates - g.amortizacoes
    fim = g.dt.max()
    serie = g[g.dt > fim - pd.DateOffset(months=meses)]
    # aceleração: média dos últimos 3 meses x média dos 12 meses anteriores a eles
    r3 = g[g.dt > fim - pd.DateOffset(months=3)].groupby(["categoria", "categoria_nome", "grupo"]).agg(
        cap_media_3m=("captacao", "mean"), liquida_3m=("liquida", "sum"), novos_3m=("n_novos", "sum")).reset_index()
    r12 = g[(g.dt <= fim - pd.DateOffset(months=3)) & (g.dt > fim - pd.DateOffset(months=15))].groupby("categoria").agg(
        cap_media_12m_ant=("captacao", "mean")).reset_index()
    ult12 = g[g.dt > fim - pd.DateOffset(months=12)].groupby("categoria").agg(
        captacao_12m=("captacao", "sum"), liquida_12m=("liquida", "sum"), novos_12m=("n_novos", "sum")).reset_index()
    res = r3.merge(r12, on="categoria", how="left").merge(ult12, on="categoria", how="left")
    res["aceleracao"] = res.cap_media_3m / res.cap_media_12m_ant - 1
    tot = g.groupby("dt").agg(captacao=("captacao", "sum"), resgates=("resgates", "sum"),
                              amortizacoes=("amortizacoes", "sum"), n_novos=("n_novos", "sum")).reset_index()
    tot["liquida"] = tot.captacao - tot.resgates - tot.amortizacoes
    return {"serie": serie, "resumo": res.sort_values("captacao_12m", ascending=False),
            "total": tot[tot.dt > fim - pd.DateOffset(months=meses)],
            "excluidos": erros[["cnpj", "dt", "cap", "pl", "pl_ant"]].sort_values("cap", ascending=False)}


OFERTA_SQL = """
SELECT cnpj, arg_max(data_registro, coalesce(data_registro, data_requerimento)) AS ultima_oferta_registro,
       arg_max(data_requerimento, coalesce(data_registro, data_requerimento)) AS ultima_oferta_requerimento,
       arg_max(valor_registrado, coalesce(data_registro, data_requerimento)) AS ultima_oferta_valor,
       arg_max(status, coalesce(data_registro, data_requerimento)) AS ultima_oferta_status,
       arg_max(publico_alvo, coalesce(data_registro, data_requerimento)) AS ultima_oferta_publico,
       count(*) FILTER (WHERE data_registro > current_date - INTERVAL 12 MONTH) AS ofertas_12m,
       sum(valor_registrado) FILTER (WHERE data_registro > current_date - INTERVAL 12 MONTH) AS valor_ofertas_12m
FROM oferta WHERE cnpj IS NOT NULL GROUP BY cnpj
"""


def _com_ofertas(d: pd.DataFrame) -> pd.DataFrame:
    try:
        return d.merge(df(OFERTA_SQL), on="cnpj", how="left")
    except Exception:  # noqa: BLE001 - base sem a tabela de ofertas
        return d


def ofertas(dias: int = 90, categoria: str | None = None) -> pd.DataFrame:
    """Ofertas de cotas de FIDC registradas/requeridas nos últimos `dias`, com o perfil do fundo quando conhecido."""
    from . import comparacao as cp
    o = df("""SELECT cnpj, cnpj_emissor, nome_emissor, data_requerimento, data_registro, data_encerramento, status,
                     valor_registrado, publico_alvo, tipo_oferta, emissao, lider, gestor_oferta, rito
              FROM oferta WHERE coalesce(data_registro, data_requerimento) > current_date - INTERVAL (?) DAY""", [dias])
    u = cp.universo()
    cols = [c for c in ["cnpj", "nome", "gestor", "categoria", "categoria_nome", "pl", "subordinacao", "q_status"]
            if c in u.columns]
    o = o.merge(u[cols], on="cnpj", how="left")
    o["nome"] = o.nome.fillna(o.nome_emissor)
    o["fundo_novo_sem_informe"] = o.pl.isna()
    if categoria:
        o = o[o.categoria == categoria]
    try:
        o = o.merge(df("SELECT cnpj, lastro FROM regulamento_ia"), on="cnpj", how="left")
    except Exception:  # noqa: BLE001
        o["lastro"] = None
    return o.sort_values(["data_registro", "valor_registrado"], ascending=[False, False])


def fundos(meses: int = 3, categoria: str | None = None) -> pd.DataFrame:
    """Fundos que mais captaram nos últimos `meses`, com o perfil para triagem."""
    from . import comparacao as cp
    d = _fluxo(meses)
    d = d[d.valido.fillna(True)]
    g = d.groupby("cnpj").agg(captacao=("cap", "sum"), cap_senior=("cap_senior", "sum"),
                              cap_mezanino=("cap_mezanino", "sum"), cap_sub=("cap_sub", "sum"),
                              resgates=("resg", "sum"), amortizacoes=("amort", "sum"),
                              meses_captando=("cap", lambda x: int((x > 0).sum())),
                              primeiro_informe=("primeiro_informe", "first")).reset_index()
    g = g[g.captacao > 0]
    g["liquida"] = g.captacao - g.resgates - g.amortizacoes
    u = cp.universo()
    cols = [c for c in ["cnpj", "nome", "gestor", "admin", "categoria", "categoria_nome", "pl", "subordinacao",
                        "jr_pl", "over90_carteira", "pdd_carteira", "q_status"] if c in u.columns]
    g = g.merge(u[cols], on="cnpj", how="inner")
    if categoria:
        g = g[g.categoria == categoria]
    g["captacao_pct_pl"] = g.captacao / g.pl
    g["novo"] = pd.to_datetime(g.primeiro_informe) > pd.Timestamp(df("SELECT ultimo_mes_completo AS d FROM _meta").d[0]) \
        - pd.DateOffset(months=6)
    try:
        ia = df("SELECT cnpj, lastro FROM regulamento_ia")
        g = g.merge(ia, on="cnpj", how="left")
    except Exception:  # noqa: BLE001
        g["lastro"] = None
    return _com_ofertas(g).sort_values("captacao", ascending=False)


def novos(meses: int = 6) -> pd.DataFrame:
    """Fundos com primeiro informe nos últimos `meses` (com PL), mais recentes primeiro."""
    from . import comparacao as cp
    d = df("""SELECT cnpj, min(dt) AS primeiro_informe FROM metricas_mes WHERE pl > 0 GROUP BY cnpj
              HAVING min(dt) > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL (?) MONTH""", [meses])
    u = cp.universo()
    cols = [c for c in ["cnpj", "nome", "gestor", "admin", "categoria", "categoria_nome", "pl", "subordinacao",
                        "jr_pl", "q_status"] if c in u.columns]
    d = d.merge(u[cols], on="cnpj", how="inner")
    try:
        d = d.merge(df("SELECT cnpj, lastro FROM regulamento_ia"), on="cnpj", how="left")
    except Exception:  # noqa: BLE001
        d["lastro"] = None
    return _com_ofertas(d).sort_values(["primeiro_informe", "pl"], ascending=[False, False])
