"""Monocedentes e estruturas de benefício tributário.

1. Grupo do cedente: dentro de cada fundo, junta os CNPJs dos 9 maiores cedentes (Tab. I) que são do mesmo grupo
   econômico: mesma raiz de CNPJ, sócio em comum ou mesmo primeiro nome na razão social (cadastro da Receita em
   fidc.cedentes). Concentração = participação do maior grupo no total dos cedentes informados.
   Universo "monocedente": maior grupo >= 80% dos cedentes informados e >= 50% da carteira (corte inicial,
   calibrado com os exemplos).

2. Benefício tributário: a empresa cede recebíveis ao FIDC e os acionistas, como cotistas da subordinada, ficam com
   o ganho. Estágios: 1 = só subordinada e poucos cotistas; 2 = sênior + sub, ainda poucos cotistas; 3 = distribuído
   a mercado (muitos cotistas/séries) - nesse caso o histórico (quanto tempo ficou no estágio 1) é o que denuncia.
   Score por pontos, transparente (cada sinal aparece na tela). Nenhum sinal é regra: são indícios que se somam.

Sinais (pontos):
- histórico: meses só com subordinada e <= 3 cotistas (>= 6: +20; 3-5: +10)
- cotistas hoje: <= 3: +15; <= 10: +10; <= 30: +3
- taxa de gestão: <= 0,5% a.a.: +15; <= 1%: +5; > 1%: -20 (produto vendido a mercado cobra mais)
- remuneração da sênior: <= CDI + 4,5%: +5; > CDI + 5,5%: -10
- concentração no grupo: >= 95%: +10; 80-95%: +5; grupo com mais de um CNPJ (várias empresas do grupo): +5
- nome do fundo aparece no cedente ou nos sócios do cedente: +10 (nem sempre: às vezes a ideia é distanciar)
- fundo exclusivo: +5
- regulamento (leitura IA, fidc.mono_ia): subordinada do cedente ou do grupo/acionistas +20; de investidores de
  fundo restrito a um cotista/grupo +5; indício lido alto +10. A leitura só soma: regulamento genérico (sub de
  terceiros, vários cedentes) é comum em estruturas que querem distanciar a empresa do fundo.
Faixas: >= 45 provável; 30-44 possível; < 30 improvável. Cedente grande empresa (S.A. aberta ou capital social
>= R$ 1 bi) fica fora por ora; cedente instituição financeira/bancarizadora (CNAE 64 exceto holdings, ou nome de
banco/SCD/securitizadora/IP) também: "excluído (cedente financeiro)" - fundo de CCB/nota comercial: "excluído (grande empresa)" - pode ser FIDC cativo, antecipação a fornecedores etc.
"""
from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

from . import config

ROTULOS = Path(__file__).parent / "seed" / "mono_rotulos.json"
CORTE_MONO = 0.80        # maior grupo / total dos cedentes informados
CAPITAL_GRANDE = 1e9     # cedente com capital social >= R$ 1 bi ou S.A. aberta = "grande empresa": fica fora do
                         # benefício tributário por ora (FIDC cativo, antecipação a fornecedores etc.; pedido do Allan)
CORTE_CARTEIRA = 0.50    # e o maior grupo precisa ter pelo menos metade da carteira (fundo que informa um só cedente
                         # pequeno não vira monocedente)

# palavras que não identificam empresa nem fundo
GENERICAS = set("""
FUNDO FUNDOS INVESTIMENTO INVESTIMENTOS DIREITOS CREDITORIOS CREDITORIO FIDC FIC RESPONSABILIDADE LIMITADA LTDA
CLASSE UNICA FECHADA ABERTA SEGMENTO FINANCEIRO FINANCEIRA COMERCIAL COMERCIAIS CREDITO RECEBIVEIS NAO PADRONIZADOS
PADRONIZADO MULTISSETORIAL MULTICARTEIRA SENIOR SUBORDINADA MEZANINO RESP LIM DE DA DO DOS DAS E EM PARA COM
SA S A ME EPP EIRELI COMERCIO INDUSTRIA INDUSTRIAL DISTRIBUIDORA DISTRIBUIDOR SERVICOS SERVICO PARTICIPACOES
PARTICIPACAO EMPREENDIMENTOS ADMINISTRACAO GESTAO HOLDING GRUPO BRASIL BRASILEIRA DO BANCO MERCANTIL
AGRO AGRONEGOCIO MERCANTIS ESPECIAL CORPORATIVO REAL ESTATE CAPITAL ASSET TRUST I II III IV V VI VII VIII IX X
""".split())


