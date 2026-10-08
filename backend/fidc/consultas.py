"""Consultas de negócio sobre a base analítica. A API só repassa o que sai daqui."""
from __future__ import annotations

import re

import pandas as pd

from . import appdb
from .db import df, one

# indicadores que aparecem na lâmina e nos painéis
KPIS = ["pl", "pl_var_mes", "dc_bruto", "pdd", "inad_total", "inad_90", "inad_360", "inad_contratos",
        "pdd_carteira", "cobertura_pdd_90", "subordinacao", "subordinacao_junior",
        "rentab_senior", "rentab_mezanino", "rentab_subordinada", "top1_cedente_pct", "top5_cedentes_pct",
        "aquisicoes", "giro_mes", "prazo_medio_dias", "liquidez_30_pl", "scr_e_h", "nr_cotistas",
        "roll_30_60", "roll_60_90", "roll_90_120", "inad_90_lag6", "inad_90_lag12", "perda_aquisicoes_12m",
        "recompra_subst_3m_carteira", "inad_90_ajustada", "baixa_implicita_mes", "var_pdd_mes",
        "taxa_desconto_compra"]

# métricas comparadas com o setor (sentido: True = maior é melhor)
COMPARAVEIS = {
    "inad_90": False, "inad_contratos": False, "pdd_carteira": False, "subordinacao": True,
    "rentab_senior": True, "rentab_subordinada": True, "roll_30_60": False, "roll_60_90": False,
    "inad_90_lag12": False, "recompra_subst_3m_carteira": False, "top1_cedente_pct": False,
    "prazo_medio_dias": None, "cobertura_pdd_90": True, "pl": True,
}

BUCKETS = ["30", "60", "90", "120", "150", "180", "360", "720", "1080", "1080p"]
BUCKET_LABEL = ["1-30", "31-60", "61-90", "91-120", "121-150", "151-180", "181-360", "361-720",
                "721-1080", ">1080"]


def cnpj_digits(s: str) -> str:
    return re.sub(r"\D", "", s or "").zfill(14)


def meta() -> dict:
    r = one("SELECT strftime(built_at, '%Y-%m-%d %H:%M'), ultimo_mes, ultimo_mes_completo FROM _meta")
    n = one("SELECT count(*) FROM fundo WHERE ultimo_informe >= (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 2 MONTH")
    return {"atualizado_em": str(r[0]), "ultimo_mes": str(r[1]), "mes_referencia": str(r[2]), "fundos_ativos": n[0]}


def ref_month() -> str:
    return str(one("SELECT ultimo_mes_completo FROM _meta")[0])


# ---------------------------------------------------------------- busca
def buscar(q: str = "", categoria: str | None = None, grupo: str | None = None,
           apenas_ativos: bool = True, limit: int = 50) -> pd.DataFrame:
    where, params = [], []
    if q:
        d = re.sub(r"\D", "", q)
        if len(d) >= 6:
            where.append("f.cnpj LIKE ?")
            params.append(f"%{d}%")
        else:
            for tok in q.split():
                where.append("strip_accents(upper(f.nome)) LIKE strip_accents(upper(?))")
                params.append(f"%{tok}%")
    if categoria:
        where.append("f.categoria = ?"); params.append(categoria)
    if grupo:
        where.append("f.grupo = ?"); params.append(grupo)
    if apenas_ativos:
        where.append("f.ultimo_informe >= (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 3 MONTH")
    sql = f"""
        SELECT f.cnpj, f.nome, f.categoria, f.categoria_nome, f.grupo, f.gestor, f.admin, f.pl,
               f.ultimo_informe, f.revisar, c.ia_diverge_informe, m.inad_90, m.pdd_carteira, m.subordinacao,
               m.rentab_senior
        FROM fundo f LEFT JOIN metricas_mes m ON m.cnpj = f.cnpj AND m.dt = f.ultimo_informe
        LEFT JOIN classificacao c ON c.cnpj = f.cnpj
        {'WHERE ' + ' AND '.join(where) if where else ''}
        ORDER BY f.pl DESC NULLS LAST LIMIT {int(limit)}"""
    return df(sql, params)


