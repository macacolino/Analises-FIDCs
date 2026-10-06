"""Regulamentos dos FIDCs: download no FNET (gratuito, sem chave), extração de texto e leitura por regras.

O que sai daqui (sempre com o trecho do regulamento que sustenta o valor):
- campos: subordinação mínima (sênior e Jr), limites de concentração (cedente/devedor), responsabilidade limitada,
  trecho dos eventos de avaliação/liquidação
- sinais: contagem de termos e leis que indicam a tese (consignado público x privado, precatório, duplicata...),
  usados na classificação

Leitura por regras (regex) - não usa IA. Valores extraídos são sugestão: aparecem como "regulamento (extração
automática)" e o dado manual sempre prevalece.

PDFs gerados no Word com fonte Calibri sem tabela de caracteres (ToUnicode) saem com os números internos dos
glifos. Corrigimos com um mapa glifo -> caractere aprendido dos próprios regulamentos que trazem a tabela
(`glifos_aprendidos.json`), que melhora conforme a base cresce.

Uso: python -m fidc.regulamentos [--limite N] [--cnpj X ...] [--workers 3] [--reprocessar]
"""
from __future__ import annotations

import argparse
import gzip
import io
import json
import logging
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import httpx

from . import config

log = logging.getLogger(__name__)

DIR = config.DATA_DIR / "regulamentos"
DB = config.DATA_DIR / "regulamentos.sqlite"
GLIFOS_SEED = Path(__file__).parent / "taxonomy" / "glifos_calibri.json"
GLIFOS = DIR / "glifos_aprendidos.json"
SEED = Path(__file__).parent / "seed" / "regulamentos.json.gz"   # resultado versionado no repositório (sem os textos)
DOWNLOAD = f"{config.FNET_BASE}/downloadDocumento?id={{}}"
VERSAO_REGRAS = 6   # mude quando as regras de leitura mudarem: força reprocessar o texto já baixado
LIMITE_DIARIO = 150   # regulamentos novos lidos por execução do ETL diário

SCHEMA = """
CREATE TABLE IF NOT EXISTS reg_doc (
  cnpj TEXT PRIMARY KEY, doc_id INTEGER, data_entrega TEXT, cnpj_busca TEXT, tipo TEXT,
  n_paginas INTEGER, n_chars INTEGER, metodo TEXT, status TEXT, erro TEXT, versao_regras INTEGER,
  processado_em TEXT);
CREATE TABLE IF NOT EXISTS reg_campo (
  cnpj TEXT, campo TEXT, valor_num REAL, valor_txt TEXT, trecho TEXT, pagina INTEGER, confianca TEXT,
  PRIMARY KEY (cnpj, campo));
CREATE TABLE IF NOT EXISTS reg_sinal (cnpj TEXT, sinal TEXT, n INTEGER, PRIMARY KEY (cnpj, sinal));
"""

_db_lock = threading.Lock()


def db() -> sqlite3.Connection:
    DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB, check_same_thread=False, timeout=60)
    con.executescript(SCHEMA)
    return con


# ------------------------------------------------------------------ FNET
HEADERS = {"X-Requested-With": "XMLHttpRequest", "User-Agent": "Mozilla/5.0 (analisador-fidc)"}


def _get(client: httpx.Client, url: str, **kw):
    for i in range(4):
        try:
            r = client.get(url, **kw)
            if r.status_code == 200:
                return r
        except httpx.HTTPError:
            pass
        time.sleep(2 ** i)
    raise RuntimeError(f"FNET falhou: {url}")


def listar_documentos(client: httpx.Client, cnpj: str) -> list[dict]:
    docs, start = [], 0
    while start < 1000:
        r = _get(client, f"{config.FNET_BASE}/pesquisarGerenciadorDocumentosDados",
                 params={"d": 1, "s": start, "l": 100, "o[0][dataEntrega]": "desc", "cnpjFundo": cnpj})
        j = r.json()
        rows = j.get("data") or []
        docs += rows
        start += len(rows)
        if not rows or start >= (j.get("recordsTotal") or 0):
            break
    return docs


