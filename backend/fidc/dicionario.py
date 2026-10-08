"""Dicionário de indicadores: rótulo, formato e definição.

Usado pela API (o frontend formata a partir daqui) e pelo export para Excel.
Formatos:
  brl    valor em R$
  pct    fração (0.05 = 5%)
  pct100 número já em % (1.2 = 1,2%) - ex.: rentabilidade informada à CVM
  x      múltiplo (1.5x)
  dias   número de dias
  int    inteiro
  data   data
  txt    texto
"""

D: dict[str, tuple[str, str, str]] = {
    "cnpj": ("CNPJ", "txt", "CNPJ do fundo/classe informado à CVM"),
    "nome": ("Nome", "txt", ""),
    "dt": ("Competência", "data", "Mês de referência do informe mensal"),
    "admin": ("Administrador", "txt", ""),
    "gestor": ("Gestor", "txt", "Cadastro CVM"),
    "categoria_nome": ("Categoria", "txt", "Taxonomia interna (categorias.yaml)"),
    "grupo": ("Grupo", "txt", ""),
    "pl": ("PL", "brl", "Patrimônio líquido (Tab. IV)"),
    "pl_var_mes": ("Var. PL mês", "pct", ""),
    "dc_bruto": ("Carteira DC bruta", "brl", "Direitos creditórios + PDD (Tab. I)"),
    "dc_liquido": ("Carteira DC líquida", "brl", "Direitos creditórios líquidos de PDD (Tab. I)"),
    "pdd": ("PDD", "brl", "Provisão para redução no valor de recuperação (Tab. I)"),
    "inad_total": ("Inad. total", "pct", "Parcelas vencidas (qualquer atraso) / carteira bruta (Tab. V+VI)"),
    "inad_90": ("Inad. >90d", "pct", "Parcelas vencidas há mais de 90 dias / carteira bruta"),
    "inad_180": ("Inad. >180d", "pct", "Parcelas vencidas há mais de 180 dias / carteira bruta"),
    "inad_360": ("Inad. >360d", "pct", "Parcelas vencidas há mais de 360 dias / carteira bruta"),
    "inad_contratos": ("Contratos c/ atraso", "pct",
                       "Saldo total dos contratos com alguma parcela em atraso / carteira bruta (Tab. I) - visão mais conservadora"),
    "pdd_carteira": ("PDD / carteira", "pct", ""),
    "cobertura_pdd_90": ("Cobertura PDD >90d", "x", "PDD / parcelas vencidas >90d"),
    "subordinacao": ("Subordinação", "pct", "(PL mezanino + subordinada) / PL das séries (Tab. X.2)"),
    "subordinacao_junior": ("Subordinação júnior", "pct", "PL subordinada júnior / PL das séries"),
    "pl_senior": ("PL sênior", "brl", ""),
    "pl_mezanino": ("PL mezanino", "brl", ""),
    "pl_subordinada": ("PL subordinada", "brl", ""),
    "rentab_senior": ("Rentab. sênior (mês)", "pct100", "Média ponderada pelo PL das séries sêniores (Tab. X.3); na página do fundo, ajustada pela amortização do mês quando a informada não a considera"),
    "rentab_mezanino": ("Rentab. mezanino (mês)", "pct100", ""),
    "rentab_subordinada": ("Rentab. subordinada (mês)", "pct100", "Média ponderada pelo PL das séries subordinadas (Tab. X.3); na página do fundo, recalculada pelo resíduo do PL quando a soma das séries não fecha"),
    "rentab_12m": ("Rentab. 12m", "pct", "Rentabilidade acumulada 12 meses da série"),
    "top1_cedente_pct": ("Maior cedente", "pct100", "% do maior cedente (Tab. I)"),
    "top5_cedentes_pct": ("Top 5 cedentes", "pct100", ""),
    "aquisicoes": ("Aquisições no mês", "brl", "Tab. VII"),
    "giro_mes": ("Giro (aquisições/carteira)", "pct", ""),
    "recompras": ("Recompras", "brl", "Recompras pelo cedente no mês (Tab. VII)"),
    "substituicoes": ("Substituições", "brl", ""),
    "taxa_desconto_compra": ("Taxa desconto compra", "pct100",
                             "Taxa média ponderada de desconto nas aquisições (Tab. IX). Unidade não padronizada entre administradores - usar com cautela"),
    "prazo_medio_dias": ("Prazo médio a vencer", "dias", "Média ponderada pelo ponto médio das faixas (Tab. V+VI)"),
    "liquidez_30_pl": ("Liquidez 30d / PL", "pct", "Ativos liquidáveis em até 30 dias / PL (Tab. X.5)"),
    "scr_e_h": ("Rating SCR E-H", "pct", "Parcela da carteira com rating de operação E a H (Tab. X.8)"),
    "nr_cotistas": ("Cotistas", "int", ""),
    "n_series": ("Séries", "int", ""),
    "n_fundos": ("Fundos", "int", ""),
    "alertas": ("Alertas", "int", "Quantidade de alertas (exceto informativos) pelas regras atuais"),
    "pl_total": ("PL total", "brl", ""),
    # proxies de safra
    "roll_30_60": ("Roll 1-30→31-60", "pct", "Atraso 31-60d no mês / atraso 1-30d no mês anterior"),
    "roll_60_90": ("Roll 31-60→61-90", "pct", ""),
    "roll_90_120": ("Roll 61-90→91-120", "pct", ""),
    "roll_120_150": ("Roll 91-120→121-150", "pct", ""),
    "roll_150_180": ("Roll 121-150→151-180", "pct", ""),
    "inad_90_lag6": ("Inad. >90d defasada 6m", "pct", "Vencido >90d hoje / carteira bruta de 6 meses atrás"),
    "inad_90_lag12": ("Inad. >90d defasada 12m", "pct", "Vencido >90d hoje / carteira bruta de 12 meses atrás"),
    "perda_aquisicoes_12m": ("Fluxo >90d / aquisições", "pct",
                             "Novo atraso 91-120d acumulado 12m / aquisições de 4 a 15 meses atrás - proxy de perda por safra de compra"),
    "recompra_subst_3m_carteira": ("Recompra+substituição 3m", "pct",
                                   "Recompras, substituições e vendas ao cedente em 3 meses / carteira bruta"),
    "inad_90_ajustada": ("Inad. >90d ajustada", "pct", "Inad. >90d + recompra/substituição 3m, sobre a carteira bruta"),
    "baixa_implicita_mes": ("Baixa implícita no mês", "pct", "Redução do saldo vencido >360d / carteira bruta - proxy de write-off"),
    "var_pdd_mes": ("Var. PDD no mês", "pct", "Variação da PDD / carteira bruta"),
    "meses_desde_inicio": ("Meses desde 1º informe", "int", ""),
    "safra_fundo": ("Safra do fundo", "int", "Ano do primeiro informe mensal"),
}


