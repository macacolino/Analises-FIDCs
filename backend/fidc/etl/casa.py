"""Métricas da casa (análise de comitê / MCMS) calculadas a partir do informe mensal.

Numeração segue as instruções do projeto MCMS v2.0 (seção 4.1). Só entram aqui as
métricas que o informe sustenta; as que dependem de regulamento, rating ou relatório
do gestor ficam em `fundo_param` / `dado_gestor` (preenchimento manual no app).

Convenções (iguais às da planilha do comitê):
- carteira = DC líquido + PDD (carteira bruta)
- Jr = PL da subordinada júnior (séries "subordinada" que não são mezanino)
- médias 12m = média das competências dos últimos 12 meses até a data-base
- vencidos por faixa = Tab. V.b + VI.b
"""

CASA_SQL = r"""
CREATE TABLE casa_mes AS
WITH f AS (
  SELECT cnpj, dt, tipo,
         coalesce(captacoes, 0) AS cap, coalesce(resgates, 0) AS res, coalesce(amortizacoes, 0) AS amo
  FROM fluxo_mes
), fl AS (
  SELECT cnpj, dt,
         sum(cap) FILTER (WHERE tipo = 'subordinada') AS cap_jr,
         sum(res + amo) FILTER (WHERE tipo = 'subordinada') AS saida_jr,
         sum(cap) FILTER (WHERE tipo = 'senior') AS cap_sr,
         sum(res + amo) FILTER (WHERE tipo = 'senior') AS saida_sr
  FROM f GROUP BY ALL
), b AS (
  SELECT m.cnpj, m.dt, m.pl, m.dc_bruto, m.pdd, m.pl_senior, m.pl_mezanino, m.pl_subordinada,
         m.subordinacao, m.rentab_subordinada, m.aging_suspeito, m.pl_outlier,
         m.in_30, m.in_60, m.in_90, m.in_120, m.in_150, m.in_180, m.in_360, m.in_720, m.in_1080, m.in_1080p,
         m.av_30, m.recompras, fm.recompras_contabil, m.aquisicoes, fm.aquisicoes_com_risco,
         m.taxa_desconto_compra, m.top1_cedente_pct, m.prazo_medio_dias, m.primeiro_informe,
         fm.dc_sem_risco, fm.pdd_sem_risco, fm.dc_empresa_recup, fm.outros_ativos,
         coalesce(fm.debentures, 0) + coalesce(fm.cri, 0) + coalesce(fm.np_comercial, 0)
           + coalesce(fm.letras_financeiras, 0) + coalesce(fm.cotas_fidc, 0) AS fora_core,
         fm.dc_a_vencer_c_parc_inad, fm.dc_parcelas_inad, fm.liq_0, fm.liq_30,
         fm.scr_aa, fm.scr_a, fm.scr_b, fm.scr_c, fm.scr_d, fm.scr_e, fm.scr_f, fm.scr_g, fm.scr_h,
         m.in_30 + m.in_60 + m.in_90 + m.in_120 + m.in_150 + m.in_180 + m.in_360 + m.in_720 + m.in_1080 + m.in_1080p
           AS vencidos,
         m.in_30 + m.in_60 + m.in_90 + m.in_120 + m.in_150 + m.in_180 + m.in_360 AS vencidos_ate_360,
         m.in_360 + m.in_720 + m.in_1080 + m.in_1080p AS vencidos_180,
         m.in_120 + m.in_150 + m.in_180 + m.in_360 + m.in_720 + m.in_1080 + m.in_1080p AS vencidos_90,
         m.in_90 + m.in_120 + m.in_150 + m.in_180 + m.in_360 + m.in_720 + m.in_1080 + m.in_1080p AS vencidos_60,
         m.in_60 + m.in_90 + m.in_120 + m.in_150 + m.in_180 + m.in_360 + m.in_720 + m.in_1080 + m.in_1080p AS vencidos_30,
         fl.cap_jr, fl.saida_jr, fl.cap_sr, fl.saida_sr
  FROM metricas_mes m
  JOIN fundo_mes fm USING (cnpj, dt)
  LEFT JOIN fl USING (cnpj, dt)
), w AS (
  SELECT *,
    lag(dt) OVER p AS dt_ant,
    lag(pl_subordinada) OVER p AS jr_ant,
    lag(vencidos_180) OVER p AS v180_ant, lag(in_180) OVER p AS v151_180_ant,
    lag(pdd, 12) OVER p AS pdd_12m, lag(vencidos_180, 12) OVER p AS v180_12m, lag(dt, 12) OVER p AS dt_12m,
    lag(pl, 12) OVER p AS pl_12m, lag(pl_subordinada, 12) OVER p AS jr_12m,
    lag(pl_senior, 12) OVER p AS sr_12m, lag(subordinacao, 12) OVER p AS sub_12m,
    lag(roll_ok, 1) OVER p AS roll_1, lag(roll_ok, 2) OVER p AS roll_2
  FROM (SELECT *, in_60 / nullif(lag(in_30) OVER (PARTITION BY cnpj ORDER BY dt), 0) AS roll_ok FROM b)
  WINDOW p AS (PARTITION BY cnpj ORDER BY dt)
), w2 AS (
  SELECT *,
    -- baixas a prejuízo estimadas (proxy validada contra WOP do gestor na análise do MR FIDC):
    -- (>180 d em m-1) + (151-180 d em m-1) - (>180 d em m), nunca negativa
    CASE WHEN date_diff('month', dt_ant, dt) = 1
         THEN greatest(coalesce(v180_ant, 0) + coalesce(v151_180_ant, 0) - coalesce(vencidos_180, 0), 0) END AS baixas_mes,
    -- resultado da Jr no mês = ΔPL Jr + saídas (resgates + amortizações) - captações
    CASE WHEN date_diff('month', dt_ant, dt) = 1
         THEN pl_subordinada - jr_ant + coalesce(saida_jr, 0) - coalesce(cap_jr, 0) END AS resultado_jr_mes
  FROM w
), r AS (
  SELECT *,
    count(*) OVER y AS n12,
    avg(pdd) OVER y AS pdd_media_12m,
    avg(vencidos_ate_360) OVER y AS vencidos_360_media_12m,
    avg(dc_bruto) OVER y AS carteira_media_12m,
    avg(pl) OVER y AS pl_medio_12m,
    avg(coalesce(recompras_contabil, recompras)) OVER y AS recompra_media_12m,
    sum(recompras) OVER y AS recompra_paga_12m,
    sum(recompras_contabil) OVER y AS recompra_contabil_12m,
    avg(outros_ativos / nullif(pl, 0)) OVER y AS outros_ativos_pl_12m,
    max(fora_core / nullif(pl, 0)) OVER y13 AS fora_core_pl_max13,
    sum(baixas_mes) OVER y AS baixas_12m,
    sum(resultado_jr_mes) OVER y AS resultado_jr_12m,
    sum(aquisicoes) OVER y AS aquisicoes_12m,
    -- taxa IX: só valores entre 12% e 100% a.a. (unidade não padronizada entre administradores)
    sum(taxa_desconto_compra * aquisicoes_com_risco) FILTER (WHERE taxa_desconto_compra BETWEEN 12 AND 100) OVER y
      / nullif(sum(aquisicoes_com_risco) FILTER (WHERE taxa_desconto_compra BETWEEN 12 AND 100) OVER y, 0) AS taxa_ix_12m,
    sum(aquisicoes_com_risco) FILTER (WHERE taxa_desconto_compra BETWEEN 12 AND 100) OVER y
      / nullif(sum(aquisicoes) OVER y, 0) AS taxa_ix_cobertura,
    exp(sum(ln(1 + rentab_subordinada / 100)) FILTER (WHERE rentab_subordinada > -100) OVER y) - 1 AS retorno_jr_12m,
    count(rentab_subordinada) OVER y AS n_retorno_jr,
    count(*) FILTER (WHERE rentab_subordinada < 0) OVER y AS meses_jr_negativa_12m,
    sum(coalesce(saida_sr, 0) - coalesce(cap_sr, 0)) OVER y AS resgate_liquido_sr_12m
  FROM w2
  WINDOW y AS (PARTITION BY cnpj ORDER BY dt RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW),
         y13 AS (PARTITION BY cnpj ORDER BY dt RANGE BETWEEN INTERVAL 12 MONTH PRECEDING AND CURRENT ROW)
), jrneg AS (
  -- maior sequência de meses seguidos com rentabilidade da Jr negativa nos últimos 12 meses
  SELECT cnpj, dt, max(run) OVER (PARTITION BY cnpj ORDER BY dt RANGE BETWEEN INTERVAL 11 MONTH PRECEDING AND CURRENT ROW) AS jr_neg_seguidos
  FROM (SELECT cnpj, dt,
               -- negativos acumulados dentro do bloco iniciado no último mês não negativo
               sum(CASE WHEN rentab_subordinada < 0 THEN 1 ELSE 0 END)
                 OVER (PARTITION BY cnpj, grp ORDER BY dt) AS run
        FROM (SELECT cnpj, dt, rentab_subordinada,
                     sum(CASE WHEN rentab_subordinada < 0 THEN 0 ELSE 1 END) OVER (PARTITION BY cnpj ORDER BY dt) AS grp
              FROM b))
)
SELECT r.cnpj, r.dt,
  r.pl_subordinada AS jr, r.pl_mezanino AS mz, r.pl_senior AS sr, r.n12 AS meses_janela,
  -- ===== colchão e estrutura
  r.pl_subordinada / nullif(r.pdd_media_12m, 0) AS m01_jr_pdd,
  r.pl_subordinada / nullif(r.vencidos_360_media_12m, 0) AS m02_jr_vencidos360,
  r.subordinacao AS m24_sub_efetiva,
  (coalesce(r.pl_subordinada, 0) + coalesce(r.pl_mezanino, 0)) / nullif(r.dc_bruto, 0) AS m29_colchao_carteira,
  r.pl_subordinada / nullif(r.dc_bruto, 0) AS m29b_jr_carteira,
  -- ===== perdas e carteira
  r.recompra_media_12m / nullif(r.carteira_media_12m, 0) AS m05_recompra_carteira,
  r.recompra_paga_12m / nullif(r.recompra_contabil_12m, 0) AS m06_preco_recompra,
  (coalesce(r.dc_sem_risco, 0) + coalesce(r.pdd_sem_risco, 0)) / nullif(r.dc_bruto, 0) AS m12_sem_aquisicao,
  r.dc_empresa_recup / nullif(r.pl, 0) AS m13_rj_pl,
  r.outros_ativos_pl_12m AS m14_outros_ativos_pl,
  r.fora_core_pl_max13 AS m15_fora_core_pl,
  CASE WHEN r.n12 >= 12 AND date_diff('month', r.dt_12m, r.dt) = 12
       THEN (r.pdd - r.pdd_12m + coalesce(r.baixas_12m, 0)) / nullif(r.carteira_media_12m, 0) END AS m16_custo_credito,
  -- variante da Base MCMS: ΔPDD 12m + queda líquida do estoque > 180 d (subestima quando há fluxo de baixas)
  CASE WHEN r.n12 >= 12 AND date_diff('month', r.dt_12m, r.dt) = 12
       THEN (r.pdd - r.pdd_12m + greatest(coalesce(r.v180_12m, 0) - coalesce(r.vencidos_180, 0), 0))
            / nullif(r.carteira_media_12m, 0) END AS m16b_custo_credito_simples,
  r.baixas_12m,
  -- ===== retorno e spread
  CASE WHEN r.n12 >= 12 THEN r.resultado_jr_12m / nullif(r.pl_medio_12m, 0) END AS m19_excesso_spread,
  CASE WHEN r.n_retorno_jr >= 12 THEN r.retorno_jr_12m END AS m21_retorno_jr_12m,
  r.taxa_ix_12m AS m22_taxa_ix_aa, r.taxa_ix_cobertura AS m22_cobertura,
  -- ===== operação
  r.prazo_medio_dias AS m23_pmr,
  date_diff('month', r.primeiro_informe, r.dt) / 12.0 AS m28_anos_informe,
  -- ===== pares / carteira (aba Pares da Base MCMS)
  r.vencidos / nullif(r.dc_bruto, 0) AS vencido_carteira,
  r.vencidos_30 / nullif(r.dc_bruto, 0) AS over30_carteira,
  r.vencidos_60 / nullif(r.dc_bruto, 0) AS over60_carteira,
  r.vencidos_90 / nullif(r.dc_bruto, 0) AS over90_carteira,
  r.vencidos_180 / nullif(r.pl, 0) AS over180_pl,
  r.pdd / nullif(r.vencidos_90, 0) AS pdd_over90,
  r.pl / nullif(r.pl_12m, 0) - 1 AS cresc_pl_12m,
  r.pl_subordinada / nullif(r.jr_12m, 0) - 1 AS cresc_jr_12m,
  r.subordinacao - r.sub_12m AS var_sub_12m,
  r.pl_subordinada / nullif(r.pl, 0) AS jr_pl,
  r.resgate_liquido_sr_12m / nullif(r.sr_12m, 0) AS resgate_liq_sr_12m,
  (coalesce(r.liq_0, 0) + coalesce(r.liq_30, 0)) / nullif(coalesce(r.pl_senior, 0) + coalesce(r.pl_mezanino, 0), 0)
    AS cobertura_liquidez_30d,
  -- ===== cenário extremo: todo vencido + o a vencer de créditos com parcela vencida vira perda
  greatest(coalesce(r.dc_a_vencer_c_parc_inad, 0) - coalesce(r.dc_parcelas_inad, 0), 0) AS avencer_de_inadimplentes,
  greatest(r.vencidos + greatest(coalesce(r.dc_a_vencer_c_parc_inad, 0) - coalesce(r.dc_parcelas_inad, 0), 0)
           - coalesce(r.pdd, 0), 0) AS pdd_adicional_extremo,
  r.pl_subordinada - greatest(r.vencidos + greatest(coalesce(r.dc_a_vencer_c_parc_inad, 0)
           - coalesce(r.dc_parcelas_inad, 0), 0) - coalesce(r.pdd, 0), 0) AS jr_pos_extremo,
  -- ===== PDD implícita pela Res. CMN 2.682 sobre o SCR (por operação)
  coalesce(r.scr_a, 0) * 0.005 + coalesce(r.scr_b, 0) * 0.01 + coalesce(r.scr_c, 0) * 0.03
    + coalesce(r.scr_d, 0) * 0.10 + coalesce(r.scr_e, 0) * 0.30 + coalesce(r.scr_f, 0) * 0.50
    + coalesce(r.scr_g, 0) * 0.70 + coalesce(r.scr_h, 0) AS pdd_2682,
  r.pdd / nullif(coalesce(r.scr_a, 0) * 0.005 + coalesce(r.scr_b, 0) * 0.01 + coalesce(r.scr_c, 0) * 0.03
    + coalesce(r.scr_d, 0) * 0.10 + coalesce(r.scr_e, 0) * 0.30 + coalesce(r.scr_f, 0) * 0.50
    + coalesce(r.scr_g, 0) * 0.70 + coalesce(r.scr_h, 0), 0) AS pdd_sobre_2682,
  -- ===== insumos das red flags (para mostrar o número junto do sinal)
  r.recompras / nullif(r.aquisicoes, 0) AS recompra_aquisicoes_mes,
  r.recompras / nullif(r.recompras_contabil, 0) AS preco_recompra_mes,
  r.meses_jr_negativa_12m, j.jr_neg_seguidos,
  r.roll_ok AS roll_m0, r.roll_1 AS roll_m1, r.roll_2 AS roll_m2,
  -- ===== red flags calculáveis pelo informe (biblioteca MCMS v2.0, seção 6) - 0 ok, 1 amarelo, 2 vermelho
  CASE WHEN r.recompras / nullif(r.aquisicoes, 0) > 0.10 THEN 2
       WHEN r.recompras / nullif(r.aquisicoes, 0) > 0.05 THEN 1 ELSE 0 END AS rf01_recompra,
  CASE WHEN r.aging_suspeito THEN NULL
       WHEN r.roll_ok > r.roll_1 AND r.roll_1 > r.roll_2 AND r.vencidos > 0.01 * r.dc_bruto THEN 1 ELSE 0 END AS rf02_roll,
  CASE WHEN r.vencidos_180 / nullif(r.pl, 0) > 0.03 THEN 2
       WHEN r.vencidos_180 / nullif(r.pl, 0) > 0.01 THEN 1 ELSE 0 END AS rf04_vencido_180,
  CASE WHEN r.vencidos_90 < 0.005 * r.dc_bruto THEN 0
       WHEN r.pdd / nullif(r.vencidos_90, 0) < 0.7 THEN 2
       WHEN r.pdd / nullif(r.vencidos_90, 0) < 1.0 THEN 1 ELSE 0 END AS rf09_pdd_over90,
  CASE WHEN (r.pl / nullif(r.pl_12m, 0) - 1) > 2 * greatest(r.pl_subordinada / nullif(r.jr_12m, 0) - 1, 0)
            AND r.pl / nullif(r.pl_12m, 0) - 1 > 0.2 THEN 1
       WHEN r.subordinacao - r.sub_12m < -0.05 THEN 1 ELSE 0 END AS rf10_alavancagem,
  CASE WHEN j.jr_neg_seguidos >= 2 THEN 2 WHEN r.meses_jr_negativa_12m >= 1 THEN 1 ELSE 0 END AS rf14_jr_negativa,
  CASE WHEN r.dc_empresa_recup / nullif(r.pl, 0) > 0.05 THEN 2
       WHEN r.dc_empresa_recup / nullif(r.pl, 0) > 0.02 THEN 1 ELSE 0 END AS rf16_rj,
  CASE WHEN r.n12 < 12 THEN NULL
       WHEN r.resultado_jr_12m / nullif(r.pl_medio_12m, 0) < 0.03 THEN 2
       WHEN r.resultado_jr_12m / nullif(r.pl_medio_12m, 0) < 0.06 THEN 1 ELSE 0 END AS rf17_spread,
  CASE WHEN r.recompras_contabil > 0 AND r.recompras / r.recompras_contabil < 0.90 THEN 2
       WHEN r.recompras_contabil > 0 AND r.recompras / r.recompras_contabil < 0.95 THEN 1 ELSE 0 END AS rf19_recompra_desconto,
  CASE WHEN r.resgate_liquido_sr_12m / nullif(r.sr_12m, 0) > 0.30 THEN 2
       WHEN r.resgate_liquido_sr_12m / nullif(r.sr_12m, 0) > 0.15 THEN 1 ELSE 0 END AS rf23_fuga_senior,
  CASE WHEN r.top1_cedente_pct > 20 THEN 2 WHEN r.top1_cedente_pct > 10 THEN 1 ELSE 0 END AS rf24_cedente
FROM r LEFT JOIN jrneg j USING (cnpj, dt)
"""