def escolher_regulamento(docs: list[dict]) -> dict | None:
    """Regulamento vigente = documento mais recente da categoria Regulamento que não foi cancelado.
    Sem isso, usa o instrumento de alteração do regulamento mais recente (costuma trazer o texto consolidado)."""
    def ok(d):
        return not (d.get("descricaoStatus") or "").startswith("Cancel")
    regs = [d for d in docs if (d.get("categoriaDocumento") or "").strip() == "Regulamento" and ok(d)]
    if not regs:
        regs = [d for d in docs if "Regulamento" in (d.get("tipoDocumento") or "") and ok(d)]
    if not regs:
        return None

    def data(d):
        try:
            return datetime.strptime(d["dataEntrega"], "%d/%m/%Y %H:%M")
        except (KeyError, TypeError, ValueError):
            return datetime.min
    return max(regs, key=data)


# ------------------------------------------------------------------ texto
def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", t)


def _carregar_glifos() -> dict[str, dict[int, str]]:
    out: dict[str, dict[int, str]] = {}
    for f in (GLIFOS_SEED, GLIFOS):
        if f.exists():
            for fam, m in json.loads(f.read_text()).items():
                out.setdefault(fam, {}).update({int(k): v for k, v in m.items()})
    return out


_glifos = None
_glifos_novos: dict[str, dict[int, str]] = {}
_glifos_lock = threading.Lock()


def _familia(font) -> str:
    nome = str(font.get("/BaseFont", ""))
    nome = nome.split("+", 1)[-1].lstrip("/")
    return nome.split(",")[0].split("-")[0]   # Calibri-Bold -> Calibri (mesma ordem de glifos)


def _aprender(font) -> None:
    """Fonte Type0 COM ToUnicode: guarda cid -> caractere para decodificar PDFs da mesma família sem tabela."""
    try:
        data = font["/ToUnicode"].get_object().get_data().decode("latin-1")
    except Exception:  # noqa: BLE001
        return
    fam = _familia(font)
    m = {}
    for blk in re.findall(r"beginbfchar(.*?)endbfchar", data, re.S):
        for cid, uni in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", blk):
            if len(uni) == 4:
                m[int(cid, 16)] = chr(int(uni, 16))
    for blk in re.findall(r"beginbfrange(.*?)endbfrange", data, re.S):
        for a, b, u in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]{4})>", blk):
            for i, cid in enumerate(range(int(a, 16), int(b, 16) + 1)):
                m[cid] = chr(int(u, 16) + i)
    if m:
        with _glifos_lock:
            _glifos_novos.setdefault(fam, {}).update(m)


def salvar_glifos() -> None:
    with _glifos_lock:
        if not _glifos_novos:
            return
        atual = json.loads(GLIFOS.read_text()) if GLIFOS.exists() else {}
        for fam, m in _glifos_novos.items():
            atual.setdefault(fam, {}).update({str(k): v for k, v in m.items()})
        GLIFOS.write_text(json.dumps(atual))


def extrair_texto(pdf: bytes) -> tuple[list[str], str]:
    """Texto por página. Método 'pypdf' ou 'pypdf+glifos' (quando precisou decodificar Calibri sem tabela)."""
    global _glifos
    from pypdf import PdfReader
    if _glifos is None:
        _glifos = _carregar_glifos()
    rd = PdfReader(io.BytesIO(pdf))
    paginas, usou_mapa = [], False
    for p in rd.pages:
        partes: list[str] = []

        def visitor(text, cm, tm, font, size, partes=partes):
            nonlocal usou_mapa
            if not text:
                return
            if font is not None and font.get("/Subtype") == "/Type0":
                if "/ToUnicode" in font:
                    _aprender(font)
                else:
                    mapa = _glifos.get(_familia(font))
                    if mapa:
                        text = "".join(mapa.get(ord(c), c) for c in text)
                        usou_mapa = True
            partes.append(text)
        try:
            p.extract_text(visitor_text=visitor)
        except Exception:  # noqa: BLE001 - página corrompida não derruba o documento
            pass
        paginas.append("".join(partes))
    return paginas, "pypdf+glifos" if usou_mapa else "pypdf"


def texto_legivel(t: str) -> bool:
    """Heurística: texto legível tem muitas palavras comuns do português."""
    n = _norm(t)
    hits = sum(n.count(w) for w in (" de ", " do ", " da ", " que ", " cotas", " fundo"))
    return len(n) > 2000 and hits / max(len(n), 1) > 0.01