def _norm(t: str | None) -> str:
    t = unicodedata.normalize("NFD", t or "").encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]+", " ", t)


def _tokens(t: str | None) -> list[str]:
    return [w for w in _norm(t).split() if len(w) >= 3 and w not in GENERICAS and not w.isdigit()]


def _cadastro() -> dict[str, dict]:
    db = config.DATA_DIR / "cedentes.sqlite"
    try:
        from . import cedentes
        cedentes.importar_seed()
    except Exception:  # noqa: BLE001 - sem seed/sem rede: segue só com a raiz do CNPJ
        pass
    if not db.exists():
        return {}
    con = sqlite3.connect(db)
    out = {}
    for c, rs, nf, soc, nat, cap, cnae, ativ, ab in con.execute(
            "SELECT cnpj, razao_social, nome_fantasia, socios, natureza, capital_social, cnae, cnae_desc, abertura "
            "FROM cedente_info WHERE erro IS NULL"):
        out[c] = {"razao": rs, "fantasia": nf, "natureza": nat, "capital": cap, "cnae": cnae, "atividade": ativ,
                  "abertura": ab,
                  "socios": [s.get("nome") for s in json.loads(soc or "[]") if s.get("nome")]}
    return out


_FIN_NOME = re.compile(r"SOCIEDADE DE CREDITO DIRETO|\bSCD\b|\bBANCO\b|INSTITUICAO\s+DE\s+PAGAMENTO|SECURITIZADORA|"
                       r"EMPRESTIMO ENTRE PESSOAS|CREDITO,? FINANCIAMENTO|DISTRIBUIDORA DE TITULOS|CORRETORA DE")


_PAGTO = re.compile(r"MEIOS? DE PAGAMENTO|CREDENCIADORA|UNIDADES? DE RECEBIVEIS|RECEBIVEIS DE CARTAO|ADQUIREN")


def fundo_pagamento(nome: str | None, categoria: str | None) -> str | None:
    """FIDC de recebíveis de cartão/meios de pagamento: funding de credenciadora/subadquirente/IP, não benefício
    tributário (MDR II, SumUp, Iugu, CloudWalk...). Pelo nome do fundo ou pela categoria cartão."""
    if categoria == "cartao":
        return "categoria cartão"
    m = _PAGTO.search(_norm(nome))
    return f"nome do fundo: {m.group(0).lower()}" if m else None


_PUB = re.compile(r"MUNICIPIO|ESTADO D[OAE] |AUTARQUIA|ADMINISTRACAO PUBLICA|ORGAO PUBLICO|FUNDACAO PUBLICA|PODER EXECUTIVO|"
                  r"PREFEITURA|SECRETARIA")
PUBLICAS = {"precatorios", "precatorios_federais", "setor_publico_outros", "judicial"}
# tipos de crédito que não são estrutura de benefício tributário (Allan, 15/10/2026): consignado, multicedente
# multissacado (concessão de crédito B2B) e financiamento de veículos
TIPOS_FORA = {"consignado_publico": "consignado", "consignado_privado": "consignado",
              "consignado_indefinido": "consignado", "multicedente_multissacado": "multicedente multissacado (MCMS)",
              "veiculos": "financiamento de veículos"}
ALERTAS = Path(__file__).parent / "seed" / "alertas_manuais.json"


def publico(c: dict, categoria: str | None) -> str | None:
    """Cedente ente público (município, estado, autarquia) ou fundo de créditos públicos/judiciais."""
    if _PUB.search(_norm(c.get("natureza"))) or _PUB.search(_norm(c.get("razao"))):
        return f"{c.get('razao')}: ente público"
    if categoria in PUBLICAS:
        return f"categoria {categoria}"
    return None


