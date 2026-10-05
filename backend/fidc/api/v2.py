"""Rotas da v2: comparação com pares, qualidade dos dados, métricas da casa, stress, roteiro de DD,
parâmetros manuais, grupos de pares e contexto setorial (BCB, originadores, red flags)."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import yaml
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from .. import appdb, catalogo, comparacao as cp, config, consultas, excel
from ..db import df

router = APIRouter(prefix="/api")
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ROTEIROS_FILE = config.TAXONOMY_FILE.parent / "roteiros.yaml"


def _usuario(request: Request) -> str | None:
    return request.headers.get("Cf-Access-Authenticated-User-Email") or request.headers.get("X-Usuario")


def _xlsx(sheets: dict, nome: str, notas: dict | None = None) -> Response:
    return Response(excel.to_xlsx(sheets, notas), media_type=XLSX,
                    headers={"Content-Disposition": f'attachment; filename="{nome}_{datetime.now():%Y%m%d}.xlsx"'})


def _out(d: pd.DataFrame, formato: str | None, nome: str, nota: str | None = None):
    if formato == "xlsx":
        return _xlsx({nome: d}, nome.lower().replace(" ", "_"), {nome: nota} if nota else None)
    return excel.json_safe(d)


def _pares_kw(modo: str, grupo_id: int | None, cnpjs: str | None, uma_por_gestora: bool, excluir_erro: bool) -> dict:
    return {"modo": modo, "grupo_id": grupo_id, "cnpjs": cnpjs.split(",") if cnpjs else None,
            "uma_por_gestora": uma_por_gestora, "excluir_erro": excluir_erro}


def _clean(obj):
    import math
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, float) and not math.isfinite(obj):
        return None
    if hasattr(obj, "item"):
        return _clean(obj.item())
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()[:10]
    return obj


# ------------------------------------------------------------------ catálogo
@router.get("/catalogo")
def catalogo_json():
    rot = yaml.safe_load(open(ROTEIROS_FILE, encoding="utf-8"))
    return {
        "metricas": [{"metrica": k, "label": l, "fmt": f, "sentido": s, "bloco": b, "definicao": d}
                     for k, l, f, s, b, d in catalogo.METRICAS],
        "red_flags": [{"id": i, "nome": n, "regra": r} for i, n, r in catalogo.RED_FLAGS],
        "blocos": catalogo.BLOCOS,
        "parametros": [{"chave": k, "label": v[0], "fmt": v[1], "fonte": v[2], "uso": v[3]}
                       for k, v in rot["parametros"].items()],
    }


# ------------------------------------------------------------------ comparação
@router.get("/comparar/{cnpj}")
def comparar(cnpj: str, modo: str = "categoria", grupo_id: int | None = None, cnpjs: str | None = None,
             uma_por_gestora: bool = False, excluir_erro: bool = True, formato: str | None = None):
    try:
        r = cp.comparar(cnpj, **_pares_kw(modo, grupo_id, cnpjs, uma_por_gestora, excluir_erro))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    if formato == "xlsx":
        m = pd.DataFrame(r["metricas"])
        return _xlsx({"Métricas vs pares": m, "Red flags": pd.DataFrame(r["red_flags"]),
                      "Pares": pd.DataFrame(r["pares"]["lista"]), "Blocos": pd.DataFrame(r["blocos"])},
                     f"comparacao_{r['fundo']['cnpj']}",
                     {"Métricas vs pares": f"{r['fundo']['nome']} · {r['fundo']['dt']} · pares: {r['pares']['descricao']} (n={r['pares']['n']})"})
    return _clean(r)


@router.get("/comparar/{cnpj}/serie")
def comparar_serie(cnpj: str, metrica: str, meses: int = 24, modo: str = "categoria", grupo_id: int | None = None,
                   cnpjs: str | None = None, uma_por_gestora: bool = False, excluir_erro: bool = True,
                   formato: str | None = None):
    try:
        d = cp.serie_vs_pares(cnpj, metrica, meses, **_pares_kw(modo, grupo_id, cnpjs, uma_por_gestora, excluir_erro))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _out(d, formato, "Série vs pares")


@router.get("/comparar/{cnpj}/dispersao")
def comparar_dispersao(cnpj: str, x: str, y: str, modo: str = "categoria", grupo_id: int | None = None,
                       cnpjs: str | None = None, uma_por_gestora: bool = False, excluir_erro: bool = True):
    try:
        d = cp.dispersao(cnpj, x, y, **_pares_kw(modo, grupo_id, cnpjs, uma_por_gestora, excluir_erro))
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return excel.json_safe(d)


@router.get("/lado-a-lado")
def lado_a_lado(cnpjs: str, formato: str | None = None):
    tab, fundos = cp.lado_a_lado(cnpjs.split(","))
    if formato == "xlsx":
        t = tab.rename(columns=dict(zip(fundos.cnpj, fundos.nome)))
        return _xlsx({"Lado a lado": t, "Fundos": fundos}, "lado_a_lado")
    return {"metricas": excel.json_safe(tab), "fundos": excel.json_safe(fundos)}


# ------------------------------------------------------------------ fundo: casa, safras, qualidade, stress
@router.get("/fundos/{cnpj}/mudancas")
def mudancas(cnpj: str):
    return _clean(cp.o_que_mudou(cnpj))


@router.get("/fundos/{cnpj}/casa")
def casa(cnpj: str, meses: int = 36, formato: str | None = None):
    d = df(f"""SELECT * FROM comp_mes WHERE cnpj = ?
               AND dt > (SELECT max(dt) FROM comp_mes WHERE cnpj = ?) - INTERVAL {int(meses)} MONTH ORDER BY dt""",
           [consultas.cnpj_digits(cnpj)] * 2)
    return _out(d, formato, "Métricas da casa")


@router.get("/fundos/{cnpj}/safras")
def safras(cnpj: str, formato: str | None = None):
    d = df("""SELECT safra, base, f30, f60, f180, f360, f30_base_aquisicoes FROM safra_venc
              WHERE cnpj = ? AND safra > (SELECT max(dt) FROM metricas_mes WHERE cnpj = ?) - INTERVAL 25 MONTH
              ORDER BY safra""", [consultas.cnpj_digits(cnpj)] * 2)
    return _out(d, formato, "Safras", "Proxy sem fita: safra = mês de vencimento; base = a vencer ≤ 30 d no fim do mês anterior.")


@router.get("/fundos/{cnpj}/qualidade")
def qualidade_fundo(cnpj: str, formato: str | None = None):
    d = df("""SELECT q.dt, q.id, k.severidade, k.descricao, k.recomendacao, q.valor
              FROM qualidade q JOIN qualidade_check k USING (id)
              WHERE q.cnpj = ? AND q.dt > (SELECT max(dt) FROM metricas_mes WHERE cnpj = ?) - INTERVAL 13 MONTH
              ORDER BY q.dt DESC, q.id""", [consultas.cnpj_digits(cnpj)] * 2)
    return _out(d, formato, "Qualidade")


@router.get("/fundos/{cnpj}/stress")
def stress(cnpj: str, perda_base: float | None = None, lgd_evento: float = 0.6, evento_pct_pl: float | None = None,
           spread_aa: float | None = None):
    try:
        return _clean(cp.stress(cnpj, perda_base=perda_base, lgd_evento=lgd_evento, evento_pct_pl=evento_pct_pl,
                                spread_aa=spread_aa))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


# ------------------------------------------------------------------ parâmetros manuais
class ParamIn(BaseModel):
    chave: str
    competencia: str = ""
    valor_num: float | None = None
    valor_txt: str | None = None
    fonte: str | None = None
    data_base: str | None = None


@router.get("/fundos/{cnpj}/params")
def params(cnpj: str):
    with appdb.session() as s:
        return [dict(r) for r in s.execute("SELECT * FROM fundo_param WHERE cnpj = ? ORDER BY chave, competencia DESC",
                                           [consultas.cnpj_digits(cnpj)])]


@router.put("/fundos/{cnpj}/params")
def set_param(cnpj: str, p: ParamIn, request: Request):
    with appdb.session() as s:
        s.execute("""INSERT INTO fundo_param (cnpj, chave, competencia, valor_num, valor_txt, fonte, data_base, autor)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                     ON CONFLICT (cnpj, chave, competencia) DO UPDATE SET valor_num = excluded.valor_num,
                     valor_txt = excluded.valor_txt, fonte = excluded.fonte, data_base = excluded.data_base,
                     autor = excluded.autor, atualizado_em = datetime('now')""",
                  [consultas.cnpj_digits(cnpj), p.chave, p.competencia, p.valor_num, p.valor_txt, p.fonte,
                   p.data_base, _usuario(request)])
    return {"ok": True}


@router.delete("/fundos/{cnpj}/params/{chave}")
def del_param(cnpj: str, chave: str, competencia: str = ""):
    with appdb.session() as s:
        s.execute("DELETE FROM fundo_param WHERE cnpj = ? AND chave = ? AND competencia = ?",
                  [consultas.cnpj_digits(cnpj), chave, competencia])
    return {"ok": True}


def _param_atual(cnpj: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for p in params(cnpj):  # ordenado por competência desc: o primeiro de cada chave é o mais recente
        out.setdefault(p["chave"], p)
    return out


def derivados_regulamento(cnpj: str) -> list[dict]:
    """Métricas que dependem de parâmetro manual + informe (M03, M04, folga de subordinação, RF08)."""
    pr = _param_atual(cnpj)
    u = cp.universo()
    row = u[u.cnpj == consultas.cnpj_digits(cnpj)]
    if row.empty:
        return []
    r = row.iloc[0]
    jr, pl, sub = r.get("jr"), r.get("pl"), r.get("subordinacao")
    out = []

    def v(k):
        x = pr.get(k)
        return x["valor_num"] if x else None
    if v("sub_min_senior") is not None and sub is not None and pd.notna(sub):
        folga = sub - v("sub_min_senior")
        out.append({"metrica": "M24 folga da subordinação (p.p.)", "valor": folga, "fmt": "pct",
                    "red_flag": "RF08 V" if folga < 0 else "RF08 A" if folga < 0.03 else None,
                    "fonte": pr["sub_min_senior"]["fonte"]})
    if v("jr_min_pl") is not None and r.get("jr_pl") is not None:
        folga = r["jr_pl"] - v("jr_min_pl")
        out.append({"metrica": "Folga da Jr mínima (p.p.)", "valor": folga, "fmt": "pct",
                    "red_flag": "RF08-Jr V" if folga < 0 else "RF08-Jr A" if folga < 0.03 else None,
                    "fonte": pr["jr_min_pl"]["fonte"]})
    for chave, lim5, lim1, label in (("cedentes", "limite_5_cedentes", "limite_maior_cedente", "M03 Jr ÷ limite dos 5 maiores cedentes"),
                                     ("sacados", "limite_5_sacados", "limite_maior_sacado", "M04 Jr ÷ limite dos 5 maiores sacados")):
        lim = v(lim5) if v(lim5) is not None else (5 * v(lim1) if v(lim1) is not None else None)
        if lim and jr and pl:
            out.append({"metrica": label, "valor": jr / (lim * pl), "fmt": "x",
                        "nota": None if v(lim5) is not None else "sem limite para os 5 maiores: 5 × limite individual",
                        "fonte": (pr.get(lim5) or pr.get(lim1))["fonte"]})
    if (pr.get("responsabilidade_limitada") or {}).get("valor_txt", "").strip().upper().startswith("N"):
        out.append({"metrica": "Responsabilidade limitada", "valor": None, "fmt": "txt", "red_flag": "RF21 V (trava)",
                    "fonte": pr["responsabilidade_limitada"]["fonte"]})
    return out


@router.get("/fundos/{cnpj}/regulamento")
def regulamento(cnpj: str):
    return _clean(derivados_regulamento(cnpj))


# ------------------------------------------------------------------ roteiro de DD
def _roteiros_para(categoria: str) -> list[tuple[str, dict]]:
    rot = yaml.safe_load(open(ROTEIROS_FILE, encoding="utf-8"))["roteiros"]
    esp = [(k, r) for k, r in rot.items() if categoria in r.get("aplica_a", [])]
    return esp or [(k, r) for k, r in rot.items() if "*" in r.get("aplica_a", [])]


@router.get("/fundos/{cnpj}/roteiro")
def roteiro(cnpj: str):
    cnpj = consultas.cnpj_digits(cnpj)
    u = cp.universo()
    row = u[u.cnpj == cnpj]
    cat = row.categoria.iloc[0] if not row.empty else ""
    comp = None
    try:
        comp = {m["metrica"]: m for m in cp.comparar(cnpj)["metricas"]}
    except LookupError:
        pass
    pr = _param_atual(cnpj)
    pcat = yaml.safe_load(open(ROTEIROS_FILE, encoding="utf-8"))["parametros"]
    with appdb.session() as s:
        resp = {r["pergunta_id"]: dict(r) for r in s.execute("SELECT * FROM dd_resposta WHERE cnpj = ?", [cnpj])}
    bcb = {}
    out = []
    for rid, r in _roteiros_para(cat):
        blocos = []
        for b in r["blocos"]:
            itens = []
            for it in b["itens"]:
                auto = None
                m = it.get("metrica")
                if m and m.startswith("param:"):
                    p = pr.get(m[6:])
                    if p:
                        fmt_p = (pcat.get(m[6:]) or [None, "txt"])[1]
                        auto = {"valor": p["valor_num"] if p["valor_num"] is not None else p["valor_txt"],
                                "fmt": "num" if fmt_p == "txt" else fmt_p, "fonte": p["fonte"], "data_base": p["data_base"]}
                elif m and m.startswith("bcb:"):
                    code = int(m[4:])
                    if code not in bcb:
                        x = df("SELECT nome, unidade, dt, valor FROM bcb_serie WHERE codigo = ? ORDER BY dt DESC LIMIT 13", [code])
                        bcb[code] = x
                    x = bcb[code]
                    if not x.empty:
                        auto = {"valor": float(x.valor.iloc[0]), "unidade": x.unidade.iloc[0], "data_base": str(x.dt.iloc[0])[:10],
                                "valor_12m_antes": float(x.valor.iloc[-1]) if len(x) == 13 else None, "fonte": f"BCB SGS {code}"}
                elif m and comp and m in comp:
                    c = comp[m]
                    auto = {"valor": c["valor"], "fmt": c["fmt"], "mediana_pares": c["mediana"], "posicao": c["posicao"],
                            "percentil": c["percentil"], "fonte": "Informe CVM"}
                itens.append({**it, "auto": auto, "resposta": resp.get(it["id"])})
            blocos.append({"nome": b["nome"], "itens": itens})
        out.append({"id": rid, "nome": r["nome"], "blocos": blocos})
    return _clean(out)


class RespostaIn(BaseModel):
    status: str = "pendente"
    resposta: str | None = None
    fonte: str | None = None


@router.put("/fundos/{cnpj}/roteiro/{pergunta_id}")
def set_resposta(cnpj: str, pergunta_id: str, body: RespostaIn, request: Request):
    with appdb.session() as s:
        s.execute("""INSERT INTO dd_resposta (cnpj, pergunta_id, status, resposta, fonte, autor) VALUES (?, ?, ?, ?, ?, ?)
                     ON CONFLICT (cnpj, pergunta_id) DO UPDATE SET status = excluded.status, resposta = excluded.resposta,
                     fonte = excluded.fonte, autor = excluded.autor, atualizado_em = datetime('now')""",
                  [consultas.cnpj_digits(cnpj), pergunta_id, body.status, body.resposta, body.fonte, _usuario(request)])
    return {"ok": True}


# ------------------------------------------------------------------ pacote do comitê (Excel)
@router.get("/fundos/{cnpj}/comite.xlsx")
def comite_xlsx(cnpj: str, modo: str = "categoria", grupo_id: int | None = None, uma_por_gestora: bool = False):
    try:
        r = cp.comparar(cnpj, modo=modo, grupo_id=grupo_id, uma_por_gestora=uma_por_gestora)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    c = consultas.cnpj_digits(cnpj)
    st = cp.stress(c)
    rot = roteiro(c)
    rot_rows = [{"roteiro": x["nome"], "bloco": b["nome"], "pergunta": i["pergunta"], "fonte esperada": i["fonte"],
                 "valor automático": (i["auto"] or {}).get("valor"), "mediana pares": (i["auto"] or {}).get("mediana_pares"),
                 "status": (i["resposta"] or {}).get("status", "pendente"), "resposta": (i["resposta"] or {}).get("resposta")}
                for x in rot for b in x["blocos"] for i in b["itens"]]
    sheets = {
        "Métricas vs pares": pd.DataFrame(r["metricas"]).drop(columns=["definicao"]),
        "Red flags": pd.DataFrame(r["red_flags"]),
        "Regulamento (manual)": pd.DataFrame(derivados_regulamento(c)),
        "Stress": pd.DataFrame(st.get("cenarios", [])),
        "Safras": df("SELECT safra, base, f30, f60, f180, f360 FROM safra_venc WHERE cnpj = ? ORDER BY safra DESC LIMIT 24", [c]),
        "Qualidade": df("""SELECT q.dt, q.id, k.severidade, k.descricao FROM qualidade q
                                                  JOIN qualidade_check k USING (id) WHERE q.cnpj = ? ORDER BY dt DESC LIMIT 60""", [c]),
        "Roteiro de DD": pd.DataFrame(rot_rows),
        "Parâmetros manuais": pd.DataFrame(params(c)),
        "Pares": pd.DataFrame(r["pares"]["lista"]),
        "Histórico 13m": df("SELECT * FROM comp_mes WHERE cnpj = ? ORDER BY dt DESC LIMIT 13", [c]),
    }
    nota = (f"{r['fundo']['nome']} · data-base {r['fundo']['dt']} · pares: {r['pares']['descricao']} (n={r['pares']['n']}). "
            "Estatísticas sem o próprio fundo; posição no sentido de cada métrica (quartil). Fonte: informe mensal CVM.")
    return _xlsx(sheets, f"comite_{c}", {"Métricas vs pares": nota})


# ------------------------------------------------------------------ grupos de pares
class GrupoIn(BaseModel):
    nome: str
    descricao: str | None = None
    uma_por_gestora: bool = False


class MembroIn(BaseModel):
    cnpj: str
    incluir: bool = True
    motivo: str | None = None


@router.get("/grupos")
def listar_grupos():
    return cp.grupos()


@router.post("/grupos")
def criar_grupo(g: GrupoIn, request: Request):
    with appdb.session() as s:
        cur = s.execute("INSERT INTO grupo_pares (nome, descricao, uma_por_gestora, criado_por) VALUES (?, ?, ?, ?)",
                        [g.nome, g.descricao, int(g.uma_por_gestora), _usuario(request)])
        return {"id": cur.lastrowid}


@router.put("/grupos/{gid}")
def editar_grupo(gid: int, g: GrupoIn):
    with appdb.session() as s:
        s.execute("UPDATE grupo_pares SET nome = ?, descricao = ?, uma_por_gestora = ? WHERE id = ?",
                  [g.nome, g.descricao, int(g.uma_por_gestora), gid])
    return {"ok": True}


@router.delete("/grupos/{gid}")
def apagar_grupo(gid: int):
    with appdb.session() as s:
        s.execute("DELETE FROM grupo_pares WHERE id = ?", [gid])
    return {"ok": True}


@router.put("/grupos/{gid}/membros")
def upsert_membro(gid: int, m: MembroIn):
    with appdb.session() as s:
        s.execute("""INSERT INTO grupo_pares_membro (grupo_id, cnpj, incluir, motivo) VALUES (?, ?, ?, ?)
                     ON CONFLICT (grupo_id, cnpj) DO UPDATE SET incluir = excluded.incluir, motivo = excluded.motivo""",
                  [gid, consultas.cnpj_digits(m.cnpj), int(m.incluir), m.motivo])
    return {"ok": True}


@router.delete("/grupos/{gid}/membros/{cnpj}")
def remover_membro(gid: int, cnpj: str):
    with appdb.session() as s:
        s.execute("DELETE FROM grupo_pares_membro WHERE grupo_id = ? AND cnpj = ?", [gid, consultas.cnpj_digits(cnpj)])
    return {"ok": True}


@router.get("/grupos/{gid}/painel")
def painel_grupo(gid: int, formato: str | None = None):
    g = next((g for g in cp.grupos() if g["id"] == gid), None)
    if not g:
        raise HTTPException(404)
    u = cp.universo()
    memb = pd.DataFrame(g["membros"]) if g["membros"] else pd.DataFrame(columns=["cnpj", "incluir", "motivo"])
    d = memb.merge(u, on="cnpj", how="left")
    cols = ["cnpj", "nome", "incluir", "motivo", "gestor", "dt", "q_status"] + [m[0] for m in catalogo.METRICAS] + \
           [r[0] for r in catalogo.RED_FLAGS]
    d = d[[c for c in cols if c in d.columns]]
    return _out(d, formato, f"Grupo {g['nome']}"[:31])


# ------------------------------------------------------------------ setor
@router.get("/setores/{categoria}/bcb")
def setor_bcb(categoria: str, formato: str | None = None):
    d = df("""SELECT s.codigo, s.nome, s.unidade, s.metrica, s.dt, s.valor FROM bcb_serie s
              JOIN bcb_categoria c USING (codigo) WHERE c.categoria = ? AND s.dt >= DATE '2016-01-01'
              ORDER BY s.codigo, s.dt""", [categoria])
    return _out(d, formato, "Séries BCB")


@router.get("/setores/{categoria}/originadores")
def setor_originadores(categoria: str, top: int = 40, formato: str | None = None):
    return _out(cp.originadores(categoria, top), formato, "Originadores",
                "Cedentes informados na Tab. I (até 9 por fundo). Exposição = % do cedente × carteira bruta do fundo (estimativa).")


@router.get("/setores/{categoria}/redflags")
def setor_redflags(categoria: str, formato: str | None = None):
    return _out(cp.red_flags_setor(None if categoria == "todas" else categoria), formato, "Red flags")


@router.get("/setores/{categoria}/gestores")
def setor_gestores(categoria: str, formato: str | None = None):
    return _out(cp.gestores_setor(categoria), formato, "Gestores")


@router.get("/setores/{categoria}/distribuicao")
def setor_distribuicao(categoria: str, metrica: str, carteira: bool = True):
    """Valores de todos os fundos da categoria para uma métrica (histograma), marcando carteira/watchlist."""
    if metrica not in catalogo.BY_KEY:
        raise HTTPException(400, "métrica inválida")
    u = cp.universo()
    u = u[(u.categoria == categoria) & (u.pl > 0) & (u.q_status.fillna("ok") != "erro")]
    with appdb.session() as s:
        listas = {}
        for r in s.execute("SELECT cnpj, tipo FROM lista"):
            listas.setdefault(r["cnpj"], []).append(r["tipo"])
    d = u[["cnpj", "nome", "pl", metrica]].rename(columns={metrica: "valor"}).dropna(subset=["valor"])
    d["listas"] = d.cnpj.map(lambda c: ",".join(listas.get(c, [])))
    return excel.json_safe(d)


# ------------------------------------------------------------------ qualidade (mercado)
@router.get("/qualidade/checks")
def qualidade_checks():
    return excel.json_safe(df("SELECT * FROM qualidade_check ORDER BY id"))


@router.get("/qualidade/resumo")
def qualidade_resumo(formato: str | None = None):
    d = df("""SELECT q.dt, q.id, count(*) AS n_fundos FROM qualidade q
              WHERE q.dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 24 MONTH
                AND q.dt <= (SELECT ultimo_mes_completo FROM _meta)
              GROUP BY ALL ORDER BY dt, id""")
    tot = df("""SELECT dt, count(*) AS n_informes, count(*) FILTER (WHERE status = 'erro') AS com_erro,
                       count(*) FILTER (WHERE status = 'alerta') AS com_alerta
                FROM qualidade_resumo WHERE dt > (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 24 MONTH
                  AND dt <= (SELECT ultimo_mes_completo FROM _meta) GROUP BY dt ORDER BY dt""")
    if formato == "xlsx":
        return _xlsx({"Por mês": tot, "Por checagem": d}, "qualidade")
    return {"por_checagem": excel.json_safe(d), "por_mes": excel.json_safe(tot)}


@router.get("/qualidade/fundos")
def qualidade_fundos(check: str | None = None, categoria: str | None = None, formato: str | None = None):
    conds, params_ = ["q.dt = (SELECT ultimo_mes_completo FROM _meta)"], []
    if check:
        conds.append("q.id = ?"); params_.append(check)
    if categoria:
        conds.append("c.categoria = ?"); params_.append(categoria)
    d = df(f"""SELECT q.cnpj, m.nome, c.categoria_nome, m.pl, q.id, k.severidade, k.descricao, q.valor
               FROM qualidade q JOIN qualidade_check k USING (id) JOIN metricas_mes m USING (cnpj, dt)
               JOIN classificacao c USING (cnpj)
               WHERE {' AND '.join(conds)} ORDER BY k.severidade, m.pl DESC""", params_)
    return _out(d, formato, "Fundos com falha")