# Safras por mês de vencimento (proxy sem fita, método da análise do MR FIDC):
# base da safra m = a vencer em até 30 dias no fim de m-1 (títulos que vencem em m)
# F30 = vencidos 31-60 d no fim de m+1 / base; F60 = 61-90 d em m+2; F180 = 151-180 d em m+5;
# F360 = 361-720 d em m+12 (aproximação). Exige meses contíguos.
SAFRA_SQL = r"""
CREATE TABLE safra_venc AS
WITH m AS (
  SELECT cnpj, dt, av_30, aquisicoes, in_60, in_90, in_180, in_720, aging_suspeito,
         lead(dt, 2) OVER p AS dt2, lead(in_60, 2) OVER p AS f30_v, lead(aging_suspeito, 2) OVER p AS s2,
         lead(dt, 3) OVER p AS dt3, lead(in_90, 3) OVER p AS f60_v, lead(aging_suspeito, 3) OVER p AS s3,
         lead(dt, 6) OVER p AS dt6, lead(in_180, 6) OVER p AS f180_v, lead(aging_suspeito, 6) OVER p AS s6,
         lead(dt, 13) OVER p AS dt13, lead(in_720, 13) OVER p AS f360_v
  FROM metricas_mes
  WINDOW p AS (PARTITION BY cnpj ORDER BY dt)
)
SELECT cnpj,
       CAST(last_day(dt + INTERVAL 1 MONTH) AS DATE) AS safra,   -- mês de vencimento da safra
       av_30 AS base,
       CASE WHEN date_diff('month', dt, dt2) = 2 AND NOT coalesce(s2, false) THEN f30_v / nullif(av_30, 0) END AS f30,
       CASE WHEN date_diff('month', dt, dt3) = 3 AND NOT coalesce(s3, false) THEN f60_v / nullif(av_30, 0) END AS f60,
       CASE WHEN date_diff('month', dt, dt6) = 6 AND NOT coalesce(s6, false) THEN f180_v / nullif(av_30, 0) END AS f180,
       CASE WHEN date_diff('month', dt, dt13) = 13 THEN f360_v / nullif(av_30, 0) END AS f360,
       CASE WHEN date_diff('month', dt, dt2) = 2 THEN f30_v / nullif(aquisicoes, 0) END AS f30_base_aquisicoes
FROM m
WHERE av_30 > 0
"""

def build(con) -> None:
    con.execute(CASA_SQL)
    con.execute(SAFRA_SQL)
