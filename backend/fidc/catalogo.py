"""Catálogo das métricas comparáveis (fundo × pares × mercado).

sentido: +1 = maior é melhor, -1 = menor é melhor, 0 = contexto (sem juízo).
bloco: agrupamento da análise de comitê (instruções MCMS v2.0, seção 5).
Os números "Mxx" seguem a numeração das 29 métricas MCMS.
"""

# key, rótulo, formato, sentido, bloco, definição
METRICAS: list[tuple[str, str, str, int, str, str]] = [
    # --- Colchão e estrutura
    ("subordinacao", "Subordinação efetiva (Mz+Jr)/PL", "pct", +1, "Colchão e estrutura",
     "(PL mezanino + subordinada) / PL das séries. Métrica 24 (efetiva; o mínimo vem do regulamento)."),
    ("jr_pl", "Jr / PL", "pct", +1, "Colchão e estrutura", "PL da subordinada júnior / PL."),
    ("m01_jr_pdd", "Jr ÷ PDD média 12m", "x", +1, "Colchão e estrutura",
     "Quantas PDDs médias a Jr absorve antes de atingir a cota acima dela."),
    ("m02_jr_vencidos360", "Jr ÷ vencidos 1–360d média 12m", "x", +1, "Colchão e estrutura",
     "Quantas vezes o estoque médio de vencidos até 360 d precisaria virar perda para consumir a Jr."),
    ("m29_colchao_carteira", "(Jr+Mz) ÷ carteira", "pct", +1, "Colchão e estrutura",
     "Perda adicional (além da PDD) que consome a subordinação antes de atingir a sênior."),
    ("m29b_jr_carteira", "Jr ÷ carteira", "pct", +1, "Colchão e estrutura",
     "Perda adicional que consome a Jr antes de atingir a mezanino."),
    # --- Perdas e carteira
    ("vencido_carteira", "Vencido total / carteira", "pct", -1, "Perdas e carteira", "Todas as faixas de atraso."),
    ("over30_carteira", "Over 30 / carteira", "pct", -1, "Perdas e carteira", "Vencidos há mais de 30 dias."),
    ("over90_carteira", "Over 90 / carteira", "pct", -1, "Perdas e carteira", "Vencidos há mais de 90 dias."),
    ("over180_pl", "Over 180 / PL", "pct", -1, "Perdas e carteira",
     "Vencidos > 180 d não baixados, em % do PL (RF04: >1% A, >3% V)."),
    ("inad_contratos", "Contratos com atraso / carteira", "pct", -1, "Perdas e carteira",
     "Saldo total dos contratos com parcela vencida (Tab. I)."),
    ("pdd_carteira", "PDD / carteira", "pct", 0, "Perdas e carteira", "Contexto: PDD alta pode ser prudência ou perda."),
    ("pdd_over90", "PDD / Over 90", "x", +1, "Perdas e carteira", "Cobertura da PDD (RF09: <100% A, <70% V)."),
    ("m16_custo_credito", "Custo de crédito 12m", "pct", -1, "Perdas e carteira",
     "(ΔPDD 12m + baixas estimadas 12m) / carteira média. Baixas = (>180d m-1) + (151-180d m-1) − (>180d m)."),
    ("m16b_custo_credito_simples", "Custo de crédito 12m (variante simples)", "pct", -1, "Perdas e carteira",
     "(ΔPDD 12m + queda líquida do estoque >180d) / carteira média - definição da Base MCMS; subestima com fluxo de baixas."),
    ("m05_recompra_carteira", "Recompra média ÷ carteira 12m", "pct", -1, "Perdas e carteira",
     "Recompra mensal média (valor contábil) / carteira média 12m."),
    ("m06_preco_recompra", "Preço ÷ contábil da recompra 12m", "pct", +1, "Perdas e carteira",
     "Abaixo de 100% = perda que não passa pela PDD."),
    ("roll_30_60", "Roll 1-30 → 31-60", "pct", -1, "Perdas e carteira", "Proxy de safra: migração de faixa."),
    ("roll_60_90", "Roll 31-60 → 61-90", "pct", -1, "Perdas e carteira", ""),
    ("m17_f30_media", "F30 médio das safras (12m)", "pct", -1, "Perdas e carteira",
     "Safra por mês de vencimento: vencidos 31-60d em m+1 / a vencer ≤30d em m-1."),
    ("m17_f180_media", "F180 médio das safras", "pct", -1, "Perdas e carteira",
     "Vencidos 151-180d em m+5 / base da safra ≈ perda da safra."),
    ("inad_90_lag12", "Inad. >90d defasada 12m", "pct", -1, "Perdas e carteira", ""),
    ("pdd_sobre_2682", "PDD ÷ PDD implícita (Res. 2.682 sobre SCR)", "x", 0, "Perdas e carteira",
     "Contexto: abaixo de 1x = provisão menor que a régua do SCR."),
    # --- Concentração e lastro
    ("top1_cedente_pct", "Maior cedente (informe)", "pct100", -1, "Concentração e lastro",
     "Campo de cedentes da Tab. I (base declarada pelo administrador)."),
    ("top5_cedentes_pct", "5 maiores cedentes (informe)", "pct100", -1, "Concentração e lastro", ""),
    ("m12_sem_aquisicao", "Sem aquisição substancial / carteira", "pct", 0, "Concentração e lastro",
     "Risco retido pelo cedente (coobrigação)."),
    ("m13_rj_pl", "Cedidos por empresas em RJ / PL", "pct", -1, "Concentração e lastro", "Só a parcela do informe."),
    ("m14_outros_ativos_pl", "Outros ativos / PL (média 12m)", "pct", -1, "Concentração e lastro", ""),
    ("m15_fora_core_pl", "Debêntures+CRI+NP+LF+FIDC / PL (máx 13m)", "pct", -1, "Concentração e lastro", ""),
    # --- Retorno e spread
    ("m19_excesso_spread", "Excesso de spread observado", "pct", +1, "Retorno e spread",
     "Resultado da Jr 12m (ΔPL + resgates + amortizações − captações) / PL médio 12m (RF17: <6% A, <3% V)."),
    ("m21_retorno_jr_12m", "Retorno da Jr 12m", "pct", +1, "Retorno e spread",
     "Rentabilidade informada da subordinada, encadeada em 12 meses."),
    ("retorno_jr_pct_cdi", "Retorno Jr 12m em % do CDI", "x", +1, "Retorno e spread", ""),
    ("rentab_senior", "Rentab. sênior (mês)", "pct100", +1, "Retorno e spread", ""),
    ("m22_taxa_ix_aa", "Taxa média de aquisição (Tab. IX)", "pct100", 0, "Retorno e spread",
     "Ponderada pelas aquisições 12m, só valores entre 12% e 100% a.a."),
    # --- Operação, liquidez e governança
    ("m23_pmr", "PMR do ativo (dias)", "dias", 0, "Operação e liquidez", "Ponto médio das faixas a vencer."),
    ("cobertura_liquidez_30d", "Liquidez 30d ÷ (Sr+Mz)", "x", +1, "Operação e liquidez",
     "Ativos liquidáveis em 30 dias / PL sênior + mezanino."),
    ("resgate_liq_sr_12m", "Resgate líquido da sênior 12m", "pct", -1, "Operação e liquidez",
     "RF23 fuga da sênior: >15% A, >30% V do PL sênior de 12m atrás."),
    ("cresc_pl_12m", "Crescimento do PL 12m", "pct", 0, "Operação e liquidez", ""),
    ("m28_anos_informe", "Anos com informe na CVM", "num", +1, "Operação e liquidez", ""),
    ("pl", "PL", "brl", 0, "Operação e liquidez", ""),
]

