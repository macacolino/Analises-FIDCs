"""Resumo mês a mês de um fundo (o que vai no informe mensal da CVM) e rentabilidade por série.

Rentabilidade por série: o informe traz a rentabilidade do mês informada pelo administrador (Tab. X.3), que às
vezes NÃO considera amortizações (a cota cai no mês em que amortiza e a rentabilidade sai baixa ou negativa).
Recalculamos a variação ajustada por amortização com o que o informe dá:
    amortização por cota (estimada) = amortização do tipo de cota no mês (Tab. X.4) / cotas do tipo no mês
    rentab. ajustada = (valor da cota + amortização por cota) / valor da cota no mês anterior - 1
A amortização vem por tipo (sênior, mezanino, subordinada), não por série: ela é atribuída às séries cuja cota caiu
em relação às demais do mesmo tipo (ou a todas, se caíram juntas) e dividida pelas cotas delas - aproximação. Regra de uso:
- informada e ajustada próximas (até 0,3 p.p.) ou sem amortização no mês: vale a informada;
- houve amortização e a informada é a variação crua da cota: vale a ajustada (marcada como estimativa).

Subordinada como resíduo: quando a soma das séries difere do PL do fundo (Tab. IV) em mais de 2%, a subordinada informada
variou mais de 10% no mês (implausível) e há uma única série
subordinada, o PL da subordinada é recalculado como PL − sênior − mezanino (a júnior é, por definição, o resíduo) e a
rentabilidade dela no mês = (PL residual + amortizações − captações da subordinada) / PL residual do mês anterior − 1.
Ex.: F3 Falcon ago/26 - séries somam 7,6% abaixo do PL e a subordinada informada cai 29,9%.

CDI + x% a.a.: ((1 + retorno) / (1 + CDI no mesmo período)) ^ (12 / meses) − 1.
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
       m.liquidez_30_pl, m.top1_cedente_pct, m.nr_cotistas, k.cdi_mes, m.sub_residual, m.pl_subordinada_informada
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
    crua = s.valor_cota / s.valor_cota_ant - 1
    # a amortização do tipo vai para as séries cuja cota caiu em relação às demais do mesmo tipo (mais de 0,5 p.p.
    # abaixo da mediana); se nenhuma se destaca, todas amortizaram e ela é dividida pelas cotas do tipo
    med = crua.groupby([s.dt, s.tipo]).transform("median")
    caiu = (crua < med - 0.005) & (s.qt_cotas > 0)
    algum = caiu.groupby([s.dt, s.tipo]).transform("any")
    elegivel = caiu | ~algum
    qt_base = s.qt_cotas.where(elegivel, 0).groupby([s.dt, s.tipo]).transform("sum")
    s["amort_por_cota"] = (s.amort_tipo.fillna(0) / qt_base).where(elegivel & (qt_base > 0), 0.0)
    aj = (s.valor_cota + s.amort_por_cota) / s.valor_cota_ant - 1
    aj = aj.where(aj.abs() < 0.5)
    inf = s.rentab_informada.where(s.rentab_informada.abs() < 0.5)
    usa_aj = (s.amort_tipo.fillna(0) > 0) & aj.notna() & (inf.isna() | (((inf - aj).abs() > 0.003)
                                                                     & ((inf - crua).abs() <= 0.003)))
    s["rentab_ajustada"] = aj
    s["rentab"] = np.where(usa_aj, aj, inf.fillna(aj))
    s["ajuste_amortizacao"] = usa_aj
    s["pct_cdi"] = (s.rentab / s.cdi_mes).where(s.cdi_mes > 0)
    s = _subordinada_residual(cnpj, s)
    s["spread_aa"] = ((1 + s.rentab) / (1 + s.cdi_mes)) ** 12 - 1
    s = s[s.dt > s.dt.max() - pd.DateOffset(months=meses)]
    s["ordem"] = s.tipo.map(ORDEM).fillna(9)
    return s.sort_values(["dt", "ordem", "serie"]).drop(columns=["ordem"])


def _subordinada_residual(cnpj: str, s: pd.DataFrame) -> pd.DataFrame:
    """Recalcula a rentabilidade da subordinada pelo resíduo do PL quando a soma das séries não fecha com o PL."""
    s["sub_residual"] = False
    m = df("""SELECT m.dt, m.pl, m.pl_subordinada, m.sub_residual,
                     coalesce(f.captacoes, 0) AS cap, coalesce(f.amortizacoes, 0) + coalesce(f.resgates, 0) AS saida
              FROM metricas_mes m LEFT JOIN fluxo_mes f ON f.cnpj = m.cnpj AND f.dt = m.dt AND f.tipo = 'subordinada'
              WHERE m.cnpj = ? ORDER BY m.dt""", [cnpj])
    if m.empty:
        return s
    m["dt"] = pd.to_datetime(m.dt)
    m["res"] = m.pl_subordinada            # já é o resíduo nos meses marcados; nos demais, a série informada
    m["erro"] = m.sub_residual.fillna(False).astype(bool)   # soma das séries não fecha com o PL (metricas_mes)
    ant = m.shift(1)
    contig = ant.dt.notna() & (ant.dt + pd.offsets.MonthEnd(1) == m.dt)
    m["r_res"] = ((m.res + m.saida - m.cap) / ant.res - 1).where(contig & (ant.res > 0) & (m.res > 0))
    m["usa"] = (m.erro | ant.erro.fillna(False).astype(bool)) & m.r_res.notna() & (m.r_res.abs() < 0.5)
    m = m.set_index("dt")
    sub = s.tipo == "subordinada"
    unica = s[sub].groupby("dt").serie.transform("count") == 1
    alvo = s.index[sub][unica.values]
    for i in alvo:
        dt = s.at[i, "dt"]
        if dt in m.index and bool(m.at[dt, "usa"]):
            s.at[i, "rentab"] = m.at[dt, "r_res"]
            s.at[i, "pl_serie"] = m.at[dt, "res"]
            s.at[i, "sub_residual"] = True
    s["pct_cdi"] = (s.rentab / s.cdi_mes).where(s.cdi_mes > 0)
    return s


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
            linha[f"spread_aa_{nome}"] = ((1 + c) / (1 + k)) ** (12 / len(y)) - 1 if k > -1 and c > -1 else None
        linha["desde"] = x.dt.min().date().isoformat()
        aj = x[x.sub_residual] if "sub_residual" in x else x.iloc[0:0]
        linha["meses_residual"] = ", ".join(d.strftime("%m/%Y") for d in aj.dt) if len(aj) else None
        linha["meses"] = len(x)
        rows.append(linha)
    return pd.DataFrame(rows)


def por_tipo(s: pd.DataFrame) -> pd.DataFrame:
    """Uma pseudo-série por classe de cota: rentabilidade do mês ponderada pelo PL do mês anterior de cada série
    (ou do próprio mês, na falta dele). Usada quando o fundo tem muitas séries."""
    if s.empty:
        return s
    x = s[s.rentab.notna() & s.tipo.isin(list(TIPOS))].copy()
    x["peso"] = (x.valor_cota_ant * x.qt_cotas).where(x.valor_cota_ant.notna(), x.pl_serie).fillna(0).clip(lower=0)
    x["rp"] = x.rentab * x.peso
    g = x.groupby(["dt", "tipo"]).agg(rp=("rp", "sum"), peso=("peso", "sum"), pl_serie=("pl_serie", "sum"),
                                      cdi_mes=("cdi_mes", "first"), nr_cotistas=("nr_cotistas", "sum"),
                                      n_series=("serie", "nunique"), sub_residual=("sub_residual", "max")).reset_index()
    g["rentab"] = (g.rp / g.peso).where(g.peso > 0)
    g["pct_cdi"] = (g.rentab / g.cdi_mes).where(g.cdi_mes > 0)
    g["spread_aa"] = ((1 + g.rentab) / (1 + g.cdi_mes)) ** 12 - 1
    g["serie"] = g.tipo.map(lambda t: f"{TIPOS[t]} (todas as séries)")
    return g.drop(columns=["rp", "peso"])


def tabela(cnpj: str, meses: int = 60) -> dict:
    """Resumo mensal (linhas = meses, mais recente primeiro) com a rentabilidade de cada série em colunas e, à parte,
    de cada classe de cota (todas as séries somadas, ponderadas pelo PL)."""
    r = df(RESUMO_SQL, [cnpj, cnpj, cnpj, meses])
    r["dt"] = pd.to_datetime(r.dt)
    s = rentab_series(cnpj, meses)
    tipos = por_tipo(s)
    series = _rotulos(s) if not s.empty else []
    for t in ("senior", "mezanino", "subordinada"):
        if not tipos.empty and (tipos.tipo == t).any():
            series.append({"key": f"t_{t}", "serie": f"{TIPOS[t]} (todas as séries)", "tipo": t,
                           "rotulo": TIPOS[t], "agregado": True})
    cols = {}
    for d in series:
        x = (tipos if d.get("agregado") else s)
        x = x[x.serie == d["serie"]].set_index("dt")
        cols[f"{d['key']}_rentab"] = r.dt.map(x.rentab)
        cols[f"{d['key']}_pct_cdi"] = r.dt.map(x.pct_cdi)
        cols[f"{d['key']}_pl"] = r.dt.map(x.pl_serie)
        cols[f"{d['key']}_spread_aa"] = r.dt.map(x.spread_aa)
    if cols:
        r = pd.concat([r, pd.DataFrame(cols)], axis=1)
    r = r.sort_values("dt", ascending=False)
    r["dt"] = r.dt.dt.date.astype(str)
    jan = janelas(s)
    if not tipos.empty:
        jt = janelas(tipos.assign(sub_residual=tipos.sub_residual.astype(bool)))
        jt["agregado"] = True
        jt["rotulo"] = jt.tipo.map(TIPOS)
        jan = pd.concat([jan.assign(agregado=False), jt], ignore_index=True)
    return {"meses": r, "series": series, "rentab": s, "janelas": jan}


def planilhas(cnpj: str, meses: int = 60) -> dict[str, pd.DataFrame]:
    """Abas do Excel: resumo mensal com nomes legíveis, matriz de rentabilidade por série e detalhe."""
    t = tabela(cnpj, meses)
    nomes = {d["key"]: d["rotulo"] for d in t["series"]}
    m = t["meses"].copy()
    ren = {}
    for c in m.columns:
        k, _, sufixo = c.partition("_")
        if k in nomes:
            ren[c] = f"{nomes[k]} - " + {"rentab": "rentab. mês", "pct_cdi": "% CDI", "pl": "PL",
                                         "spread_aa": "CDI + % a.a."}[sufixo]
    m = m.rename(columns=ren)
    det = t["rentab"].copy()
    if not det.empty:
        det["dt"] = det.dt.dt.date.astype(str)
        det["rotulo"] = det.serie.map({d["serie"]: d["rotulo"] for d in t["series"]})
        det = det[["dt", "rotulo", "serie", "tipo", "qt_cotas", "valor_cota", "pl_serie", "rentab_informada",
                   "amort_por_cota", "rentab_ajustada", "ajuste_amortizacao", "sub_residual", "rentab", "cdi_mes", "pct_cdi",
                   "spread_aa",
                   "desempenho_esperado", "nr_cotistas"]]
    return {"Resumo mensal": m, "Rentab. acumulada": t["janelas"], "Rentab. por série": det}
