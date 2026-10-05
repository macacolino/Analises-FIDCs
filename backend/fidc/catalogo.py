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
    ("m01_jr_pdd", "M01 Jr ÷ PDD média 12m", "x", +1, "Colchão e estrutura",
     "Quantas PDDs médias a Jr absorve antes de atingir a cota acima dela."),
    ("m02_jr_vencidos360", "M02 Jr ÷ vencidos 1–360d média 12m", "x", +1, "Colchão e estrutura",
     "Quantas vezes o estoque médio de vencidos até 360 d precisaria virar perda para consumir a Jr."),
    ("m29_colchao_carteira", "M29 (Jr+Mz) ÷ carteira", "pct", +1, "Colchão e estrutura",
     "Perda adicional (além da PDD) que consome a subordinação antes de atingir a sênior."),
    ("m29b_jr_carteira", "M29b Jr ÷ carteira", "pct", +1, "Colchão e estrutura",
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
    ("m16_custo_credito", "M16 Custo de crédito 12m", "pct", -1, "Perdas e carteira",
     "(ΔPDD 12m + baixas estimadas 12m) / carteira média. Baixas = (>180d m-1) + (151-180d m-1) − (>180d m)."),
    ("m16b_custo_credito_simples", "M16b Custo de crédito 12m (variante simples)", "pct", -1, "Perdas e carteira",
     "(ΔPDD 12m + queda líquida do estoque >180d) / carteira média - definição da Base MCMS; subestima com fluxo de baixas."),
    ("m05_recompra_carteira", "M05 Recompra média ÷ carteira 12m", "pct", -1, "Perdas e carteira",
     "Recompra mensal média (valor contábil) / carteira média 12m."),
    ("m06_preco_recompra", "M06 Preço ÷ contábil da recompra 12m", "pct", +1, "Perdas e carteira",
     "Abaixo de 100% = perda que não passa pela PDD."),
    ("roll_30_60", "Roll 1-30 → 31-60", "pct", -1, "Perdas e carteira", "Proxy de safra: migração de faixa."),
    ("roll_60_90", "Roll 31-60 → 61-90", "pct", -1, "Perdas e carteira", ""),
    ("m17_f30_media", "M17 F30 médio das safras (12m)", "pct", -1, "Perdas e carteira",
     "Safra por mês de vencimento: vencidos 31-60d em m+1 / a vencer ≤30d em m-1."),
    ("m17_f180_media", "M17 F180 médio das safras", "pct", -1, "Perdas e carteira",
     "Vencidos 151-180d em m+5 / base da safra ≈ perda da safra."),
    ("inad_90_lag12", "Inad. >90d defasada 12m", "pct", -1, "Perdas e carteira", ""),
    ("pdd_sobre_2682", "PDD ÷ PDD implícita (Res. 2.682 sobre SCR)", "x", 0, "Perdas e carteira",
     "Contexto: abaixo de 1x = provisão menor que a régua do SCR."),
    # --- Concentração e lastro
    ("top1_cedente_pct", "Maior cedente (informe)", "pct100", -1, "Concentração e lastro",
     "Campo de cedentes da Tab. I (base declarada pelo administrador)."),
    ("top5_cedentes_pct", "5 maiores cedentes (informe)", "pct100", -1, "Concentração e lastro", ""),
    ("m12_sem_aquisicao", "M12 Sem aquisição substancial / carteira", "pct", 0, "Concentração e lastro",
     "Risco retido pelo cedente (coobrigação)."),
    ("m13_rj_pl", "M13 Cedidos por empresas em RJ / PL", "pct", -1, "Concentração e lastro", "Só a parcela do informe."),
    ("m14_outros_ativos_pl", "M14 Outros ativos / PL (média 12m)", "pct", -1, "Concentração e lastro", ""),
    ("m15_fora_core_pl", "M15 Debêntures+CRI+NP+LF+FIDC / PL (máx 13m)", "pct", -1, "Concentração e lastro", ""),
    # --- Retorno e spread
    ("m19_excesso_spread", "M19 Excesso de spread observado", "pct", +1, "Retorno e spread",
     "Resultado da Jr 12m (ΔPL + resgates + amortizações − captações) / PL médio 12m (RF17: <6% A, <3% V)."),
    ("m21_retorno_jr_12m", "M21 Retorno da Jr 12m", "pct", +1, "Retorno e spread",
     "Rentabilidade informada da subordinada, encadeada em 12 meses."),
    ("retorno_jr_pct_cdi", "Retorno Jr 12m em % do CDI", "x", +1, "Retorno e spread", ""),
    ("rentab_senior", "Rentab. sênior (mês)", "pct100", +1, "Retorno e spread", ""),
    ("m22_taxa_ix_aa", "M22 Taxa média de aquisição (Tab. IX)", "pct100", 0, "Retorno e spread",
     "Ponderada pelas aquisições 12m, só valores entre 12% e 100% a.a."),
    # --- Operação, liquidez e governança
    ("m23_pmr", "M23 PMR do ativo (dias)", "dias", 0, "Operação e liquidez", "Ponto médio das faixas a vencer."),
    ("cobertura_liquidez_30d", "Liquidez 30d ÷ (Sr+Mz)", "x", +1, "Operação e liquidez",
     "Ativos liquidáveis em 30 dias / PL sênior + mezanino."),
    ("resgate_liq_sr_12m", "Resgate líquido da sênior 12m", "pct", -1, "Operação e liquidez",
     "RF23 fuga da sênior: >15% A, >30% V do PL sênior de 12m atrás."),
    ("cresc_pl_12m", "Crescimento do PL 12m", "pct", 0, "Operação e liquidez", ""),
    ("m28_anos_informe", "M28 Anos com informe na CVM", "num", +1, "Operação e liquidez", ""),
    ("pl", "PL", "brl", 0, "Operação e liquidez", ""),
]

RED_FLAGS = [
    ("rf01_recompra", "RF01 Recompra mascarando inadimplência", "Recompra ÷ aquisições do mês: >5% A, >10% V"),
    ("rf02_roll", "RF02 Roll 1-30→31-60 em alta", "Alta em 2 meses seguidos com atraso relevante"),
    ("rf04_vencido_180", "RF04 Vencido > 180 d não baixado", ">1% PL A, >3% PL V"),
    ("rf09_pdd_over90", "RF09 PDD ÷ Over 90", "<100% A, <70% V (com Over 90 ≥ 0,5% da carteira)"),
    ("rf10_alavancagem", "RF10 PL crescendo sem a Jr / subordinação caindo",
     "PL 12m > 2x crescimento da Jr (e > 20%) ou subordinação −5 p.p. em 12m"),
    ("rf14_jr_negativa", "RF14 Retorno negativo da Jr", "1 mês em 12 A; 2+ seguidos V"),
    ("rf16_rj", "RF16 Cedidos por empresas em RJ", ">2% PL A, >5% PL V"),
    ("rf17_spread", "RF17 Excesso de spread baixo", "<6% a.a. A, <3% a.a. V"),
    ("rf19_recompra_desconto", "RF19 Recompra abaixo do contábil", "preço <95% A, <90% V no mês"),
    ("rf23_fuga_senior", "RF23 Fuga da sênior", "resgate líquido 12m >15% A, >30% V do PL sênior"),
    ("rf24_cedente", "RF24 Cedente relevante no informe", "maior cedente >10% A, >20% V (campo do informe)"),
]

BLOCOS = ["Colchão e estrutura", "Perdas e carteira", "Concentração e lastro", "Retorno e spread",
          "Operação e liquidez"]

BY_KEY = {m[0]: m for m in METRICAS}
