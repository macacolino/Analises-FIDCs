# Analisador de FIDCs

Ferramenta interna para analisar FIDCs a partir de dados públicos: mercado inteiro mapeado,
análise setorial por estratégia, lâmina por fundo, carteira e watchlist com alertas e relatório
mensal. Tudo exporta para Excel.

**Fontes (somente públicas nesta fase)**
| Fonte | O que vem | Atualização |
|---|---|---|
| CVM – Informe Mensal de FIDC (`dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL`) | Tabelas I a X: carteira, PDD, inadimplência por faixa, séries, rentabilidade, cedentes, aquisições/recompras | ETL diário; a CVM republica o mês conforme os informes chegam |
| CVM – Cadastro (`dados.cvm.gov.br/dados/FI/CAD/DADOS/registro_fundo_classe.zip`) | Gestor, administrador, custodiante, auditor, datas | ETL diário |
| FNET/B3 (`fnet.bmfbovespa.com.br`) | Fatos relevantes, assembleias, regulamentos, relatórios de rating | Sob demanda, cache de 6h |

Histórico desde jan/2013. Em ago/2026: 4.400 fundos/classes, PL somado de R$ 989,5 bi (com FIC-FIDC).

---

## Rodando

### Jeito mais simples (no seu computador)
Instale [Python 3.11+](https://www.python.org/downloads/) (marque "Add python.exe to PATH") e [Node.js LTS](https://nodejs.org/).
Baixe o projeto e dê dois cliques em `iniciar.bat` (Windows) ou rode `./iniciar.sh` (Mac/Linux).
Na primeira vez leva ~5 min (baixa os dados da CVM); depois abre em http://localhost:8000.

### Com Docker (servidor)
```bash
docker compose up -d --build
# abre em http://<servidor>:8000
```
Na primeira subida o ETL baixa ~175 MB da CVM e monta a base (~3 min). Depois roda todo dia
às 7h (`FIDC_ETL_HORA`). Dados ficam no volume `fidc-data` (base DuckDB + SQLite com carteira,
watchlist, notas e ajustes de categoria). **Faça backup do `app.sqlite`** — é o único arquivo
com informação que não se recupera da CVM.

### Desenvolvimento local
```bash
cd backend
pip install -r requirements.txt
python -m fidc.etl                 # baixa e monta a base em ../data
uvicorn fidc.api.main:app --reload # API em :8000

cd ../frontend
npm install
npm run dev                        # front em :5173 (proxy /api -> :8000)
```
Testes: `cd backend && pytest`.

### Acesso de várias pessoas
Nesta fase **não há login** (decisão de projeto: só dados públicos). Para expor fora da máquina:
- Rede interna: basta liberar a porta 8000.
- Fora da rede: **Cloudflare Tunnel + Cloudflare Access** (código por e-mail restrito ao domínio do banco)
  ou Tailscale. A API já lê o header `Cf-Access-Authenticated-User-Email` para registrar autor de notas
  e ajustes quando o Access estiver ligado — não precisa mudar código.

Quando entrarem dados enviados pelos fundos (confidenciais / LGPD), login vira obrigatório e o
hospedagem deve ser revisada com Segurança da Informação.

---

## Novidades da v2
- **Comparação fundo × pares × mercado** (foco principal): para cada uma das ~40 métricas, valor do fundo, P25/mediana/P75 dos pares
  (sem o próprio fundo), percentil e posição por quartil no sentido da métrica; placar por bloco (colchão, perdas, concentração,
  retorno, operação); série de 24 meses com faixa P25–P75; ranking dos pares; dispersão com eixos selecionáveis; "lado a lado" de até 8 fundos.
  Pares = categoria, mercado ou **grupo salvo** (ex.: "Pares MCMS", carregado da Base MCMS de ago/26), com "1 fundo por gestora" e
  exclusão de pares com dado inconsistente.
- **Validação e consistência dos dados**: 16 checagens por informe (PL das séries × PL, aging × total, identidade I.2.a, balanço,
  rentabilidade × cota, cedente fora de 0–100%, taxa IX fora de faixa, PDD × Res. 2.682, lacunas...). Página Qualidade, selo na lâmina.
- **Métricas da casa (MCMS)** e **red flags** calculadas do informe para todos os fundos; **safras por mês de vencimento** (F30/F60/F180/F360).
- **Stress test** dinâmico por fundo (parâmetros editáveis); **pacote do comitê** em Excel.
- **Setor automatizado**: 39 séries do Banco Central por categoria; originadores/cedentes com razão social; gestores; red flags do setor; distribuição.
- **Roteiro de DD** por categoria (consignado privado, MCMS, geral) e **dados manuais** de regulamento e gestor com fonte e data-base.
- Mapeamento completo do que sai do informe e do que é manual: [docs/MAPEAMENTO_ANALISES.md](docs/MAPEAMENTO_ANALISES.md).

## Páginas
| Página | O que tem |
|---|---|
| **Mercado** | PL por grupo de estratégia desde 2016; tabela de categorias com inadimplência, PDD, subordinação, rentabilidade |
| **Setores** | Por categoria: evolução de PL, inadimplência, PDD, subordinação, rentabilidade e roll rates (agregado e mediana); aging da categoria; ranking de fundos; ranking de séries por rentabilidade 12m; curvas de safra de fundos |
| **Pesquisa** | Busca por nome/CNPJ com filtro de categoria |
| **Lâmina do fundo** | Cadastro, alertas, KPIs vs. mediana da categoria, evolução vs. setor, proxies de safra, posição percentual na categoria, aging e cedentes, séries, eventos FNET, notas, ajuste manual de categoria, export completo em Excel |
| **Comparar** | Fundo × pares (categoria, grupo salvo, mercado) e lado a lado |
| **Grupos de pares** | Benchmarks da equipe com Incluir S/N e painel de métricas |
| **Qualidade** | Checagens de consistência por mês e fundos com falha |
| **Carteira / Watchlist** | Painel com variação de 3 meses, comparação com o setor, alertas, eventos FNET de 90 dias, relatório mensal em Excel (resumo, alertas, histórico 24m, séries, cedentes) |

---

## Taxonomia (categorias)
Arquivo `backend/fidc/taxonomy/categorias.yaml`. **Para criar ou mudar categoria, edite o YAML e
rode o ETL** (`python -m fidc.etl --sem-download`, ~20 s) — não precisa mexer em código.

A CVM classifica a carteira por segmento (Tabela II), mas não separa consignado público de privado,
não tem "multicedente multissacado" e joga muita coisa em "Financeiro – outros". Por isso cada fundo
passa por regras em ordem: ajuste manual > segmento da Tabela II > palavras do nome > concentração
de cedentes. Classificações de baixa confiança ficam marcadas como **revisar**.

Cortes atuais (proposta inicial, calibrar com o uso):
- segmento dominante: ≥ 50% da carteira
- multicedente: maior cedente ≤ 15%
- mono-cedente: maior cedente ≥ 50%

Ajuste manual: na lâmina, aba "Carteira e cedentes" → Categoria. Fica salvo e sobrevive aos ETLs.

---

## Metodologia dos indicadores
Todas as definições também aparecem passando o mouse sobre o indicador no app (`backend/fidc/dicionario.py`).

- **Carteira bruta** = direitos creditórios (Tab. I, que já vêm líquidos de PDD) + PDD. Verificado:
  em 96% dos fundos com PDD, a soma dos itens I.2.a.1–10 menos a PDD bate com o total I.2.a.
- **Inadimplência** (Tab. V + VI) = valor das **parcelas** vencidas / carteira bruta. Visão "parcela".
- **Contratos com atraso** (Tab. I) = saldo total dos contratos com alguma parcela vencida / carteira bruta. Visão "contrato", mais conservadora.
- **Subordinação** = (PL mezanino + subordinada) / PL das séries (quantidade × valor da cota, Tab. X.2). Nula quando o fundo tem uma única série.
- **Rentabilidade**: informada pelo administrador (Tab. X.3, % ao mês). Por tipo de cota, ponderada pelo PL da série. 12m só quando a série tem 12 meses seguidos com o mesmo nome.

### Proxies de safra
O informe mensal não traz dados por safra de originação. Os proxies:
1. **Roll rate**: atraso na faixa *k+1* no mês / atraso na faixa *k* no mês anterior (1-30→31-60, 31-60→61-90, 61-90→91-120…). Indicador antecedente de deterioração.
2. **Inadimplência defasada**: vencido >90d hoje / carteira bruta de 6 e 12 meses atrás. Corrige a diluição em fundos que crescem rápido.
3. **Fluxo >90d / aquisições**: novo atraso 91-120d acumulado em 12m / aquisições de 4 a 15 meses antes (Tab. VII). Mais próximo de "perda por safra de compra", mas mistura safras.
4. **Inadimplência ajustada**: inadimplência >90d + recompras, substituições e vendas ao cedente em 3 meses. Mostra atraso "escondido" pelo cedente.
5. **Perda implícita**: queda do saldo vencido >360d (proxy de baixa) e variação da PDD.
6. **Safra de fundos**: mediana dos indicadores por meses de vida, agrupando fundos pelo ano do 1º informe (fundos já existentes em 2013 ficam de fora).

### Tratamento de dados ruins
- Reenvios: para cada fundo/mês fica a versão do arquivo mais recente da CVM.
- PL 10× acima do mês anterior **e** do seguinte (126 casos): marcado `pl_outlier` e excluído dos agregados.
- Todo o atraso na faixa 1-30d quando o mês anterior tinha atraso >90d (759 casos, 0,3%): marcado `aging_suspeito`; indicadores de aging do mês são anulados.
- % de cedente fora de 0–100: descartado.
- "Mês de referência" = último mês com ≥ 90% dos informes do mês anterior (o mês corrente aparece parcial).

### Alertas (carteira/watchlist/lâmina)
Regras em `backend/fidc/consultas.py` (`REGRAS_ALERTA`): subordinação caiu >5 p.p. em 3m; inadimplência
>90d subiu >2 p.p. em 3m ou está >2× a mediana da categoria; PDD subiu >2 p.p.; recompra/substituição
>5% da carteira em 3m; roll 31-60→61-90 >80%; PL caiu >20% em 3m; rentabilidade sênior negativa;
informe atrasado; maior cedente >50% (informativo).

---

## Limitações conhecidas
- Dados declarados pelos administradores, sem auditoria; há erros de unidade e de preenchimento.
- Taxa de desconto das aquisições (Tab. IX) não tem unidade padronizada entre administradores.
- Nomes de séries mudaram com a Res. CVM 175; rentabilidade 12m de séries antigas não é encadeada.
- A API do FNET não é documentada oficialmente; o app degrada para cache/aviso se ela falhar.
- "Financeiro – outros" (~R$ 158 bi) ainda concentra fundos sem detalhe; melhora com regras novas ou leitura dos regulamentos.

## Estrutura
```
backend/fidc/
  etl/            download CVM, zip→parquet, build da base (DuckDB), cadastro, pipeline
  taxonomy/       categorias.yaml + classificador
  consultas.py    lâmina, setores, rankings, alertas, painéis
  api/main.py     FastAPI (toda tabela aceita ?formato=xlsx)
  fnet.py         cliente FNET com cache
frontend/src/     React + AG Grid + Recharts
```
