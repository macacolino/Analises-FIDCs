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
    "rentab_senior": ("Rentab. sênior (mês)", "pct100", "Média ponderada pelo PL das séries sêniores (Tab. X.3)"),
    "rentab_mezanino": ("Rentab. mezanino (mês)", "pct100", ""),
    "rentab_subordinada": ("Rentab. subordinada (mês)", "pct100", ""),
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
        D.setdefault(key, (nome, "int", regra))
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
