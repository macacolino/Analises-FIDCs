"""PDD por administrador: a régua efetivamente praticada, a partir do informe mensal (sem custo de leitura).

Duas medidas, por fundo e agregadas por administrador:

1. PDD declarada / PDD pela régua da Res. CMN 2.682 aplicada à carteira vencida do informe (Tab. V + VI):
       1-30 d: 1%  31-60: 3%  61-90: 10%  91-120: 30%  121-150: 50%  151-180: 70%  > 180: 100%
   (a 2.682 tem 0,5% até 14 dias e 1% de 15 a 30; usamos 1% na faixa 1-30). É uma régua MÍNIMA: o informe traz
   parcelas vencidas, e a 2.682 / o "efeito vagão" provisionam o contrato inteiro, além da provisão por rating
   na compra. Razão < 1 = PDD abaixo até da régua mínima sobre as parcelas vencidas.

2. Curva implícita do administrador: % de provisão por faixa de atraso que melhor explica a PDD declarada nos fundos
   dele (12 meses, PDD/carteira contra a carteira por faixa / carteira, mínimos quadrados não negativos, curva
   crescente com o atraso e limitada a 100%).
   Estimativa estatística - mostra a régua "praticada", que pode diferir da política escrita.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

REGUA_2682 = {"in_30": 0.01, "in_60": 0.03, "in_90": 0.10, "in_120": 0.30, "in_150": 0.50, "in_180": 0.70, "in_mais180": 1.0}
FAIXAS = [("a_vencer", "A vencer"), ("in_30", "1-30 d"), ("in_60", "31-60 d"), ("in_90", "61-90 d"), ("in_120", "91-120 d"),
          ("in_150", "121-150 d"), ("in_180", "151-180 d"), ("in_mais180", "> 180 d")]

BASE_SQL = """
SELECT m.cnpj, m.dt, m.nome, m.admin, m.pl, m.dc_bruto AS carteira, m.pdd, m.aging_suspeito,
       coalesce(m.av_30,0)+coalesce(m.av_60,0)+coalesce(m.av_90,0)+coalesce(m.av_120,0)+coalesce(m.av_150,0)
         +coalesce(m.av_180,0)+coalesce(m.av_360,0)+coalesce(m.av_720,0)+coalesce(m.av_1080,0)+coalesce(m.av_1080p,0) AS a_vencer,
       coalesce(m.in_30,0) AS in_30, coalesce(m.in_60,0) AS in_60, coalesce(m.in_90,0) AS in_90,
       coalesce(m.in_120,0) AS in_120, coalesce(m.in_150,0) AS in_150, coalesce(m.in_180,0) AS in_180,
       coalesce(m.in_360,0)+coalesce(m.in_720,0)+coalesce(m.in_1080,0)+coalesce(m.in_1080p,0) AS in_mais180,
       c.categoria_nome
FROM metricas_mes m LEFT JOIN classificacao c USING (cnpj)
WHERE m.dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 12 MONTH AND m.dt <= (SELECT ultimo_mes_completo FROM _meta)
  AND m.dc_bruto > 0 AND m.pdd IS NOT NULL AND NOT coalesce(m.aging_suspeito, false) AND NOT coalesce(m.pl_outlier, false)
"""


def nnls(a: np.ndarray, b: np.ndarray, iters: int = 200) -> np.ndarray:
    """Mínimos quadrados não negativos (Lawson-Hanson simplificado)."""
    n = a.shape[1]
    x, passivo = np.zeros(n), np.zeros(n, bool)
    for _ in range(iters):
        w = a.T @ (b - a @ x)
        cand = ~passivo & (w > 1e-12)
        if not cand.any():
            break
        passivo[np.argmax(np.where(cand, w, -np.inf))] = True
        while True:
            z = np.zeros(n)
            z[passivo] = np.linalg.lstsq(a[:, passivo], b, rcond=None)[0]
            if (z[passivo] > 0).all():
                x = z
                break
            neg = passivo & (z <= 0)
            alpha = np.min(x[neg] / (x[neg] - z[neg] + 1e-18))
            x = x + alpha * (z - x)
            passivo &= x > 1e-12
    return x


def _regua(d: pd.DataFrame) -> pd.Series:
    return sum(d[k] * v for k, v in REGUA_2682.items())


def tabelas(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = con.execute(BASE_SQL).df()
    if d.empty:
        return d, d
    d["regua_2682"] = _regua(d)
    d["vencido"] = d[[k for k, _ in FAIXAS[1:]]].sum(axis=1)
    d["vencido_90"] = d[["in_120", "in_150", "in_180", "in_mais180"]].sum(axis=1)
    ult = d.sort_values("dt").groupby("cnpj").tail(1).copy()
    ult["pdd_carteira"] = ult.pdd / ult.carteira
    ult["pdd_regua"] = (ult.pdd / ult.regua_2682).where(ult.regua_2682 > 0)
    ult["pdd_vencido90"] = (ult.pdd / ult.vencido_90).where(ult.vencido_90 > 0)
    ult["abaixo_regua"] = (ult.pdd_regua < 1).where(ult.regua_2682 > 0)
    fundo = ult[["cnpj", "nome", "admin", "categoria_nome", "dt", "pl", "carteira", "pdd", "pdd_carteira", "vencido",
                 "vencido_90", "regua_2682", "pdd_regua", "pdd_vencido90", "abaixo_regua"]]

    linhas = []
    for adm, g in d.groupby("admin"):
        u = ult[ult.admin == adm]
        com = u[u.regua_2682 > 0]
        r = {"admin": adm, "fundos": int(u.cnpj.nunique()), "pl": float(u.pl.sum()),
             "fundos_com_vencido": int(len(com)),
             "pdd_carteira_mediana": float(u.pdd_carteira.median()),
             "pdd_regua_mediana": float(com.pdd_regua.median()) if len(com) else None,
             "pct_abaixo_regua": float(com.abaixo_regua.mean()) if len(com) else None,
             "pdd_vencido90_mediana": float(u.pdd_vencido90.median()) if u.pdd_vencido90.notna().any() else None}
        # curva implícita: precisa de variação suficiente (fundos e meses com atraso)
        gg = g[g.vencido > 0]
        if gg.cnpj.nunique() >= 3 and len(gg) >= 24:
            cols = [k for k, _ in FAIXAS]
            a = (gg[cols].div(gg.carteira, axis=0)).to_numpy()
            b = (gg.pdd / gg.carteira).to_numpy()
            # curva crescente com o atraso: x = L·d com d >= 0 (L triangular inferior de uns)
            low = np.tril(np.ones((len(cols), len(cols))))
            x = low @ nnls(a @ low, b)
            ajuste = a @ x
            r2 = 1 - ((b - ajuste) ** 2).sum() / max(((b - b.mean()) ** 2).sum(), 1e-18)
            for (k, _), v in zip(FAIXAS, x):
                r[f"curva_{k}"] = float(min(v, 1.0))
            r["curva_r2"] = float(r2)
            r["curva_n"] = int(len(gg))
        linhas.append(r)
    adm = pd.DataFrame(linhas).sort_values("pl", ascending=False)
    return fundo, adm


def build_table(con) -> None:
    fundo, adm = tabelas(con)
    for nome, t in (("pdd_fundo", fundo), ("pdd_admin", adm)):
        con.register("_t", t)
        con.execute(f"CREATE OR REPLACE TABLE {nome} AS SELECT * FROM _t")
        con.unregister("_t")
