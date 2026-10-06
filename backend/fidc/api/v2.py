"""Rotas da v2: comparação com pares, qualidade dos dados, métricas da casa, stress, roteiro de DD,
parâmetros manuais, grupos de pares e contexto setorial (BCB, originadores, red flags)."""
from __future__ import annotations

import json
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
        "metricas": [{"metrica": k, "codigo": catalogo.codigo(k), "label": l, "fmt": f, "sentido": s, "bloco": b,
                      "definicao": d} for k, l, f, s, b, d in catalogo.METRICAS],
        "red_flags": [{"id": i, "codigo": catalogo.codigo(i), "nome": n, "regra": r} for i, n, r in catalogo.RED_FLAGS],
        "blocos": catalogo.BLOCOS,
        "parametros": [{"chave": k, "label": v[0], "fmt": v[1], "fonte": v[2], "uso": v[3]}
                       for k, v in rot["parametros"].items()],
    }


# ------------------------------------------------------------------ comparação
@router.get("/comparar/{cnpj}")
def comparar(cnpj: str, modo: str = "categoria", grupo_id: int | None = None, cnpjs: str | None = None,
             uma_por_gestora: bool = False, excluir_erro: bool = True, ignorar_sem_vencido: bool = True,
             formato: str | None = None):
    try:
        r = cp.comparar(cnpj, ignorar_sem_vencido=ignorar_sem_vencido,
                        **_pares_kw(modo, grupo_id, cnpjs, uma_por_gestora, excluir_erro))
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
                   ignorar_sem_vencido: bool = True, formato: str | None = None):
    try:
        d = cp.serie_vs_pares(cnpj, metrica, meses, ignorar_sem_vencido=ignorar_sem_vencido,
                              **_pares_kw(modo, grupo_id, cnpjs, uma_por_gestora, excluir_erro))
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


def _campos_extraidos(cnpj: str) -> list[dict]:
    """Parâmetros lidos do regulamento (IA prevalece sobre regras), com a data de entrega do documento."""
    try:
        return df("""SELECT c.campo, c.valor_num, c.valor_txt, c.trecho, c.pagina, c.fonte, r.data_entrega,
                            CASE WHEN c.fonte = 'ia' THEN i.confianca ELSE x.confianca END AS confianca
                     FROM regulamento_param c JOIN regulamento r USING (cnpj)
                     LEFT JOIN regulamento_ia i USING (cnpj)
                     LEFT JOIN regulamento_campo x ON x.cnpj = c.cnpj AND x.campo = c.campo
                     WHERE c.cnpj = ?""", [consultas.cnpj_digits(cnpj)]).to_dict("records")
    except Exception:  # noqa: BLE001 - base sem a tabela
        return []


def _fonte_reg(c: dict) -> str:
    pg = c.get("pagina")
    pg = f", p. {int(pg)}" if pg is not None and pd.notna(pg) else ""
    return ("regulamento (leitura IA" if c.get("fonte") == "ia" else "regulamento (extração automática") + pg + ")"


def _param_atual(cnpj: str) -> dict[str, dict]:
    """Valor manual (mais recente) e, na falta dele, o extraído automaticamente do regulamento."""
    out: dict[str, dict] = {}
    for p in params(cnpj):  # ordenado por competência desc: o primeiro de cada chave é o mais recente
        out.setdefault(p["chave"], p)
    for c in _campos_extraidos(cnpj):
        if c["campo"] not in out and (c["valor_num"] is not None and pd.notna(c["valor_num"]) or c["valor_txt"]):
            out[c["campo"]] = {"chave": c["campo"], "valor_num": c["valor_num"], "valor_txt": c["valor_txt"],
                               "fonte": _fonte_reg(c),
                               "data_base": (c.get("data_entrega") or "")[:10] or None, "auto": True}
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


TESES = [  # rótulo, sinais que somam a favor
    ("Consignado INSS", ["consig_inss"]), ("Consignado servidor público", ["consig_servidor"]),
    ("Consignado privado (CLT)", ["consig_privado"]), ("FGTS", ["fgts"]), ("Precatórios", ["precatorio"]),
    ("Duplicatas / recebíveis comerciais", ["duplicata", "cheque"]), ("Cartão", ["cartao"]),
    ("Veículos", ["veiculo"]), ("Imobiliário", ["imobiliario"]), ("Agro", ["agro"]), ("Judicial", ["judicial"]),
]