# ------------------------------------------------------------------ leitura por regras
SINAIS = {
    # consignado
    "consignado": r"consig",   # consignado, consignação, consignável, "CONSIG"
    "consig_inss": r"\binss\b|8\.213|beneficios? previdenciari|previdencia social|\brgps\b|aposentad|pensionist|"
                   r"pensao por morte|instituto nacional do seguro social",
    "consig_servidor": r"servidor\w* public|8\.112|\bsiape\b|\bentes?\b|orgaos? (publicos? )?consignantes?|prefeitura|"
                       r"governo do estado|forcas armadas|\bmilitar",
    # Lei 10.820/2003 cobre CLT e também aposentados do INSS (art. 6º): fica num sinal neutro
    "lei_10820": r"10\.820",
    "consig_privado": r"setor privado|trabalhador\w* (do setor privado|celetist)|\bclt\b|esocial|e-?social|"
                      r"credito do trabalhador|15\.179|1\.292|empregador(?:es|as?)?\b(?! rural)|carteira de trabalho",
    "dataprev": r"dataprev", "fgts": r"\bfgts\b|saque.aniversario",
    # outros lastros
    "precatorio": r"precatori", "duplicata": r"duplicata", "cheque": r"\bcheques?\b", "ccb": r"\bccb\b|cedulas? de credito bancario",
    "cartao": r"cartao de credito|cartoes de credito|arranjos? de pagamento", "veiculo": r"veiculo",
    "imobiliario": r"imobiliari|alugue", "agro": r"\bcpr\b|agronegocio|produtor rural",
    "judicial": r"acoes? judicia|direitos? creditorios? judicia|processos? judicia",
    "multicedente": r"multicedente|multi-cedente|diversos cedentes", "multissacado": r"multissacado|multi-sacado|diversos sacados",
    "npl": r"nao performad|inadimplid|vencidos e nao pagos.*aquisi",
    "fic": r"cotas de (outros )?fundos de investimento em direitos creditorios|\bfic[- ]fidc",
}


def sinais(texto: str) -> dict[str, int]:
    n = _norm(texto)
    return {k: len(re.findall(p, n)) for k, p in SINAIS.items()}


_PCT = r"(\d{1,3}(?:[.,]\d+)?)\s?%"


def _sentencas(paginas: list[str]):
    """(página, sentença) com espaços normalizados. Sentença ~ trecho entre pontos/ponto-e-vírgula."""
    for i, p in enumerate(paginas, 1):
        t = re.sub(r"\s+", " ", p)
        for s in re.split(r"(?<=[;:])\s|(?<=\.)\s(?=\d+(?:\.\d+)*\.?\s|[A-Z(])", t):
            if len(s) > 20:
                yield i, s.strip()


def _num(s: str) -> float:
    return float(s.replace(".", "").replace(",", ".")) if s.count(",") else float(s)


