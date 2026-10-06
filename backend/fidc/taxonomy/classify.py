"""Classificação dos FIDCs pela taxonomia em categorias.yaml.

As características usadas vêm do informe mais recente de cada fundo (Tabela II
para segmentos, Tabela I para cedentes e cotas de FIDC) e dos últimos 12 meses
(Tabela VII para aquisição de créditos inadimplentes).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd
import yaml

from .. import appdb, config

SEGMENTOS = ["A", "B", "C1", "C2", "C3", "D1", "D2", "D3", "D4", "E", "F1", "F2", "F3", "F4",
             "F5", "F6", "F7", "F8", "G", "H1", "H2", "I1", "I2", "I3", "I4", "J", "K"]


def normalize(text: str | None) -> str:
    if not text:
        return ""
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", t.upper()).strip()


@dataclass
class Regra:
    nome_inclui: list[re.Pattern] = field(default_factory=list)
    nome_exclui: list[re.Pattern] = field(default_factory=list)
    segmentos: list[str] = field(default_factory=list)
    segmento_pct: float | None = None
    top1_cedente_max: float | None = None
    top1_cedente_min: float | None = None
    cotas_fidc_min: float | None = None
    aquisicao_inad_min: float | None = None
    sem_carteira: bool = False
    sem_cedente: bool = False
    pmr_min: float | None = None
    pmr_max: float | None = None
    taxa_min: float | None = None
    taxa_max: float | None = None
    reg_min: dict[str, int] = field(default_factory=dict)
    reg_max: dict[str, int] = field(default_factory=dict)
    reg_maior: list[tuple[str, list[str]]] = field(default_factory=list)
    com_regulamento: bool = False
    revisar: bool = False

    @classmethod
    def from_dict(cls, d: dict) -> "Regra":
        seg = d.get("segmento_min") or {}
        return cls(
            nome_inclui=[re.compile(p) for p in d.get("nome_inclui", [])],
            nome_exclui=[re.compile(p) for p in d.get("nome_exclui", [])],
            segmentos=list(seg.get("segmentos", [])),
            segmento_pct=seg.get("pct"),
            top1_cedente_max=d.get("top1_cedente_max"),
            top1_cedente_min=d.get("top1_cedente_min"),
            cotas_fidc_min=d.get("cotas_fidc_min"),
            aquisicao_inad_min=d.get("aquisicao_inad_min"),
            sem_carteira=bool(d.get("sem_carteira", False)),
            sem_cedente=bool(d.get("sem_cedente", False)),
            pmr_min=d.get("pmr_min"), pmr_max=d.get("pmr_max"),
            taxa_min=d.get("taxa_min"), taxa_max=d.get("taxa_max"),
            reg_min=dict(d.get("reg_min") or {}), reg_max=dict(d.get("reg_max") or {}),
            reg_maior=[(a, [b] if isinstance(b, str) else list(b)) for a, b in (d.get("reg_maior") or {}).items()],
            com_regulamento=bool(d.get("com_regulamento", False)),
            revisar=bool(d.get("revisar", False)),
        )

    def match(self, f: dict) -> bool:
        nome = f["nome_norm"]
        if self.nome_inclui and not any(p.search(nome) for p in self.nome_inclui):
            return False
        if self.nome_exclui and any(p.search(nome) for p in self.nome_exclui):
            return False
        if self.segmentos:
            share = sum(f.get(f"sh_{s}") or 0 for s in self.segmentos)
            if share < (self.segmento_pct or 0.5):
                return False
        top1 = f.get("top1_cedente_pct")
        if self.top1_cedente_max is not None and (top1 is None or pd.isna(top1) or top1 > self.top1_cedente_max):
            return False
        if self.top1_cedente_min is not None and (top1 is None or pd.isna(top1) or top1 < self.top1_cedente_min):
            return False
        if self.cotas_fidc_min is not None and not (f.get("sh_cotas_fidc") or 0) >= self.cotas_fidc_min:
            return False
        if self.aquisicao_inad_min is not None and not (f.get("sh_aquis_inad") or 0) >= self.aquisicao_inad_min:
            return False
        if self.sem_carteira and not f.get("sem_carteira"):
            return False
        if self.sem_cedente and not (top1 is None or pd.isna(top1)):
            return False
        for lim, campo, maior in ((self.pmr_min, "pmr", True), (self.pmr_max, "pmr", False),
                                  (self.taxa_min, "taxa_ix", True), (self.taxa_max, "taxa_ix", False)):
            if lim is None:
                continue
            v = f.get(campo)
            if v is None or pd.isna(v) or (v < lim if maior else v > lim):
                return False
        if self.reg_min or self.reg_max or self.reg_maior or self.com_regulamento:
            tem = bool(f.get("tem_reg"))
            if (self.reg_min or self.reg_maior or self.com_regulamento) and not tem:
                return False

            def sig(k):  # "a+b" soma sinais
                return sum(f.get(f"reg_{x.strip()}") or 0 for x in k.split("+"))
            if any(sig(k) < n for k, n in self.reg_min.items()):
                return False
            if tem and any(sig(k) > n for k, n in self.reg_max.items()):   # sem regulamento lido: não restringe
                return False
            if any(sig(a) <= sum(sig(b) for b in bs) for a, bs in self.reg_maior):
                return False
        return True


@dataclass
class Categoria:
    id: str
    nome: str
    grupo: str
    regras: list[Regra]
    alias_de: str | None = None   # bloco de regras extra que classifica numa categoria já existente


def load_taxonomy(path=None) -> list[Categoria]:
    data = yaml.safe_load(open(path or config.TAXONOMY_FILE, encoding="utf-8"))
    cats = []
    for c in data["categorias"]:
        cats.append(Categoria(c["id"], c["nome"], c.get("grupo", "Outros"),
                              [Regra.from_dict(r) for r in c.get("regras", [])], c.get("alias_de")))
    ids = [c.id for c in cats]
    if len(ids) != len(set(ids)):
        raise ValueError("ids de categoria duplicados em categorias.yaml")
    return cats


def classify_one(f: dict, cats: list[Categoria]) -> tuple[Categoria, Regra | None, int]:
    for c in cats:
        for i, r in enumerate(c.regras):
            if r.match(f):
                return c, r, i
    return cats[-1], None, -1


FEATURES_SQL = f"""
WITH ult AS (
  SELECT * FROM fundo_mes
  QUALIFY row_number() OVER (PARTITION BY cnpj ORDER BY dt DESC) = 1
), aq AS (
  SELECT cnpj, sum(aquisicoes_inad) / nullif(sum(aquisicoes), 0) AS sh_aquis_inad
  FROM fundo_mes f
  WHERE dt > (SELECT max(dt) FROM fundo_mes g WHERE g.cnpj = f.cnpj) - INTERVAL 12 MONTH
  GROUP BY cnpj
), ced AS (
  SELECT cnpj, dt, max(pct) FILTER (WHERE rank = 1) AS top1_cedente_pct FROM cedente_mes GROUP BY ALL
), op AS (
  SELECT m.cnpj, m.prazo_medio_dias AS pmr, c.m22_taxa_ix_aa AS taxa_ix
  FROM metricas_mes m LEFT JOIN casa_mes c USING (cnpj, dt)
  QUALIFY row_number() OVER (PARTITION BY m.cnpj ORDER BY m.dt DESC) = 1
)
SELECT u.cnpj, u.nome, u.dt,
       {', '.join(f'coalesce(u.seg_{s}, 0) AS seg_{s}' for s in SEGMENTOS)},
       u.cotas_fidc, u.ativo, c.top1_cedente_pct, aq.sh_aquis_inad, op.pmr, op.taxa_ix