def financeiro(c: dict) -> str | None:
    """Cedente instituição financeira/bancarizadora (banco, SCD, SEP, financeira, securitizadora, IP): o fundo é de
    CCB/nota comercial ou de originação de terceiros, não de benefício tributário. CNAE 64, exceto holdings
    (6461-6463: holding do grupo da empresa é justamente o caso que interessa)."""
    cnae = re.sub(r"\D", "", c.get("cnae") or "")
    if cnae[:2] == "64" and cnae[:4] not in ("6461", "6462", "6463"):
        return f"CNAE {c.get('cnae')} ({c.get('atividade')})"
    if _FIN_NOME.search(_norm(c.get("razao"))):
        return "razão social de instituição financeira"
    return None


def _grupos(cedentes: list[tuple[str, float]], cad: dict) -> list[dict]:
    """Agrupa os cedentes de um fundo: raiz igual, sócio em comum ou mesmo 1º nome significativo da razão social."""
    pai = list(range(len(cedentes)))

    def raiz(i):
        while pai[i] != i:
            pai[i] = pai[pai[i]]
            i = pai[i]
        return i

    def unir(a, b):
        pai[raiz(a)] = raiz(b)

    info = []
    for doc, _ in cedentes:
        c = cad.get(doc, {})
        t = _tokens(c.get("razao"))
        info.append({"raiz": doc[:8] if len(doc) == 14 else doc, "socios": {_norm(s).strip() for s in c.get("socios", [])},
                     "nome1": t[0] if t else None})
    for i in range(len(cedentes)):
        for j in range(i + 1, len(cedentes)):
            a, b = info[i], info[j]
            if a["raiz"] == b["raiz"] or (a["socios"] & b["socios"]) or (a["nome1"] and a["nome1"] == b["nome1"]):
                unir(i, j)
    g = defaultdict(list)
    for i in range(len(cedentes)):
        g[raiz(i)].append(i)
    out = []
    for idx in g.values():
        docs = [cedentes[i][0] for i in idx]
        nome = next((cad[d]["razao"] for d in docs if d in cad and cad[d].get("razao")), None)
        c0 = next((cad[d] for d in docs if d in cad), {})
        out.append({"docs": docs, "pct": sum(cedentes[i][1] for i in idx), "nome": nome,
                    "cnae": c0.get("cnae"), "atividade": c0.get("atividade")})
    return sorted(out, key=lambda x: -x["pct"])


def _ligada(nome: str | None, doc: str, g1: dict | None, cad: dict, quem: str) -> str | None:
    """Prestador (consultoria, agente de cobrança) do grupo do cedente: o próprio cedente, mesma raiz de CNPJ,
    sócio em comum (Receita) ou mesmo 1º nome significativo da razão social."""
    if not nome or not g1:
        return None
    docs = g1["docs"]
    pc = cad.get(doc, {}) if doc else {}
    soc_g = {_norm(x).strip() for d in docs for x in cad.get(d, {}).get("socios", [])}
    soc_c = {_norm(x).strip() for x in pc.get("socios", [])}
    nom_g = {(_tokens(cad.get(d, {}).get("razao")) or [None])[0] for d in docs} - {None}
    if doc and doc in docs:
        return f"{quem} é o próprio cedente"
    if doc and doc[:8] in {d[:8] for d in docs}:
        return "mesma raiz de CNPJ do cedente"
    if soc_c & soc_g:
        return "sócio em comum com o cedente: " + ", ".join(sorted(soc_c & soc_g)[:2]).title()
    if (_tokens(pc.get("razao") or nome) or [None])[0] in nom_g:
        return "mesmo nome do cedente"
    return None


def _rotulos() -> dict[str, dict]:
    if not ROTULOS.exists():
        return {}
    return {r["cnpj"]: r for r in json.loads(ROTULOS.read_text())}


def prioridade() -> dict[str, int]:
    """Ordem das filas de leitura (foco atual: monocedentes): 0 = candidato a benefício tributário, 1 = monocedente,
    2 = categoria monocedente sem grupo fechado ainda. Quem não aparece fica depois."""
    from .db import df
    try:
        u = df("""SELECT m.cnpj, CASE WHEN m.monocedente AND m.bt_faixa IN ('provável', 'possível') THEN 0 WHEN m.monocedente THEN 1
                         ELSE 2 END AS k
                  FROM mono_fundo m JOIN fundo f USING (cnpj)
                  WHERE m.monocedente OR f.categoria = 'monocedente_comercial'""")
    except Exception:  # noqa: BLE001 - base antiga sem a tabela
        return {}
    return dict(zip(u.cnpj, u.k))