@router.get("/fundos/{cnpj}/regulamento/extraido")
def regulamento_extraido(cnpj: str):
    """Regulamento vigente no FNET lido por regras: campos com trecho e página, sinais da tese e divergência
    com a categoria atribuída pelo informe."""
    c = consultas.cnpj_digits(cnpj)
    try:
        doc = df("SELECT * FROM regulamento WHERE cnpj = ?", [c]).to_dict("records")
        sig = df("SELECT sinal, n FROM regulamento_sinal WHERE cnpj = ? ORDER BY n DESC", [c]).to_dict("records")
        evs = df("""SELECT campo, valor_num, valor_txt, trecho, pagina, 'regras' AS fonte, confianca FROM regulamento_campo
                    WHERE cnpj = ? AND campo LIKE 'eventos%'""", [c]).to_dict("records")
    except Exception:  # noqa: BLE001
        doc, sig, evs = [], [], []
    try:
        ia = df("SELECT * FROM regulamento_ia WHERE cnpj = ?", [c]).to_dict("records")
    except Exception:  # noqa: BLE001
        ia = []
    if ia:
        for k in ("eventos_avaliacao", "eventos_liquidacao"):
            ia[0][k] = json.loads(ia[0][k] or "[]")
    if not doc:
        return {"status": "nao_processado"}
    d = doc[0]
    manual = {p["chave"] for p in params(c)}
    pcat = yaml.safe_load(open(ROTEIROS_FILE, encoding="utf-8"))["parametros"]
    campos = []
    for x in _campos_extraidos(c) + evs:
        meta = pcat.get(x["campo"])
        campos.append({**x, "label": meta[0] if meta else x["campo"], "fmt": meta[1] if meta else "txt",
                       "parametro": bool(meta), "tem_manual": x["campo"] in manual})
    n = {s["sinal"]: s["n"] for s in sig}
    teses = sorted(((rot, sum(n.get(k, 0) for k in ks)) for rot, ks in TESES), key=lambda t: -t[1])
    teses = [{"tese": t, "mencoes": v} for t, v in teses if v > 0]
    doc_id = d.get("doc_id")
    return _clean({**d, "url_pdf": f"{config.FNET_BASE}/downloadDocumento?id={int(doc_id)}" if doc_id else None,
                   "url_ver": f"{config.FNET_BASE}/exibirDocumento?id={int(doc_id)}&cvm=true" if doc_id else None,
                   "campos": campos, "sinais": sig, "teses": teses, "ia": ia[0] if ia else None})


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
                                "fmt": "num" if fmt_p == "txt" else fmt_p, "fonte": p["fonte"], "data_base": p.get("data_base")}
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
def comite_xlsx(cnpj: str, modo: str = "categoria", grupo_id: int | None = None, uma_por_gestora: bool = False,
                excluir_erro: bool = True, ignorar_sem_vencido: bool = True):
    try:
        r = cp.comparar(cnpj, modo=modo, grupo_id=grupo_id, uma_por_gestora=uma_por_gestora,
                        excluir_erro=excluir_erro, ignorar_sem_vencido=ignorar_sem_vencido)
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


# ------------------------------------------------------------------ estrutura (regulamento) por categoria e mercado
REF_CHAVES = {  # chave: (rótulo, compara com a coluna do informe)
    "sub_min_senior": ("Subordinação mínima da sênior (% PL)", "subordinacao"),
    "jr_min_pl": ("Jr mínima (% PL)", "jr_pl"),
    "limite_maior_cedente": ("Limite do maior cedente (% PL)", None),
    "limite_maior_sacado": ("Limite do maior sacado (% PL)", None),
}


class RefIn(BaseModel):
    chave: str
    valor_num: float | None = None
    fonte: str | None = None


def _refs(categoria: str | None = None) -> dict[tuple[str, str], dict]:
    with appdb.session() as s:
        q = "SELECT * FROM categoria_ref" + (" WHERE categoria = ?" if categoria else "")
        return {(r["categoria"], r["chave"]): dict(r) for r in s.execute(q, [categoria] if categoria else [])}


@router.get("/categorias/{categoria}/referencia")
def get_referencia(categoria: str):
    refs = _refs(categoria)
    est = estrutura(categoria)
    out = []
    for k, (label, _) in REF_CHAVES.items():
        vals = est[f"{k}_fundo"].dropna() if f"{k}_fundo" in est else pd.Series(dtype=float)
        r = refs.get((categoria, k)) or {}
        out.append({"chave": k, "label": label, "valor_num": r.get("valor_num"), "fonte": r.get("fonte"),
                    "autor": r.get("autor"), "atualizado_em": r.get("atualizado_em"),
                    "n_regulamentos": int(len(vals)), "p25": vals.quantile(.25) if len(vals) else None,
                    "mediana": vals.median() if len(vals) else None, "p75": vals.quantile(.75) if len(vals) else None})
    return _clean(out)


@router.put("/categorias/{categoria}/referencia")
def set_referencia(categoria: str, r: RefIn, request: Request):
    if r.chave not in REF_CHAVES:
        raise HTTPException(400, "chave inválida")
    with appdb.session() as s:
        if r.valor_num is None:
            s.execute("DELETE FROM categoria_ref WHERE categoria = ? AND chave = ?", [categoria, r.chave])
        else:
            s.execute("""INSERT INTO categoria_ref (categoria, chave, valor_num, fonte, autor) VALUES (?,?,?,?,?)
                         ON CONFLICT (categoria, chave) DO UPDATE SET valor_num = excluded.valor_num,
                         fonte = excluded.fonte, autor = excluded.autor, atualizado_em = datetime('now')""",
                      [categoria, r.chave, r.valor_num, r.fonte, _usuario(request)])
    return {"ok": True}