# ---------------------------------------------------------------- lâmina
def lamina(cnpj: str) -> dict | None:
    cnpj = cnpj_digits(cnpj)
    cab = df("""
        SELECT f.cnpj, f.nome, f.categoria, f.categoria_nome, f.grupo, f.revisar, c.origem,
               c.segmento_principal, c.segmento_principal_pct, c.ia_carteira_compat, c.ia_diverge_informe,
               ia.tese AS ia_tese, f.gestor, f.admin, k.custodiante, k.auditor,
               k.data_inicio, k.situacao, k.publico_alvo, f.condominio, f.exclusivo, f.ultimo_informe,
               m.primeiro_informe
        FROM fundo f JOIN classificacao c USING (cnpj) LEFT JOIN cadastro k USING (cnpj)
        LEFT JOIN metricas_mes m ON m.cnpj = f.cnpj AND m.dt = f.ultimo_informe
        LEFT JOIN regulamento_ia ia ON ia.cnpj = f.cnpj
        WHERE f.cnpj = ?""", [cnpj])
    if cab.empty:
        return None
    head = cab.iloc[0].to_dict()
    dt = head["ultimo_informe"]
    kpi = df(f"SELECT dt, {', '.join(KPIS)} FROM metricas_mes WHERE cnpj = ? AND dt = ?", [cnpj, dt])

    comp = comparativo_setor(cnpj, head["categoria"], dt)
    series = series_fundo(cnpj, dt)
    cedentes = df("SELECT rank, cedente_doc, pct FROM cedente_mes WHERE cnpj = ? AND dt = ? ORDER BY rank",
                  [cnpj, dt])
    aging = df(f"SELECT {', '.join(f'in_{b}' for b in BUCKETS)}, {', '.join(f'av_{b}' for b in BUCKETS)} "
               "FROM metricas_mes WHERE cnpj = ? AND dt = ?", [cnpj, dt])
    aging_rows = []
    if not aging.empty:
        a = aging.iloc[0]
        aging_rows = [{"faixa": lb, "vencido": a[f"in_{b}"], "a_vencer": a[f"av_{b}"]}
                      for b, lb in zip(BUCKETS, BUCKET_LABEL)]
    with appdb.session() as s:
        listas = [r["tipo"] for r in s.execute("SELECT tipo FROM lista WHERE cnpj = ?", [cnpj])]
        notas = [dict(r) for r in s.execute("SELECT * FROM nota WHERE cnpj = ? ORDER BY id DESC", [cnpj])]
    return {
        "cabecalho": head, "kpis": kpi.iloc[0].to_dict() if not kpi.empty else {},
        "comparativo": comp, "series": series, "cedentes": cedentes, "aging": aging_rows,
        "alertas": alertas([cnpj]).get(cnpj, []), "listas": listas, "notas": notas,
    }


def comparativo_setor(cnpj: str, categoria: str, dt) -> list[dict]:
    """Valor do fundo vs. mediana e quartis da categoria no mesmo mês, com percentil."""
    cols = list(COMPARAVEIS)
    sql = f"""
        WITH m AS (
          SELECT m.cnpj, {', '.join(f'm.{c}' for c in cols)}
          FROM metricas_mes m JOIN classificacao c USING (cnpj)
          WHERE c.categoria = ? AND m.dt = ? AND m.pl > 0 AND NOT m.pl_outlier
        )
        SELECT {', '.join(
            f"(SELECT {c} FROM m WHERE cnpj = ?) AS v_{c}, "
            f"quantile_cont({c}, 0.25) AS p25_{c}, median({c}) AS med_{c}, quantile_cont({c}, 0.75) AS p75_{c}, "
            f"count({c}) AS n_{c}, "
            f"(SELECT count(*) FROM m WHERE {c} < (SELECT {c} FROM m WHERE cnpj = ?))::DOUBLE / nullif(count({c}), 0) AS pr_{c}"
            for c in cols)}
        FROM m"""
    params = [categoria, dt] + [cnpj, cnpj] * len(cols)
    r = df(sql, params)
    if r.empty:
        return []
    r = r.iloc[0]
    out = []
    for c in cols:
        out.append({"metrica": c, "valor": r[f"v_{c}"], "p25": r[f"p25_{c}"], "mediana": r[f"med_{c}"],
                    "p75": r[f"p75_{c}"], "n": int(r[f"n_{c}"]), "percentil": r[f"pr_{c}"],
                    "maior_melhor": COMPARAVEIS[c]})
    return out


