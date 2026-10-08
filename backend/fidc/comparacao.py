"""Comparação fundo × pares × mercado.

Regras (instruções MCMS v2.0, seção 5, aplicadas a qualquer categoria):
- Estatísticas dos pares SEM o próprio fundo: mediana, P25, P75, n; percentil quando n ≥ 5.
- Posição no sentido de cada métrica: quartil favorável / neutro / quartil desfavorável.
- Opcional "uma gestora = um fundo": fica o maior fundo de cada gestora.
- Por padrão, pares com erro de consistência no mês (qualidade) ficam fora das estatísticas.
"""
from __future__ import annotations

import math
import re
import threading

import httpx
import numpy as np
import pandas as pd

from . import appdb, catalogo, config
from .db import df

_cache: dict = {}
_lock = threading.Lock()
RF_COLS = [r[0] for r in catalogo.RED_FLAGS]
# métricas que dependem das faixas de atraso: fundos com zero vencido declarado (não verificável) saem das estatísticas
AGING_KEYS = {"vencido_carteira", "over30_carteira", "over90_carteira", "over180_pl", "inad_contratos", "pdd_over90",
              "roll_30_60", "roll_60_90", "m17_f30_media", "m17_f180_media", "inad_90_lag12", "m02_jr_vencidos360"}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "").zfill(14)


def universo() -> pd.DataFrame:
    """Última foto comparável de cada fundo (até o mês de referência), com categoria e gestor."""
    mtime = config.DB_PATH.stat().st_mtime
    with _lock:
        if _cache.get("mtime") == mtime:
            return _cache["u"]
    u = df("""
        WITH ref AS (SELECT ultimo_mes_completo AS r FROM _meta)
        SELECT c.*, k.categoria, k.categoria_nome, k.grupo, cad.gestor, f.admin,
               (c.dt < (SELECT r FROM ref)) AS defasado
        FROM comp_mes c
        JOIN classificacao k USING (cnpj)
        LEFT JOIN cadastro cad USING (cnpj)
        LEFT JOIN fundo f USING (cnpj)
        WHERE c.dt <= (SELECT r FROM ref) AND c.dt > (SELECT r FROM ref) - INTERVAL 3 MONTH
        QUALIFY row_number() OVER (PARTITION BY c.cnpj ORDER BY c.dt DESC) = 1
    """)
    with _lock:
        _cache.update(mtime=mtime, u=u)
    return u


# ------------------------------------------------------------------ grupos de pares
def grupos() -> list[dict]:
    with appdb.session() as s:
        gs = [dict(r) for r in s.execute("SELECT * FROM grupo_pares ORDER BY nome")]
        for g in gs:
            g["membros"] = [dict(r) for r in s.execute(
                "SELECT cnpj, incluir, motivo FROM grupo_pares_membro WHERE grupo_id = ?", [g["id"]])]
    return gs


def resolver_pares(cnpj: str, modo: str = "categoria", grupo_id: int | None = None,
                   cnpjs: list[str] | None = None, uma_por_gestora: bool = False,
                   excluir_erro: bool = True, pl_min: float = 0) -> tuple[pd.DataFrame, str]:
    """Devolve (linhas dos pares no universo, descrição do grupo). Nunca inclui o próprio fundo."""
    u = universo()
    cnpj = _digits(cnpj)
    me = u[u.cnpj == cnpj]
    if modo == "grupo" and grupo_id:
        g = next((g for g in grupos() if g["id"] == grupo_id), None)
        if not g:
            raise ValueError("grupo inexistente")
        sel = {m["cnpj"] for m in g["membros"] if m["incluir"]}
        p = u[u.cnpj.isin(sel)]
        desc = f"Grupo '{g['nome']}'"
        uma_por_gestora = uma_por_gestora or bool(g["uma_por_gestora"])
    elif modo == "lista" and cnpjs:
        p = u[u.cnpj.isin({_digits(c) for c in cnpjs})]
        desc = "Lista personalizada"
    elif modo == "mercado":
        p = u
        desc = "Mercado inteiro"
    else:
        cat = me.categoria.iloc[0] if not me.empty else None
        p = u[u.categoria == cat]
        desc = f"Categoria: {me.categoria_nome.iloc[0]}" if not me.empty else "Categoria"
    p = p[(p.cnpj != cnpj) & (p.pl > pl_min) & (~p.pl_outlier.fillna(False))]
    if excluir_erro:
        p = p[p.q_status.fillna("ok") != "erro"]
    if uma_por_gestora:
        p = p.sort_values("pl", ascending=False).drop_duplicates(subset=["gestor"], keep="first")
        desc += " · 1 fundo por gestora"
    return p, desc


