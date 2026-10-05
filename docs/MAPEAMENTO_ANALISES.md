# Mapeamento das análises: o que o app entrega e de onde vem

Legenda: **Auto** = calculado do informe CVM / BCB, atualiza sozinho · **Proxy** = aproximação a partir do informe (método declarado) ·
**Manual** = campo no app (aba "Regulamento e gestor" ou "Roteiro de DD"), com fonte e data-base · **Indisponível** = não existe em fonte pública.

## 1. Consignado privado

### Análise do setor
| Pergunta | Status | Onde / como |
|---|---|---|
| Atualizar infos de mercado automaticamente | **Auto** | Setores › Consignado privado › Mercado (Banco Central): saldo (SGS 20576), taxa (20744), inadimplência > 90 d (21116), concessões (20668). ETL diário |
| Evolução por clusters principais / clusters red flag | **Proxy** (fundos) / **Manual** (devedores) | Fundos agrupados por categoria e grupo de pares; red flags por setor (aba "Red flags do setor"). Cluster de devedor (porte, faturamento, tempo de casa, renda) não existe no informe → campos manuais (`pct_empresas_menos_20`, `pct_tempo_casa_12m`, `pct_ate_2sm`...) |
| % do mercado no leilão direto x indireto | **Indisponível** em fonte pública / **Manual** por fundo | Não há série no BCB/CVM. Por fundo: `pct_direto`, `pct_indireto` (relatório do gestor) |
| Principais players dentro dos FIDCs (corbans, SCDs) | **Auto** | Setores › Originadores / cedentes: CNPJs de cedente da Tab. I com razão social (Receita via BrasilAPI) e exposição estimada. Ex. ago/26: Parati, Celcoin SCD, UP.P SEP, BMP SCD, Cobuccio |
| Gestores e administradores do setor | **Auto** | Setores › Gestores |
| Inadimplência do mercado (5% → 10%) | **Auto** | BCB 21116 = 10,56% em ago/26 |
| Revínculo, margem, portabilidade, risco operacional do empregador | **Manual** (qualitativo) | Roteiro de DD › Mercado e regulatório |

### Originador, regulamento e carteira
| Pergunta | Status | Onde |
|---|---|---|
| Ágio máximo, clawback, amortização Jr, sequencial x pari passu, eventos | **Manual** | Roteiro de DD › Regulamento |
| Originador na subordinada júnior? | **Proxy** + Manual | Informe traz nº de cotistas da Jr (Tab. X.1.1) e cedentes; quem é o cotista exige regulamento/extrato |
| Seguir a política de crédito: perfil da carteira por cluster | **Manual** | Campos do gestor (fita) |
| % direto x indireto, safras novas por canal | **Manual** | `pct_direto`, `pct_indireto` |
| Over 60/90–180 por safra, FPD 60 | **Proxy** + Manual | Safras por mês de vencimento (F30/F60/F180) do informe; FPD e over por safra de originação exigem fita (`fpd60`, `over90_safra`) |
| Over 90 / vencidos | **Auto** | Over 90/carteira, aging por faixa, roll rates |
| % fraude x operacional | **Manual** | `pct_inad_fraude` |
| Originação mensal | **Auto** (aquisições do fundo, Tab. VII) / Manual (originação da casa) | Giro e aquisições |
| Taxa média e prazo médio | **Auto** (Tab. IX filtrada 12–100% a.a.; PMR por faixas) / Manual (taxa de originação e cedida) | M22, M23; `taxa_originacao_am`, `taxa_cedida_am` |
| Portabilidade | **Manual** | `pct_portabilidade` |
| % margem consignável utilizada | **Manual** | `margem_utilizada` |
| Rentabilidade da sub Jr | **Auto** | M21 retorno Jr 12m (+ % do CDI), M19 excesso de spread |
| PMR | **Auto** | M23 |
| Stress test dinâmico mensal | **Auto** | Aba Stress (parâmetros editáveis); pacote do comitê em Excel |
| Pontos positivos x negativos vs mercado | **Auto** | Aba "Vs. pares": posição por quartil em cada métrica, placar por bloco |

## 2. Análise de comitê MCMS (29 métricas)
| # | Métrica | Status |
|---|---|---|
| 1, 2 | Jr ÷ PDD média; Jr ÷ vencidos 1–360 d | Auto (bate com a Base MCMS) |
| 3, 4 | Jr ÷ limite 5 maiores cedentes / sacados | Manual (limites do regulamento) + Auto |
| 5, 6 | Recompra ÷ carteira; preço ÷ contábil | Auto (Tab. VII; usamos valor contábil na 5, a Base usa valor pago) |
| 7 | % liquidação pelo sacado | Manual |
| 8–11 | Concentração cedente/sacado / PL | Auto parcial (cedentes da Tab. I) + Manual (sacados) |
| 12–15 | Sem aquisição, RJ, outros ativos, fora do core | Auto |
| 16 | Custo de crédito 12m | Auto, em duas versões: baixas mensais (método MR, validado vs WOP) e ΔPDD + queda >180 d (método Base MCMS) |
| 17 | Safras F30/F60/F180/F360 | Proxy (por mês de vencimento) |
| 18 | Custo de alavancagem | Manual (spreads) + rentabilidade observada |
| 19 | Excesso de spread observado | Auto |
| 20 | Receita implícita − taxa de cessão | Manual (taxa de cessão e DF) — não implementado |
| 21 | Retorno Jr 12m e % CDI | Auto (CDI do BCB) |
| 22, 23 | Taxa média (IX), PMR | Auto |
| 24 | Subordinação mínima e folga | Manual (mínimo) + Auto (efetiva) |
| 25–27 | Cláusulas do regulamento | Manual (Roteiro de DD) |
| 28 | Tempo de existência | Auto (anos com informe) |
| 29 | Perda para atingir a sênior | Auto |
| Red flags | RF01, 02, 04, 09, 10, 14, 16, 17, 19, 23, 24 automáticas; RF08 e RF21 com parâmetro manual; demais no roteiro |

## 3. Batimento com a Base MCMS (ago/26, 21 fundos)
Calculado de forma independente (conector FIDCs.com.br + FNET) × este app (dados abertos CVM):
- **Batem em 21/21**: PL, crescimento 12m, vencido/carteira, Over 30, Over 90, Over 180/PL, PDD/carteira, Jr/PL, M01, M12, M14, M29; PDD/Over 90 20/20; subordinação efetiva 19/19.
- **Diferenças explicadas**: M16 (definição — as duas versões estão no app); M05 (valor contábil × pago); M15 (incluímos NP comerciais, como a planilha do MR); M02, M19, M21, M23 em poucos fundos (reapresentações e janela de séries).
- **Medianas dos Pares MCMS** (n = 10): Over 90 3,6% (P25–P75 2,7%–5,8%), PDD/carteira 5,6%, PDD/Over 90 157%, subordinação 43,6%, (Jr+Mz)/carteira 49,7% — iguais à Base; excesso de spread 8,3% (Base 8,4%).