def series_fundo(cnpj: str, dt=None) -> pd.DataFrame:
    """Séries/subclasses do fundo no mês, com rentabilidade acumulada 12m."""
    return df("""
        WITH s AS (
          SELECT *, count(*) OVER w AS n12,
                 exp(sum(ln(1 + rentab_mes / 100)) OVER w) - 1 AS rentab_12m
          FROM serie_mes
          WHERE cnpj = ? AND abs(rentab_mes) < 50
          WINDOW w AS (PARTITION BY serie ORDER BY dt RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW)
        )
        SELECT x.serie, x.tipo, x.qt_cotas, x.valor_cota, x.pl_serie, x.rentab_mes,
               CASE WHEN s.n12 = 12 THEN s.rentab_12m END AS rentab_12m,
               x.desempenho_esperado, x.desempenho_real, x.nr_cotistas
        FROM serie_mes x LEFT JOIN s USING (cnpj, dt, serie)
        WHERE x.cnpj = ? AND x.dt = coalesce(?::DATE, (SELECT max(dt) FROM serie_mes WHERE cnpj = ?))
        ORDER BY CASE x.tipo WHEN 'senior' THEN 1 WHEN 'mezanino' THEN 2 WHEN 'subordinada' THEN 3 ELSE 4 END,
                 x.pl_serie DESC NULLS LAST""", [cnpj, cnpj, dt, cnpj])


def historico(cnpj: str, meses: int = 60) -> pd.DataFrame:
    """Série histórica do fundo + mediana da categoria no mesmo mês."""
    cnpj = cnpj_digits(cnpj)
    return df(f"""
        SELECT m.dt, {', '.join(f'm.{k}' for k in KPIS)},
               s.inad_90_mediana AS setor_inad_90, s.pdd_carteira_mediana AS setor_pdd_carteira,
               s.subordinacao_mediana AS setor_subordinacao, s.rentab_senior_mediana AS setor_rentab_senior,
               s.rentab_subordinada_mediana AS setor_rentab_subordinada,
               s.roll_30_60_mediana AS setor_roll_30_60, s.roll_60_90_mediana AS setor_roll_60_90,
               s.inad_90_lag12_mediana AS setor_inad_90_lag12,
               {', '.join(f'm.in_{b}' for b in BUCKETS)}
        FROM metricas_mes m
        JOIN classificacao c USING (cnpj)
        LEFT JOIN setor_mes s ON s.categoria = c.categoria AND s.dt = m.dt
        WHERE m.cnpj = ? AND m.dt > (SELECT max(dt) FROM metricas_mes WHERE cnpj = ?) - INTERVAL {int(meses)} MONTH
        ORDER BY m.dt""", [cnpj, cnpj])


# ---------------------------------------------------------------- setores
def categorias() -> pd.DataFrame:
    return df("""
        SELECT k.ordem, k.categoria, k.categoria_nome, k.grupo, s.n_fundos, s.pl_total, s.inad_90,
               s.inad_90_mediana, s.pdd_carteira, s.subordinacao, s.rentab_senior_mediana,
               s.rentab_subordinada_mediana, s.roll_60_90_mediana, s.prazo_medio_dias_mediana
        FROM categoria k
        LEFT JOIN setor_mes s ON s.categoria = k.categoria AND s.dt = (SELECT ultimo_mes_completo FROM _meta)
        ORDER BY k.ordem""")


def mercado_historico() -> pd.DataFrame:
    return df("""
        SELECT s.dt, k.grupo, sum(s.pl_total) AS pl_total, sum(s.n_fundos) AS n_fundos
        FROM setor_mes s JOIN categoria k USING (categoria)
        WHERE s.dt <= (SELECT ultimo_mes_completo FROM _meta)
        GROUP BY ALL ORDER BY s.dt, k.grupo""")


def setor_historico(categoria: str) -> pd.DataFrame:
    return df("""SELECT * FROM setor_mes WHERE categoria = ? AND dt <= (SELECT ultimo_mes_completo FROM _meta)
                 ORDER BY dt""", [categoria])


def setor_ranking(categoria: str | None = None, dt: str | None = None) -> pd.DataFrame:
    dt = dt or ref_month()
    where = "AND c.categoria = ?" if categoria else ""
    params = [dt] + ([categoria] if categoria else [])
    return df(f"""
        SELECT m.cnpj, m.nome, c.categoria_nome, k.gestor, m.admin, {', '.join(f'm.{k}' for k in KPIS)}
        FROM metricas_mes m JOIN classificacao c USING (cnpj) LEFT JOIN cadastro k USING (cnpj)
        WHERE m.dt = ? AND m.pl > 0 AND NOT m.pl_outlier {where}
        ORDER BY m.pl DESC""", params)


