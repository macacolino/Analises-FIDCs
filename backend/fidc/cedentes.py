"""Cadastro dos cedentes (Receita Federal): razão social, atividade e sócios de cada CNPJ que aparece entre os
9 maiores cedentes do informe mensal (Tab. I). Serve para juntar CNPJs do mesmo grupo econômico (nome e sócios em
comum) - base da análise de monocedentes e da estrutura de benefício tributário.

Fonte: APIs públicas da base CNPJ da Receita (publica.cnpj.ws e receitaws.com.br), cada uma limitada a ~3 consultas
por minuto; as duas são usadas alternadamente. O resultado fica em data/cedentes.sqlite e num seed versionado
(seed/cedentes.json.gz), de modo que o build não depende da rede. Fila priorizada: cedentes de fundos concentrados
(monocedente primeiro), depois o resto.

    python -m fidc.cedentes --buscar [--limite N] [--minutos M]
    python -m fidc.cedentes --seed
"""
from __future__ import annotations

import argparse
import gzip
import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import httpx

from . import config

log = logging.getLogger(__name__)
DB = config.DATA_DIR / "cedentes.sqlite"
SEED = Path(__file__).parent / "seed" / "cedentes.json.gz"
SCHEMA = """CREATE TABLE IF NOT EXISTS cedente_info (
    cnpj TEXT PRIMARY KEY, raiz TEXT, razao_social TEXT, nome_fantasia TEXT, cnae TEXT, cnae_desc TEXT,
    uf TEXT, municipio TEXT, abertura TEXT, situacao TEXT, natureza TEXT, socios TEXT, fonte TEXT, consultado_em TEXT,
    erro TEXT, capital_social REAL)"""
INTERVALO = 21.0   # segundos entre consultas na mesma fonte (3/min)


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB, timeout=60)
    con.execute(SCHEMA)
    if "capital_social" not in {r[1] for r in con.execute("PRAGMA table_info(cedente_info)")}:
        con.execute("ALTER TABLE cedente_info ADD COLUMN capital_social REAL")
    return con


def _num(v) -> float | None:
    try:
        return float(str(v).replace(",", "")) if v not in (None, "") else None
    except ValueError:
        return None


def _cnpjws(c: str, cli: httpx.Client) -> dict | None:
    r = cli.get(f"https://publica.cnpj.ws/cnpj/{c}")
    if r.status_code == 404:
        return {"erro": "não encontrado"}
    r.raise_for_status()
    d = r.json()
    e = d.get("estabelecimento") or {}
    ap = e.get("atividade_principal") or {}
    return {
        "razao_social": d.get("razao_social"), "nome_fantasia": e.get("nome_fantasia"),
        "cnae": ap.get("subclasse") or ap.get("id"), "cnae_desc": ap.get("descricao"),
        "uf": (e.get("estado") or {}).get("sigla"), "municipio": (e.get("cidade") or {}).get("nome"),
        "abertura": e.get("data_inicio_atividade"), "situacao": e.get("situacao_cadastral"),
        "natureza": (d.get("natureza_juridica") or {}).get("descricao"),
        "capital_social": _num(d.get("capital_social")),
        "socios": [{"nome": s.get("nome"), "doc": s.get("cpf_cnpj_socio"), "tipo": s.get("tipo"),
                    "qualificacao": (s.get("qualificacao_socio") or {}).get("descricao")} for s in d.get("socios") or []],
        "fonte": "publica.cnpj.ws",
    }


def _receitaws(c: str, cli: httpx.Client) -> dict | None:
    r = cli.get(f"https://receitaws.com.br/v1/cnpj/{c}")
    r.raise_for_status()
    d = r.json()
    if d.get("status") == "ERROR":
        msg = d.get("message", "")
        if "inválido" in msg.lower() or "rejeitado" in msg.lower() or "não" in msg.lower():
            return {"erro": msg}
        raise RuntimeError(msg)
    ap = (d.get("atividade_principal") or [{}])[0]
    return {
        "razao_social": d.get("nome"), "nome_fantasia": d.get("fantasia") or None,
        "cnae": ap.get("code"), "cnae_desc": ap.get("text"), "uf": d.get("uf"), "municipio": d.get("municipio"),
        "abertura": d.get("abertura"), "situacao": d.get("situacao"), "natureza": d.get("natureza_juridica"),
        "capital_social": _num(d.get("capital_social")),
        "socios": [{"nome": s.get("nome"), "doc": None, "tipo": None, "qualificacao": s.get("qual")}
                   for s in d.get("qsa") or []],
        "fonte": "receitaws.com.br",
    }