# ------------------------------------------------------------------ comparação
def _stat(vals: pd.Series, v, sentido: int) -> dict:
    vals = vals.dropna()
    vals = vals[np.isfinite(vals)]
    n = len(vals)
    out = {"n": n, "p25": None, "mediana": None, "p75": None, "percentil": None, "posicao": "n/d"}
    if n == 0:
        return out
    out.update(p25=float(vals.quantile(0.25)), mediana=float(vals.median()), p75=float(vals.quantile(0.75)))
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return out
    if n >= 5:
        out["percentil"] = float((vals < v).mean() + 0.5 * (vals == v).mean())
    if sentido == 0:
        out["posicao"] = "contexto"
    elif n >= 4:
        melhor = v >= out["p75"] if sentido > 0 else v <= out["p25"]
        pior = v <= out["p25"] if sentido > 0 else v >= out["p75"]
        out["posicao"] = "favoravel" if melhor and not pior else "desfavoravel" if pior and not melhor else "neutro"
    return out


def comparar(cnpj: str, ignorar_sem_vencido: bool = True, **kw) -> dict:
    u = universo()
    cnpj = _digits(cnpj)
    me = u[u.cnpj == cnpj]
    if me.empty:
        raise LookupError("fundo sem informe recente")
    row = me.iloc[0]
    pares, desc = resolver_pares(cnpj, **kw)
    mercado = u[(u.cnpj != cnpj) & (u.pl > 0) & (~u.pl_outlier.fillna(False)) & (u.q_status.fillna("ok") != "erro")]
    mets = []
    zero_fundo = bool(row.get("sem_vencido_declarado"))
    for key, label, fmt, sentido, bloco, defin in catalogo.METRICAS:
        v = row.get(key)
        v = None if v is None or (isinstance(v, float) and not math.isfinite(v)) else float(v)
        pp, mm = pares, mercado
        if ignorar_sem_vencido and key in AGING_KEYS:
            pp = pares[~pares.sem_vencido_declarado.fillna(False)]
            mm = mercado[~mercado.sem_vencido_declarado.fillna(False)]
        s = _stat(pp[key], v, sentido)
        sm = _stat(mm[key], v, sentido)
        if zero_fundo and key in AGING_KEYS:
            s["posicao"] = "zero_declarado"
        mets.append({"metrica": key, "codigo": catalogo.codigo(key), "label": label, "fmt": fmt, "sentido": sentido,
                     "bloco": bloco, "definicao": defin, "valor": v, **s,
                     "mercado_mediana": sm["mediana"], "mercado_percentil": sm["percentil"]})
    blocos = []
    for b in catalogo.BLOCOS:
        ms = [m for m in mets if m["bloco"] == b]
        blocos.append({"bloco": b, "favoravel": sum(m["posicao"] == "favoravel" for m in ms),
                       "neutro": sum(m["posicao"] == "neutro" for m in ms),
                       "desfavoravel": sum(m["posicao"] == "desfavoravel" for m in ms)})
    rfs = []
    for col, nome, regra in catalogo.RED_FLAGS:
        lvl = row.get(col)
        lvl = None if lvl is None or (isinstance(lvl, float) and math.isnan(lvl)) else int(lvl)
        pct_pares = float((pares[col] >= 1).mean()) if len(pares) else None
        rfs.append({"id": col, "codigo": catalogo.codigo(col), "nome": nome, "regra": regra, "nivel": lvl,
                    "definicao": catalogo.RF_DEFINICAO.get(col),
                    "detalhe": detalhe_rf(col, row), "pct_pares_com_flag": pct_pares})
    return {
        "fundo": {"cnpj": cnpj, "nome": row["nome"], "dt": str(row["dt"])[:10], "categoria": row["categoria_nome"],
                  "sem_vencido_declarado": zero_fundo,
                  "gestor": row.get("gestor"), "defasado": bool(row["defasado"]), "q_status": row.get("q_status"),
                  "q_checks": row.get("q_checks")},
        "pares": {"descricao": desc, "n": len(pares),
                  "n_sem_vencido": int(pares.sem_vencido_declarado.fillna(False).sum()),
                  "lista": pares[["cnpj", "nome", "gestor", "pl", "q_status"]].sort_values("pl", ascending=False)
                  .to_dict("records")},
        "metricas": mets, "blocos": blocos, "red_flags": rfs,
    }


