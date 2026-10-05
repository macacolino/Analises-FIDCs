"""Checagens de validação e consistência do informe mensal.

Cada checagem olha uma identidade contábil ou um padrão de erro já visto em informes
reais (ver arquivo_aprendizado do projeto MCMS). Resultado:
- `qualidade_check`: catálogo das checagens (id, descrição, severidade, o que fazer)
- `qualidade`: uma linha por fundo × mês × checagem que FALHOU (status alerta/erro)
- `qualidade_resumo`: por fundo × mês, contagem de erros e alertas e um status geral

Severidade:
- erro    = o dado do mês não fecha; indicadores derivados podem estar errados
- alerta  = dado estranho ou incompleto; usar com cuidado
- info    = característica do informe que muda a leitura (não invalida)
"""

CHECKS = [
    # id, descrição, severidade, recomendação
    ("Q01", "PL das séries (Σ quantidade × valor da cota) difere do PL informado (Tab. IV) em mais de 5%", "erro",
     "Subordinação e rentabilidade por classe podem estar erradas no mês. Conferir o informe no FNET."),
    ("Q02", "Soma das 10 faixas de vencidos difere do total vencido informado (Tab. V/VI.b) em mais de 1%", "erro",
     "Indicadores de inadimplência e roll rate do mês não são confiáveis."),
    ("Q03", "Soma das 10 faixas a vencer difere do total a vencer informado (Tab. V/VI.a) em mais de 1%", "alerta",
     "Prazo médio e base das safras podem estar distorcidos."),
    ("Q04", "Itens de DC (I.2.a/b.1 a 10) menos PDD não batem com o total de DC informado (diferença > 1%)", "alerta",
     "Carteira bruta pode estar errada. Em ago-nov/25 o layout antigo omitia o item 5 em vários fundos."),
    ("Q05", "Ativo − passivo difere do PL em mais de 2%", "erro",
     "Balanço do informe não fecha; checar se há reapresentação."),
    ("Q06", "Rentabilidade informada da série difere da variação da cota em mais de 1 p.p. (mês sem amortização)", "alerta",
     "Usar a rentabilidade com cautela; pode haver amortização não informada ou série renumerada."),
    ("Q07", "Taxa média de desconto (Tab. IX) fora de 12%–100% a.a.", "info",
     "Taxa ignorada nas métricas (unidade não padronizada entre administradores)."),
    ("Q08", "Percentual de cedente fora de 0–100% ou soma dos 9 maiores acima de 100%", "alerta",
     "Concentração de cedentes descartada no mês."),
    ("Q09", "Todo o atraso declarado na faixa 1-30 d, mas o mês anterior tinha atraso > 90 d", "erro",
     "Aging mal preenchido: indicadores de inadimplência do mês foram anulados."),
    ("Q10", "PL 10× maior que o do mês anterior e o do seguinte", "erro",
     "Erro de unidade/preenchimento: fundo excluído dos agregados no mês."),
    ("Q11", "Lacuna: mês(es) sem informe antes desta competência", "alerta",
     "Métricas de 12 meses e roll rates usam janelas incompletas."),
    ("Q12", "Fundo com PL mas sem séries de cotas informadas (Tab. X.2 zerada)", "alerta",
     "Subordinação e PL por classe indisponíveis no mês."),
    ("Q13", "Tab. VII ambígua: aquisições 'a vencer adimplentes' (a.3) repetem 'com aquisição substancial' (a.1)", "info",
     "Padrão de alguns administradores; quebra de aquisições por tipo não é confiável."),
    ("Q14", "PDD informada fora de 0,5x–3x da PDD implícita pela Res. CMN 2.682 sobre o SCR", "info",
     "Critério de provisão diverge muito da régua do SCR; investigar política de PDD."),
    ("Q15", "Carteira por segmento (Tab. II) difere da carteira bruta (Tab. I, DC + PDD) em mais de 10%", "alerta",
     "Classificação setorial do fundo pode estar errada."),
    ("Q16", "Rentabilidade de série fora de −50%/+50% no mês", "alerta",
     "Valor excluído das médias de rentabilidade."),
    ("Q17", "Nenhum vencido declarado (faixas de atraso e Tab. I zeradas) com carteira de direitos creditórios", "info",
     "Zero não verificável: na comparação, o fundo fica fora das estatísticas de inadimplência por padrão."),
    ("Q18", "PDD acima de 1% da carteira sem nenhum vencido declarado", "alerta",
     "Provável aging não preenchido (ou PDD por arrasto/coobrigação): inadimplência do fundo não é confiável."),
]

