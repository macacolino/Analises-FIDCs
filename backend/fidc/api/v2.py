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

from .. import appdb, catalogo, comparacao as cp, config, consultas, excel, mensal
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
        "red_flags": [{"id": i, "codigo": catalogo.codigo(i), "nome": n, "regra": r, "definicao": catalogo.RF_DEFINICAO.get(i)} for i, n, r in catalogo.RED_FLAGS],
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


@router.get("/fundos/{cnpj}/mensal")
def fundo_mensal(cnpj: str, meses: int = 60, formato: str | None = None):
    """Resumo mês a mês (informe CVM) com rentabilidade por série ajustada por amortização."""
    c = consultas.cnpj_digits(cnpj)
    if formato == "xlsx":
        notas = {"Resumo mensal": "Fonte: informe mensal CVM. Rentabilidade por série: informada pelo administrador ou, "
                                  "quando ela não considera a amortização do mês, recalculada (estimativa).",
                 "Rentab. por série": "rentab = valor usado; ajuste_amortizacao = verdadeiro quando foi recalculada "
                                      "com a amortização do tipo de cota (Tab. X.4) dividida pelas cotas do tipo."}
        return _xlsx(mensal.planilhas(c, meses), f"mensal_{c}", notas)
    t = mensal.tabela(c, meses)
    return {"meses": excel.json_safe(t["meses"]), "series": t["series"], "janelas": excel.json_safe(t["janelas"])}


SEG_NOMES = {
    "A": "Industrial", "B": "Imobiliário", "C1": "Comercial", "C2": "Varejo", "C3": "Arrendamento", "D1": "Serviços",
    "D2": "Serviços públicos", "D3": "Educação", "D4": "Entretenimento", "E": "Agronegócio", "F1": "Crédito pessoal",
    "F2": "Consignado", "F3": "Corporativo", "F4": "Middle market", "F5": "Veículos", "F6": "Imob. empresarial",
    "F7": "Imob. residencial", "F8": "Financeiro - outros", "G": "Cartão de crédito", "H1": "Factoring PF",
    "H2": "Factoring PJ", "I1": "Precatórios", "I2": "Tributário", "I3": "Royalties", "I4": "Setor público - outros",
    "J": "Ações judiciais", "K": "Marcas/PI"}


@router.get("/fundos/{cnpj}/lamina-extra")
def lamina_extra(cnpj: str):
    """Complementos da lâmina em PDF: parâmetros do regulamento (manual > IA > regras), segmentos da carteira (Tab. II)
    e leitura do regulamento por IA."""
    c = consultas.cnpj_digits(cnpj)
    pcat = yaml.safe_load(open(ROTEIROS_FILE, encoding="utf-8"))["parametros"]
    par = []
    for k, p in _param_atual(c).items():
        meta = pcat.get(k)
        if not meta or k.startswith("eventos"):
            continue
        v = p.get("valor_num")
        par.append({"chave": k, "label": meta[0], "fmt": meta[1],
                    "valor_num": None if v is None or pd.isna(v) else float(v), "valor_txt": p.get("valor_txt"),
                    "fonte": p.get("fonte"), "manual": not p.get("auto")})
    seg = df(f"""SELECT {', '.join(f'seg_{k}' for k in SEG_NOMES)}, seg_total FROM fundo_mes
                 WHERE cnpj = ? ORDER BY dt DESC LIMIT 1""", [c])
    segs = []
    if not seg.empty:
        r = seg.iloc[0]
        tot = sum(max(float(r[f"seg_{k}"] or 0), 0) for k in SEG_NOMES)
        if tot > 0:
            segs = sorted(({"segmento": n, "pct": max(float(r[f"seg_{k}"] or 0), 0) / tot}
                           for k, n in SEG_NOMES.items() if (r[f"seg_{k}"] or 0) > 0), key=lambda x: -x["pct"])
    try:
        ia = df("SELECT tese, lastro, consignado, foco_precatorio, precatorio_alimentar, confianca, observacoes, "
                "processado_em FROM regulamento_ia WHERE cnpj = ?", [c]).to_dict("records")
    except Exception:  # noqa: BLE001
        ia = []
    try:
        doc = df("SELECT data_entrega, url_ver FROM regulamento WHERE cnpj = ?", [c]).to_dict("records")
    except Exception:  # noqa: BLE001
        doc = []
    return _clean({"parametros": par, "segmentos": segs, "ia": ia[0] if ia else None, "regulamento": doc[0] if doc else None})


