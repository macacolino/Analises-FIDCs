"""Senha única do time (FIDC_SENHA) e feedback (FIDC_FEEDBACK_URL).

Sem FIDC_SENHA o app fica aberto (uso local / Codespace). Com ela, toda rota exige o cookie de sessão, que é um HMAC
da senha: trocar a senha derruba todas as sessões. O feedback vai para data/feedback.jsonl e, se houver
FIDC_FEEDBACK_URL (Apps Script de uma planilha Google), também para a planilha - o disco do Cloud Run é apagado a cada
reinício, então a planilha é o registro que vale.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import html
import json
import logging
import os
from datetime import datetime
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel

from .. import config

log = logging.getLogger(__name__)
router = APIRouter()
COOKIE = "fidc_sessao"
DIAS = 30
LIVRES = ("/login", "/healthz", "/favicon.svg", "/ouribank_white.png", "/ouribank_teal_dark.png")


def _senha() -> str:
    return os.environ.get("FIDC_SENHA", "")


def _token(senha: str) -> str:
    return hmac.new(senha.encode(), b"fidc-sessao-v1", hashlib.sha256).hexdigest()


def _ok(request: Request) -> bool:
    s = _senha()
    return not s or hmac.compare_digest(request.cookies.get(COOKIE, ""), _token(s))


async def middleware(request: Request, call_next):
    p = request.url.path
    if _ok(request) or p in LIVRES:
        return await call_next(request)
    if p.startswith("/api/"):
        return JSONResponse({"detail": "Sessão expirada: entre de novo com a senha."}, status_code=401)
    destino = p + (f"?{request.url.query}" if request.url.query else "")
    return RedirectResponse(f"/login?next={quote(destino)}", status_code=303)


PAGINA = """<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Analisador de FIDCs</title><style>
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#15252D;font-family:Inter,system-ui,sans-serif;color:#15252D}}
form{{background:#fff;border-radius:18px;padding:32px 28px;width:min(340px,calc(100vw - 32px));box-shadow:0 12px 40px rgba(0,0,0,.25)}}
img{{height:26px;display:block;margin-bottom:18px}} h1{{font-size:18px;margin:0 0 4px}} p{{margin:0 0 18px;color:#5b6b73;font-size:13px}}
input{{width:100%;box-sizing:border-box;padding:11px 12px;border:1px solid #d5dde1;border-radius:10px;font-size:15px}}
button{{margin-top:14px;width:100%;padding:11px;border:0;border-radius:10px;background:#428087;color:#fff;font-size:15px;cursor:pointer}}
.err{{color:#C25450;font-size:13px;margin-top:10px}}</style></head><body>
<form method="post" action="/login"><img src="/ouribank_teal_dark.png" alt="Ouribank"><h1>Analisador de FIDCs</h1>
<p>Versão de testes. Entre com a senha do time.</p>
<input type="password" name="senha" placeholder="Senha" autofocus required>
<input type="hidden" name="next" value="{next}"><button>Entrar</button>{erro}</form></body></html>"""


def _seguro(nxt: str) -> str:
    return nxt if nxt.startswith("/") and not nxt.startswith("//") else "/"


@router.get("/login", include_in_schema=False)
def login_form(next: str = "/"):
    return HTMLResponse(PAGINA.format(next=html.escape(_seguro(next)), erro=""))


@router.post("/login", include_in_schema=False)
async def login(request: Request, senha: str = Form(""), next: str = Form("/")):
    s = _senha()
    if s and not hmac.compare_digest(senha.encode(), s.encode()):
        await asyncio.sleep(1)     # freia tentativa em série
        return HTMLResponse(PAGINA.format(next=html.escape(_seguro(next)), erro='<div class="err">Senha incorreta.</div>'),
                            status_code=401)
    r = RedirectResponse(_seguro(next), status_code=303)
    if s:
        r.set_cookie(COOKIE, _token(s), max_age=DIAS * 86400, httponly=True, samesite="lax",
                     secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https")
    return r


@router.get("/logout", include_in_schema=False)
def logout():
    r = RedirectResponse("/login", status_code=303)
    r.delete_cookie(COOKIE)
    return r


@router.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}


class FeedbackIn(BaseModel):
    texto: str
    nome: str | None = None
    pagina: str | None = None
    cnpj: str | None = None


@router.post("/api/feedback")
async def feedback(body: FeedbackIn):
    texto = body.texto.strip()[:5000]
    if not texto:
        return JSONResponse({"detail": "Escreva o comentário."}, status_code=400)
    reg = {"data": datetime.now().isoformat(timespec="seconds"), "nome": (body.nome or "").strip()[:80],
           "pagina": (body.pagina or "")[:300], "cnpj": (body.cnpj or "")[:20], "texto": texto,
           "versao": os.environ.get("FIDC_VERSAO", "")}
    with open(config.DATA_DIR / "feedback.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False) + "\n")
    url = os.environ.get("FIDC_FEEDBACK_URL")
    planilha = False
    if url:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
                r = await c.post(url, json=reg)
                planilha = r.status_code < 400
        except httpx.HTTPError as e:
            log.warning("feedback não chegou na planilha: %s", e)
    return {"ok": True, "planilha": planilha}
