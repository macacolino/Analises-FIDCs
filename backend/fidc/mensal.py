"""Resumo mês a mês de um fundo (o que vai no informe mensal da CVM) e rentabilidade por série.

Rentabilidade por série: o informe traz a rentabilidade do mês informada pelo administrador (Tab. X.3), que às
vezes NÃO considera amortizações (a cota cai no mês em que amortiza e a rentabilidade sai baixa ou negativa).
Recalculamos a variação ajustada por amortização com o que o informe dá:
    amortização por cota (estimada) = amortização do tipo de cota no mês (Tab. X.4) / cotas do tipo no mês
    rentab. ajustada = (valor da cota + amortização por cota) / valor da cota no mês anterior - 1
A amortização vem por tipo (sênior, mezanino, subordinada), não por série: se as séries do mesmo tipo amortizam
valores diferentes por cota, o ajuste é aproximado. Regra de uso:
- informada e ajustada próximas (até 0,3 p.p.) ou sem amortização no mês: vale a informada;
- houve amortização e a informada é a variação crua da cota: vale a ajustada (marcada como estimativa).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .db import df

TIPOS = {"senior": "Sênior", "mezanino": "Mezanino", "subordinada": "Subordinada"}
ORDEM = {"senior": 1, "mezanino": 2, "subordinada": 3}

RESUMO_SQL = """
WITH f AS (SELECT dt, sum(captacoes) AS captacoes, sum(resgates) AS resgates, sum(amortizacoes) AS amortizacoes
           FROM fluxo_mes WHERE cnpj = ? GROUP BY dt)
SELECT m.dt, m.pl, m.pl_senior, m.pl_mezanino, m.pl_subordinada, m.subordinacao, m.subordinacao_junior,
       m.dc_bruto AS carteira, m.inad_total, m.inad_90, m.inad_360, m.pdd, m.pdd_carteira, m.cobertura_pdd_90,
       m.prazo_medio_dias, m.aquisicoes, m.recompras, m.substituicoes, f.captacoes, f.resgates, f.amortizacoes,
       m.liquidez_30_pl, m.top1_cedente_pct, m.nr_cotistas, k.cdi_mes