@router.get("/pdd/administradores")
def pdd_administradores(formato: str | None = None):
    """Régua de PDD praticada por administrador (informe mensal) e, quando lida, a política das demonstrações."""
    d = df("SELECT * FROM pdd_admin ORDER BY pl DESC")
    try:
        pol = df("SELECT * FROM pdd_politica_admin")
        d = d.merge(pol, on="admin", how="left")
    except Exception:  # noqa: BLE001 - política ainda não extraída
        pass
    return _out(d, formato, "PDD por administrador",
                "PDD ÷ régua 2.682 = PDD declarada / (1% 1-30d, 3% 31-60, 10% 61-90, 30% 91-120, 50% 121-150, 70% 151-180, "
                "100% >180 sobre as parcelas vencidas do informe). Curva implícita: % por faixa que melhor explica a PDD "
                "declarada nos fundos do administrador em 12 meses (estimativa).")


@router.get("/pdd/fundos")
def pdd_fundos(admin: str | None = None, formato: str | None = None):
    d = df("SELECT * FROM pdd_fundo WHERE (? IS NULL OR admin = ?) ORDER BY pl DESC", [admin, admin])
    try:
        pol = df("SELECT cnpj, metodo, faixas_txt, efeito_vagao, provisao_inicial, data_df FROM pdd_politica")
        d = d.merge(pol, on="cnpj", how="left")
    except Exception:  # noqa: BLE001
        pass
    return _out(d, formato, "PDD por fundo")


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


# ------------------------------------------------------------------ comparativo por estratégia (ex.: precatórios)
COMP_PARAMS = ["taxa_gestao", "taxa_administracao", "taxa_performance", "taxa_minima_cessao", "benchmark_senior"]


