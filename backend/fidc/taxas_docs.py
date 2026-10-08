"""Documento de onde tirar as taxas (administração, gestão, performance) quando o regulamento lido não as traz.

Sob a Res. CVM 175 o regulamento costuma vir em partes: a parte geral ("Regulamento") e o anexo da classe
("Anexo ao Regulamento"), entregues como documentos separados no FNET; as taxas ficam no anexo. Há também fundos com
só um instrumento de alteração, ou com a taxa numa tabela por faixa de PL.

Para cada fundo sem taxa:
1. procura no texto já baixado páginas com taxa + número (% ou R$), com uma busca mais aberta que a dos trechos;
2. se não houver, baixa do FNET, nesta ordem, até 4 documentos: anexos ao regulamento (mais recentes primeiro),
   regulamentos anteriores e instrumentos de alteração; usa o primeiro que tiver taxa com número;
3. guarda só as páginas úteis em data/regulamentos_taxas/<cnpj>.json.gz e a origem em reg_taxa_doc.

    python -m fidc.taxas_docs --limite 2000 --workers 4
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import httpx

from . import regulamentos as rg

log = logging.getLogger(__name__)
DIR = rg.DIR.parent / "regulamentos_taxas"
MAX_DOWNLOADS = 4
SCHEMA = """CREATE TABLE IF NOT EXISTS reg_taxa_doc (cnpj TEXT PRIMARY KEY, doc_id INTEGER, categoria TEXT,
  data_entrega TEXT, status TEXT, paginas TEXT, processado_em TEXT)"""

# nome da taxa e, até 400 caracteres depois, um número em % ou R$ (pega tabela por faixa e redações variadas)
_NOME = re.compile(r"taxa (maxima |minima |global )?de (administracao|gestao)|remuneracao (da|do|a|ao|pel[ao]s?|minima|maxima|total|fixa|correspondente|"
                   r"equivalente|anual|mensal|devida)|taxa de gestao|pela (administracao|gestao)")
_NUM = re.compile(r"\d+[,.]\d+ ?%|\d+ ?% ?\(|\d+ ?por cento|r\$ ?\d")


def paginas_com_taxa(paginas: list[str]) -> list[int]:
    """Índices (0-based) das páginas com nome de taxa seguido de número (% ou R$)."""
    out = []
    for i, p in enumerate(paginas):
        if re.search(r"\.{8,}", p):          # sumário
            continue
        t = rg._norm(re.sub(r"\s+", " ", p))
        if any(_NUM.search(t[m.end():m.end() + 400]) for m in _NOME.finditer(t)):
            out.append(i)
    return out


def db():
    con = rg.db()
    con.execute(SCHEMA)
    return con


def carregar(cnpj: str) -> dict | None:
    """Páginas com taxa (do regulamento já baixado ou de outro documento do FNET), com a origem."""
    f = DIR / f"{cnpj}.json.gz"
    return json.loads(gzip.decompress(f.read_bytes())) if f.exists() else None


def _salvar(cnpj: str, doc: dict, paginas: list[str], idx: list[int], status: str) -> None:
    DIR.mkdir(parents=True, exist_ok=True)
    sel = sorted({j for i in idx for j in (i, i + 1) if j < len(paginas)})
    if sel:
        (DIR / f"{cnpj}.json.gz").write_bytes(gzip.compress(json.dumps({
            "doc_id": doc.get("id"), "categoria": doc.get("categoria"), "data_entrega": doc.get("dataEntrega"),
            "paginas": {str(i + 1): paginas[i] for i in sel}}, ensure_ascii=False).encode()))
    con = db()
    con.execute("INSERT OR REPLACE INTO reg_taxa_doc VALUES (?,?,?,?,?,?,?)",
                [cnpj, doc.get("id"), doc.get("categoria"), doc.get("dataEntrega"), status,
                 ",".join(str(i + 1) for i in idx), datetime.now().isoformat(timespec="seconds")])
    con.commit()
    con.close()


def _data(d: dict) -> datetime:
    try:
        return datetime.strptime(d["dataEntrega"], "%d/%m/%Y %H:%M")
    except (KeyError, TypeError, ValueError):
        return datetime.min


def candidatos(docs: list[dict], doc_atual: int | None) -> list[dict]:
    def ok(d):
        return not (d.get("descricaoStatus") or "").startswith("Cancel") and int(d["id"]) != (doc_atual or -1)

    def cat(d):
        return f"{(d.get('categoriaDocumento') or '').strip()} {(d.get('tipoDocumento') or '').strip()}"
    anexos = [d for d in docs if ok(d) and re.search(r"Anexo|Suplemento|Ap[êe]ndice", cat(d))]
    regs = [d for d in docs if ok(d) and (d.get("categoriaDocumento") or "").strip() == "Regulamento"]
    alts = [d for d in docs if ok(d) and "Altera" in cat(d) and "Regulamento" in cat(d)]
    out = []
    for grupo in (anexos, regs, alts):
        out += sorted(grupo, key=_data, reverse=True)
    return [{**d, "categoria": cat(d).strip()} for d in out]


def processar(cnpj: str, client: httpx.Client) -> str:
    con = db()
    row = con.execute("SELECT doc_id, cnpj_busca, data_entrega, tipo FROM reg_doc WHERE cnpj = ?", [cnpj]).fetchone()
    con.close()
    atual = rg.DIR / f"{cnpj}.json.gz"
    if row and atual.exists():
        paginas = json.loads(gzip.decompress(atual.read_bytes()))[0]
        idx = paginas_com_taxa(paginas)
        if idx:
            _salvar(cnpj, {"id": row[0], "categoria": row[3] or "Regulamento", "dataEntrega": row[2]}, paginas, idx,
                    "regulamento_atual")
            return "regulamento_atual"
    try:
        docs = rg.listar_documentos(client, (row[1] if row else None) or cnpj)
        if row and row[1] and row[1] != cnpj:
            docs += rg.listar_documentos(client, cnpj)
    except Exception as e:  # noqa: BLE001
        log.warning("taxas %s: %s", cnpj, e)
        return "erro_listagem"
    for d in candidatos(docs, row[0] if row else None)[:MAX_DOWNLOADS]:
        try:
            pdf = rg._get(client, rg.DOWNLOAD.format(int(d["id"]))).content
            if pdf[:4] != b"%PDF":
                continue
            paginas, _ = rg.extrair_texto(pdf)
        except Exception as e:  # noqa: BLE001
            log.warning("taxas %s doc %s: %s", cnpj, d.get("id"), e)
            continue
        idx = paginas_com_taxa(paginas)
        if idx:
            _salvar(cnpj, d, paginas, idx, "outro_documento")
            return "outro_documento"
    _salvar(cnpj, {}, [], [], "nao_encontrado")
    return "nao_encontrado"


def rodar(cnpjs: list[str], workers: int = 4) -> dict:
    res: dict[str, int] = {}
    with httpx.Client(timeout=180, headers=rg.HEADERS, follow_redirects=True) as client, \
            ThreadPoolExecutor(workers) as ex:
        futs = {ex.submit(processar, c, client): c for c in cnpjs}
        for i, f in enumerate(as_completed(futs), 1):
            st = f.result()
            res[st] = res.get(st, 0) + 1
            if i % 50 == 0:
                log.info("taxas: %d/%d %s", i, len(cnpjs), res)
    rg.salvar_glifos()
    return res


def main():
    from . import agente_sessao as s
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--limite", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--cnpjs", help="arquivo com um CNPJ por linha")
    ap.add_argument("--refazer", action="store_true", help="processa de novo quem já tem reg_taxa_doc")
    a = ap.parse_args()
    if a.cnpjs:
        cs = open(a.cnpjs).read().split()
    else:
        con = db()
        feitos = {c for (c,) in con.execute("SELECT cnpj FROM reg_taxa_doc")}
        con.close()
        cs = [c for c, _ in s.fila_taxas(100000, todos=True) if a.refazer or c not in feitos][:a.limite]
    print(json.dumps(rodar(cs, a.workers)))


if __name__ == "__main__":
    main()