def estrutura(categoria: str | None = None) -> pd.DataFrame:
    """Por fundo: estrutura atual (informe) x mínimos/limites. Fonte do mínimo: manual > IA > regras >
    referência da categoria."""
    u = cp.universo()
    u = u[(u.pl > 0)]
    if categoria:
        u = u[u.categoria == categoria]
    base = u[["cnpj", "nome", "gestor", "categoria", "categoria_nome", "pl", "subordinacao", "jr_pl",
              "top1_cedente_pct", "q_status"]].copy()
    chaves = list(REF_CHAVES)
    try:
        reg = df(f"""SELECT cnpj, campo, valor_num, fonte FROM regulamento_param
                     WHERE campo IN ({','.join('?' * len(chaves))}) AND valor_num IS NOT NULL""", chaves)
    except Exception:  # noqa: BLE001
        reg = pd.DataFrame(columns=["cnpj", "campo", "valor_num", "fonte"])
    with appdb.session() as s:
        man = pd.DataFrame([dict(r) for r in s.execute(
            f"""SELECT cnpj, chave AS campo, valor_num FROM fundo_param WHERE chave IN ({','.join('?' * len(chaves))})
                AND valor_num IS NOT NULL ORDER BY competencia DESC""", chaves)], columns=["cnpj", "campo", "valor_num"])
    man = man.drop_duplicates(["cnpj", "campo"]).assign(fonte="manual")
    todos = pd.concat([man, reg], ignore_index=True).drop_duplicates(["cnpj", "campo"])   # manual primeiro
    refs = _refs(categoria)
    for k, (_, col) in REF_CHAVES.items():
        t = todos[todos.campo == k].set_index("cnpj")
        base[f"{k}_fundo"] = base.cnpj.map(t.valor_num)
        base[f"{k}_fonte"] = base.cnpj.map(t.fonte)
        ref = base.categoria.map(lambda c, k=k: (refs.get((c, k)) or {}).get("valor_num"))
        base[k] = base[f"{k}_fundo"].where(base[f"{k}_fundo"].notna(), ref)
        base.loc[base[f"{k}_fundo"].isna() & ref.notna(), f"{k}_fonte"] = "referência da categoria"
        if col:
            base[f"folga_{k}"] = base[col] - base[k]
    base["top1_cedente_frac"] = base.top1_cedente_pct / 100

    def status(r):
        f = r.get("folga_sub_min_senior")
        if f is None or pd.isna(f):
            return "sem mínimo"
        return "abaixo do mínimo" if f < 0 else "folga < 3 p.p." if f < 0.03 else "ok"
    base["status_sub"] = base.apply(status, axis=1)
    return base.sort_values("pl", ascending=False)


@router.get("/setores/{categoria}/estrutura")
def setor_estrutura(categoria: str, formato: str | None = None):
    d = estrutura(None if categoria == "todas" else categoria)
    return _out(d, formato, "Estrutura x regulamento",
                "Mínimo por fundo: manual > leitura IA > leitura por regras > referência da categoria. "
                "Maior cedente do informe (% da carteira) é comparado ao limite do regulamento (% do PL): aproximação.")


@router.get("/mercado/estrutura")
def mercado_estrutura(formato: str | None = None):
    d = estrutura(None)
    d = d[d.q_status.fillna("ok") != "erro"]
    g = d.groupby(["categoria", "categoria_nome"])
    out = g.agg(n_fundos=("cnpj", "size"), n_com_minimo=("sub_min_senior", lambda x: int(x.notna().sum())),
                sub_min_p25=("sub_min_senior_fundo", lambda x: x.quantile(.25)),
                sub_min_mediana=("sub_min_senior_fundo", "median"),
                sub_min_p75=("sub_min_senior_fundo", lambda x: x.quantile(.75)),
                subordinacao_mediana=("subordinacao", "median"),
                folga_mediana=("folga_sub_min_senior", "median"),
                n_abaixo=("status_sub", lambda x: int((x == "abaixo do mínimo").sum())),
                n_folga_3pp=("status_sub", lambda x: int((x == "folga < 3 p.p.").sum())),
                jr_min_mediana=("jr_min_pl_fundo", "median")).reset_index()
    refs = _refs()
    out["sub_min_referencia"] = out.categoria.map(lambda c: (refs.get((c, "sub_min_senior")) or {}).get("valor_num"))
    pl_abaixo = d[d.status_sub == "abaixo do mínimo"].groupby("categoria").pl.sum()
    out["pl_abaixo"] = out.categoria.map(pl_abaixo).fillna(0)
    return _out(out.sort_values("n_fundos", ascending=False), formato, "Estrutura por categoria")