def serie_vs_pares(cnpj: str, metrica: str, meses: int = 24, ignorar_sem_vencido: bool = True, **kw) -> pd.DataFrame:
    if metrica not in catalogo.BY_KEY:
        raise ValueError("métrica inválida")
    pares, _ = resolver_pares(cnpj, **kw)
    ids = [_digits(cnpj)] + pares.cnpj.tolist()
    ph = ",".join("?" for _ in ids)
    d = df(f"""
        SELECT cnpj, dt, {metrica} AS v FROM comp_mes
        WHERE cnpj IN ({ph}) AND NOT pl_outlier AND coalesce(q_status, 'ok') <> 'erro'
          {f"AND (cnpj = '{ids[0]}' OR NOT coalesce(sem_vencido_declarado, false))" if ignorar_sem_vencido and metrica in AGING_KEYS else ""}
          AND dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL {int(meses)} MONTH
          AND dt <= (SELECT ultimo_mes_completo FROM _meta)""", ids)
    me = d[d.cnpj == ids[0]].set_index("dt")["v"]
    p = d[d.cnpj != ids[0]].groupby("dt")["v"]
    out = pd.DataFrame({"p25": p.quantile(0.25), "mediana": p.median(), "p75": p.quantile(0.75), "n": p.count()})
    out["fundo"] = me
    return out.reset_index().sort_values("dt")


def dispersao(cnpj: str, x: str, y: str, **kw) -> pd.DataFrame:
    for k in (x, y):
        if k not in catalogo.BY_KEY:
            raise ValueError("métrica inválida")
    pares, _ = resolver_pares(cnpj, **kw)
    u = universo()
    me = u[u.cnpj == _digits(cnpj)]
    d = pd.concat([me.assign(destaque=True), pares.assign(destaque=False)])
    out = d[["cnpj", "nome", "gestor", "pl", "destaque"]].copy()
    out["x"], out["y"] = d[x].values, d[y].values
    return out


def lado_a_lado(cnpjs: list[str]) -> pd.DataFrame:
    u = universo()
    sel = u[u.cnpj.isin([_digits(c) for c in cnpjs])].set_index("cnpj")
    rows = []
    for key, label, fmt, sentido, bloco, _ in catalogo.METRICAS:
        r = {"metrica": key, "label": label, "fmt": fmt, "sentido": sentido, "bloco": bloco}
        for c in sel.index:
            v = sel.loc[c, key]
            r[c] = None if pd.isna(v) else float(v)
        rows.append(r)
    return pd.DataFrame(rows), sel[["nome", "categoria_nome", "gestor", "dt"]].reset_index()


def o_que_mudou(cnpj: str) -> list[dict]:
    """Variação do último mês contra o anterior nas métricas-chave, com leitura direcional."""
    keys = ["pl", "over90_carteira", "pdd_carteira", "subordinacao", "jr_pl", "roll_30_60",
            "m05_recompra_carteira", "top1_cedente_pct", "rentab_senior", "m19_excesso_spread", "m23_pmr"]
    d = df(f"""SELECT dt, {', '.join(keys)}, {', '.join(RF_COLS)} FROM comp_mes WHERE cnpj = ?
               ORDER BY dt DESC LIMIT 2""", [_digits(cnpj)])
    if len(d) < 2:
        return []
    a, b = d.iloc[0], d.iloc[1]
    out = []
    for k in keys:
        _, label, fmt, sentido, _, _ = catalogo.BY_KEY[k]
        va, vb = a[k], b[k]
        if pd.isna(va) or pd.isna(vb):
            continue
        delta = (va / vb - 1) if fmt == "brl" and vb else va - vb
        relevante = abs(delta) > (0.05 if fmt == "brl" else 0.01 if fmt == "pct" else 0.5 if fmt == "pct100" else 10 if fmt == "dias" else 0.1)
        if not relevante:
            continue
        direcao = "melhora" if (delta > 0) == (sentido > 0) and sentido != 0 else "piora" if sentido != 0 else "variação"
        out.append({"metrica": k, "label": label, "fmt": fmt, "anterior": float(vb), "atual": float(va),
                    "delta": float(delta), "delta_fmt": "pct" if fmt == "brl" else fmt, "direcao": direcao})
    for col, nome, _ in catalogo.RED_FLAGS:
        va, vb = a[col], b[col]
        if pd.notna(va) and (pd.isna(vb) and va > 0 or pd.notna(vb) and va > vb):
            cor = "vermelho" if va == 2 else "amarelo"
            txt = f"{nome}: passou a ser calculada (12 meses de histórico) e já está {cor}" if pd.isna(vb) else f"{nome}: subiu para {cor}"
            out.append({"metrica": col, "label": txt, "detalhe": detalhe_rf(col, a), "direcao": "piora", "fmt": "txt"})
    return out