def ordenar(u, limite: int):
    """Ordena um DataFrame de fila (cnpj, pl e opcionalmente k = prioridade anterior) com monocedentes na frente."""
    pr = prioridade()
    u = u.copy()
    u["_mono"] = u.cnpj.map(pr).fillna(9)
    chaves = ["_mono"] + (["k"] if "k" in u.columns else []) + ["pl"]
    return u.sort_values(chaves, ascending=[True] * (len(chaves) - 1) + [False], na_position="last").head(limite)


def build_table(con) -> None:
    import pandas as pd
    cad = _cadastro()
    ced = con.execute("""
        SELECT k.cnpj, k.cedente_doc, k.pct FROM cedente_mes k JOIN fundo f ON f.cnpj = k.cnpj AND k.dt = f.ultimo_informe
        WHERE k.cedente_doc <> '99999999999999' AND k.pct > 0 ORDER BY k.cnpj, k.rank""").fetchall()
    por_fundo = defaultdict(list)
    for c, d, p in ced:
        por_fundo[c].append((d, float(p)))
    # histórico de estágio: meses só com subordinada e até 3 cotistas
    hist = {c: (m1, mt, ini) for c, m1, mt, ini in con.execute("""
        WITH s AS (SELECT cnpj, dt, bool_and(tipo = 'subordinada') so_sub FROM serie_mes
                   WHERE coalesce(pl_serie, 0) > 0 GROUP BY 1, 2)
        SELECT m.cnpj, count(*) FILTER (WHERE s.so_sub AND m.nr_cotistas <= 3), count(*), min(m.dt)
        FROM metricas_mes m JOIN s ON s.cnpj = m.cnpj AND s.dt = m.dt GROUP BY 1""").fetchall()}
    fundos = con.execute("""
        SELECT f.cnpj, f.nome, f.categoria, f.pl, f.gestor, m.nr_cotistas, r.estrutura, r.taxa_gestao, r.spread_senior_aa,
               r.rentab_subordinada_12m_pct_cdi, k.exclusivo, m.inad_90,
               (SELECT count(*) FROM serie_mes s WHERE s.cnpj = f.cnpj AND s.dt = f.ultimo_informe
                  AND coalesce(s.pl_serie, 0) > 0) AS n_series
        FROM fundo f LEFT JOIN metricas_mes m ON m.cnpj = f.cnpj AND m.dt = f.ultimo_informe
        LEFT JOIN fundo_resumo r ON r.cnpj = f.cnpj LEFT JOIN cadastro k ON k.cnpj = f.cnpj
        WHERE f.categoria NOT IN ('fic_fidc')""").df()
    rot = _rotulos()
    try:
        from . import mono_ia
        ia = mono_ia.linhas()
    except Exception:  # noqa: BLE001
        ia = {}
    try:
        cons = {c: (n, re.sub(r"\D", "", cj or ""), an, re.sub(r"\D", "", aj or "")[:14]) for c, n, cj, an, aj in con.execute(
            "SELECT cnpj, CASE WHEN consultoria_situacao = 'nomeada' THEN consultoria END, consultoria_cnpj, "
            "agente_cobranca, agente_cobranca_cnpj FROM consultoria_fundo").fetchall()}
    except Exception:  # noqa: BLE001 - base sem consultoria
        cons = {}
    alertas = {a["cnpj"]: a["descricao"] for a in json.loads(ALERTAS.read_text())} if ALERTAS.exists() else {}
    linhas, grupos_out = [], []
    for f in fundos.itertuples(index=False):
        cs = por_fundo.get(f.cnpj, [])
        gs = _grupos(cs, cad) if cs else []
        tot = sum(p for _, p in cs)
        g1 = gs[0] if gs else None
        conc = g1["pct"] / tot if g1 and tot else None
        for i, g in enumerate(gs):
            grupos_out.append({"cnpj": f.cnpj, "ordem": i + 1, "grupo": g["nome"], "cnpjs": ", ".join(g["docs"]),
                               "n_cnpjs": len(g["docs"]), "pct_carteira": g["pct"] / 100,
                               "cnae": g["cnae"], "atividade": g["atividade"],
                               "pct_informados": g["pct"] / tot if tot else None})
        m1, mt, ini = hist.get(f.cnpj, (0, 0, None))
        cot = f.nr_cotistas if f.nr_cotistas == f.nr_cotistas else None
        # nome do fundo x cedente/sócios
        tok_f = set(_tokens(f.nome))
        alvo = set()
        for d in (g1["docs"] if g1 else []):
            c = cad.get(d, {})
            for t in [c.get("razao"), c.get("fantasia"), *c.get("socios", [])]:
                alvo |= set(_tokens(t))
        nome_bate = sorted(tok_f & alvo)

        grande = fin = pub = None
        pub = publico({}, f.categoria)
        for d in (g1["docs"] if g1 else []):
            c = cad.get(d, {})
            pub = pub or publico(c, None)
            fin = fin or financeiro(c) and f"{c.get('razao')}: {financeiro(c)}"
            if "ABERTA" in _norm(c.get("natureza")):
                grande = f"{c.get('razao')}: S.A. aberta"
            elif (c.get("capital") or 0) >= CAPITAL_GRANDE:
                grande = f"{c.get('razao')}: capital social R$ {c['capital'] / 1e9:,.1f} bi".replace(",", "X").replace(".", ",").replace("X", ".")
            if grande:
                break
        pts, sinais = 0, []

        def s(p, txt):
            nonlocal pts
            pts += p
            sinais.append(f"{'+' if p >= 0 else ''}{p} {txt}")

        if m1 >= 6:
            s(20, f"{m1} meses só com subordinada e até 3 cotistas")
        elif m1 >= 3:
            s(10, f"{m1} meses só com subordinada e até 3 cotistas")
        if cot is not None:
            if cot <= 3:
                s(15, f"{int(cot)} cotista(s)")
            elif cot <= 10:
                s(10, f"{int(cot)} cotistas")
            elif cot <= 30:
                s(3, f"{int(cot)} cotistas")
        tg = f.taxa_gestao if f.taxa_gestao == f.taxa_gestao else None
        if tg is not None:
            if tg <= 0.005:
                s(15, f"taxa de gestão {tg * 100:.2f}% a.a.")
            elif tg <= 0.01:
                s(5, f"taxa de gestão {tg * 100:.2f}% a.a.")
            else:
                s(-20, f"taxa de gestão {tg * 100:.2f}% a.a. (alta para estrutura proprietária)")
        sp = f.spread_senior_aa if f.spread_senior_aa == f.spread_senior_aa else None
        if sp is not None:
            if sp <= 0.045:
                s(5, f"sênior a CDI + {sp * 100:.1f}% a.a.")
            elif sp > 0.055:
                s(-10, f"sênior a CDI + {sp * 100:.1f}% a.a. (remuneração de mercado)")
        if conc is not None:
            if conc >= 0.95:
                s(10, f"maior grupo = {conc:.0%} dos cedentes")
            elif conc >= CORTE_MONO:
                s(5, f"maior grupo = {conc:.0%} dos cedentes")
            if g1 and len(g1["docs"]) > 1:
                s(5, f"{len(g1['docs'])} CNPJs do mesmo grupo cedendo")
        if nome_bate:
            s(10, "nome do fundo no cedente/sócios: " + ", ".join(nome_bate[:3]))
        if isinstance(f.exclusivo, str) and f.exclusivo.upper().startswith("S"):
            s(5, "fundo exclusivo")
        # leitura do regulamento (IA): quem é dono da subordinada pesa mais que qualquer número do informe
        x = ia.get(f.cnpj) or {}
        sub = x.get("subordinada_subscritor")
        if sub in ("cedente", "acionistas_ou_grupo_do_cedente"):
            s(20, "regulamento: subordinada do " + ("cedente" if sub == "cedente" else "grupo/acionistas do cedente"))
        if x.get("cotista_exclusivo_ou_grupo") is True and not (isinstance(f.exclusivo, str) and f.exclusivo.upper().startswith("S")):
            s(5, "regulamento: fundo restrito a um cotista/grupo")
        ind = x.get("indicio_beneficio_tributario")
        if ind == "alto":
            s(10, "leitura do regulamento: indício alto")
        # indício "baixo" não tira ponto: regulamento genérico é comum justamente para distanciar a empresa do fundo
        # (Fiducia e JPA Agro, confirmados pelo time, foram lidos como "baixo")

        estrutura = f.estrutura
        if cot is not None and estrutura == "classe única" and cot <= 5:
            estagio = 1
        elif cot is not None and estrutura == "classes" and cot <= 10:
            estagio = 2
        elif m1 >= 3:
            estagio = 3
        else:
            estagio = None
        faixa = "provável" if pts >= 45 else "possível" if pts >= 30 else "improvável"
        pag = fundo_pagamento(f.nome, f.categoria)
        if pag and not fin:
            fin = "fundo de recebíveis de meios de pagamento/cartão (" + pag + ")"
        if f.categoria in TIPOS_FORA and not pub:
            faixa = "excluído (tipo de crédito)"
            sinais.insert(0, "fora: " + TIPOS_FORA[f.categoria])
        elif pub:
            faixa = "excluído (cedente público)"
            sinais.insert(0, "fora: crédito público/judicial - " + pub)
        elif fin:
            faixa = "excluído (cedente financeiro)"
            sinais.insert(0, "fora: cedente instituição financeira/bancarizadora (CCB/nota comercial) - " + fin)
        elif grande:
            faixa = "excluído (grande empresa)"
            sinais.insert(0, "fora: cedente grande empresa - " + grande)
        # consultoria de crédito x grupo do cedente: mesma raiz, sócio em comum ou mesmo nome
        cn, cdoc, an, adoc = cons.get(f.cnpj, (None, "", None, ""))
        ccad = cad.get(cdoc, {}) if cdoc else {}
        ligada = _ligada(cn, cdoc, g1, cad, "a consultoria")
        cob_ligada = _ligada(an, adoc, g1, cad, "o agente de cobrança")
        r = rot.get(f.cnpj, {})
        linhas.append({
            "cnpj": f.cnpj, "mono_grupo": g1["nome"] if g1 else None,
            "mono_grupo_cnpjs": len(g1["docs"]) if g1 else None,
            "mono_conc_grupo": conc, "mono_conc_carteira": g1["pct"] / 100 if g1 else None,
            "mono_cedentes_informados": len(cs),
            "monocedente": bool(conc is not None and conc >= CORTE_MONO and g1["pct"] / 100 >= CORTE_CARTEIRA),
            "bt_meses_estagio1": m1, "bt_inicio": ini, "bt_estagio": estagio, "bt_score": pts, "bt_faixa": faixa,
            "bt_sinais": " | ".join(sinais), "bt_nome_cedente": ", ".join(nome_bate) or None,
            "bt_rotulo": r.get("rotulo"), "bt_rotulo_obs": r.get("obs"),
            "mono_grupo_cnae": g1["cnae"] if g1 else None, "mono_grupo_atividade": g1["atividade"] if g1 else None,
            "bt_ia_sub": sub, "bt_ia_sub_nome": x.get("subordinada_subscritor_nome"),
            "bt_ia_coobrigacao": x.get("coobrigacao_cedente"), "bt_ia_indicio": ind,
            "bt_ia_justificativa": x.get("justificativa"), "bt_ia_trecho": x.get("trecho"), "bt_ia_pagina": x.get("pagina"),
            "bt_ia_cedente": x.get("cedente_nome"), "bt_ia_objetivo": x.get("objetivo"),
            "mono_consultoria_ligada": ligada, "mono_consultoria_cnae": ccad.get("cnae"),
            "mono_consultoria_atividade": ccad.get("atividade"), "mono_consultoria_abertura": ccad.get("abertura"),
            "mono_consultoria_capital": ccad.get("capital"),
            "mono_cobranca_ligada": cob_ligada, "bt_alerta": alertas.get(f.cnpj),
        })
    df = pd.DataFrame(linhas)
    con.register("_m", df)
    con.execute("CREATE OR REPLACE TABLE mono_fundo AS SELECT * FROM _m")
    con.unregister("_m")
    dg = pd.DataFrame(grupos_out, columns=["cnpj", "ordem", "grupo", "cnpjs", "n_cnpjs", "pct_carteira", "pct_informados",
                                           "cnae", "atividade"])
    con.register("_g", dg)
    con.execute("CREATE OR REPLACE TABLE mono_grupo AS SELECT * FROM _g")
    con.unregister("_g")


if __name__ == "__main__":
    import duckdb
    c = duckdb.connect(str(config.DB_PATH))
    build_table(c)
    print(c.execute("SELECT bt_faixa, count(*) FROM mono_fundo WHERE monocedente GROUP BY 1").fetchall())