def campos(paginas: list[str]) -> list[dict]:
    out: dict[str, dict] = {}

    def put(campo, valor_num=None, valor_txt=None, trecho="", pagina=None, confianca="media"):
        if campo not in out:       # primeira ocorrência no texto costuma ser a definição
            out[campo] = {"campo": campo, "valor_num": valor_num, "valor_txt": valor_txt,
                          "trecho": trecho[:600], "pagina": pagina, "confianca": confianca}

    sents = list(_sentencas(paginas))
    # --- subordinação mínima
    for pg, s in sents:
        n = _norm(s)
        if "subordina" not in n or not re.search(r"minim|no minimo|nao inferior|igual ou superior", n):
            continue
        if re.search(r"quorum|em circulacao (de cada|objeto)|spread|liquidez|ao ano|a\.a\.|amortizac|taxa de|glossario", n):
            continue
        # o percentual tem de vir logo depois da menção à subordinação (não um % qualquer da sentença)
        m = None
        for k in re.finditer(r"subordina", n):
            m = re.compile(_PCT).search(n, k.start(), k.start() + 250)
            if m:
                break
        if not m:
            continue
        v = _num(m.group(1)) / 100
        if not 0 < v < 1:
            continue
        # numerador: Jr (júnior) ou todas as subordinadas; base: PL ou subordinadas
        jr = bool(re.search(r"cotas subordinadas juniore?s?|subordinadas? junior|cotas juniores", n))
        mez_e_jr = bool(re.search(r"mezanino e (subordinadas? )?junior", n))
        base_sub = bool(re.search(r"patrimonio liquido das (classes|cotas) subordinadas|valor das cotas subordinadas em circulacao\)?$", n)) \
            and not re.search(r"patrimonio liquido d[ao] (classe|fundo)\b(?! subordinad)", n.split("subordina", 1)[-1][:120])
        if jr and not mez_e_jr:
            if base_sub:
                put("jr_min_sobre_subordinadas", v, None, s, pg)
            else:
                put("jr_min_pl", v, None, s, pg)
        elif "mezanino" in n and not mez_e_jr and "senior" not in n and not re.search(r"cotas subordinadas e o", n):
            put("mz_min_pl", v, None, s, pg, "baixa")
        else:
            put("sub_min_senior", v, None, s, pg)
    # --- limites de concentração: entre as cláusulas candidatas fica a mais restritiva (menor %), ignorando as
    # exceções ("acima do limite de 20% quando...") e as regras de desenquadramento
    cand: dict[str, list] = {}
    for pg, s in sents:
        n = _norm(s)
        m = re.search(_PCT, s)
        if not m or not re.search(r"maximo|nao podera|ate|limite|superior a", n):
            continue
        if re.search(r"acima do limite|deixem? de representar|excedid|desenquadr", n):
            continue
        v = _num(m.group(1)) / 100
        if not 0 < v <= 1:
            continue
        for campo, pat in (("limite_5_cedentes", r"\(?(5|cinco)\)?\s(\(\w+\)\s)?maiores cedentes"),
                           ("limite_10_cedentes", r"\(?(10|dez)\)?\s(\(\w+\)\s)?maiores cedentes"),
                           ("limite_5_sacados", r"\(?(5|cinco)\)?\s(\(\w+\)\s)?maiores (devedores|sacados)"),
                           ("limite_10_sacados", r"\(?(10|dez)\)?\s(\(\w+\)\s)?maiores (devedores|sacados)"),
                           ("limite_maior_cedente", r"mesmo cedente|cada cedente|um unico cedente|maior cedente"),
                           ("limite_maior_sacado", r"mesmo (devedor|sacado)|cada (devedor|sacado)|maior (devedor|sacado)")):
            if re.search(pat, n):
                cand.setdefault(campo, []).append((v, s, pg))
                break
    for campo, lst in cand.items():
        v, s, pg = min(lst, key=lambda x: x[0])
        conf = "alta" if len({round(x[0], 4) for x in lst}) == 1 else "media"
        put(campo, v, None, s, pg, conf)
    # --- responsabilidade: conta as duas formas (o termo de ciência de responsabilidade ilimitada é citado mesmo
    # em classe limitada quando o regulamento prevê as duas)
    tudo = _norm(" ".join(paginas))
    lim = len(re.findall(r"responsabilidade (dos cotistas )?(e |sera )?limitada|responsabilidade limitada", tudo))
    ilim = len(re.findall(r"responsabilidade ilimitada|ausencia de limitacao de responsabilidade", tudo))
    if lim or ilim:
        put("responsabilidade_limitada", None, "S" if lim >= ilim else "N",
            f"menções: 'responsabilidade limitada' {lim}×, 'ilimitada' {ilim}×", None,
            "alta" if not (lim and ilim) else "baixa")
    # --- eventos de avaliação e liquidação: a frase que abre a lista ("a ocorrência de qualquer das seguintes
    # hipóteses constituirá Evento de Avaliação: (i) ...")
    for campo, nucleo in (("eventos_avaliacao", r"eventos? de avalia[çc][ãa]o"),
                          ("eventos_liquidacao", r"eventos? de liquida[çc][ãa]o( antecipada)?")):
        pat = re.compile(r"(?i)[^.;:]{0,200}?" + nucleo + r"[^.;:]{0,100}:")
        achou = False
        for pg, p in enumerate(paginas, 1):
            t = re.sub(r"\s+", " ", p)
            for m in pat.finditer(t):
                if re.search(r"(?i)seguint|considerad|constitu|configur|caracteriz", m.group(0)):
                    i = m.start() + len(m.group(0)) - len(m.group(0).lstrip())
                    put(campo, None, t[i:i + 2500], t[i:i + 600], pg, "media")
                    achou = True
                    break
            if achou:
                break
    # derivado: Jr mínima em % do PL quando definida sobre as subordinadas
    if "jr_min_sobre_subordinadas" in out and "sub_min_senior" in out and "jr_min_pl" not in out:
        a, b = out["jr_min_sobre_subordinadas"], out["sub_min_senior"]
        put("jr_min_pl", a["valor_num"] * b["valor_num"], None,
            f"calculado: {a['valor_num']:.2%} das subordinadas × subordinação mínima {b['valor_num']:.2%}", a["pagina"], "media")
    return list(out.values())