def label(col: str) -> str:
    _merge_catalogo()
    return D.get(col, (col, "", ""))[0]


def fmt(col: str) -> str:
    _merge_catalogo()
    if col in D:
        return D[col][1]
    if col.endswith("_mediana"):
        return fmt(col[: -len("_mediana")])
    return ""


def _merge_catalogo() -> None:
    from . import catalogo
    for key, label, fmt, _sentido, _bloco, defin in catalogo.METRICAS:
        D.setdefault(key, (label, fmt, defin))
    for key, nome, regra in catalogo.RED_FLAGS:
        D.setdefault(key, (nome, "int", regra + " " + catalogo.RF_DEFINICAO.get(key, "")))
    D.update({
        "jr": ("PL Jr", "brl", ""), "mz": ("PL mezanino", "brl", ""), "sr": ("PL sênior", "brl", ""),
        "q_status": ("Qualidade do dado", "txt", "ok / alerta / erro pelas checagens de consistência"),
        "q_erros": ("Erros de consistência", "int", ""), "q_alertas": ("Alertas de consistência", "int", ""),
        "q_checks": ("Checagens que falharam", "txt", ""), "m17_f30_ultima": ("F30 da safra mais recente", "pct", ""),
        "m17_f60_media": ("F60 médio das safras", "pct", ""), "retorno_jr_menos_cdi": ("Retorno Jr 12m − CDI", "pct", ""),
        "pdd_2682": ("PDD implícita Res. 2.682", "brl", ""), "baixas_12m": ("Baixas estimadas 12m", "brl", ""),
        "avencer_de_inadimplentes": ("A vencer de créditos com parcela vencida", "brl", ""),
        "pdd_adicional_extremo": ("PDD adicional no cenário extremo", "brl",
                                  "Todo o vencido + o a vencer de créditos com parcela vencida viram perda, menos a PDD atual"),
        "jr_pos_extremo": ("Jr após o cenário extremo", "brl", ""),
        "m22_cobertura": ("Cobertura da taxa IX (aquisições válidas / total)", "pct", ""),
        "base": ("Base da safra (a vencer ≤30d)", "brl", ""), "f30": ("F30", "pct", "Vencidos 31-60d em m+1 / base"),
        "f60": ("F60", "pct", "Vencidos 61-90d em m+2 / base"), "f180": ("F180", "pct", "Vencidos 151-180d em m+5 / base"),
        "f360": ("F360", "pct", "Vencidos 361-720d em m+12 / base"), "safra": ("Safra (mês de vencimento)", "data", ""),
        "f30_base_aquisicoes": ("F30 sobre aquisições do mês anterior", "pct", ""),
        "exposicao_estimada": ("Exposição estimada", "brl", "% do cedente × carteira bruta do fundo"),
        "maior_pct": ("Maior % em um fundo", "pct100", ""), "nome_cedente": ("Cedente", "txt", ""),
        "cedente": ("CNPJ do cedente", "txt", ""), "pct_com_flag": ("% dos fundos com flag", "pct", ""),
        "pl_com_flag": ("PL dos fundos com flag", "brl", ""), "amarelo": ("Amarelo", "int", ""),
        "vermelho": ("Vermelho", "int", ""), "over90_mediana": ("Over 90 (mediana)", "pct", ""),
        "subordinacao_mediana": ("Subordinação (mediana)", "pct", ""),
        "retorno_jr_mediana": ("Retorno Jr 12m (mediana)", "pct", ""), "valor": ("Valor", "num", ""),
        "pl_serie": ("PL da série", "brl", "Quantidade de cotas × valor da cota (Tab. X.2)"),
        "rentab_mes": ("Rentab. mês", "pct100", "Rentabilidade da série no mês informada pelo administrador (Tab. X.3)"),
        "valor_cota": ("Valor da cota", "num", ""), "qt_cotas": ("Qtd. cotas", "num", ""),
        "desempenho_real": ("Desempenho real", "pct100", ""), "desempenho_esperado": ("Desempenho esperado", "pct100", ""),
        "tipo": ("Tipo de cota", "txt", "senior, mezanino ou subordinada (júnior), lido do nome da série"),
        "serie": ("Série / subclasse", "txt", ""),
        # oportunidades / captação
        "captacao": ("Captação", "brl", "Subscrições no período (Tab. X.4, todas as classes)"),
        "cap_senior": ("Captação sênior", "brl", ""), "cap_mezanino": ("Captação mezanino", "brl", ""),
        "cap_sub": ("Captação subordinada", "brl", ""), "resgates": ("Resgates", "brl", ""),
        "amortizacoes": ("Amortizações", "brl", ""), "liquida": ("Captação líquida", "brl",
                                                                 "Captação − resgates − amortizações"),
        # PDD por administrador
        "fundos": ("Fundos", "int", ""), "fundos_com_vencido": ("Fundos com vencido", "int", ""),
        "pdd_carteira_mediana": ("PDD / carteira (mediana)", "pct", "Mediana entre os fundos do administrador"),
        "pdd_regua_mediana": ("PDD ÷ régua 2.682 (mediana)", "x",
                              "PDD declarada / PDD pela régua da Res. CMN 2.682 sobre as parcelas vencidas (1% 1-30 d, 3% 31-60, "
                              "10% 61-90, 30% 91-120, 50% 121-150, 70% 151-180, 100% > 180). Régua mínima: abaixo de 1x, a PDD "
                              "não cobre nem a régua aplicada só às parcelas vencidas"),
        "pct_abaixo_regua": ("Fundos abaixo da régua", "pct", "Parcela dos fundos com vencido cuja PDD fica abaixo da régua 2.682"),
        "pdd_vencido90_mediana": ("PDD / vencido > 90 d (mediana)", "x", ""),
        "pdd_regua": ("PDD ÷ régua 2.682", "x", "PDD declarada / PDD pela régua 2.682 sobre as parcelas vencidas"),
        "pdd_vencido90": ("PDD / vencido > 90 d", "x", ""), "regua_2682": ("PDD pela régua 2.682", "brl", ""),
        "vencido": ("Vencido (parcelas)", "brl", ""), "vencido_90": ("Vencido > 90 d", "brl", ""),
        "abaixo_regua": ("Abaixo da régua", "txt", ""),
        "curva_a_vencer": ("Curva: a vencer", "pct", "Provisão implícita sobre a carteira a vencer (estimativa)"),
        "curva_in_30": ("Curva: 1-30 d", "pct", "Provisão implícita sobre parcelas com 1-30 dias de atraso (estimativa)"),
        "curva_in_60": ("Curva: 31-60 d", "pct", ""), "curva_in_90": ("Curva: 61-90 d", "pct", ""),
        "curva_in_120": ("Curva: 91-120 d", "pct", ""), "curva_in_150": ("Curva: 121-150 d", "pct", ""),
        "curva_in_180": ("Curva: 151-180 d", "pct", ""), "curva_in_mais180": ("Curva: > 180 d", "pct", ""),
        "curva_r2": ("R² da curva", "num", "Quanto da variação da PDD entre fundos/meses a curva explica (0 a 1)"),
        "curva_n": ("Observações da curva", "int", "Fundo-meses com vencido usados na estimativa"),
        "metodo": ("Método (demonstrações)", "txt", "Metodologia de PDD descrita na nota explicativa"),
        "faixas_txt": ("Régua escrita", "txt", "Percentuais por faixa de atraso descritos nas demonstrações"),
        "efeito_vagao": ("Efeito vagão", "txt", "Atraso numa parcela provisiona todo o fluxo do devedor"),
        "provisao_inicial": ("Provisão na compra (rating)", "txt", ""), "data_df": ("Demonstrações de", "txt", ""),
        "metodo_predominante": ("Método predominante", "txt", ""), "regua_escrita_tipica": ("Régua escrita típica", "txt", ""),
        "fundos_com_politica": ("Fundos com política lida", "int", ""),
        "captacoes": ("Captações", "brl", "Subscrições no mês (Tab. X.4, todas as classes)"),
        "carteira": ("Carteira DC bruta", "brl", "Direitos creditórios + PDD (Tab. I)"),
        "cdi_mes": ("CDI mês", "pct", "CDI do mês (BCB, série 4391)"),
        "rentab_informada": ("Rentab. informada", "pct", "Rentabilidade do mês informada pelo administrador (Tab. X.3)"),
        "rentab_ajustada": ("Rentab. ajustada", "pct", "(cota + amortização por cota) / cota do mês anterior − 1; "
                            "amortização do tipo de cota (Tab. X.4) dividida pelas cotas do tipo - estimativa"),
        "amort_por_cota": ("Amortização por cota (estim.)", "num", ""),
        "ajuste_amortizacao": ("Ajustada p/ amortização", "txt", "Verdadeiro quando a informada não considerava a amortização"),
        "rotulo": ("Série", "txt", ""),
        "captacao_pct_pl": ("Captação / PL", "pct", ""), "meses_captando": ("Meses com captação", "int", ""),
        "novo": ("Fundo novo (≤ 6 meses)", "txt", ""), "primeiro_informe": ("1º informe", "data", ""),
        "lastro": ("Lastro (regulamento)", "txt", "Resumo do lastro lido no regulamento (IA)"),
        "cap_media_3m": ("Captação média 3m", "brl", "Média mensal dos últimos 3 meses"),
        "cap_media_12m_ant": ("Captação média 12m anteriores", "brl", "Média mensal dos 12 meses antes dos últimos 3"),
        "aceleracao": ("Aceleração da captação", "pct", "Média 3m / média dos 12m anteriores − 1"),
        "liquida_3m": ("Captação líquida 3m", "brl", ""), "novos_3m": ("Fundos novos 3m", "int", ""),
        "captacao_12m": ("Captação 12m", "brl", ""), "liquida_12m": ("Captação líquida 12m", "brl", ""),
        "novos_12m": ("Fundos novos 12m", "int", ""),
        "ultima_oferta_registro": ("Última oferta: registro", "data", "Data de registro da última oferta de cotas na CVM"),
        "ultima_oferta_requerimento": ("Última oferta: requerimento", "data", ""),
        "ultima_oferta_valor": ("Última oferta: valor", "brl", "Valor total registrado (teto da oferta)"),
        "ultima_oferta_status": ("Última oferta: status", "txt", ""),
        "ultima_oferta_publico": ("Última oferta: público", "txt", ""),
        "ofertas_12m": ("Ofertas 12m", "int", "Ofertas registradas nos últimos 12 meses"),
        "valor_ofertas_12m": ("Valor ofertado 12m", "brl", "Soma do valor registrado das ofertas em 12 meses"),
        "data_requerimento": ("Requerimento", "data", ""), "data_registro": ("Registro", "data", "Data de registro da oferta na CVM"),
        "data_encerramento": ("Encerramento", "data", ""), "status": ("Status", "txt", ""),
        "valor_registrado": ("Valor registrado", "brl", "Teto da oferta (não é o captado)"),
        "publico_alvo": ("Público-alvo", "txt", ""), "tipo_oferta": ("Tipo", "txt", ""), "emissao": ("Emissão", "txt", ""),
        "lider": ("Coordenador líder", "txt", ""), "gestor_oferta": ("Gestor (oferta)", "txt", ""), "rito": ("Rito", "txt", ""),
        "nome_emissor": ("Emissor", "txt", ""), "cnpj_emissor": ("CNPJ emissor", "txt", ""),
        "fundo_novo_sem_informe": ("Ainda sem informe", "txt", "Fundo da oferta ainda não aparece no informe mensal"),
        # comparativo por estratégia
        "dt_informe": ("Informe usado", "data", "Último informe do fundo com séries (até 3 meses antes da referência)"),
        "foco": ("Foco do lastro", "txt", "Precatórios: federal ou estadual/municipal (leitura IA; '(regras)' = leitura por texto)"),
        "alimentar": ("Alimentar", "txt", "Foco em precatórios de natureza alimentar"),
        "pct_precatorios": ("% em precatórios", "pct", "Segmento I1 (precatórios) da Tab. II / carteira"),
        "estrutura": ("Estrutura", "txt", "Cota única = uma só série com PL; senão sênior + subordinada"),
        "rentab_12m_cota_unica": ("Rentab. 12m cota única", "pct", "Tab. X.3; anualizada se a série tem 6-11 meses"),
        "rentab_12m_senior": ("Rentab. 12m sênior", "pct", "Média ponderada pelo PL das séries sênior"),
        "rentab_12m_mezanino": ("Rentab. 12m mezanino", "pct", ""),
        "rentab_12m_subordinada": ("Rentab. 12m subordinada", "pct", ""),
        "spread_cdi_12m": ("Remuneração vs CDI (CDI + x)", "pct",
                           "(1 + rentab. 12m da cota única ou sênior) / (1 + CDI 12m) − 1"),
        "pct_cdi_12m": ("% do CDI 12m", "pct", "Rentab. 12m / CDI 12m"),
        "meses_rentab": ("Meses na conta", "int", "Meses de histórico da série usados (12 = completo)"),
        "cdi_12m": ("CDI 12m", "pct", ""),
        "benchmark_senior": ("Benchmark da sênior", "txt", "Regulamento/suplemento (pode faltar: costuma estar no suplemento)"),
        "taxa_gestao": ("Taxa de gestão", "pct", "% a.a. do PL (regulamento)"),
        "taxa_administracao": ("Taxa de administração", "pct", "% a.a. do PL (regulamento)"),
        "taxa_performance": ("Taxa de performance", "pct", "% do que exceder o benchmark (regulamento)"),
        "taxa_minima_cessao": ("Taxa mínima de cessão", "pct", "Regulamento (a.m. ou a.a. conforme o texto)"),
        "taxa_gestao_fonte": ("Fonte taxa de gestão", "txt", ""), "taxa_minima_cessao_fonte": ("Fonte taxa mín. cessão", "txt", ""),
        # estrutura x regulamento
        "status_sub": ("Subordinação vs mínimo", "txt", "abaixo do mínimo / folga < 3 p.p. / ok / sem mínimo"),
        "sub_min_senior": ("Subordinação mínima", "pct", "Mínimo exigido pelo regulamento (manual > IA > regras > referência da categoria)"),
        "sub_min_senior_fonte": ("Fonte do mínimo", "txt", ""),
        "folga_sub_min_senior": ("Folga da subordinação", "pct", "Subordinação atual (informe) − mínima"),
        "jr_min_pl": ("Jr mínima (% PL)", "pct", "Mínimo de cotas subordinadas júnior pelo regulamento"),
        "jr_min_pl_fonte": ("Fonte Jr mínima", "txt", ""),
        "folga_jr_min_pl": ("Folga da Jr", "pct", "Jr/PL atual − Jr mínima"),
        "top1_cedente_frac": ("Maior cedente (informe)", "pct", "% da carteira do maior cedente (Tab. I)"),
        "limite_maior_cedente": ("Limite maior cedente", "pct", "Limite do regulamento (% do PL)"),
        "limite_maior_cedente_fonte": ("Fonte limite cedente", "txt", ""),
        "limite_maior_sacado": ("Limite maior sacado", "pct", "Limite do regulamento (% do PL)"),
        "n_com_minimo": ("Fundos com mínimo", "int", "Fundos com subordinação mínima conhecida (inclui referência da categoria)"),
        "sub_min_p25": ("Sub. mínima P25", "pct", "Entre os regulamentos lidos da categoria"),
        "sub_min_mediana": ("Sub. mínima mediana", "pct", "Entre os regulamentos lidos da categoria"),
        "sub_min_p75": ("Sub. mínima P75", "pct", ""),
        "sub_min_referencia": ("Referência da categoria", "pct", "Subordinação mínima de referência (editável na página do setor)"),
        "folga_mediana": ("Folga mediana", "pct", "Mediana de subordinação atual − mínima"),
        "n_abaixo": ("Abaixo do mínimo", "int", "Fundos com subordinação atual abaixo do mínimo"),
        "n_folga_3pp": ("Folga < 3 p.p.", "int", ""),
        "pl_abaixo": ("PL abaixo do mínimo", "brl", ""),
        "jr_min_mediana": ("Jr mínima mediana", "pct", ""),
    })


def as_json() -> dict:
    _merge_catalogo()
    return {k: {"label": v[0], "fmt": v[1], "desc": v[2]} for k, v in D.items()}