QUALIDADE_SQL = r"""
CREATE TABLE qualidade AS
WITH f AS (
  SELECT f.*, m.pl_series, m.aging_suspeito, m.pl_outlier, m.dc_bruto,
         lag(f.dt) OVER (PARTITION BY f.cnpj ORDER BY f.dt) AS dt_ant,
         f.in_30 + f.in_60 + f.in_90 + f.in_120 + f.in_150 + f.in_180 + f.in_360 + f.in_720 + f.in_1080 + f.in_1080p AS in_soma,
         f.av_30 + f.av_60 + f.av_90 + f.av_120 + f.av_150 + f.av_180 + f.av_360 + f.av_720 + f.av_1080 + f.av_1080p AS av_soma,
         c.pdd_sobre_2682
  FROM fundo_mes f JOIN metricas_mes m USING (cnpj, dt) LEFT JOIN casa_mes c USING (cnpj, dt)
), s AS (  -- séries: rentabilidade informada x variação da cota
  SELECT x.cnpj, x.dt, count(*) FILTER (
           WHERE x.pl_serie > 0 AND x.valor_cota > 0 AND p.valor_cota > 0
             AND abs((x.valor_cota / p.valor_cota - 1) * 100 - x.rentab_mes) > 1
             AND coalesce(fl.amo, 0) = 0) AS n_div,
         count(*) FILTER (WHERE abs(x.rentab_mes) >= 50) AS n_extremas
  FROM serie_mes x
  LEFT JOIN serie_mes p ON p.cnpj = x.cnpj AND p.serie = x.serie AND p.dt = CAST(last_day(x.dt - INTERVAL 1 MONTH) AS DATE)
  LEFT JOIN (SELECT cnpj, dt, sum(amortizacoes) AS amo FROM fluxo_mes GROUP BY ALL) fl
         ON fl.cnpj = x.cnpj AND fl.dt = x.dt
  GROUP BY ALL
), ced AS (
  SELECT cnpj, dt, count(*) FILTER (WHERE pct_raw < 0 OR pct_raw > 100) AS n_inval, sum(pct) AS soma
  FROM cedente_mes GROUP BY ALL
), checks AS (
  SELECT f.cnpj, f.dt, 'Q01' AS id, abs(f.pl_series / f.pl - 1) AS valor
  FROM f WHERE f.pl > 0 AND f.pl_series > 0 AND abs(f.pl_series / f.pl - 1) > 0.05
  UNION ALL
  SELECT cnpj, dt, 'Q02', abs(in_soma - in_total_inf) / in_total_inf FROM f
  WHERE in_total_inf > 1000 AND abs(in_soma - in_total_inf) > greatest(0.01 * in_total_inf, 1000)
  UNION ALL
  SELECT cnpj, dt, 'Q03', abs(av_soma - av_total_inf) / av_total_inf FROM f
  WHERE av_total_inf > 1000 AND abs(av_soma - av_total_inf) > greatest(0.01 * av_total_inf, 1000)
  UNION ALL
  SELECT cnpj, dt, 'Q04', abs(soma_itens_com_risco - coalesce(pdd_com_risco, 0) - dc_com_risco) / dc_com_risco FROM f
  WHERE dc_com_risco > 1e5 AND soma_itens_com_risco IS NOT NULL
    AND abs(soma_itens_com_risco - coalesce(pdd_com_risco, 0) - dc_com_risco) > 0.01 * dc_com_risco
  UNION ALL
  SELECT cnpj, dt, 'Q05', abs(ativo - coalesce(passivo, 0) - pl) / pl FROM f
  WHERE pl > 0 AND ativo > 0 AND abs(ativo - coalesce(passivo, 0) - pl) > 0.02 * pl
  UNION ALL
  SELECT cnpj, dt, 'Q06', n_div FROM s WHERE n_div > 0
  UNION ALL
  SELECT cnpj, dt, 'Q07', taxa_desconto_compra FROM f
  WHERE taxa_desconto_compra IS NOT NULL AND taxa_desconto_compra <> 0 AND taxa_desconto_compra NOT BETWEEN 12 AND 100
  UNION ALL
  SELECT cnpj, dt, 'Q08', soma FROM ced WHERE n_inval > 0 OR soma > 100.5
  UNION ALL
  SELECT cnpj, dt, 'Q09', NULL FROM f WHERE aging_suspeito
  UNION ALL
  SELECT cnpj, dt, 'Q10', pl FROM f WHERE pl_outlier
  UNION ALL
  SELECT cnpj, dt, 'Q11', date_diff('month', dt_ant, dt) - 1 FROM f WHERE date_diff('month', dt_ant, dt) > 1
  UNION ALL
  SELECT cnpj, dt, 'Q12', pl FROM f WHERE pl > 1e5 AND coalesce(pl_series, 0) = 0
  UNION ALL
  SELECT cnpj, dt, 'Q13', aquisicoes_a_vencer_adimpl FROM f
  WHERE aquisicoes_com_risco > 0 AND aquisicoes_a_vencer_adimpl = aquisicoes_com_risco
    AND coalesce(aquisicoes, 0) > aquisicoes_com_risco
  UNION ALL
  SELECT cnpj, dt, 'Q14', pdd_sobre_2682 FROM f
  WHERE pdd_sobre_2682 IS NOT NULL AND pdd > 1e5 AND (pdd_sobre_2682 < 0.5 OR pdd_sobre_2682 > 3)
  UNION ALL
  -- a Tab. II soma a carteira BRUTA (DC + PDD): bate em ~95% dos fundos
  SELECT cnpj, dt, 'Q15', abs(seg_total / dc_bruto - 1) FROM f
  WHERE dc_bruto > 1e6 AND seg_total > 0 AND abs(seg_total / dc_bruto - 1) > 0.10
  UNION ALL
  SELECT cnpj, dt, 'Q16', n_extremas FROM s WHERE n_extremas > 0
  UNION ALL
  SELECT cnpj, dt, 'Q17', dc_bruto FROM f
  WHERE dc_bruto > 1e6 AND in_soma = 0 AND coalesce(dc_inadimplente, 0) + coalesce(dc_a_vencer_c_parc_inad, 0) = 0
  UNION ALL
  SELECT cnpj, dt, 'Q18', pdd / dc_bruto FROM f
  WHERE dc_bruto > 1e6 AND in_soma = 0 AND coalesce(dc_inadimplente, 0) + coalesce(dc_a_vencer_c_parc_inad, 0) = 0
    AND pdd > 0.01 * dc_bruto
)
SELECT c.cnpj, c.dt, c.id, k.severidade, c.valor
FROM checks c JOIN qualidade_check k USING (id)
"""

RESUMO_SQL = r"""
CREATE TABLE qualidade_resumo AS
SELECT m.cnpj, m.dt,
       count(q.id) FILTER (WHERE q.severidade = 'erro') AS n_erros,
       count(q.id) FILTER (WHERE q.severidade = 'alerta') AS n_alertas,
       count(q.id) FILTER (WHERE q.severidade = 'info') AS n_info,
       CASE WHEN count(q.id) FILTER (WHERE q.severidade = 'erro') > 0 THEN 'erro'
            WHEN count(q.id) FILTER (WHERE q.severidade = 'alerta') > 0 THEN 'alerta'
            ELSE 'ok' END AS status,
       string_agg(q.id, ',' ORDER BY q.id) AS checks
FROM metricas_mes m LEFT JOIN qualidade q USING (cnpj, dt)
GROUP BY ALL
"""


def build(con) -> None:
    import pandas as pd
    cat = pd.DataFrame(CHECKS, columns=["id", "descricao", "severidade", "recomendacao"])
    con.register("_qc", cat)
    con.execute("CREATE OR REPLACE TABLE qualidade_check AS SELECT * FROM _qc")
    con.unregister("_qc")
    con.execute(QUALIDADE_SQL)
    con.execute(RESUMO_SQL)