# ------------------------------------------------------------------ pipeline por fundo
def processar(cnpj: str, cnpj_fundo: str | None = None, client: httpx.Client | None = None,
              reprocessar: bool = False) -> dict:
    own = client is None
    client = client or httpx.Client(timeout=180, headers=HEADERS, follow_redirects=True)
    con = db()
    try:
        alvo_docs = []
        for alvo in dict.fromkeys([cnpj, cnpj_fundo or cnpj]):
            docs = listar_documentos(client, alvo)
            if docs:
                alvo_docs.append((alvo, docs))
        escolhido, busca = None, None
        for alvo, docs in alvo_docs:
            d = escolher_regulamento(docs)
            if d:
                escolhido, busca = d, alvo
                break
        if not escolhido:
            _salvar(con, cnpj, {"status": "sem_regulamento"})
            return {"cnpj": cnpj, "status": "sem_regulamento"}
        doc_id = int(escolhido["id"])
        txt_file = DIR / f"{cnpj}.json.gz"
        ant = con.execute("SELECT doc_id, versao_regras FROM reg_doc WHERE cnpj = ?", [cnpj]).fetchone()
        if ant and ant[0] == doc_id and ant[1] == VERSAO_REGRAS and txt_file.exists() and not reprocessar:
            return {"cnpj": cnpj, "status": "sem_mudanca"}
        if txt_file.exists() and ant and ant[0] == doc_id:
            paginas, metodo = json.loads(gzip.decompress(txt_file.read_bytes()))
        else:
            pdf = _get(client, DOWNLOAD.format(doc_id)).content
            if pdf[:4] != b"%PDF":
                _salvar(con, cnpj, {"status": "nao_pdf", "doc_id": doc_id})
                return {"cnpj": cnpj, "status": "nao_pdf"}
            paginas, metodo = extrair_texto(pdf)
            txt_file.write_bytes(gzip.compress(json.dumps([paginas, metodo]).encode()))
        texto = "\n".join(paginas)
        legivel = texto_legivel(texto)
        meta = {"doc_id": doc_id, "data_entrega": escolhido.get("dataEntrega"), "cnpj_busca": busca,
                "tipo": (escolhido.get("tipoDocumento") or escolhido.get("categoriaDocumento") or "").strip(),
                "n_paginas": len(paginas), "n_chars": len(texto), "metodo": metodo,
                "status": "ok" if legivel else "ilegivel"}
        cs = campos(paginas) if legivel else []
        ss = sinais(texto) if legivel else {}
        _salvar(con, cnpj, meta, cs, ss)
        return {"cnpj": cnpj, **meta, "n_campos": len(cs)}
    except Exception as e:  # noqa: BLE001
        log.warning("regulamento %s: %s", cnpj, e)
        _salvar(con, cnpj, {"status": "erro", "erro": str(e)[:300]})
        return {"cnpj": cnpj, "status": "erro", "erro": str(e)}
    finally:
        con.close()
        if own:
            client.close()