RED_FLAGS = [  # (coluna, nome, regra em português: A = amarelo, V = vermelho)
    ("rf01_recompra", "Recompra mascarando inadimplência",
     "Amarelo: recompras pelo cedente acima de 5% das aquisições do mês. Vermelho: acima de 10%."),
    ("rf02_roll", "Roll 1-30→31-60 em alta",
     "Amarelo: a rolagem de atraso 1-30 d para 31-60 d subiu 2 meses seguidos, com atraso relevante na carteira."),
    ("rf04_vencido_180", "Vencido > 180 d não baixado",
     "Amarelo: parcelas vencidas há mais de 180 dias somam mais de 1% do PL. Vermelho: mais de 3% do PL."),
    ("rf09_pdd_over90", "PDD ÷ Over 90",
     "Amarelo: a PDD cobre menos de 100% do vencido > 90 dias. Vermelho: menos de 70%. "
     "Só avaliada quando o vencido > 90 dias é pelo menos 0,5% da carteira."),
    ("rf10_alavancagem", "PL crescendo sem a Jr / subordinação caindo",
     "Amarelo: em 12 meses o PL cresceu mais que o dobro do crescimento da Jr (e mais de 20%), "
     "ou a subordinação caiu mais de 5 p.p."),
    ("rf14_jr_negativa", "Retorno negativo da Jr",
     "Amarelo: a Jr rendeu negativo em 1 mês dos últimos 12. Vermelho: 2 ou mais meses negativos seguidos."),
    ("rf16_rj", "Cedidos por empresas em RJ",
     "Amarelo: créditos cedidos por empresas em recuperação judicial acima de 2% do PL. Vermelho: acima de 5%."),
    ("rf17_spread", "Excesso de spread baixo",
     "Amarelo: excesso de spread abaixo de 6% a.a. Vermelho: abaixo de 3% a.a."),
    ("rf19_recompra_desconto", "Recompra abaixo do contábil",
     "Amarelo: no mês, o cedente recomprou créditos a menos de 95% do valor contábil. Vermelho: a menos de 90%."),
    ("rf23_fuga_senior", "Fuga da sênior",
     "Amarelo: resgates líquidos da sênior em 12 meses acima de 15% do PL sênior. Vermelho: acima de 30%."),
    ("rf24_cedente", "Cedente relevante no informe",
     "Amarelo: o maior cedente responde por mais de 10% da carteira. Vermelho: mais de 20% (Tab. I do informe)."),
]

