"""API do Analisador de FIDCs.

Toda rota de tabela aceita ?formato=xlsx para baixar em Excel.
Com FIDC_SENHA definida, tudo exige a senha única do time (acesso.py); sem ela, fica aberto (uso local).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import appdb, comparacao, config, consultas, dicionario, excel, fnet
from . import acesso, v2
from ..etl import pipeline
from ..taxonomy import classify

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app):
    from .. import persistencia
    log.info("persistência do app.sqlite: %s", persistencia.baixar())   # antes de qualquer acesso ao app.sqlite
    try:
        comparacao.seed_grupos()
    except Exception:  # noqa: BLE001 - seed é conveniência
        log.exception("falha ao carregar grupos iniciais")
    if os.environ.get("FIDC_AGENDADOR", "1") == "1":
        threading.Thread(target=_agendador, daemon=True).start()
        threading.Thread(target=_agendador_regulamentos, daemon=True).start()
    yield


app = FastAPI(title="Analisador de FIDCs", version="0.1.0", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=2000)
app.middleware("http")(acesso.middleware)

ETL_STATUS: dict = {"rodando": False, "ultimo": None}


def _usuario(request: Request) -> str | None:
    # Preparado para quando houver login na borda (Cloudflare Access envia este header)
    return request.headers.get("Cf-Access-Authenticated-User-Email") or request.headers.get("X-Usuario")


def _out(data: pd.DataFrame, formato: str | None, nome: str, nota: str | None = None):
    if formato == "xlsx":
        content = excel.to_xlsx({nome: data}, {nome: nota} if nota else None)
        fname = f"{nome.lower().replace(' ', '_')}_{datetime.now():%Y%m%d}.xlsx"
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})
    return excel.json_safe(data)


def _jsonable(obj):
    if isinstance(obj, pd.DataFrame):
        return excel.json_safe(obj)
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()[:10]
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if isinstance(obj, float) and obj != obj:
        return None
    if hasattr(obj, "item"):  # numpy
        v = obj.item()
        return None if isinstance(v, float) and v != v else v
    return obj


# ------------------------------------------------------------------ meta
@app.get("/api/meta")
def meta():
    from .. import persistencia
    return {**consultas.meta(), "etl": ETL_STATUS, "persistencia": persistencia.ESTADO}


@app.get("/api/dicionario")
def dic():
    return dicionario.as_json()


# ------------------------------------------------------------------ fundos
@app.get("/api/fundos")
def fundos(q: str = "", categoria: str | None = None, grupo: str | None = None,
           ativos: bool = True, limit: int = Query(50, le=5000), formato: str | None = None):
    return _out(consultas.buscar(q, categoria, grupo, ativos, limit), formato, "Fundos")


@app.get("/api/fundos/{cnpj}")
def fundo(cnpj: str):
    d = consultas.lamina(cnpj)
    if d is None:
        raise HTTPException(404, "Fundo não encontrado")
    return _jsonable(d)


@app.get("/api/fundos/{cnpj}/historico")
def fundo_hist(cnpj: str, meses: int = 60, formato: str | None = None):
    return _out(consultas.historico(cnpj, meses), formato, "Histórico")


@app.get("/api/fundos/{cnpj}/series")
def fundo_series(cnpj: str, formato: str | None = None):
    return _out(consultas.series_fundo(consultas.cnpj_digits(cnpj)), formato, "Séries")


@app.get("/api/fundos/{cnpj}/eventos")
def fundo_eventos(cnpj: str, todos: bool = False):
    d = fnet.documentos(cnpj)
    if not todos:
        d = {**d, "documentos": [x for x in d["documentos"] if x["categoria"] in fnet.EVENTOS]}
    return d


@app.get("/api/fundos/{cnpj}/lamina.xlsx")
def fundo_lamina_xlsx(cnpj: str):
    d = consultas.lamina(cnpj)
    if d is None:
        raise HTTPException(404, "Fundo não encontrado")
    cab = pd.DataFrame([{"campo": k, "valor": v} for k, v in d["cabecalho"].items()])
    kpis = pd.DataFrame([{"indicador": dicionario.label(k), "valor": v, "formato": dicionario.fmt(k)}
                         for k, v in d["kpis"].items()])
    comp = pd.DataFrame(d["comparativo"])
    if not comp.empty:
        comp.insert(0, "indicador", comp["metrica"].map(dicionario.label))
    sheets = {"Cadastro": cab, "Indicadores": kpis, "Vs categoria": comp, "Séries": d["series"],
              "Cedentes": d["cedentes"], "Aging": pd.DataFrame(d["aging"]),
              "Alertas": pd.DataFrame(d["alertas"]), "Histórico": consultas.historico(cnpj, 120)}
    content = excel.to_xlsx(sheets)
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="lamina_{consultas.cnpj_digits(cnpj)}.xlsx"'})


class CategoriaIn(BaseModel):
    categoria: str
    motivo: str | None = None


@app.put("/api/fundos/{cnpj}/categoria")
def set_categoria(cnpj: str, body: CategoriaIn, request: Request, bg: BackgroundTasks):
    ids = {c.id for c in classify.load_taxonomy() if not c.alias_de and not c.usar_tese_ia}
    if body.categoria not in ids:
        raise HTTPException(400, "Categoria inexistente")
    with appdb.session() as s:
        s.execute("""INSERT INTO override_categoria (cnpj, categoria, autor, motivo) VALUES (?, ?, ?, ?)
                     ON CONFLICT (cnpj) DO UPDATE SET categoria = excluded.categoria, autor = excluded.autor,
                     motivo = excluded.motivo, atualizado_em = datetime('now')""",
                  [consultas.cnpj_digits(cnpj), body.categoria, _usuario(request), body.motivo])
    bg.add_task(_run_etl, False)
    return {"ok": True, "aviso": "Reclassificação em andamento (~30s)"}


@app.delete("/api/fundos/{cnpj}/categoria")
def del_categoria(cnpj: str, bg: BackgroundTasks):
    with appdb.session() as s:
        s.execute("DELETE FROM override_categoria WHERE cnpj = ?", [consultas.cnpj_digits(cnpj)])
    bg.add_task(_run_etl, False)
    return {"ok": True}


class NotaIn(BaseModel):
    texto: str
    autor: str | None = None


@app.post("/api/fundos/{cnpj}/notas")
def add_nota(cnpj: str, body: NotaIn, request: Request):
    with appdb.session() as s:
        s.execute("INSERT INTO nota (cnpj, texto, autor) VALUES (?, ?, ?)",
                  [consultas.cnpj_digits(cnpj), body.texto, body.autor or _usuario(request)])
    return {"ok": True}


@app.delete("/api/notas/{nota_id}")
def del_nota(nota_id: int):
    with appdb.session() as s:
        s.execute("DELETE FROM nota WHERE id = ?", [nota_id])
    return {"ok": True}


# ------------------------------------------------------------------ setores e mercado
@app.get("/api/categorias")
def categorias(formato: str | None = None):
    return _out(consultas.categorias(), formato, "Categorias")


@app.get("/api/mercado/historico")
def mercado_hist(formato: str | None = None):
    return _out(consultas.mercado_historico(), formato, "Mercado",
                "PL somado inclui FIC-FIDC (há dupla contagem com os FIDCs investidos)")


@app.get("/api/setores/{categoria}")
def setor(categoria: str):
    return _jsonable({
        "historico": consultas.setor_historico(categoria),
        "aging": consultas.setor_aging(categoria),
    })


@app.get("/api/setores/{categoria}/ranking")
def setor_ranking(categoria: str, formato: str | None = None):
    cat = None if categoria == "todas" else categoria
    return _out(consultas.setor_ranking(cat), formato, "Ranking fundos")


@app.get("/api/setores/{categoria}/safra")
def setor_safra(categoria: str, metrica: str = "inad_90", formato: str | None = None):
    try:
        d = consultas.safra_fundos(categoria, metrica)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return _out(d, formato, "Safra de fundos")


@app.get("/api/ranking/series")
def ranking_series(categoria: str | None = None, tipo: str | None = None, pl_min: float = 0,
                   limit: int = Query(500, le=20000), formato: str | None = None):
    d = consultas.ranking_series(categoria, tipo, pl_min=pl_min).head(limit)
    return _out(d, formato, "Ranking séries",
                "Rentabilidade informada pelo administrador à CVM (Tab. X.3); 12m só para séries com 12 meses completos")


# ------------------------------------------------------------------ carteira / watchlist
TIPOS = ("carteira", "watchlist")


class ItemLista(BaseModel):
    cnpj: str
    tese: str | None = None


@app.get("/api/listas/{tipo}")
def lista(tipo: str, formato: str | None = None):
    if tipo not in TIPOS:
        raise HTTPException(404)
    return _out(consultas.painel(tipo), formato, tipo.capitalize())


@app.post("/api/listas/{tipo}")
def lista_add(tipo: str, item: ItemLista, request: Request):
    if tipo not in TIPOS:
        raise HTTPException(404)
    with appdb.session() as s:
        s.execute("""INSERT INTO lista (cnpj, tipo, adicionado_por, tese) VALUES (?, ?, ?, ?)
                     ON CONFLICT (cnpj, tipo) DO UPDATE SET tese = coalesce(excluded.tese, lista.tese)""",
                  [consultas.cnpj_digits(item.cnpj), tipo, _usuario(request), item.tese])
    return {"ok": True}


@app.delete("/api/listas/{tipo}/{cnpj}")
def lista_del(tipo: str, cnpj: str):
    with appdb.session() as s:
        s.execute("DELETE FROM lista WHERE tipo = ? AND cnpj = ?", [tipo, consultas.cnpj_digits(cnpj)])
    return {"ok": True}


@app.get("/api/listas/{tipo}/relatorio.xlsx")
def lista_relatorio(tipo: str):
    if tipo not in TIPOS:
        raise HTTPException(404)
    sheets = consultas.relatorio_lista(tipo)
    content = excel.to_xlsx(sheets, {"Resumo": f"{tipo.capitalize()} - referência {consultas.ref_month()}"})
    return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="relatorio_{tipo}_{datetime.now():%Y%m}.xlsx"'})


@app.get("/api/listas/{tipo}/eventos")
def lista_eventos(tipo: str, dias: int = 60):
    """Eventos FNET recentes de todos os fundos da lista (fatos relevantes, assembleias etc.)."""
    corte = (datetime.now() - timedelta(days=dias)).isoformat()
    out = []
    for item in consultas.lista_cnpjs(tipo):
        for e in fnet.eventos(item["cnpj"]):
            if (e["data_entrega"] or "") >= corte:
                out.append({**e, "cnpj": item["cnpj"]})
    return sorted(out, key=lambda e: e["data_entrega"] or "", reverse=True)


# ------------------------------------------------------------------ taxonomia e ETL
@app.get("/api/taxonomia")
def taxonomia():
    return [{"id": c.id, "nome": c.nome, "grupo": c.grupo} for c in classify.load_taxonomy() if not c.alias_de and not c.usar_tese_ia]


def _run_etl(download: bool = True):
    ETL_STATUS["rodando"] = True
    t0 = time.time()
    try:
        r = pipeline.run(download=download)
        ETL_STATUS["ultimo"] = {"fim": datetime.now().isoformat(), "segundos": round(time.time() - t0), **r}
    except Exception as e:  # noqa: BLE001
        log.exception("ETL falhou")
        ETL_STATUS["ultimo"] = {"fim": datetime.now().isoformat(), "status": "erro", "erro": str(e)}
    finally:
        ETL_STATUS["rodando"] = False


@app.post("/api/admin/etl")
def etl(bg: BackgroundTasks, download: bool = True):
    if ETL_STATUS["rodando"]:
        return {"status": "ja_em_execucao"}
    bg.add_task(_run_etl, download)
    return {"status": "iniciado"}


def _agendador():
    """Roda o ETL todo dia no horário FIDC_ETL_HORA (padrão 7h). A CVM republica ao longo do mês."""
    hora = int(os.environ.get("FIDC_ETL_HORA", "7"))
    while True:
        agora = datetime.now()
        prox = agora.replace(hour=hora, minute=0, second=0, microsecond=0)
        if prox <= agora:
            prox += timedelta(days=1)
        time.sleep((prox - agora).total_seconds())
        _run_etl(True)
        _bimestral()


def _agendador_regulamentos():
    """Regulamentos de madrugada (FIDC_REGULAMENTOS_HORA, padrão 3h): baixa e lê por regras os regulamentos novos
    (até FIDC_REGULAMENTOS_LIMITE, padrão 300) e, se houver ANTHROPIC_API_KEY, lê por IA os novos/alterados
    (até FIDC_IA_LIMITE, padrão 200). Reconstrói a base no fim. FIDC_REGULAMENTOS_HORA=-1 desliga."""
    hora = int(os.environ.get("FIDC_REGULAMENTOS_HORA", "3"))
    if hora < 0:
        return
    while True:
        agora = datetime.now()
        prox = agora.replace(hour=hora, minute=0, second=0, microsecond=0)
        if prox <= agora:
            prox += timedelta(days=1)
        time.sleep((prox - agora).total_seconds())
        try:
            from .. import agente_regulamento, regulamentos
            itens = regulamentos.fila(int(os.environ.get("FIDC_REGULAMENTOS_LIMITE", "300")))
            if itens:
                regulamentos.rodar(itens, workers=3)
            if os.environ.get("ANTHROPIC_API_KEY"):
                pend = agente_regulamento.pendentes(int(os.environ.get("FIDC_IA_LIMITE", "200")))
                if pend:
                    agente_regulamento.lote(pend)
            _run_etl(False)
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning("rotina noturna de regulamentos falhou: %s", e)


def _bimestral():
    """A cada ~60 dias: reaplica as regras de leitura aos regulamentos baixados e, se houver ANTHROPIC_API_KEY,
    lê por IA os regulamentos novos ou alterados (lote, 50% de desconto). Reconstrói a base depois."""
    marca = config.DATA_DIR / ".regulamentos_bimestral"
    try:
        if marca.exists() and time.time() - marca.stat().st_mtime < 60 * 86400:
            return
        from .. import agente_regulamento, regulamentos
        regulamentos.reler_textos()
        if os.environ.get("ANTHROPIC_API_KEY"):
            itens = agente_regulamento.pendentes()
            if itens:
                agente_regulamento.lote(itens)
        marca.touch()
        _run_etl(False)
    except Exception as e:  # noqa: BLE001 - rotina de fundo não derruba o app
        logging.getLogger(__name__).warning("rotina bimestral de regulamentos falhou: %s", e)


@app.exception_handler(RuntimeError)
def _runtime(_, exc: RuntimeError):
    return JSONResponse({"detail": str(exc)}, status_code=503)


app.include_router(acesso.router)
app.include_router(v2.router)


# ------------------------------------------------------------------ frontend (build estático)
STATIC = Path(os.environ.get("FIDC_STATIC_DIR", Path(__file__).resolve().parents[3] / "frontend" / "dist"))
if STATIC.exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        if path and f.is_file():
            return FileResponse(f)
        return FileResponse(STATIC / "index.html")