# ------------------------------------------------------------------ stress test
def stress(cnpj: str, perda_base: float | None = None, multiplicadores=(1, 2, 4), lgd_evento: float = 0.6,
           evento_pct_pl: float | None = None, meses: int = 12, spread_aa: float | None = None) -> dict:
    """Stress simplificado (12 meses) a partir do informe.

    Perda anual = custo de crédito 12m (M16) × multiplicador; evento de concentração = maior cedente × LGD
    (só nos cenários > 1x). Receita para absorver = excesso de spread observado (M19, que já é pós-perdas;
    somamos de volta a perda base para não contar a perda duas vezes). Perdas consomem Jr → Mz → Sênior.
    """
    d = df("""SELECT c.*, m.dc_bruto FROM comp_mes c JOIN metricas_mes m USING (cnpj, dt)
              WHERE cnpj = ? ORDER BY dt DESC LIMIT 1""", [_digits(cnpj)])
    if d.empty:
        raise LookupError("fundo sem dados")
    r = d.iloc[0]
    jr, mz, sr = (float(r[k]) if pd.notna(r[k]) else 0.0 for k in ("jr", "mz", "sr"))
    cart = float(r["dc_bruto"] or 0)
    base = perda_base if perda_base is not None else (float(r["m16_custo_credito"]) if pd.notna(r["m16_custo_credito"]) else None)
    if base is None or cart <= 0:
        return {"disponivel": False, "motivo": "Sem custo de crédito 12m (fundo com menos de 12 meses ou sem carteira)."}
    pl = jr + mz + sr
    spread = spread_aa if spread_aa is not None else (float(r["m19_excesso_spread"]) if pd.notna(r["m19_excesso_spread"]) else 0.0)
    receita_pre_perda = spread * pl + base * cart          # excesso de spread antes das perdas (R$/ano)
    ev_pct = evento_pct_pl if evento_pct_pl is not None else ((float(r["top1_cedente_pct"]) / 100) if pd.notna(r["top1_cedente_pct"]) else 0.0)
    cen = []
    for mult in multiplicadores:
        perda = base * mult * cart * meses / 12
        evento = (ev_pct * pl * lgd_evento) if mult > 1 else 0.0
        receita = receita_pre_perda * meses / 12 * (1 if mult == 1 else 0.5 if mult == 2 else 0.25)
        consumo = max(perda + evento - receita, 0.0)
        perda_jr = min(consumo, jr)
        perda_mz = min(max(consumo - jr, 0), mz)
        perda_sr = min(max(consumo - jr - mz, 0), sr)
        cen.append({"cenario": f"{mult}x", "perda_anual_pct": base * mult, "evento_rs": evento, "receita_rs": receita,
                    "consumo_rs": consumo, "perda_jr_pct": perda_jr / jr if jr else None,
                    "perda_mz_pct": perda_mz / mz if mz else None, "perda_sr_pct": perda_sr / sr if sr else None,
                    "jr_pl_final": (jr - perda_jr) / (pl - consumo) if pl - consumo > 0 else None})
    # perda anual (% carteira) que zera a Jr e que começa a atingir a sênior, com a receita base
    limiar_jr = (jr + receita_pre_perda) / cart
    limiar_sr = (jr + mz + receita_pre_perda) / cart
    return {"disponivel": True, "dt": str(r["dt"])[:10], "jr": jr, "mz": mz, "sr": sr, "carteira": cart,
            "custo_credito_base": base, "excesso_spread": spread, "evento_pct_pl": ev_pct, "lgd_evento": lgd_evento,
            "limiar_perda_jr": limiar_jr, "limiar_perda_senior": limiar_sr,
            "multiplo_limiar_jr": limiar_jr / base if base > 0 else None,
            "multiplo_limiar_senior": limiar_sr / base if base > 0 else None,
            "cenarios": cen,
            "premissas": "Carteira constante; perdas absorvidas Jr → Mz → Sênior; receita pré-perdas = excesso de "
                         "spread observado + perda base; nos cenários 2x e 4x a receita cai a 50% e 25% "
                         "(mora não recebida) e entra a quebra do maior cedente com LGD informada."}