def ranking_series(categoria: str | None = None, tipo: str | None = None, dt: str | None = None,
                   pl_min: float = 0) -> pd.DataFrame:
    """Ranking por série: rentabilidade do mês e acumulada 12m (só séries com 12 meses completos)."""
    dt = dt or ref_month()
    conds, params = ["x.dt = ?", "x.pl_serie > ?"], [dt, pl_min]
    if categoria:
        conds.append("c.categoria = ?"); params.append(categoria)
    if tipo:
        conds.append("x.tipo = ?"); params.append(tipo)
    return df(f"""
        WITH s AS (
          SELECT cnpj, serie, count(*) AS n12, exp(sum(ln(1 + rentab_mes / 100))) - 1 AS rentab_12m
          FROM serie_mes
          WHERE dt > ?::DATE - INTERVAL 12 MONTH AND dt <= ?::DATE AND abs(rentab_mes) < 50
          GROUP BY ALL
        )
        SELECT x.cnpj, f.nome, c.categoria_nome, x.serie, x.tipo, x.pl_serie, x.rentab_mes,
               CASE WHEN s.n12 = 12 THEN s.rentab_12m END AS rentab_12m,
               m.subordinacao, m.inad_90, m.pdd_carteira
        FROM serie_mes x JOIN classificacao c USING (cnpj) JOIN fundo f USING (cnpj)
        LEFT JOIN s USING (cnpj, serie)
        LEFT JOIN metricas_mes m ON m.cnpj = x.cnpj AND m.dt = x.dt
        WHERE {' AND '.join(conds)}
        ORDER BY rentab_12m DESC NULLS LAST""", [dt, dt] + params)


def safra_fundos(categoria: str, metrica: str = "inad_90") -> pd.DataFrame:
    """Curva por safra de fundos: mediana da métrica por meses desde o 1º informe, agrupada por ano de início.

    Fundos que já existiam em 2013 (início da série histórica) ficam de fora: o 1º informe deles
    não é o início real do fundo."""
    if metrica not in COMPARAVEIS and metrica not in KPIS:
        raise ValueError("métrica inválida")
    return df(f"""
        SELECT m.safra_fundo, m.meses_desde_inicio, median(m.{metrica}) AS valor, count(*) AS n_fundos
        FROM metricas_mes m JOIN classificacao c USING (cnpj)
        WHERE c.categoria = ? AND m.safra_fundo > 2013 AND m.pl > 0 AND NOT m.pl_outlier
          AND m.dt <= (SELECT ultimo_mes_completo FROM _meta)
        GROUP BY ALL HAVING count(*) >= 3
        ORDER BY 1, 2""", [categoria])


def setor_aging(categoria: str) -> list[dict]:
    r = df(f"""
        SELECT {', '.join(f'sum(m.in_{b}) AS in_{b}' for b in BUCKETS)}, sum(m.dc_bruto) AS dc
        FROM metricas_mes m JOIN classificacao c USING (cnpj)
        WHERE c.categoria = ? AND m.dt = (SELECT ultimo_mes_completo FROM _meta)""", [categoria])
    if r.empty:
        return []
    a = r.iloc[0]
    return [{"faixa": lb, "vencido": a[f"in_{b}"], "pct_carteira": (a[f"in_{b}"] / a["dc"]) if a["dc"] else None}
            for b, lb in zip(BUCKETS, BUCKET_LABEL)]