def comparativo(categorias: list[str]) -> pd.DataFrame:
    """Uma linha por fundo: rentabilidade 12m por tipo de cota (informe), remuneração implícita vs CDI,
    estrutura, subordinação, taxas e benchmark (regulamento: manual > IA > regras) e foco do lastro."""
    ph = ",".join("?" * len(categorias))
    base = df(f"""
        WITH ult AS (SELECT ultimo_mes_completo AS dt FROM _meta),
        -- último informe de cada fundo com séries (até 3 meses de atraso), não só o mês de referência
        uf AS (
          SELECT s.cnpj, max(s.dt) AS dt FROM serie_mes s JOIN fundo f USING (cnpj)
          WHERE f.categoria IN ({ph}) AND s.pl_serie > 1000
            AND s.dt BETWEEN (SELECT dt FROM ult) - INTERVAL 3 MONTH AND (SELECT dt FROM ult)
          GROUP BY s.cnpj),
        -- rentabilidade mês a mês, sem depender do nome da série (administradores renomeiam séries)
        mes AS (
          SELECT s.cnpj, s.dt,
                 arg_max(s.rentab_mes, s.pl_serie) AS r_maior,
                 sum(s.rentab_mes * s.pl_serie) FILTER (WHERE s.tipo = 'senior')
                   / nullif(sum(s.pl_serie) FILTER (WHERE s.tipo = 'senior'), 0) AS r_sen,
                 sum(s.rentab_mes * s.pl_serie) FILTER (WHERE s.tipo = 'mezanino')
                   / nullif(sum(s.pl_serie) FILTER (WHERE s.tipo = 'mezanino'), 0) AS r_mez,
                 sum(s.rentab_mes * s.pl_serie) FILTER (WHERE s.tipo = 'subordinada')
                   / nullif(sum(s.pl_serie) FILTER (WHERE s.tipo = 'subordinada'), 0) AS r_sub
          FROM serie_mes s JOIN uf USING (cnpj)
          WHERE s.dt > uf.dt - INTERVAL 12 MONTH AND s.dt <= uf.dt AND s.pl_serie > 1000
            AND s.rentab_mes BETWEEN -60 AND 60   -- fora disso é erro de preenchimento
          GROUP BY ALL),
        agg AS (
          -- 12 meses; com 6 a 11 meses de histórico, anualizado
          SELECT m.cnpj,
                 (SELECT count(*) FROM serie_mes z WHERE z.cnpj = m.cnpj AND z.dt = any_value(uf.dt)
                    AND z.pl_serie > 1000) AS n_series_pl,
                 CASE WHEN count(r_maior) >= 6 THEN exp(sum(ln(1 + r_maior / 100)) * 12.0 / count(r_maior)) - 1 END AS r12_unica,
                 CASE WHEN count(r_sen) >= 6 THEN exp(sum(ln(1 + r_sen / 100)) * 12.0 / count(r_sen)) - 1 END AS r12_senior,
                 CASE WHEN count(r_mez) >= 6 THEN exp(sum(ln(1 + r_mez / 100)) * 12.0 / count(r_mez)) - 1 END AS r12_mezanino,
                 CASE WHEN count(r_sub) >= 6 THEN exp(sum(ln(1 + r_sub / 100)) * 12.0 / count(r_sub)) - 1 END AS r12_sub,
                 count(r_maior) AS meses_rentab
          FROM mes m JOIN uf USING (cnpj) GROUP BY m.cnpj),
        seg AS (
          SELECT cnpj, coalesce(seg_I1, 0) / nullif(""" + " + ".join(f"coalesce(seg_{x}, 0)" for x in
                 ["A", "B", "C1", "C2", "C3", "D1", "D2", "D3", "D4", "E", "F1", "F2", "F3", "F4", "F5", "F6", "F7",
                  "F8", "G", "H1", "H2", "I1", "I2", "I3", "I4", "J", "K"]) + f""", 0) AS pct_precatorios
          FROM fundo_mes JOIN uf USING (cnpj, dt))
        SELECT f.cnpj, f.nome, f.gestor, f.admin, f.categoria, f.categoria_nome, f.pl, a.n_series_pl,
               a.r12_unica, a.r12_senior, a.r12_mezanino, a.r12_sub, a.meses_rentab, k.cdi_12m, g.pct_precatorios,
               uf.dt AS dt_informe
        FROM fundo f LEFT JOIN agg a USING (cnpj) LEFT JOIN uf USING (cnpj) LEFT JOIN seg g USING (cnpj)
        LEFT JOIN cdi_mes k ON k.dt = coalesce(uf.dt, (SELECT dt FROM ult))
        WHERE f.categoria IN ({ph}) AND f.pl > 0
          AND f.ultimo_informe >= (SELECT dt FROM ult) - INTERVAL 3 MONTH""", categorias + categorias)
    if base.empty:
        return base
    for c in ("r12_unica", "r12_senior", "r12_mezanino", "r12_sub"):
        base[c] = base[c].where(base[c].between(-0.9, 3))
    base["estrutura"] = base.n_series_pl.map(lambda n: "cota única" if n == 1 else "sênior + subordinada" if n and n > 1 else None)
    unica = base.estrutura == "cota única"
    base["rentab_12m_cota_unica"] = base.r12_unica.where(unica)
    base["rentab_12m_senior"] = base.r12_senior.where(~unica)
    base["rentab_12m_mezanino"] = base.r12_mezanino.where(~unica)
    base["rentab_12m_subordinada"] = base.r12_sub.where(~unica)
    ref = base.rentab_12m_cota_unica.where(unica, base.rentab_12m_senior)
    base["spread_cdi_12m"] = (1 + ref) / (1 + base.cdi_12m) - 1        # CDI + x (composto)
    base["pct_cdi_12m"] = ref / base.cdi_12m
    u = cp.universo()[["cnpj", "subordinacao", "jr_pl", "over90_carteira", "q_status"]]
    base = base.merge(u, on="cnpj", how="left")
    # parâmetros do regulamento: manual > IA > regras
    try:
        reg = df(f"""SELECT cnpj, campo, valor_num, valor_txt, fonte FROM regulamento_param
                     WHERE campo IN ({','.join('?' * len(COMP_PARAMS))}) AND cnpj IN (SELECT cnpj FROM fundo
                     WHERE categoria IN ({ph}))""", COMP_PARAMS + categorias)
        ia = df(f"""SELECT cnpj, benchmark_senior AS bench_ia, foco_precatorio, precatorio_alimentar
                    FROM regulamento_ia""")
        sig = df("""SELECT cnpj, sum(n) FILTER (WHERE sinal = 'prec_federal') AS f,
                           sum(n) FILTER (WHERE sinal = 'prec_estadual') AS e,
                           sum(n) FILTER (WHERE sinal = 'prec_alimentar') AS a
                    FROM regulamento_sinal GROUP BY cnpj""")
    except Exception:  # noqa: BLE001
        reg = pd.DataFrame(columns=["cnpj", "campo", "valor_num", "valor_txt", "fonte"])
        ia = pd.DataFrame(columns=["cnpj", "bench_ia", "foco_precatorio", "precatorio_alimentar"])
        sig = pd.DataFrame(columns=["cnpj", "f", "e", "a"])
    with appdb.session() as s:
        man = pd.DataFrame([dict(r) for r in s.execute(
            f"""SELECT cnpj, chave AS campo, valor_num, valor_txt FROM fundo_param WHERE chave IN
                ({','.join('?' * len(COMP_PARAMS))}) ORDER BY competencia DESC""", COMP_PARAMS)],
            columns=["cnpj", "campo", "valor_num", "valor_txt"]).drop_duplicates(["cnpj", "campo"]).assign(fonte="manual")
    todos = pd.concat([man, reg], ignore_index=True).drop_duplicates(["cnpj", "campo"])
    for k in COMP_PARAMS:
        t = todos[todos.campo == k].set_index("cnpj")
        col = "valor_txt" if k == "benchmark_senior" else "valor_num"
        base[k] = base.cnpj.map(t[col])
        base[f"{k}_fonte"] = base.cnpj.map(t.fonte)
    base = base.merge(ia, on="cnpj", how="left").merge(sig, on="cnpj", how="left")
    base["benchmark_senior"] = base.benchmark_senior.where(base.benchmark_senior.notna(), base.bench_ia)

    def foco(r):
        if isinstance(r.foco_precatorio, str) and r.foco_precatorio != "nao_se_aplica":
            return {"federal": "federal", "estadual_municipal": "estadual/municipal", "misto": "misto"}[r.foco_precatorio]
        f = r.f if r.f is not None and not pd.isna(r.f) else 0
        e = r.e if r.e is not None and not pd.isna(r.e) else 0
        if f >= 2 and f > e:
            return "federal (regras)"
        if e >= 2 and e > f:
            return "estadual/municipal (regras)"
        return None
    base["foco"] = base.apply(foco, axis=1)

    def alim(r):
        v = r.precatorio_alimentar
        if v is not None and not pd.isna(v):
            return "sim" if bool(v) else "não"
        a = r.a if r.a is not None and not pd.isna(r.a) else 0
        return "provável (regras)" if a >= 2 else None
    base["alimentar"] = base.apply(alim, axis=1)
    cols = ["cnpj", "nome", "gestor", "categoria_nome", "pl", "dt_informe", "foco", "alimentar", "pct_precatorios", "estrutura",
            "rentab_12m_cota_unica", "rentab_12m_senior", "spread_cdi_12m", "pct_cdi_12m", "rentab_12m_mezanino",
            "rentab_12m_subordinada", "meses_rentab", "cdi_12m", "subordinacao", "jr_pl", "benchmark_senior", "taxa_gestao",
            "taxa_administracao", "taxa_performance", "taxa_minima_cessao", "over90_carteira", "q_status", "admin",
            "taxa_gestao_fonte", "taxa_minima_cessao_fonte"]
    return base[cols].sort_values("pl", ascending=False)