FROM ult u LEFT JOIN ced c USING (cnpj, dt) LEFT JOIN aq USING (cnpj) LEFT JOIN op USING (cnpj)
"""


def _sinais_regulamento(con) -> pd.DataFrame | None:
    try:
        s = con.execute("""SELECT r.cnpj, s.sinal, s.n FROM regulamento r LEFT JOIN regulamento_sinal s USING (cnpj)
                           WHERE r.status = 'ok'""").df()
    except Exception:  # noqa: BLE001 - base sem regulamentos
        return None
    if s.empty:
        return None
    p = s.dropna(subset=["sinal"]).pivot_table(index="cnpj", columns="sinal", values="n", aggfunc="sum")
    p = p.reindex(s.cnpj.unique()).fillna(0).add_prefix("reg_").reset_index()
    p["tem_reg"] = True
    return p


def features(con) -> pd.DataFrame:
    df = con.execute(FEATURES_SQL).df()
    sig = _sinais_regulamento(con)
    if sig is not None:
        df = df.merge(sig, on="cnpj", how="left")
    df["tem_reg"] = df["tem_reg"].fillna(False).astype(bool) if "tem_reg" in df else False
    seg = df[[f"seg_{s}" for s in SEGMENTOS]].clip(lower=0)
    total = seg.sum(axis=1)
    for s in SEGMENTOS:
        df[f"sh_{s}"] = (seg[f"seg_{s}"] / total).where(total > 0, 0.0)
    df["sem_carteira"] = total <= 0
    df["sh_cotas_fidc"] = (df["cotas_fidc"] / df["ativo"]).where(df["ativo"] > 0, 0.0)
    df["nome_norm"] = df["nome"].map(normalize)
    seg_cols = [f"sh_{s}" for s in SEGMENTOS]
    df["segmento_principal"] = df[seg_cols].idxmax(axis=1).str.replace("sh_", "", regex=False)
    df.loc[df["sem_carteira"], "segmento_principal"] = None
    df["segmento_principal_pct"] = df[seg_cols].max(axis=1)
    return df


def classify_frame(df: pd.DataFrame, cats: list[Categoria] | None = None,
                   overrides: dict[str, str] | None = None) -> pd.DataFrame:
    cats = cats or load_taxonomy()
    by_id = {c.id: c for c in cats}
    overrides = overrides or {}
    rows = []
    for f in df.to_dict("records"):
        if f["cnpj"] in overrides and overrides[f["cnpj"]] in by_id:
            c = by_id[overrides[f["cnpj"]]]
            rows.append((f["cnpj"], c.id, c.nome, c.grupo, "manual", False))
            continue
        c, r, i = classify_one(f, cats)
        origem = (f"{c.id} regra {i + 1}" if c.alias_de else f"regra {i + 1}") if r else "padrão"
        if c.alias_de:
            c = by_id[c.alias_de]
        rows.append((f["cnpj"], c.id, c.nome, c.grupo, origem, bool(r.revisar) if r else True))
    out = pd.DataFrame(rows, columns=["cnpj", "categoria", "categoria_nome", "grupo", "origem", "revisar"])
    return out.merge(df[["cnpj", "segmento_principal", "segmento_principal_pct", "top1_cedente_pct",
                         "sh_cotas_fidc", "sh_aquis_inad"]], on="cnpj", how="left")


def build_table(con) -> None:
    out = classify_frame(features(con), overrides=appdb.overrides())
    con.register("_cls", out)
    con.execute("CREATE OR REPLACE TABLE classificacao AS SELECT * FROM _cls")
    con.unregister("_cls")
    cats = load_taxonomy()
    tax = pd.DataFrame([(i, c.id, c.nome, c.grupo) for i, c in enumerate(cats) if not c.alias_de],
                       columns=["ordem", "categoria", "categoria_nome", "grupo"])
    con.register("_tax", tax)
    con.execute("CREATE OR REPLACE TABLE categoria AS SELECT * FROM _tax")
    con.unregister("_tax")