# ---------------------------------------------------------------- alertas
REGRAS_ALERTA = [
    # (id, descrição, função(atual, 3m atrás, setor) -> bool, severidade)
    ("subordinacao_queda", "Subordinação caiu mais de 5 p.p. em 3 meses",
     lambda a, b, s: _d(a, b, "subordinacao") < -0.05, "alta"),
    ("inad_alta", "Inadimplência >90d subiu mais de 2 p.p. em 3 meses",
     lambda a, b, s: _d(a, b, "inad_90") > 0.02, "alta"),
    ("inad_vs_setor", "Inadimplência >90d acima de 2x a mediana da categoria (e > 2%)",
     lambda a, b, s: _v(a, "inad_90") > 0.02 and _v(a, "inad_90") > 2 * (_v(s, "inad_90_mediana") or 0), "media"),
    ("pdd_alta", "PDD/carteira subiu mais de 2 p.p. em 3 meses",
     lambda a, b, s: _d(a, b, "pdd_carteira") > 0.02, "media"),
    ("recompra", "Recompra/substituição pelo cedente acima de 5% da carteira em 3 meses",
     lambda a, b, s: _v(a, "recompra_subst_3m_carteira") > 0.05, "alta"),
    ("roll_alto", "Roll rate 31-60→61-90 acima de 80% (com atraso relevante)",
     lambda a, b, s: _v(a, "roll_60_90") > 0.8 and _v(a, "inad_total") > 0.01, "media"),
    ("pl_queda", "PL caiu mais de 20% em 3 meses",
     lambda a, b, s: _v(b, "pl") > 0 and _v(a, "pl") / _v(b, "pl") - 1 < -0.20, "media"),
    ("rentab_senior_neg", "Rentabilidade da cota sênior negativa no mês",
     lambda a, b, s: _v(a, "rentab_senior") < 0 and a.get("rentab_senior") is not None, "alta"),
    ("concentracao", "Maior cedente acima de 50% da carteira",
     lambda a, b, s: _v(a, "top1_cedente_pct") > 50, "info"),
]


def _v(r, k):
    if r is None:
        return 0.0
    v = r.get(k)
    return 0.0 if v is None or pd.isna(v) else float(v)


def _d(a, b, k):
    if a is None or b is None or a.get(k) is None or b.get(k) is None or pd.isna(a.get(k)) or pd.isna(b.get(k)):
        return 0.0
    return float(a[k]) - float(b[k])


def alertas(cnpjs: list[str]) -> dict[str, list[dict]]:
    if not cnpjs:
        return {}
    ph = ", ".join("?" for _ in cnpjs)
    m = df(f"""
        SELECT m.*, c.categoria, row_number() OVER (PARTITION BY m.cnpj ORDER BY m.dt DESC) AS rn
        FROM metricas_mes m JOIN classificacao c USING (cnpj)
        WHERE m.cnpj IN ({ph})
        QUALIFY rn IN (1, 4)""", cnpjs)
    setor = df("SELECT * FROM setor_mes WHERE dt = (SELECT ultimo_mes_completo FROM _meta)")
    setor = {r["categoria"]: r for r in setor.to_dict("records")}
    ref = pd.Timestamp(ref_month())
    out: dict[str, list[dict]] = {}
    for cnpj, g in m.groupby("cnpj"):
        a = g[g.rn == 1].iloc[0].to_dict()
        b = g[g.rn == 4].iloc[0].to_dict() if (g.rn == 4).any() else None
        s = setor.get(a["categoria"])
        lst = []
        for rid, desc, fn, sev in REGRAS_ALERTA:
            try:
                if fn(a, b, s):
                    lst.append({"id": rid, "descricao": desc, "severidade": sev, "detalhe": _detalhe_alerta(rid, a, b, s)})
            except (TypeError, ZeroDivisionError):
                pass
        if pd.Timestamp(a["dt"]) < ref:
            lst.append({"id": "informe_atrasado", "severidade": "media",
                        "descricao": f"Último informe na CVM é de {pd.Timestamp(a['dt']):%m/%Y}"})
        out[cnpj] = lst
    return out


# ---------------------------------------------------------------- carteira / watchlist
def lista_cnpjs(tipo: str) -> list[dict]:
    with appdb.session() as s:
        return [dict(r) for r in s.execute("SELECT * FROM lista WHERE tipo = ? ORDER BY adicionado_em", [tipo])]