# ------------------------------------------------------------------ setor: originadores e red flags
def nomes_cnpj(cnpjs: list[str], consultar: int = 25) -> dict[str, str]:
    """Razão social via cache local; consulta a BrasilAPI para até `consultar` CNPJs novos (14 dígitos)."""
    cnpjs = [c for c in cnpjs if c and len(c) == 14]
    with appdb.session() as s:
        have = {r["cnpj"]: r["nome"] for r in s.execute(
            f"SELECT cnpj, nome FROM cnpj_nome WHERE cnpj IN ({','.join('?' for _ in cnpjs)})", cnpjs)} if cnpjs else {}
        faltam = [c for c in cnpjs if c not in have][:consultar]
        with httpx.Client(timeout=15) as cli:
            for c in faltam:
                try:
                    j = cli.get(f"https://brasilapi.com.br/api/cnpj/v1/{c}").json()
                    nome = j.get("razao_social") or j.get("nome_fantasia")
                except Exception:  # noqa: BLE001 - nome é cosmético
                    nome = None
                if nome:
                    s.execute("INSERT OR REPLACE INTO cnpj_nome (cnpj, nome) VALUES (?, ?)", [c, nome])
                    have[c] = nome
    return have


def originadores(categoria: str, top: int = 40) -> pd.DataFrame:
    d = df("""
        SELECT cm.cedente_doc AS cedente, count(DISTINCT cm.cnpj) AS n_fundos,
               sum(cm.pct / 100 * m.dc_bruto) AS exposicao_estimada,
               max(cm.pct) AS maior_pct, string_agg(DISTINCT m.nome, ' | ') AS fundos
        FROM cedente_mes cm
        JOIN metricas_mes m USING (cnpj, dt)
        JOIN classificacao c USING (cnpj)
        WHERE c.categoria = ? AND cm.pct IS NOT NULL
          AND cm.dt = (SELECT max(dt) FROM cedente_mes x WHERE x.cnpj = cm.cnpj)
          AND cm.dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 3 MONTH
          AND length(cm.cedente_doc) = 14
        GROUP BY 1 ORDER BY exposicao_estimada DESC NULLS LAST LIMIT ?""", [categoria, top])
    nomes = nomes_cnpj(d.cedente.tolist())
    d.insert(1, "nome_cedente", d.cedente.map(nomes))
    return d


def red_flags_setor(categoria: str | None) -> pd.DataFrame:
    u = universo()
    if categoria:
        u = u[u.categoria == categoria]
    u = u[u.pl > 0]
    rows = []
    for col, nome, regra in catalogo.RED_FLAGS:
        v = u[col].dropna()
        rows.append({"id": col, "red_flag": nome, "regra": regra, "definicao": catalogo.RF_DEFINICAO.get(col),
                     "n_fundos": len(v),
                     "amarelo": int((v == 1).sum()), "vermelho": int((v == 2).sum()),
                     "pct_com_flag": float((v >= 1).mean()) if len(v) else None,
                     "pl_com_flag": float(u.loc[u[col] >= 1, "pl"].sum())})
    return pd.DataFrame(rows)


def gestores_setor(categoria: str) -> pd.DataFrame:
    u = universo()
    u = u[(u.categoria == categoria) & (u.pl > 0)]
    g = u.groupby(u.gestor.fillna("(sem cadastro)")).agg(
        n_fundos=("cnpj", "count"), pl_total=("pl", "sum"),
        over90_mediana=("over90_carteira", "median"), subordinacao_mediana=("subordinacao", "median"),
        retorno_jr_mediana=("m21_retorno_jr_12m", "median")).reset_index().rename(columns={"gestor": "nome"})
    return g.sort_values("pl_total", ascending=False)