@router.get("/comparativo")
def comparativo_api(categorias: str = "precatorios_federais,precatorios", formato: str | None = None):
    d = comparativo([c for c in categorias.split(",") if c])
    return _out(d, formato, "Comparativo",
                "Rentabilidade 12m: informe CVM (Tab. X.3), séries com 12 meses e PL. Remuneração vs CDI = "
                "(1 + rentab. 12m) / (1 + CDI 12m) − 1, sobre a cota única ou a sênior. Taxas, benchmark e taxa mínima "
                "de cessão: regulamento (manual > leitura IA > leitura por regras); benchmark costuma estar no "
                "suplemento da série e pode faltar.")


# ------------------------------------------------------------------ novas oportunidades (captação)
@router.get("/oportunidades/mercado")
def oportunidades_mercado(meses: int = 24, formato: str | None = None):
    from .. import oportunidades as op
    r = op.mercado(meses)
    if formato == "xlsx":
        return _xlsx({"Por categoria": r["resumo"], "Série mensal": r["serie"], "Total": r["total"],
                      "Excluídos (erro)": r["excluidos"]}, "captacao_mercado")
    return _clean({"serie": excel.json_safe(r["serie"]), "resumo": excel.json_safe(r["resumo"]),
                   "total": excel.json_safe(r["total"]), "n_excluidos": len(r["excluidos"])})


@router.get("/oportunidades/fundos")
def oportunidades_fundos(meses: int = 3, categoria: str | None = None, formato: str | None = None):
    from .. import oportunidades as op
    return _out(op.fundos(meses, categoria or None), formato, "Fundos captando",
                "Captação da Tab. X.4 (todas as classes); registros com captação > 1,5x o PL + resgates + amortizações "
                "excluídos como erro de preenchimento.")


@router.get("/oportunidades/ofertas")
def oportunidades_ofertas(dias: int = 90, categoria: str | None = None, formato: str | None = None):
    from .. import oportunidades as op
    return _out(op.ofertas(dias, categoria or None), formato, "Ofertas registradas",
                "Ofertas de cotas de FIDC na CVM (dados abertos, atualização diária). Valor registrado = teto da oferta, "
                "não o captado; o captado aparece depois na Tab. X.4 do informe.")


@router.get("/oportunidades/novos")
def oportunidades_novos(meses: int = 6, formato: str | None = None):
    from .. import oportunidades as op
    return _out(op.novos(meses), formato, "Fundos novos")