def painel(tipo: str) -> pd.DataFrame:
    itens = lista_cnpjs(tipo)
    if not itens:
        return pd.DataFrame()
    cnpjs = [i["cnpj"] for i in itens]
    ph = ", ".join("?" for _ in cnpjs)
    cols = ["pl", "inad_90", "pdd_carteira", "subordinacao", "rentab_senior", "rentab_subordinada",
            "roll_60_90", "inad_90_lag12", "recompra_subst_3m_carteira", "top1_cedente_pct"]
    d = df(f"""
        WITH m AS (
          SELECT m.*, row_number() OVER (PARTITION BY cnpj ORDER BY dt DESC) AS rn
          FROM metricas_mes m WHERE cnpj IN ({ph})
        )
        SELECT a.cnpj, a.nome, c.categoria_nome, c.categoria, k.gestor, a.dt,
               {', '.join(f'a.{c}' for c in cols)},
               {', '.join(f'a.{c} - b.{c} AS d3m_{c}' for c in cols if c != 'pl')},
               a.pl / nullif(b.pl, 0) - 1 AS d3m_pl,
               s.inad_90_mediana AS setor_inad_90, s.subordinacao_mediana AS setor_subordinacao,
               s.rentab_senior_mediana AS setor_rentab_senior
        FROM m a LEFT JOIN m b ON b.cnpj = a.cnpj AND b.rn = 4
        JOIN classificacao c ON c.cnpj = a.cnpj
        LEFT JOIN cadastro k ON k.cnpj = a.cnpj
        LEFT JOIN setor_mes s ON s.categoria = c.categoria AND s.dt = a.dt
        WHERE a.rn = 1
        ORDER BY a.pl DESC""", cnpjs)
    al = alertas(cnpjs)
    d["alertas"] = d["cnpj"].map(lambda c: len([x for x in al.get(c, []) if x["severidade"] != "info"]))
    d["alertas_desc"] = d["cnpj"].map(lambda c: "; ".join(x["descricao"] for x in al.get(c, [])))
    tese = {i["cnpj"]: i.get("tese") for i in itens}
    d["tese"] = d["cnpj"].map(tese)
    return d


def relatorio_lista(tipo: str) -> dict[str, pd.DataFrame]:
    """Abas do relatório mensal da carteira/watchlist."""
    p = painel(tipo)
    if p.empty:
        return {"Resumo": p}
    cnpjs = p["cnpj"].tolist()
    ph = ", ".join("?" for _ in cnpjs)
    hist = df(f"""
        SELECT m.cnpj, m.nome, m.dt, {', '.join(f'm.{k}' for k in KPIS)}
        FROM metricas_mes m
        WHERE m.cnpj IN ({ph}) AND m.dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 24 MONTH
        ORDER BY m.cnpj, m.dt""", cnpjs)
    series = pd.concat([series_fundo(c).assign(cnpj=c) for c in cnpjs], ignore_index=True)
    ced = df(f"""SELECT cnpj, dt, rank, cedente_doc, pct FROM cedente_mes c
                 WHERE cnpj IN ({ph}) AND dt = (SELECT max(dt) FROM cedente_mes x WHERE x.cnpj = c.cnpj)
                 ORDER BY cnpj, rank""", cnpjs)
    al = alertas(cnpjs)
    alert_rows = [{"cnpj": c, "nome": p.set_index("cnpj").loc[c, "nome"], **a} for c, lst in al.items() for a in lst]
    return {"Resumo": p, "Alertas": pd.DataFrame(alert_rows), "Histórico 24m": hist,
            "Séries": series, "Cedentes": ced}


def _pp(v, casas=2):
    return "n/d" if v is None or pd.isna(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def _detalhe_alerta(rid, a, b, s) -> str:
    """Número por trás do alerta: valor atual, valor de 3 meses antes e referência da categoria."""
    b = b or {}
    s = s or {}
    if rid == "subordinacao_queda":
        return f"{_pp(b.get('subordinacao'))} → {_pp(a.get('subordinacao'))}"
    if rid == "inad_alta":
        return f"{_pp(b.get('inad_90'))} → {_pp(a.get('inad_90'))}"
    if rid == "inad_vs_setor":
        return f"fundo {_pp(a.get('inad_90'))} × mediana da categoria {_pp(s.get('inad_90_mediana'))}"
    if rid == "pdd_alta":
        return f"{_pp(b.get('pdd_carteira'))} → {_pp(a.get('pdd_carteira'))}"
    if rid == "recompra":
        return f"{_pp(a.get('recompra_subst_3m_carteira'))} da carteira em 3 meses"
    if rid == "roll_alto":
        return f"roll 31-60→61-90 = {_pp(a.get('roll_60_90'), 0)}"
    if rid == "pl_queda":
        return f"PL {b.get('pl', 0) / 1e6:,.1f} mi → {a.get('pl', 0) / 1e6:,.1f} mi".replace(",", "X").replace(".", ",").replace("X", ".")
    if rid == "rentab_senior_neg":
        return f"{a.get('rentab_senior'):.2f}% no mês (média das séries sêniores ponderada pelo PL)".replace(".", ",")
    if rid == "concentracao":
        return f"maior cedente = {a.get('top1_cedente_pct'):.1f}% (campo do informe)".replace(".", ",")
    return ""