def seed_grupos() -> None:
    """Carrega grupos_iniciais.yaml na primeira subida (não mexe em grupo que já existe)."""
    import yaml
    f = config.TAXONOMY_FILE.parent / "grupos_iniciais.yaml"
    if not f.exists():
        return
    data = yaml.safe_load(open(f, encoding="utf-8")) or {}
    with appdb.session() as s:
        for g in data.get("grupos", []):
            if s.execute("SELECT 1 FROM grupo_pares WHERE nome = ?", [g["nome"]]).fetchone():
                continue
            cur = s.execute("INSERT INTO grupo_pares (nome, descricao, uma_por_gestora, criado_por) VALUES (?, ?, ?, ?)",
                            [g["nome"], g.get("descricao"), int(g.get("uma_por_gestora", False)), "carga inicial"])
            for m in g.get("membros", []):
                s.execute("INSERT INTO grupo_pares_membro (grupo_id, cnpj, incluir, motivo) VALUES (?, ?, ?, ?)",
                          [cur.lastrowid, _digits(m["cnpj"]), int(m.get("incluir", True)), m.get("motivo")])


def _p(v, casas=1):
    return "n/d" if v is None or pd.isna(v) else f"{v * 100:.{casas}f}%".replace(".", ",")


def detalhe_rf(col: str, r) -> str:
    """Frase com o número que acendeu (ou não) a red flag, na data-base do fundo."""
    g = r.get
    if col == "rf01_recompra":
        return f"recompras = {_p(g('recompra_aquisicoes_mes'))} das aquisições do mês"
    if col == "rf02_roll":
        return (f"roll 1-30→31-60 nos últimos 3 meses: {_p(g('roll_m2'), 0)} → {_p(g('roll_m1'), 0)} → "
                f"{_p(g('roll_m0'), 0)}")
    if col == "rf04_vencido_180":
        return f"vencido > 180 d = {_p(g('over180_pl'), 2)} do PL"
    if col == "rf09_pdd_over90":
        v = g("pdd_over90")
        return "n/d" if v is None or pd.isna(v) else f"PDD cobre {v * 100:.0f}% do vencido > 90 d (Over 90 = {_p(g('over90_carteira'), 2)} da carteira)"
    if col == "rf10_alavancagem":
        def mov(v, sobe, desce):
            return "n/d" if v is None or pd.isna(v) else f"{sobe if v >= 0 else desce} {_p(abs(v), 0)}"
        vs = g("var_sub_12m")
        sub = "" if vs is None or pd.isna(vs) else \
            f"; subordinação {'subiu' if vs >= 0 else 'caiu'} {abs(vs) * 100:.1f} p.p.".replace(".", ",")
        return f"PL {mov(g('cresc_pl_12m'), 'cresceu', 'caiu')} e Jr {mov(g('cresc_jr_12m'), 'cresceu', 'reduziu')}{sub}"
    if col == "rf14_jr_negativa":
        n, s = g("meses_jr_negativa_12m"), g("jr_neg_seguidos")
        return f"{0 if n is None or pd.isna(n) else int(n)} mês(es) com Jr negativa em 12m; maior sequência: {0 if s is None or pd.isna(s) else int(s)}"
    if col == "rf16_rj":
        return f"cedidos por empresas em RJ = {_p(g('m13_rj_pl'), 2)} do PL"
    if col == "rf17_spread":
        return f"excesso de spread observado em 12 meses = {_p(g('m19_excesso_spread'))} a.a."
    if col == "rf19_recompra_desconto":
        return f"recompra paga a {_p(g('preco_recompra_mes'))} do valor contábil no mês"
    if col == "rf23_fuga_senior":
        return f"resgate líquido da sênior em 12m = {_p(g('resgate_liq_sr_12m'))} do PL sênior de 12m atrás"
    if col == "rf24_cedente":
        v = g("top1_cedente_pct")
        return "nenhum cedente listado no informe" if v is None or pd.isna(v) else f"maior cedente = {v:.1f}% (campo do informe)".replace(".", ",")
    return ""