def fila(limite: int = 100000, todos: bool = False) -> list[str]:
    """CNPJs de cedentes ainda sem cadastro: primeiro os de fundos concentrados (maior grupo de CNPJ >= 25% dos
    cedentes informados), monocedente antes, por PL; depois o resto."""
    import duckdb
    feitos = {r[0] for r in db().execute("SELECT cnpj FROM cedente_info WHERE erro = 'não encontrado' "
                                         "OR (erro IS NULL AND capital_social IS NOT NULL)")}
    con = duckdb.connect(str(config.DB_PATH), read_only=True)
    linhas = con.execute("""
        WITH k AS (SELECT k.cnpj, k.cedente_doc, k.pct, f.categoria, f.pl FROM cedente_mes k
                   JOIN fundo f ON f.cnpj = k.cnpj AND k.dt = f.ultimo_informe
                   WHERE length(k.cedente_doc) = 14 AND k.cedente_doc <> '99999999999999'
                     AND f.ultimo_informe >= (SELECT ultimo_mes_completo FROM _meta) - INTERVAL 12 MONTH),
        s AS (SELECT cnpj, max(pct) / nullif(sum(pct), 0) conc FROM k GROUP BY 1)
        SELECT k.cedente_doc, min(CASE WHEN k.categoria = 'monocedente_comercial' THEN 0
                                       WHEN s.conc >= 0.25 THEN 1 ELSE 2 END) prio, max(k.pl) pl
        FROM k JOIN s USING (cnpj) GROUP BY 1 ORDER BY prio, pl DESC NULLS LAST""").fetchall()
    # cedentes dos exemplos de calibração primeiro
    try:
        rot = {r["cnpj"] for r in json.loads((Path(__file__).parent / "seed" / "mono_rotulos.json").read_text())}
        prim = {d for (d,) in con.execute("SELECT DISTINCT cedente_doc FROM cedente_mes k JOIN fundo f ON f.cnpj = k.cnpj "
                                          "AND k.dt = f.ultimo_informe WHERE k.cnpj IN (SELECT unnest(?))", [list(rot)]).fetchall()}
    except Exception:  # noqa: BLE001
        prim = set()
    if not todos:   # foco: cedentes de fundos concentrados (os de fundos pulverizados não mudam a análise)
        linhas = [x for x in linhas if x[1] <= 1]
    ordem = [c for c, _, _ in linhas if c in prim] + [c for c, _, _ in linhas if c not in prim]
    return [c for c in ordem if c not in feitos][:limite]


def buscar(limite: int = 100000, minutos: float | None = None) -> dict:
    """Consulta a fila alternando as duas fontes; grava a cada CNPJ (retomável)."""
    pend = fila(limite)
    fim = time.time() + minutos * 60 if minutos else None
    fontes = [_cnpjws, _receitaws]
    ultimo = {f.__name__: 0.0 for f in fontes}
    con = db()
    ok = falha = 0
    with httpx.Client(timeout=30, headers={"User-Agent": "analisador-fidc/1.0"}) as cli:
        for i, c in enumerate(pend):
            if fim and time.time() > fim:
                break
            gravou = False
            # até 2 tentativas por fonte; usa sempre a fonte que libera primeiro
            for _ in range(len(fontes) * 2):
                f = min(fontes, key=lambda x: ultimo[x.__name__])
                espera = ultimo[f.__name__] + INTERVALO - time.time()
                if espera > 0:
                    time.sleep(espera)
                ultimo[f.__name__] = time.time()
                try:
                    d = f(c, cli)
                except Exception as e:  # noqa: BLE001 - limite de taxa/instabilidade: tenta a outra fonte
                    log.warning("cedente %s via %s: %s", c, f.__name__, e)
                    if "429" in str(e) or "Too Many" in str(e):
                        ultimo[f.__name__] = time.time() + 60   # castigo: 1 min a mais nessa fonte
                    continue
                con.execute(f"INSERT OR REPLACE INTO cedente_info ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})", [
                    c, c[:8], d.get("razao_social"), d.get("nome_fantasia"), d.get("cnae"), d.get("cnae_desc"),
                    d.get("uf"), d.get("municipio"), d.get("abertura"), d.get("situacao"), d.get("natureza"),
                    json.dumps(d.get("socios") or [], ensure_ascii=False), d.get("fonte"),
                    datetime.now().isoformat(timespec="seconds"), d.get("erro"), d.get("capital_social")])
                con.commit()
                gravou = True
                break
            ok += gravou
            falha += not gravou
            if (ok + falha) % 25 == 0:
                log.info("cedentes: %d gravados, %d falhas, %d na fila", ok, falha, len(pend) - i - 1)
    return {"gravados": ok, "falhas": falha, "restantes": max(len(fila()), 0)}


def importar_seed() -> int:
    """Carrega o seed versionado no SQLite local (não sobrescreve consultas mais novas)."""
    if not SEED.exists():
        return 0
    linhas = json.loads(gzip.decompress(SEED.read_bytes()))
    con = db()
    con.executemany(f"INSERT OR IGNORE INTO cedente_info ({', '.join(COLS)}) VALUES ({', '.join('?' * len(COLS))})",
                    [[r.get(k) for k in COLS] for r in linhas])
    con.commit()
    return len(linhas)


COLS = ["cnpj", "raiz", "razao_social", "nome_fantasia", "cnae", "cnae_desc", "uf", "municipio", "abertura",
        "situacao", "natureza", "socios", "fonte", "consultado_em", "erro", "capital_social"]


def exportar_seed() -> Path:
    importar_seed()
    con = db()
    linhas = [dict(zip(COLS, r)) for r in con.execute(f"SELECT {', '.join(COLS)} FROM cedente_info ORDER BY cnpj")]
    SEED.write_bytes(gzip.compress(json.dumps(linhas, ensure_ascii=False).encode(), 9))
    return SEED


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--buscar", action="store_true")
    ap.add_argument("--limite", type=int, default=100000)
    ap.add_argument("--minutos", type=float)
    ap.add_argument("--seed", action="store_true")
    ap.add_argument("--fila", action="store_true")
    a = ap.parse_args()
    if a.fila:
        print(len(fila()))
    if a.buscar:
        importar_seed()
        print(json.dumps(buscar(a.limite, a.minutos), ensure_ascii=False))
    if a.seed:
        print(exportar_seed())


if __name__ == "__main__":
    main()