def _salvar(con, cnpj, meta, cs=None, ss=None):
    with _db_lock:
        con.execute("""INSERT OR REPLACE INTO reg_doc (cnpj, doc_id, data_entrega, cnpj_busca, tipo, n_paginas, n_chars,
                       metodo, status, erro, versao_regras, processado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    [cnpj, meta.get("doc_id"), meta.get("data_entrega"), meta.get("cnpj_busca"), meta.get("tipo"),
                     meta.get("n_paginas"), meta.get("n_chars"), meta.get("metodo"), meta.get("status"),
                     meta.get("erro"), VERSAO_REGRAS, datetime.now().isoformat(timespec="seconds")])
        if cs is not None:
            con.execute("DELETE FROM reg_campo WHERE cnpj = ?", [cnpj])
            con.executemany("INSERT INTO reg_campo VALUES (?,?,?,?,?,?,?)",
                            [[cnpj, c["campo"], c["valor_num"], c["valor_txt"], c["trecho"], c["pagina"], c["confianca"]]
                             for c in cs])
        if ss is not None:
            con.execute("DELETE FROM reg_sinal WHERE cnpj = ?", [cnpj])
            con.executemany("INSERT INTO reg_sinal VALUES (?,?,?)", [[cnpj, k, v] for k, v in ss.items() if v])
        con.commit()


def reler_textos() -> int:
    """Reaplica as regras de leitura aos textos já baixados (sem acessar o FNET)."""
    con = db()
    n = 0
    for (cnpj,) in con.execute("SELECT cnpj FROM reg_doc WHERE status IN ('ok', 'ilegivel')").fetchall():
        f = DIR / f"{cnpj}.json.gz"
        if not f.exists():
            continue
        paginas, metodo = json.loads(gzip.decompress(f.read_bytes()))
        texto = "\n".join(paginas)
        legivel = texto_legivel(texto)
        meta = dict(zip(["doc_id", "data_entrega", "cnpj_busca", "tipo", "n_paginas", "n_chars"],
                        con.execute("SELECT doc_id, data_entrega, cnpj_busca, tipo, n_paginas, n_chars FROM reg_doc WHERE cnpj = ?",
                                    [cnpj]).fetchone()))
        meta.update(metodo=metodo, status="ok" if legivel else "ilegivel")
        _salvar(con, cnpj, meta, campos(paginas) if legivel else [], sinais(texto) if legivel else {})
        n += 1
    con.close()
    return n


def fila(limite: int | None = None) -> list[tuple[str, str]]:
    """Fundos ativos sem regulamento processado, maiores primeiro (carteira e watchlist na frente)."""
    from . import appdb
    from .db import df
    u = df("""SELECT f.cnpj, coalesce(k.cnpj_fundo, f.cnpj) AS cnpj_fundo, f.pl, f.categoria FROM fundo f
              LEFT JOIN cadastro k USING (cnpj)
              WHERE f.ultimo_informe >= (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 3 MONTH
              ORDER BY f.pl DESC NULLS LAST""")
    with appdb.session() as s:
        prior = {r["cnpj"] for r in s.execute("SELECT cnpj FROM lista UNION SELECT cnpj FROM grupo_pares_membro")}
    con = db()
    feitos = {r[0] for r in con.execute("SELECT cnpj FROM reg_doc WHERE status <> 'erro'")}
    con.close()
    # ordem: carteira/watchlist/grupos, depois as categorias onde a leitura do regulamento mais muda a
    # classificação (consignado escondido em "outros financeiros", crédito pessoal etc.), depois o resto por PL
    foco = ["consignado_publico", "consignado_privado", "consignado_indefinido", "credito_pessoal", "fgts",
            "financeiro_outros", "outros", "sem_carteira", "multicedente_multissacado"]
    u = u[~u.cnpj.isin(feitos)].copy()
    u["k"] = [0 if c in prior else 1 + (foco.index(cat) if cat in foco else len(foco))
              for c, cat in zip(u.cnpj, u.categoria)]
    u = u.sort_values(["k", "pl"], ascending=[True, False])
    rows = list(zip(u.cnpj, u.cnpj_fundo))
    return rows[:limite] if limite else rows


_client = None


def _job(item):
    """Roda num processo separado (a extração de texto é CPU: threads não paralelizam por causa do GIL)."""
    global _client
    if _client is None:
        _client = httpx.Client(timeout=180, headers=HEADERS, follow_redirects=True)
    r = processar(item[0], item[1], _client)
    with _glifos_lock:
        r["glifos"] = {f: dict(m) for f, m in _glifos_novos.items()}
        _glifos_novos.clear()
    time.sleep(0.5)  # gentileza com o FNET
    return r


def rodar(cnpjs: list[tuple[str, str]], workers: int = 3) -> dict:
    from concurrent.futures import ProcessPoolExecutor
    stats: dict[str, int] = {}
    t0 = time.time()
    with ProcessPoolExecutor(workers) as ex:
        for i, r in enumerate(ex.map(_job, cnpjs, chunksize=1), 1):
            for fam, m in (r.pop("glifos", None) or {}).items():
                _glifos_novos.setdefault(fam, {}).update(m)
            stats[r["status"]] = stats.get(r["status"], 0) + 1
            if i % 25 == 0:
                salvar_glifos()
                log.info("%d/%d em %.0fs %s", i, len(cnpjs), time.time() - t0, stats)
    salvar_glifos()
    return stats


# ------------------------------------------------------------------ seed e base analítica
def _tabelas() -> dict[str, "pd.DataFrame"]:
    """reg_doc/reg_campo/reg_sinal: o processado localmente prevalece sobre o seed do repositório."""
    import pandas as pd
    seed = json.loads(gzip.decompress(SEED.read_bytes())) if SEED.exists() else {}
    out = {t: pd.DataFrame(seed.get(t, {}).get("rows", []), columns=seed.get(t, {}).get("cols")) for t in
           ("reg_doc", "reg_campo", "reg_sinal")}
    if DB.exists():
        con = sqlite3.connect(DB)
        local = {t: pd.read_sql(f"SELECT * FROM {t}", con) for t in out}
        con.close()
        feitos = set(local["reg_doc"].cnpj)
        for t in out:
            base = out[t]
            if len(base):
                base = base[~base.cnpj.isin(feitos)]
            out[t] = pd.concat([base, local[t]], ignore_index=True) if len(base) else local[t]
    return out


def exportar_seed() -> Path:
    t = _tabelas()
    SEED.parent.mkdir(parents=True, exist_ok=True)
    data = {k: {"cols": list(v.columns), "rows": v.astype(object).where(v.notna(), None).values.tolist()}
            for k, v in t.items()}
    SEED.write_bytes(gzip.compress(json.dumps(data, ensure_ascii=False).encode(), 9))
    if _glifos_novos or GLIFOS.exists():
        salvar_glifos()
        GLIFOS_SEED.write_text(GLIFOS.read_text())
    return SEED


def build_table(con) -> None:
    """Grava regulamento, regulamento_campo e regulamento_sinal na base DuckDB."""
    import pandas as pd
    t = _tabelas()
    nomes = {"reg_doc": "regulamento", "reg_campo": "regulamento_campo", "reg_sinal": "regulamento_sinal"}
    vazios = {"reg_doc": "cnpj VARCHAR, doc_id BIGINT, data_entrega VARCHAR, cnpj_busca VARCHAR, tipo VARCHAR, "
                         "n_paginas INTEGER, n_chars INTEGER, metodo VARCHAR, status VARCHAR, erro VARCHAR, "
                         "versao_regras INTEGER, processado_em VARCHAR",
              "reg_campo": "cnpj VARCHAR, campo VARCHAR, valor_num DOUBLE, valor_txt VARCHAR, trecho VARCHAR, "
                           "pagina INTEGER, confianca VARCHAR",
              "reg_sinal": "cnpj VARCHAR, sinal VARCHAR, n INTEGER"}
    for k, dest in nomes.items():
        d = t[k]
        if not len(d):
            con.execute(f"CREATE OR REPLACE TABLE {dest} ({vazios[k]})")
            continue
        con.register("_r", pd.DataFrame(d))
        con.execute(f"CREATE OR REPLACE TABLE {dest} AS SELECT * FROM _r")
        con.unregister("_r")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int)
    ap.add_argument("--cnpj", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--reler", action="store_true", help="só reaplica as regras aos textos já baixados")
    ap.add_argument("--seed", action="store_true", help="exporta o resultado para fidc/seed (versionado)")
    a = ap.parse_args()
    if a.seed:
        print(exportar_seed())
        return
    if a.reler:
        print({"relidos": reler_textos()})
        return
    itens = [(c, c) for c in a.cnpj] if a.cnpj else fila(a.limite)
    print(rodar(itens, a.workers))


if __name__ == "__main__":
    main()
