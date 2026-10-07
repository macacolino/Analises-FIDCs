"""Monta a base analítica (DuckDB) a partir dos parquets brutos da CVM.

Tabelas geradas
---------------
fundo_mes     1 linha por fundo/classe x mês, campos harmonizados (pré e pós Res. CVM 175)
serie_mes     1 linha por fundo x mês x série/subclasse (cotas, PL da série, rentabilidade)
cedente_mes   top 9 cedentes informados na Tabela I
metricas_mes  indicadores calculados (inadimplência, PDD, subordinação, roll rates, proxies de safra)
classificacao categoria de cada fundo (taxonomia em taxonomy/categorias.yaml)
setor_mes     agregados por categoria x mês

A base é escrita num arquivo temporário e trocada atomicamente no fim, para a
API continuar lendo a versão anterior enquanto o build roda.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import duckdb

from .. import config
from .. import agente_regulamento, regulamentos
from ..taxonomy import classify
from . import bcb, casa, cvm_cadastro, cvm_ofertas, qualidade

log = logging.getLogger(__name__)


class _Src:
    """Leitura de uma tabela bruta, com acesso seguro a colunas que podem não existir."""

    def __init__(self, con: duckdb.DuckDBPyConnection, tab: str):
        self.tab = tab
        self.path = str(config.PARQUET_DIR / tab / "*.parquet")
        self.cols = {r[0] for r in con.execute(
            f"DESCRIBE SELECT * FROM read_parquet('{self.path}', union_by_name=true)").fetchall()}

    def scan(self) -> str:
        return f"read_parquet('{self.path}', union_by_name=true)"

    def txt(self, *names: str) -> str:
        present = [f'"{n}"' for n in names if n in self.cols]
        if not present:
            return "NULL::VARCHAR"
        return present[0] if len(present) == 1 else f"coalesce({', '.join(present)})"

    def num(self, *names: str) -> str:
        """Soma numérica das colunas existentes (NULL se nenhuma estiver preenchida)."""
        present = [n for n in names if n in self.cols]
        if not present:
            return "NULL::DOUBLE"
        parts = [f'TRY_CAST("{n}" AS DOUBLE)' for n in present]
        if len(parts) == 1:
            return parts[0]
        nn = " AND ".join(f"{p} IS NULL" for p in parts)
        return f"CASE WHEN {nn} THEN NULL ELSE {' + '.join(f'coalesce({p}, 0)' for p in parts)} END"

    def key(self) -> str:
        cnpj = self.txt("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO")
        return (f"lpad(regexp_replace({cnpj}, '[^0-9]', '', 'g'), 14, '0') AS cnpj, "
                f"TRY_CAST(DT_COMPTC AS DATE) AS dt")


def _single(con, tab: str, select: str, order: str = "") -> str:
    """Tabela com 1 linha por fundo/mês: dedup preferindo o arquivo mais recente."""
    s = _Src(con, tab)
    tiebreak = f", {order} DESC NULLS LAST" if order else ""
    return f"""
      SELECT * EXCLUDE (_src) FROM (
        SELECT {s.key()}, _src, {select.format(s=s)}
        FROM {s.scan()}
      ) WHERE cnpj IS NOT NULL AND dt IS NOT NULL
      QUALIFY row_number() OVER (PARTITION BY cnpj, dt ORDER BY _src DESC{tiebreak}) = 1
    """


def _buckets(s: _Src, prefix: str, letter: str, kind: str) -> list[str]:
    """Faixas de prazo das Tabelas V/VI. kind: PRAZO_VENC, INAD, ANTECIPADO."""
    sfx = ["30", "60", "90", "120", "150", "180", "360", "720", "1080", "MAIOR_1080"]
    return [f"TAB_{prefix}_{letter}{i + 1}_VL_{kind}_{x}" for i, x in enumerate(sfx)]


ITENS = [(1, "CRED_VENC_AD"), (2, "CRED_VENC_INAD"), (3, "CRED_INAD"), (4, "CRED_DIRCRED_PERFM"),
         (5, "CRED_VENCIDO_PENDENTE"), (6, "CRED_EMP_RECUP"), (7, "CRED_RECEITA_PUBLICA"),
         (8, "CRED_ACAO_JUDIC"), (9, "CRED_FATOR_RISCO"), (10, "CRED_DIVERSO")]


def build_fundo_mes(con) -> None:
    i = _Src(con, "I")
    cedente_cols = []
    for k in range(1, 10):
        doc = i.txt(f"TAB_I2A12_CPF_CNPJ_CEDENTE_{k}", f"TAB_I2B12_CPF_CNPJ_CEDENTE_{k}",
                    f"TAB_I2B1_CPF_CNPJ_CEDENTE_{k}")
        pr = (f"coalesce({i.num(f'TAB_I2A12_PR_CEDENTE_{k}')}, {i.num(f'TAB_I2B12_PR_CEDENTE_{k}')}, "
              f"{i.num(f'TAB_I2B1_PR_CEDENTE_{k}')})")
        cedente_cols.append(f"{doc} AS ced_doc_{k}, {pr} AS ced_pr_{k}")

    con.execute("CREATE TABLE t_i AS " + _single(con, "I", f"""
        {i.txt('DENOM_SOCIAL')} AS nome,
        {i.txt('TP_FUNDO_CLASSE')} AS tp_fundo_classe,
        {i.txt('CLASSE_UNICA')} AS classe_unica,
        {i.txt('ADMIN')} AS admin,
        lpad(regexp_replace({i.txt('CNPJ_ADMIN')}, '[^0-9]', '', 'g'), 14, '0') AS cnpj_admin,
        {i.txt('CONDOM')} AS condominio,
        {i.txt('FUNDO_EXCLUSIVO')} AS exclusivo,
        {i.num('TAB_I_VL_ATIVO')} AS ativo,
        {i.num('TAB_I1_VL_DISP')} AS disponibilidades,
        {i.num('TAB_I2_VL_CARTEIRA')} AS carteira,
        {i.num('TAB_I2A_VL_DIRCRED_RISCO')} AS dc_com_risco,
        {i.num('TAB_I2B_VL_DIRCRED_SEM_RISCO')} AS dc_sem_risco,
        {i.num('TAB_I2A1_VL_CRED_VENC_AD', 'TAB_I2B1_VL_CRED_VENC_AD')} AS dc_a_vencer_adimplente,
        {i.num('TAB_I2A2_VL_CRED_VENC_INAD', 'TAB_I2B2_VL_CRED_VENC_INAD')} AS dc_a_vencer_c_parc_inad,
        {i.num('TAB_I2A21_VL_TOTAL_PARCELA_INAD', 'TAB_I2B21_VL_TOTAL_PARCELA_INAD')} AS dc_parcelas_inad,
        {i.num('TAB_I2A3_VL_CRED_INAD', 'TAB_I2B3_VL_CRED_INAD')} AS dc_inadimplente,
        {i.num('TAB_I2A4_VL_CRED_DIRCRED_PERFM', 'TAB_I2B4_VL_CRED_DIRCRED_PERFM')} AS dc_a_performar,
        {i.num('TAB_I2A6_VL_CRED_EMP_RECUP', 'TAB_I2B6_VL_CRED_EMP_RECUP')} AS dc_empresa_recup,
        {i.num('TAB_I2A8_VL_CRED_ACAO_JUDIC', 'TAB_I2B8_VL_CRED_ACAO_JUDIC')} AS dc_acao_judicial,
        abs({i.num('TAB_I2A11_VL_REDUCAO_RECUP', 'TAB_I2B11_VL_REDUCAO_RECUP')}) AS pdd,
        abs({i.num('TAB_I2A11_VL_REDUCAO_RECUP')}) AS pdd_com_risco,
        abs({i.num('TAB_I2B11_VL_REDUCAO_RECUP')}) AS pdd_sem_risco,
        {i.num('TAB_I2A5_VL_CRED_VENCIDO_PENDENTE', 'TAB_I2B5_VL_CRED_VENCIDO_PENDENTE')} AS dc_vencido_na_cessao,
        -- soma dos itens 1-10 (para checar a identidade itens - PDD = total)
        {i.num(*[f'TAB_I2A{k}_VL_{n}' for k, n in ITENS])} AS soma_itens_com_risco,
        {i.num(*[f'TAB_I2B{k}_VL_{n}' for k, n in ITENS])} AS soma_itens_sem_risco,
        {i.num('TAB_I2C1_VL_DEBENTURE')} AS debentures,
        {i.num('TAB_I2C2_VL_CRI')} AS cri,
        {i.num('TAB_I2C3_VL_NP_COMERC')} AS np_comercial,
        {i.num('TAB_I2C4_VL_LETRA_FINANC')} AS letras_financeiras,
        {i.num('TAB_I2C5_VL_COTA_FIF', 'TAB_I2C5_VL_COTA_FUNDO_ICVM555')} AS cotas_fundos,
        {i.num('TAB_I4_VL_OUTRO_ATIVO')} AS outros_ativos,
        {i.num('TAB_I4A_VL_CPRAZO')} AS outros_ativos_cp,
        {i.num('TAB_I4B_VL_LPRAZO')} AS outros_ativos_lp,
        {i.num('TAB_I2C_VL_VLMOB')} AS valores_mobiliarios,
        {i.num('TAB_I2D_VL_TITPUB_FED')} AS titulos_publicos,
        {i.num('TAB_I2E_VL_CDB')} AS cdb,
        {i.num('TAB_I2F_VL_OPER_COMPROM')} AS compromissadas,
        {i.num('TAB_I2H_VL_COTA_FIDC', 'TAB_I2I_VL_COTA_FIDC_NP')} AS cotas_fidc,
        {', '.join(cedente_cols)}
    """, order="ativo"))

    ii = _Src(con, "II")
    seg = {  # folhas mutuamente exclusivas da Tabela II
        "A": "TAB_II_A_VL_INDUST", "B": "TAB_II_B_VL_IMOBIL",
        "C1": "TAB_II_C1_VL_COMERC", "C2": "TAB_II_C2_VL_VAREJO", "C3": "TAB_II_C3_VL_ARREND",
        "D1": "TAB_II_D1_VL_SERV", "D2": "TAB_II_D2_VL_SERV_PUBLICO",
        "D3": "TAB_II_D3_VL_SERV_EDUC", "D4": "TAB_II_D4_VL_ENTRET",
        "E": "TAB_II_E_VL_AGRONEG",
        "F1": "TAB_II_F1_VL_CRED_PESSOA", "F2": "TAB_II_F2_VL_CRED_PESSOA_CONSIG",
        "F3": "TAB_II_F3_VL_CRED_CORP", "F4": "TAB_II_F4_VL_MIDMARKET", "F5": "TAB_II_F5_VL_VEICULO",
        "F6": "TAB_II_F6_VL_IMOBIL_EMPRESA", "F7": "TAB_II_F7_VL_IMOBIL_RESID", "F8": "TAB_II_F8_VL_OUTRO",
        "G": "TAB_II_G_VL_CREDITO", "H1": "TAB_II_H1_VL_PESSOA", "H2": "TAB_II_H2_VL_CORP",
        "I1": "TAB_II_I1_VL_PRECAT", "I2": "TAB_II_I2_VL_TRIBUT", "I3": "TAB_II_I3_VL_ROYALTIES",
        "I4": "TAB_II_I4_VL_OUTRO", "J": "TAB_II_J_VL_JUDICIAL", "K": "TAB_II_K_VL_MARCA",
    }
    con.execute("CREATE TABLE t_ii AS " + _single(con, "II", f"""
        {ii.num('TAB_II_VL_CARTEIRA')} AS seg_total,
        {', '.join(f"{ii.num(c)} AS seg_{k}" for k, c in seg.items())}
    """, order="seg_total"))

    iii = _Src(con, "III")
    con.execute("CREATE TABLE t_iii AS " + _single(con, "III", f"{iii.num('TAB_III_VL_PASSIVO')} AS passivo"))

    iv = _Src(con, "IV")
    con.execute("CREATE TABLE t_iv AS " + _single(con, "IV", f"""
        {iv.num('TAB_IV_A_VL_PL')} AS pl, {iv.num('TAB_IV_B_VL_PL_MEDIO')} AS pl_medio
    """, order="pl"))

    # Tabelas V (com aquisição de risco) e VI (sem) somadas
    v, vi = _Src(con, "V"), _Src(con, "VI")
    labels = ["30", "60", "90", "120", "150", "180", "360", "720", "1080", "1080p"]
    for name, s, prefix in (("t_v", v, "V"), ("t_vi", vi, "VI")):
        av = _buckets(s, prefix, "A", "PRAZO_VENC")
        av[-1] = f"TAB_{prefix}_A10_VL_PRAZO_VENC_MAIOR_1080"
        bi = _buckets(s, prefix, "B", "INAD")
        bi[-1] = f"TAB_{prefix}_B10_VL_INAD_MAIOR_1080"
        cols = ", ".join(
            [f"{s.num(c)} AS av_{lb}" for c, lb in zip(av, labels)]
            + [f"{s.num(c)} AS in_{lb}" for c, lb in zip(bi, labels)]
            + [f"{s.num(f'TAB_{prefix}_C_VL_DIRCRED_ANTECIPADO')} AS antecipado",
               f"{s.num(f'TAB_{prefix}_A_VL_DIRCRED_PRAZO')} AS av_total_inf",
               f"{s.num(f'TAB_{prefix}_B_VL_DIRCRED_INAD')} AS in_total_inf"])
        con.execute(f"CREATE TABLE {name} AS " + _single(con, prefix, cols))

    vii = _Src(con, "VII")
    con.execute("CREATE TABLE t_vii AS " + _single(con, "VII", f"""
        {vii.num('TAB_VII_A1_2_VL_DIRCRED_RISCO', 'TAB_VII_A2_2_VL_DIRCRED_SEM_RISCO')} AS aquisicoes,
        {vii.num('TAB_VII_A5_2_VL_DIRCRED_INAD')} AS aquisicoes_inad,
        {vii.num('TAB_VII_B1_2_VL_CEDENTE')} AS alienacao_cedente,
        {vii.num('TAB_VII_B2_2_VL_PREST')} AS alienacao_prestador,
        {vii.num('TAB_VII_B3_2_VL_TERCEIRO')} AS alienacao_terceiro,
        {vii.num('TAB_VII_C_2_VL_SUBST')} AS substituicoes,
        {vii.num('TAB_VII_D_2_VL_RECOMPRA')} AS recompras,
        {vii.num('TAB_VII_D_3_VL_CONTAB_RECOMPRA')} AS recompras_contabil,
        {vii.num('TAB_VII_D_1_QT_RECOMPRA')} AS recompras_qt,
        {vii.num('TAB_VII_A1_2_VL_DIRCRED_RISCO')} AS aquisicoes_com_risco,
        {vii.num('TAB_VII_A3_2_VL_DIRCRED_VENC_AD')} AS aquisicoes_a_vencer_adimpl
    """))

    ix = _Src(con, "IX")
    con.execute("CREATE TABLE t_ix AS " + _single(con, "IX", f"""
        {ix.num('TAB_IX_A1_1_2_COMPRA_MEDIA')} AS taxa_desconto_compra,
        {ix.num('TAB_IX_A2_1_2_COMPRA_MEDIA')} AS taxa_juros_compra,
        {ix.num('TAB_IX_B1_1_2_COMPRA_MEDIA')} AS taxa_desconto_compra_sem_risco
    """))

    x = _Src(con, "X")
    scr = ["AA", "A", "B", "C", "D", "E", "F", "G", "H"]
    con.execute("CREATE TABLE t_x AS " + _single(con, "X", ", ".join(
        [f"{x.num(f'TAB_X_SCR_RISCO_OPER_{r}')} AS scr_{r.lower()}" for r in scr]
        + [f"{x.num('TAB_X_DEBITO_TRIBUT')} AS dc_cedente_divida_ativa"])))

    x5 = _Src(con, "X_5")
    con.execute("CREATE TABLE t_x5 AS " + _single(con, "X_5", f"""
        {x5.num('TAB_X_VL_LIQUIDEZ_0')} AS liq_0, {x5.num('TAB_X_VL_LIQUIDEZ_30')} AS liq_30,
        {x5.num('TAB_X_VL_LIQUIDEZ_60')} AS liq_60, {x5.num('TAB_X_VL_LIQUIDEZ_90')} AS liq_90,
        {x5.num('TAB_X_VL_LIQUIDEZ_180')} AS liq_180, {x5.num('TAB_X_VL_LIQUIDEZ_360')} AS liq_360,
        {x5.num('TAB_X_VL_LIQUIDEZ_MAIOR_360')} AS liq_360p
    """))

    x7 = _Src(con, "X_7")
    con.execute("CREATE TABLE t_x7 AS " + _single(con, "X_7", f"""
        {x7.num('TAB_X_PR_GARANTIA_DIRCRED')} AS garantia_pct, {x7.num('TAB_X_VL_GARANTIA_DIRCRED')} AS garantia_valor
    """))

    x11 = _Src(con, "X_1_1")
    cot = sorted(c for c in x11.cols if c.startswith("TAB_X_NR_COTST_"))
    con.execute("CREATE TABLE t_x11 AS " + _single(con, "X_1_1", ", ".join(
        [f"{x11.num(c)} AS {c.replace('TAB_X_NR_COTST_', 'cotst_').lower()}" for c in cot])))

    vcols = lambda t: ", ".join(  # noqa: E731
        f"coalesce({t}v.{p}_{lb}, 0) + coalesce({t}vi.{p}_{lb}, 0) AS {p}_{lb}"
        for p in ("av", "in") for lb in labels)

    con.execute(f"""
        CREATE TABLE fundo_mes AS
        SELECT i.*, ii.* EXCLUDE (cnpj, dt), iii.passivo, iv.pl, iv.pl_medio,
               {vcols('')},
               coalesce(v.antecipado, 0) + coalesce(vi.antecipado, 0) AS antecipado,
               CASE WHEN v.av_total_inf IS NULL AND vi.av_total_inf IS NULL THEN NULL
                    ELSE coalesce(v.av_total_inf, 0) + coalesce(vi.av_total_inf, 0) END AS av_total_inf,
               CASE WHEN v.in_total_inf IS NULL AND vi.in_total_inf IS NULL THEN NULL
                    ELSE coalesce(v.in_total_inf, 0) + coalesce(vi.in_total_inf, 0) END AS in_total_inf,
               vii.* EXCLUDE (cnpj, dt), ix.* EXCLUDE (cnpj, dt), x.* EXCLUDE (cnpj, dt),
               x5.* EXCLUDE (cnpj, dt), x7.* EXCLUDE (cnpj, dt), x11.* EXCLUDE (cnpj, dt)
        FROM t_i i
        LEFT JOIN t_ii ii USING (cnpj, dt)
        LEFT JOIN t_iii iii USING (cnpj, dt)
        LEFT JOIN t_iv iv USING (cnpj, dt)
        LEFT JOIN t_v v USING (cnpj, dt)
        LEFT JOIN t_vi vi USING (cnpj, dt)
        LEFT JOIN t_vii vii USING (cnpj, dt)
        LEFT JOIN t_ix ix USING (cnpj, dt)
        LEFT JOIN t_x x USING (cnpj, dt)
        LEFT JOIN t_x5 x5 USING (cnpj, dt)
        LEFT JOIN t_x7 x7 USING (cnpj, dt)
        LEFT JOIN t_x11 x11 USING (cnpj, dt)
    """)
    for t in ("t_i", "t_ii", "t_iii", "t_iv", "t_v", "t_vi", "t_vii", "t_ix", "t_x", "t_x5", "t_x7", "t_x11"):
        con.execute(f"DROP TABLE {t}")

    # cedentes em formato longo
    con.execute(f"""
        CREATE TABLE cedente_mes AS
        SELECT cnpj, dt, k AS rank,
               regexp_replace(doc, '[^0-9]', '', 'g') AS cedente_doc,
               -- percentuais fora de 0-100 são erro de preenchimento
               CASE WHEN pr BETWEEN 0 AND 100 THEN pr END AS pct, pr AS pct_raw
        FROM (
          SELECT cnpj, dt, unnest([{', '.join(str(k) for k in range(1, 10))}]) AS k,
                 unnest([{', '.join(f'ced_doc_{k}' for k in range(1, 10))}]) AS doc,
                 unnest([{', '.join(f'ced_pr_{k}' for k in range(1, 10))}]) AS pr
          FROM fundo_mes)
        WHERE doc IS NOT NULL AND trim(doc) <> ''
    """)
    for k in range(1, 10):
        con.execute(f"ALTER TABLE fundo_mes DROP COLUMN ced_doc_{k}")
    for k in range(1, 10):
        con.execute(f"ALTER TABLE fundo_mes DROP COLUMN ced_pr_{k}")


def _multi(con, tab: str, select: str) -> str:
    """Tabelas por série: mantém só as linhas do arquivo mais recente de cada fundo/mês."""
    s = _Src(con, tab)
    return f"""
      SELECT * EXCLUDE (_src) FROM (
        SELECT {s.key()}, _src,
               -- nome normalizado: a CVM grafa a mesma série com/sem acento e com sobras de ' |' entre tabelas
               nullif(trim(regexp_replace(regexp_replace(strip_accents({s.txt('TAB_X_CLASSE_SERIE')}),
                    '\s+', ' ', 'g'), '\s*\|\s*$', '')), '') AS serie,
               {select.format(s=s)}
        FROM {s.scan()}
      ) WHERE cnpj IS NOT NULL AND dt IS NOT NULL AND serie IS NOT NULL
      QUALIFY _src = max(_src) OVER (PARTITION BY cnpj, dt)
          AND row_number() OVER (PARTITION BY cnpj, dt, serie ORDER BY _src) = 1
    """


def build_serie_mes(con) -> None:
    x1, x2, x3, x6 = (_Src(con, t) for t in ("X_1", "X_2", "X_3", "X_6"))
    con.execute("CREATE TABLE t_x2 AS " + _multi(con, "X_2", f"""
        {x2.num('TAB_X_QT_COTA')} AS qt_cotas, {x2.num('TAB_X_VL_COTA')} AS valor_cota"""))
    con.execute("CREATE TABLE t_x3 AS " + _multi(con, "X_3", f"{x3.num('TAB_X_VL_RENTAB_MES')} AS rentab_mes"))
    con.execute("CREATE TABLE t_x6 AS " + _multi(con, "X_6", f"""
        {x6.num('TAB_X_PR_DESEMP_REAL')} AS desempenho_real, {x6.num('TAB_X_PR_DESEMP_ESPERADO')} AS desempenho_esperado"""))
    con.execute("CREATE TABLE t_x1 AS " + _multi(con, "X_1", f"{x1.num('TAB_X_NR_COTST')} AS nr_cotistas"))
    con.execute("""
        CREATE TABLE serie_mes AS
        SELECT cnpj, dt, serie,
               CASE WHEN serie ILIKE '%mezanino%' THEN 'mezanino'
                    WHEN serie ILIKE '%subordinad%' THEN 'subordinada'
                    WHEN serie ILIKE '%senior%' OR serie ILIKE '%sênior%'
                         OR serie ILIKE 'série%' OR serie ILIKE 'serie%' THEN 'senior'
                    ELSE 'outra' END AS tipo,
               qt_cotas, valor_cota, qt_cotas * valor_cota AS pl_serie,
               rentab_mes, desempenho_real, desempenho_esperado, nr_cotistas
        FROM t_x2
        FULL JOIN t_x3 USING (cnpj, dt, serie)
        FULL JOIN t_x6 USING (cnpj, dt, serie)
        FULL JOIN t_x1 USING (cnpj, dt, serie)
    """)
    for t in ("t_x1", "t_x2", "t_x3", "t_x6"):
        con.execute(f"DROP TABLE {t}")

    # fluxos de cotas (Tab. X.4) por tipo de cota: captação, resgate, amortização
    x4 = _Src(con, "X_4")
    con.execute(f"""
        CREATE TABLE fluxo_mes AS
        WITH r AS (
          SELECT * EXCLUDE (_src) FROM (
            SELECT {x4.key()}, _src,
                   strip_accents(coalesce({x4.txt('TAB_X_CLASSE_SERIE')}, '')) AS serie,
                   {x4.txt('TAB_X_TP_OPER')} AS op, {x4.num('TAB_X_VL_TOTAL')} AS valor
            FROM {x4.scan()})
          WHERE cnpj IS NOT NULL AND dt IS NOT NULL
          QUALIFY _src = max(_src) OVER (PARTITION BY cnpj, dt)
        )
        SELECT cnpj, dt,
               CASE WHEN serie ILIKE '%mezanino%' THEN 'mezanino'
                    WHEN serie ILIKE '%subordinad%' THEN 'subordinada'
                    ELSE 'senior' END AS tipo,
               sum(valor) FILTER (WHERE op ILIKE 'Capta%') AS captacoes,
               sum(valor) FILTER (WHERE op ILIKE 'Resgates no%') AS resgates,
               sum(valor) FILTER (WHERE op ILIKE 'Amortiza%') AS amortizacoes,
               sum(valor) FILTER (WHERE op ILIKE 'Resgates Solic%') AS resgates_solicitados
        FROM r GROUP BY ALL
    """)


METRICAS_SQL = """
CREATE TABLE metricas_mes AS
SELECT * REPLACE (CASE WHEN aging_suspeito THEN NULL ELSE inad_total END AS inad_total, CASE WHEN aging_suspeito THEN NULL ELSE inad_90 END AS inad_90, CASE WHEN aging_suspeito THEN NULL ELSE inad_180 END AS inad_180, CASE WHEN aging_suspeito THEN NULL ELSE inad_360 END AS inad_360, CASE WHEN aging_suspeito THEN NULL ELSE cobertura_pdd_90 END AS cobertura_pdd_90, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE roll_30_60 END AS roll_30_60, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE roll_60_90 END AS roll_60_90, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE roll_90_120 END AS roll_90_120, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE roll_120_150 END AS roll_120_150, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE roll_150_180 END AS roll_150_180, CASE WHEN aging_suspeito THEN NULL ELSE inad_90_lag6 END AS inad_90_lag6, CASE WHEN aging_suspeito THEN NULL ELSE inad_90_lag12 END AS inad_90_lag12, CASE WHEN aging_suspeito THEN NULL ELSE perda_aquisicoes_12m END AS perda_aquisicoes_12m, CASE WHEN aging_suspeito THEN NULL ELSE inad_90_ajustada END AS inad_90_ajustada, CASE WHEN aging_suspeito OR aging_suspeito_ant THEN NULL ELSE baixa_implicita_mes END AS baixa_implicita_mes)
FROM (
SELECT *, coalesce(lag(aging_suspeito) OVER (PARTITION BY cnpj ORDER BY dt), false) AS aging_suspeito_ant
FROM (
WITH sub AS (
  SELECT cnpj, dt,
         sum(pl_serie) FILTER (WHERE pl_serie > 0) AS pl_series,
         sum(pl_serie) FILTER (WHERE tipo = 'senior' AND pl_serie > 0) AS pl_senior,
         sum(pl_serie) FILTER (WHERE tipo = 'mezanino' AND pl_serie > 0) AS pl_mezanino,
         sum(pl_serie) FILTER (WHERE tipo = 'subordinada' AND pl_serie > 0) AS pl_subordinada,
         -- rentabilidade média ponderada pelo PL da série (rentabilidade em % a.m.)
         sum(rentab_mes * pl_serie) FILTER (WHERE tipo = 'senior' AND pl_serie > 0 AND abs(rentab_mes) < 50)
           / nullif(sum(pl_serie) FILTER (WHERE tipo = 'senior' AND pl_serie > 0 AND abs(rentab_mes) < 50), 0) AS rentab_senior,
         sum(rentab_mes * pl_serie) FILTER (WHERE tipo = 'mezanino' AND pl_serie > 0 AND abs(rentab_mes) < 50)
           / nullif(sum(pl_serie) FILTER (WHERE tipo = 'mezanino' AND pl_serie > 0 AND abs(rentab_mes) < 50), 0) AS rentab_mezanino,
         sum(rentab_mes * pl_serie) FILTER (WHERE tipo = 'subordinada' AND pl_serie > 0 AND abs(rentab_mes) < 50)
           / nullif(sum(pl_serie) FILTER (WHERE tipo = 'subordinada' AND pl_serie > 0 AND abs(rentab_mes) < 50), 0) AS rentab_subordinada,
         count(*) FILTER (WHERE pl_serie > 0) AS n_series,
         sum(nr_cotistas) AS nr_cotistas
  FROM serie_mes GROUP BY ALL
), ced AS (
  SELECT cnpj, dt, max(pct) FILTER (WHERE rank = 1) AS top1_cedente_pct,
         sum(pct) FILTER (WHERE rank <= 5) AS top5_cedentes_pct, count(*) AS n_cedentes_informados
  FROM cedente_mes GROUP BY ALL
), base AS (
  SELECT f.*, s.* EXCLUDE (cnpj, dt), c.* EXCLUDE (cnpj, dt),
         coalesce(dc_com_risco, 0) + coalesce(dc_sem_risco, 0) AS dc_liquido,
         coalesce(dc_com_risco, 0) + coalesce(dc_sem_risco, 0) + coalesce(pdd, 0) AS dc_bruto,
         in_30 + in_60 + in_90 + in_120 + in_150 + in_180 + in_360 + in_720 + in_1080 + in_1080p AS inad_parcelas,
         in_120 + in_150 + in_180 + in_360 + in_720 + in_1080 + in_1080p AS inad_parcelas_90,
         in_360 + in_720 + in_1080 + in_1080p AS inad_parcelas_180,
         in_720 + in_1080 + in_1080p AS inad_parcelas_360,
         av_30 + av_60 + av_90 + av_120 + av_150 + av_180 + av_360 + av_720 + av_1080 + av_1080p AS a_vencer
  FROM fundo_mes f LEFT JOIN sub s USING (cnpj, dt) LEFT JOIN ced c USING (cnpj, dt)
), w AS (
  SELECT *,
         -- defasagens (por posição no tempo do próprio fundo; exigimos mês contíguo abaixo)
         lag(dt) OVER p AS dt_ant,
         lag(in_30) OVER p AS in_30_ant, lag(in_60) OVER p AS in_60_ant, lag(in_90) OVER p AS in_90_ant,
         lag(in_120) OVER p AS in_120_ant, lag(in_150) OVER p AS in_150_ant,
         lag(inad_parcelas_360) OVER p AS inad_parcelas_360_ant, lag(inad_parcelas_90) OVER p AS inad_parcelas_90_ant,
         lag(pdd) OVER p AS pdd_ant, lag(pl) OVER p AS pl_ant, lead(pl) OVER p AS pl_prox,
         lag(dc_bruto, 6) OVER p AS dc_bruto_6m, lag(dt, 6) OVER p AS dt_6m,
         lag(dc_bruto, 12) OVER p AS dc_bruto_12m, lag(dt, 12) OVER p AS dt_12m,
         sum(coalesce(recompras, 0) + coalesce(substituicoes, 0) + coalesce(alienacao_cedente, 0))
             OVER (p ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) AS recompra_subst_3m,
         sum(coalesce(in_120, 0)) OVER (p ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS fluxo_90_12m,
         sum(coalesce(aquisicoes, 0)) OVER (p ROWS BETWEEN 15 PRECEDING AND 4 PRECEDING) AS aquisicoes_12m_lag4,
         avg(dc_bruto) OVER (p ROWS BETWEEN 11 PRECEDING AND CURRENT ROW) AS dc_bruto_medio_12m,
         row_number() OVER p AS meses_de_vida_informe,
         min(dt) OVER (PARTITION BY cnpj) AS primeiro_informe
  FROM base
  WINDOW p AS (PARTITION BY cnpj ORDER BY dt)
)
SELECT
  cnpj, dt, nome, admin, cnpj_admin, tp_fundo_classe, condominio, exclusivo,
  pl, pl_medio, ativo, carteira, dc_liquido, dc_bruto, pdd, disponibilidades, passivo, cotas_fidc,
  pl / nullif(pl_ant, 0) - 1 AS pl_var_mes,
  -- PL 10x maior que o mês anterior E o seguinte: erro de preenchimento típico; fica fora dos agregados
  coalesce(pl_ant IS NOT NULL AND pl_prox IS NOT NULL
           AND pl > 10 * greatest(pl_ant, 1e6) AND pl > 10 * greatest(pl_prox, 1e6), false) AS pl_outlier,
  -- inadimplência (parcelas vencidas, Tab. V+VI) sobre carteira bruta
  inad_parcelas / nullif(dc_bruto, 0) AS inad_total,
  inad_parcelas_90 / nullif(dc_bruto, 0) AS inad_90,
  inad_parcelas_180 / nullif(dc_bruto, 0) AS inad_180,
  inad_parcelas_360 / nullif(dc_bruto, 0) AS inad_360,
  -- saldo de contratos com atraso (Tab. I): visão "contrato", mais conservadora
  (coalesce(dc_a_vencer_c_parc_inad, 0) + coalesce(dc_inadimplente, 0)) / nullif(dc_bruto, 0) AS inad_contratos,
  pdd / nullif(dc_bruto, 0) AS pdd_carteira,
  pdd / nullif(inad_parcelas_90, 0) AS cobertura_pdd_90,
  -- estrutura de capital
  pl_senior, pl_mezanino, pl_subordinada, pl_series, n_series, nr_cotistas,
  -- com uma única série com PL não há subordinação a medir (e há administradores que alternam o rótulo
  -- sênior/subordinada da classe única mês a mês)
  CASE WHEN n_series > 1 THEN (coalesce(pl_subordinada, 0) + coalesce(pl_mezanino, 0)) / nullif(pl_series, 0) END
    AS subordinacao,
  CASE WHEN n_series > 1 THEN pl_subordinada / nullif(pl_series, 0) END AS subordinacao_junior,
  rentab_senior, rentab_mezanino, rentab_subordinada,
  -- concentração
  top1_cedente_pct, top5_cedentes_pct, n_cedentes_informados,
  -- fluxo da carteira
  aquisicoes, aquisicoes_inad, recompras, substituicoes, alienacao_cedente,
  aquisicoes / nullif(dc_bruto, 0) AS giro_mes,
  taxa_desconto_compra, taxa_juros_compra,
  -- prazo médio a vencer (ponto médio das faixas, em dias)
  (av_30 * 15 + av_60 * 45 + av_90 * 75 + av_120 * 105 + av_150 * 135 + av_180 * 165
   + av_360 * 270 + av_720 * 540 + av_1080 * 900 + av_1080p * 1260) / nullif(a_vencer, 0) AS prazo_medio_dias,
  -- liquidez e risco
  (coalesce(liq_0, 0) + coalesce(liq_30, 0)) / nullif(pl, 0) AS liquidez_30_pl,
  (coalesce(scr_e, 0) + coalesce(scr_f, 0) + coalesce(scr_g, 0) + coalesce(scr_h, 0))
     / nullif(coalesce(scr_aa, 0) + coalesce(scr_a, 0) + coalesce(scr_b, 0) + coalesce(scr_c, 0) + coalesce(scr_d, 0)
       + coalesce(scr_e, 0) + coalesce(scr_f, 0) + coalesce(scr_g, 0) + coalesce(scr_h, 0), 0) AS scr_e_h,
  garantia_pct,
  -- ===== PROXIES DE SAFRA =====
  -- (1) roll rates: só com mês anterior contíguo
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN in_60 / nullif(in_30_ant, 0) END AS roll_30_60,
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN in_90 / nullif(in_60_ant, 0) END AS roll_60_90,
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN in_120 / nullif(in_90_ant, 0) END AS roll_90_120,
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN in_150 / nullif(in_120_ant, 0) END AS roll_120_150,
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN in_180 / nullif(in_150_ant, 0) END AS roll_150_180,
  -- (2) inadimplência defasada
  CASE WHEN date_diff('month', dt_6m, dt) = 6 THEN inad_parcelas_90 / nullif(dc_bruto_6m, 0) END AS inad_90_lag6,
  CASE WHEN date_diff('month', dt_12m, dt) = 12 THEN inad_parcelas_90 / nullif(dc_bruto_12m, 0) END AS inad_90_lag12,
  -- (3) curva por aquisições: fluxo novo em 91-120d nos últimos 12m / aquisições de 4 a 15 meses atrás
  CASE WHEN meses_de_vida_informe >= 16 THEN fluxo_90_12m / nullif(aquisicoes_12m_lag4, 0) END AS perda_aquisicoes_12m,
  -- (4) inadimplência ajustada por recompra/substituição pelo cedente (3 meses)
  recompra_subst_3m / nullif(dc_bruto, 0) AS recompra_subst_3m_carteira,
  (inad_parcelas_90 + recompra_subst_3m) / nullif(dc_bruto, 0) AS inad_90_ajustada,
  -- (5) perda implícita: redução do saldo vencido >360d + variação de PDD
  CASE WHEN date_diff('month', dt_ant, dt) = 1
       THEN greatest(coalesce(inad_parcelas_360_ant, 0) - coalesce(inad_parcelas_360, 0), 0) / nullif(dc_bruto, 0) END
       AS baixa_implicita_mes,
  CASE WHEN date_diff('month', dt_ant, dt) = 1 THEN (pdd - pdd_ant) / nullif(dc_bruto, 0) END AS var_pdd_mes,
  -- (6) safra de fundos
  primeiro_informe, date_diff('month', primeiro_informe, dt) AS meses_desde_inicio,
  year(primeiro_informe) AS safra_fundo,
  -- todo o atraso na faixa 1-30d, sendo que no mês anterior havia atraso >90d: erro de preenchimento
  -- das faixas (visto em informes reais); indicadores de aging desse mês são anulados
  coalesce(inad_parcelas > 0 AND in_30 >= 0.999 * inad_parcelas AND inad_parcelas_90_ant > 0, false) AS aging_suspeito,
  -- faixas para gráficos
  in_30, in_60, in_90, in_120, in_150, in_180, in_360, in_720, in_1080, in_1080p,
  av_30, av_60, av_90, av_120, av_150, av_180, av_360, av_720, av_1080, av_1080p,
  scr_aa, scr_a, scr_b, scr_c, scr_d, scr_e, scr_f, scr_g, scr_h
FROM w
)
)
"""

SETOR_SQL = """
CREATE TABLE setor_mes AS
WITH m AS (
  SELECT m.*, c.categoria
  FROM metricas_mes m JOIN classificacao c USING (cnpj)
  WHERE m.pl > 0 AND NOT m.pl_outlier
)
SELECT categoria, dt,
  count(*) AS n_fundos,
  sum(pl) AS pl_total,
  sum(dc_bruto) AS dc_bruto_total,
  -- agregados ponderados (somas de numerador e denominador)
  sum(inad_total * dc_bruto) / nullif(sum(dc_bruto) FILTER (WHERE inad_total IS NOT NULL), 0) AS inad_total,
  sum(inad_90 * dc_bruto) / nullif(sum(dc_bruto) FILTER (WHERE inad_90 IS NOT NULL), 0) AS inad_90,
  sum(pdd) / nullif(sum(dc_bruto), 0) AS pdd_carteira,
  sum(subordinacao * pl_series) / nullif(sum(pl_series) FILTER (WHERE subordinacao IS NOT NULL), 0) AS subordinacao,
  -- medianas (robustas a fundos com dado ruim)
  median(inad_90) AS inad_90_mediana,
  median(pdd_carteira) AS pdd_carteira_mediana,
  median(subordinacao) AS subordinacao_mediana,
  median(rentab_senior) AS rentab_senior_mediana,
  median(rentab_subordinada) AS rentab_subordinada_mediana,
  median(roll_30_60) AS roll_30_60_mediana,
  median(roll_60_90) AS roll_60_90_mediana,
  median(roll_90_120) AS roll_90_120_mediana,
  median(inad_90_lag12) AS inad_90_lag12_mediana,
  median(recompra_subst_3m_carteira) AS recompra_subst_3m_mediana,
  median(prazo_medio_dias) AS prazo_medio_dias_mediana,
  median(top1_cedente_pct) AS top1_cedente_pct_mediana
FROM m GROUP BY ALL
"""


# Tabela larga usada nas comparações (fundo x pares x mercado): tudo que é comparável, por fundo x mês
COMP_SQL = """
CREATE TABLE comp_mes AS
WITH sv AS (
  SELECT cnpj, safra, f30,
         avg(f30) OVER (PARTITION BY cnpj ORDER BY safra RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW) AS f30_12,
         avg(f60) OVER (PARTITION BY cnpj ORDER BY safra RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW) AS f60_12,
         avg(f180) OVER (PARTITION BY cnpj ORDER BY safra RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW) AS f180_12
  FROM safra_venc
)
SELECT m.cnpj, m.dt, m.nome, m.pl, m.pl_outlier, m.aging_suspeito,
       m.inad_total, m.inad_90, m.inad_contratos, m.pdd_carteira, m.cobertura_pdd_90, m.subordinacao,
       m.subordinacao_junior, m.rentab_senior, m.rentab_mezanino, m.rentab_subordinada, m.top1_cedente_pct,
       m.top5_cedentes_pct, m.giro_mes, m.prazo_medio_dias, m.liquidez_30_pl, m.scr_e_h,
       m.roll_30_60, m.roll_60_90, m.roll_90_120, m.inad_90_lag12, m.perda_aquisicoes_12m,
       m.recompra_subst_3m_carteira, m.inad_90_ajustada, m.dc_bruto, m.n_series, m.nr_cotistas,
       -- nenhum vencido nas faixas (Tab. V/VI) nem na Tab. I: zero declarado, não verificável
       (m.in_30 + m.in_60 + m.in_90 + m.in_120 + m.in_150 + m.in_180 + m.in_360 + m.in_720 + m.in_1080 + m.in_1080p = 0
        AND coalesce(fm.dc_inadimplente, 0) + coalesce(fm.dc_a_vencer_c_parc_inad, 0) = 0) AS sem_vencido_declarado,
       c.* EXCLUDE (cnpj, dt, jr, mz, sr, meses_janela, m24_sub_efetiva),
       c.jr, c.mz, c.sr, c.meses_janela,
       c.m21_retorno_jr_12m / nullif(k.cdi_12m, 0) AS retorno_jr_pct_cdi,
       c.m21_retorno_jr_12m - k.cdi_12m AS retorno_jr_menos_cdi,
       q.n_erros AS q_erros, q.n_alertas AS q_alertas, q.status AS q_status, q.checks AS q_checks,
       s1.f30 AS m17_f30_ultima, s1.f30_12 AS m17_f30_media, s2.f60_12 AS m17_f60_media, s5.f180_12 AS m17_f180_media
FROM metricas_mes m
JOIN casa_mes c USING (cnpj, dt)
JOIN fundo_mes fm USING (cnpj, dt)
LEFT JOIN cdi_mes k USING (dt)
LEFT JOIN qualidade_resumo q USING (cnpj, dt)
-- safra mais recente com F30 observável vence em m-1; F60 em m-2; F180 em m-5
LEFT JOIN sv s1 ON s1.cnpj = m.cnpj AND s1.safra = CAST(last_day(m.dt - INTERVAL 1 MONTH) AS DATE)
LEFT JOIN sv s2 ON s2.cnpj = m.cnpj AND s2.safra = CAST(last_day(m.dt - INTERVAL 2 MONTH) AS DATE)
LEFT JOIN sv s5 ON s5.cnpj = m.cnpj AND s5.safra = CAST(last_day(m.dt - INTERVAL 5 MONTH) AS DATE)
"""


# parâmetros do regulamento por fundo: leitura por IA prevalece sobre a leitura por regras
# (o dado manual, no app.sqlite, prevalece sobre os dois - aplicado na API)
REG_PARAM_SQL = """
CREATE OR REPLACE TABLE regulamento_param AS
SELECT cnpj, campo, valor_num, valor_txt, 'ia' AS fonte, pagina, trecho FROM regulamento_ia_campo
UNION ALL
SELECT r.cnpj, r.campo, r.valor_num, r.valor_txt, 'regras' AS fonte, r.pagina, r.trecho FROM regulamento_campo r
WHERE r.campo NOT IN ('eventos_avaliacao', 'eventos_liquidacao', 'jr_min_sobre_subordinadas')
  AND NOT EXISTS (SELECT 1 FROM regulamento_ia_campo i WHERE i.cnpj = r.cnpj AND i.campo = r.campo)
"""


def build(db_path: Path | None = None) -> Path:
    """Reconstrói a base inteira. Retorna o caminho do arquivo final."""
    final = Path(db_path or config.DB_PATH)
    tmp = final.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    con = duckdb.connect(str(tmp))
    log.info("fundo_mes"); build_fundo_mes(con)
    log.info("serie_mes"); build_serie_mes(con)
    log.info("metricas_mes"); con.execute(METRICAS_SQL)
    log.info("bcb"); bcb.build_table(con)
    log.info("casa_mes / safras"); casa.build(con)
    log.info("qualidade"); qualidade.build(con)
    log.info("regulamentos"); regulamentos.build_table(con); agente_regulamento.build_table(con)
    con.execute(REG_PARAM_SQL)
    log.info("classificacao"); classify.build_table(con)
    log.info("comp_mes")
    con.execute(COMP_SQL)
    log.info("setor_mes"); con.execute(SETOR_SQL)
    log.info("cadastro"); cvm_cadastro.build_table(con)
    log.info("ofertas"); cvm_ofertas.build_table(con)
    con.execute("""
        CREATE TABLE fundo AS  -- última foto de cada fundo, para busca
        SELECT m.cnpj, m.nome, m.admin, k.gestor, m.dt AS ultimo_informe, m.pl, c.categoria, c.categoria_nome,
               c.grupo, c.revisar, m.condominio, m.exclusivo, k.data_inicio, k.situacao
        FROM metricas_mes m JOIN classificacao c USING (cnpj) LEFT JOIN cadastro k USING (cnpj)
        QUALIFY row_number() OVER (PARTITION BY m.cnpj ORDER BY m.dt DESC) = 1
    """)
    # "mês completo" = último mês em que pelo menos 90% dos fundos do mês anterior já entregaram.
    # O mês corrente costuma aparecer parcial (a CVM publica conforme os informes chegam).
    con.execute("""
        CREATE TABLE _meta AS
        WITH n AS (SELECT dt, count(*) AS n FROM fundo_mes GROUP BY dt),
             r AS (SELECT dt, n, n / lag(n) OVER (ORDER BY dt) AS ratio FROM n)
        SELECT now() AS built_at, (SELECT max(dt) FROM n) AS ultimo_mes,
               (SELECT max(dt) FROM r WHERE ratio >= 0.9) AS ultimo_mes_completo
    """)
    con.close()
    os.replace(tmp, final)
    log.info("base pronta: %s", final)
    return final