FROM metricas_mes m LEFT JOIN f USING (dt) LEFT JOIN cdi_mes k USING (dt)
WHERE m.cnpj = ? AND m.dt > (SELECT max(dt) FROM metricas_mes WHERE cnpj = ?) - INTERVAL (?) MONTH
ORDER BY m.dt
"""


def rentab_series(cnpj: str, meses: int = 60) -> pd.DataFrame:
    """Uma linha por série e mês: valor da cota, PL, rentabilidade informada, ajustada e a usada, CDI e % do CDI."""
    s = df("""SELECT s.dt, s.serie, s.tipo, s.qt_cotas, s.valor_cota, s.pl_serie, s.rentab_mes / 100 AS rentab_informada,
                     s.desempenho_esperado / 100 AS desempenho_esperado, s.nr_cotistas, f.amortizacoes AS amort_tipo,
                     k.cdi_mes
              FROM serie_mes s
              LEFT JOIN fluxo_mes f ON f.cnpj = s.cnpj AND f.dt = s.dt AND f.tipo = s.tipo
              LEFT JOIN cdi_mes k ON k.dt = s.dt
              WHERE s.cnpj = ? AND s.dt > (SELECT max(dt) FROM serie_mes WHERE cnpj = ?) - INTERVAL (?) MONTH
              ORDER BY s.serie, s.dt""", [cnpj, cnpj, meses + 1])
    if s.empty:
        return s
    s["dt"] = pd.to_datetime(s.dt)
    s = s.sort_values(["serie", "dt"])
    prev = s.groupby("serie")[["dt", "valor_cota"]].shift(1)
    contiguo = prev.dt.notna() & (prev.dt + pd.offsets.MonthEnd(1) == s.dt)
    s["valor_cota_ant"] = prev.valor_cota.where(contiguo)
    qt_tipo = s.groupby(["dt", "tipo"]).qt_cotas.transform("sum")
    s["amort_por_cota"] = (s.amort_tipo.fillna(0) / qt_tipo).where(qt_tipo > 0, 0.0)
    crua = s.valor_cota / s.valor_cota_ant - 1
    aj = (s.valor_cota + s.amort_por_cota) / s.valor_cota_ant - 1
    aj = aj.where(aj.abs() < 0.5)
    inf = s.rentab_informada.where(s.rentab_informada.abs() < 0.5)
    usa_aj = (s.amort_tipo.fillna(0) > 0) & aj.notna() & (inf.isna() | (((inf - aj).abs() > 0.003)
                                                                     & ((inf - crua).abs() <= 0.003)))
    s["rentab_ajustada"] = aj
    s["rentab"] = np.where(usa_aj, aj, inf.fillna(aj))
    s["ajuste_amortizacao"] = usa_aj
    s["pct_cdi"] = (s.rentab / s.cdi_mes).where(s.cdi_mes > 0)
    s = s[s.dt > s.dt.max() - pd.DateOffset(months=meses)]
    s["ordem"] = s.tipo.map(ORDEM).fillna(9)
    return s.sort_values(["dt", "ordem", "serie"]).drop(columns=["ordem"])


def _rotulos(s: pd.DataFrame) -> list[dict]:
    """Rótulo curto por série (Sênior 1, Mezanino 1...), na ordem do tipo e do PL atual."""
    ult = s.sort_values("dt").groupby("serie").tail(1).copy()
    ult["ordem"] = ult.tipo.map(ORDEM).fillna(9)
    ult = ult.sort_values(["ordem", "pl_serie"], ascending=[True, False])
    out, cont = [], {}
    for i, r in enumerate(ult.itertuples()):
        cont[r.tipo] = cont.get(r.tipo, 0) + 1
        out.append({"key": f"s{i + 1}", "serie": r.serie, "tipo": r.tipo,
                    "rotulo": f"{TIPOS.get(r.tipo, r.tipo or 'Outra')} {cont[r.tipo]}"})
    return out


def janelas(s: pd.DataFrame) -> pd.DataFrame:
    """Rentabilidade acumulada por série em 3, 6, 12, 24 meses e desde o primeiro mês disponível, vs. CDI."""
    if s.empty:
        return pd.DataFrame()
    fim = s.dt.max()
    rows = []
    for r in _rotulos(s):
        x = s[s.serie == r["serie"]].sort_values("dt")
        linha = {"serie": r["serie"], "rotulo": r["rotulo"], "tipo": r["tipo"]}
        for n, nome in ((3, "3m"), (6, "6m"), (12, "12m"), (24, "24m"), (None, "inicio")):
            y = x if n is None else x[x.dt > fim - pd.DateOffset(months=n)]
            completo = n is None or (len(y) == n and y.rentab.notna().all())
            if y.empty or not completo or y.rentab.isna().all():
                linha[f"cota_{nome}"] = linha[f"cdi_{nome}"] = linha[f"pct_cdi_{nome}"] = None
                continue
            c = float(np.prod(1 + y.rentab.fillna(0)) - 1)
            k = float(np.prod(1 + y.cdi_mes.fillna(0)) - 1)
            linha[f"cota_{nome}"], linha[f"cdi_{nome}"] = c, k
            linha[f"pct_cdi_{nome}"] = c / k if k > 0 else None
        linha["desde"] = x.dt.min().date().isoformat()
        linha["meses"] = len(x)
        rows.append(linha)
    return pd.DataFrame(rows)


def tabela(cnpj: str, meses: int = 60) -> dict:
    """Resumo mensal (linhas = meses, mais recente primeiro) com a rentabilidade de cada série em colunas."""
    r = df(RESUMO_SQL, [cnpj, cnpj, cnpj, meses])
    r["dt"] = pd.to_datetime(r.dt)
    s = rentab_series(cnpj, meses)
    series = _rotulos(s) if not s.empty else []
    for d in series:
        x = s[s.serie == d["serie"]].set_index("dt")
        r[f"{d['key']}_rentab"] = r.dt.map(x.rentab)
        r[f"{d['key']}_pct_cdi"] = r.dt.map(x.pct_cdi)
        r[f"{d['key']}_pl"] = r.dt.map(x.pl_serie)
    r = r.sort_values("dt", ascending=False)
    r["dt"] = r.dt.dt.date.astype(str)
    return {"meses": r, "series": series, "rentab": s, "janelas": janelas(s)}


def planilhas(cnpj: str, meses: int = 60) -> dict[str, pd.DataFrame]:
    """Abas do Excel: resumo mensal com nomes legíveis, matriz de rentabilidade por série e detalhe."""
    t = tabela(cnpj, meses)
    nomes = {d["key"]: d["rotulo"] for d in t["series"]}
    m = t["meses"].copy()
    ren = {}
    for c in m.columns:
        k, _, sufixo = c.partition("_")
        if k in nomes:
            ren[c] = f"{nomes[k]} - " + {"rentab": "rentab. mês", "pct_cdi": "% CDI", "pl": "PL"}[sufixo]
    m = m.rename(columns=ren)
    det = t["rentab"].copy()
    if not det.empty:
        det["dt"] = det.dt.dt.date.astype(str)
        det["rotulo"] = det.serie.map({d["serie"]: d["rotulo"] for d in t["series"]})
        det = det[["dt", "rotulo", "serie", "tipo", "qt_cotas", "valor_cota", "pl_serie", "rentab_informada",
                   "amort_por_cota", "rentab_ajustada", "ajuste_amortizacao", "rentab", "cdi_mes", "pct_cdi",
                   "desempenho_esperado", "nr_cotistas"]]
    return {"Resumo mensal": m, "Rentab. acumulada": t["janelas"], "Rentab. por série": det}