# o que cada red flag quer dizer (aparece ao passar o mouse)
RF_DEFINICAO = {
    "rf01_recompra": "O cedente recompra do fundo créditos que atrasaram. Recompra alta em relação ao que o fundo "
                     "compra pode esconder inadimplência: o atraso some da carteira do fundo e não aparece no informe.",
    "rf02_roll": "Roll rate = parte do saldo em atraso de 1-30 dias que, no mês seguinte, passou para 31-60 dias. "
                 "Subida contínua antecipa piora da inadimplência antes de ela chegar ao vencido > 90 dias.",
    "rf04_vencido_180": "Crédito vencido há mais de 180 dias costuma já estar provisionado ou baixado. Mantê-lo na "
                        "carteira em volume relevante pode inflar o PL e esconder perda que ainda vai bater na cota.",
    "rf09_pdd_over90": "Compara a provisão (PDD) com o saldo vencido há mais de 90 dias. Provisão menor que o "
                       "vencido indica provisionamento insuficiente: a perda ainda pode cair sobre as cotas.",
    "rf10_alavancagem": "O fundo cresce com cotas sênior/mezanino sem o originador aportar Jr na mesma proporção, "
                        "ou a subordinação está caindo: o colchão de proteção por real investido diminui.",
    "rf14_jr_negativa": "A Jr rende negativo quando as perdas superam o excesso de spread. É o primeiro sinal de que "
                        "o colchão das cotas sênior está sendo consumido.",
    "rf16_rj": "Parte da carteira foi cedida por empresas em recuperação judicial: risco de questionamento da cessão "
               "e de perda de coobrigação.",
    "rf17_spread": "Excesso de spread = rentabilidade da carteira menos o custo das cotas sênior/mezanino e as "
                   "despesas do fundo. É a primeira proteção contra perdas, antes de consumir a Jr.",
    "rf19_recompra_desconto": "O cedente recomprou créditos pagando menos que o valor contábil: o fundo realiza perda "
                              "e o crédito problemático sai da carteira.",
    "rf23_fuga_senior": "Investidores da sênior estão resgatando em volume relevante: pode indicar perda de confiança "
                        "e reduz a escala do fundo.",
    "rf24_cedente": "Concentração no maior cedente informado na Tab. I: se ele tiver problema (fraude, recompra não "
                    "honrada, RJ), o impacto no fundo é proporcional à concentração.",
}

BLOCOS = ["Colchão e estrutura", "Perdas e carteira", "Concentração e lastro", "Retorno e spread",
          "Operação e liquidez"]

BY_KEY = {m[0]: m for m in METRICAS}


def codigo(key: str) -> str | None:
    """Código da métrica/red flag na numeração MCMS (M01, RF04...) - mostrado só no glossário e no tooltip."""
    import re as _re
    m = _re.match(r"(m|rf)(\d+)(b?)_", key)
    if not m:
        return None
    return f"{'M' if m.group(1) == 'm' else 'RF'}{m.group(2)}{m.group(3)}"
