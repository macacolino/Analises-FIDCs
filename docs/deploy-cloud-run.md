# Publicar o Analisador no Google Cloud Run (versão de testes do time)

Resultado: um link fixo (`https://fidc-xxxxx.us-central1.run.app`), protegido por uma senha única, que o time abre no
navegador. Cada push no branch `claude/fidc-analyzer-s3kbfx` (inclusive o da rodada noturna de leitura) reconstrói a
base e publica sozinho pelo GitHub Actions (`.github/workflows/cloudrun.yml`). O botão **Feedback** no canto da tela
grava os comentários numa planilha Google.

Tempo: ~20 min, uma vez. Custo esperado: perto de zero (ver "Custos" no fim).

---

## 1. Projeto no Google Cloud (console, ~5 min)

1. Entre em <https://console.cloud.google.com> com a conta Google que vai pagar (cadastre o cartão se pedir).
2. Abra o **Cloud Shell** (ícone `>_` no topo à direita). Tudo abaixo é colado lá.
3. Escolha um ID de projeto único (só minúsculas, números e hífen), por exemplo `fidc-ouribank-teste`, e rode:

```bash
PROJETO=fidc-ouribank-teste          # troque se o nome já existir
gcloud projects create $PROJETO
gcloud config set project $PROJETO
gcloud billing accounts list          # copie o ACCOUNT_ID que aparecer
gcloud billing projects link $PROJETO --billing-account=COLE_O_ACCOUNT_ID
```

4. Alerta de orçamento (recomendado): menu **Faturamento > Orçamentos e alertas > Criar orçamento**, valor R$ 10/mês,
   alertas em 50%, 90% e 100%. O Google não corta o serviço no limite; ele só avisa por e-mail.

## 2. Serviços, repositório de imagens e conta de deploy (Cloud Shell, ~3 min)

Cole o bloco inteiro:

```bash
REGIAO=us-central1
gcloud services enable run.googleapis.com artifactregistry.googleapis.com

# repositório das imagens, guardando só as 2 últimas (o armazenamento acima de 0,5 GB é cobrado)
gcloud artifacts repositories create fidc --repository-format=docker --location=$REGIAO
cat > politica.json <<'JSON'
[{"name": "manter-2", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
 {"name": "apagar-antigas", "action": {"type": "Delete"}, "condition": {"tagState": "any", "olderThan": "1d"}}]
JSON
gcloud artifacts repositories set-cleanup-policies fidc --location=$REGIAO --policy=politica.json --no-dry-run

# conta que o GitHub usa para publicar
gcloud iam service-accounts create github-deploy --display-name="GitHub deploy FIDC"
SA=github-deploy@$PROJETO.iam.gserviceaccount.com
for papel in roles/run.admin roles/artifactregistry.writer roles/iam.serviceAccountUser; do
  gcloud projects add-iam-policy-binding $PROJETO --member=serviceAccount:$SA --role=$papel --quiet > /dev/null
done
gcloud iam service-accounts keys create chave.json --iam-account=$SA
echo "--- copie TUDO entre as chaves { } abaixo para o secret GCP_SA_KEY do GitHub ---"
cat chave.json
```

Depois de colar a chave no GitHub (passo 4), apague-a do Cloud Shell: `rm chave.json`.
**Não mande a chave por chat nem e-mail.**

## 3. Planilha de feedback (~5 min)

1. Crie uma planilha Google nova, por exemplo "Feedback Analisador FIDC".
2. Menu **Extensões > Apps Script**, apague o que estiver lá e cole:

```javascript
function doPost(e) {
  const d = JSON.parse(e.postData.contents);
  const aba = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
  if (aba.getLastRow() === 0) aba.appendRow(['Data', 'Nome', 'Tela', 'CNPJ', 'Comentário', 'Versão']);
  aba.appendRow([d.data, d.nome, d.pagina, d.cnpj, d.texto, d.versao]);
  return ContentService.createTextOutput('ok');
}
```

3. **Implantar > Nova implantação**, tipo **App da Web**. Em "Executar como" escolha **Eu**; em "Quem pode acessar"
   escolha **Qualquer pessoa**. Autorize quando o Google pedir.
4. Copie a **URL do app da Web** (termina em `/exec`). Só o app conhece essa URL; ela só consegue acrescentar linhas.

## 4. Cadastrar no GitHub (~3 min)

No repositório `macacolino/Analises-FIDCs`: **Settings > Secrets and variables > Actions**.

Aba **Secrets** > *New repository secret*, um por vez:

| Nome | Valor |
|---|---|
| `GCP_SA_KEY` | o conteúdo inteiro do `chave.json` (de `{` até `}`) |
| `FIDC_SENHA` | a senha única do time (evite vírgula e `#`) |
| `FIDC_FEEDBACK_URL` | a URL `/exec` da planilha |

Aba **Variables** > *New repository variable*:

| Nome | Valor |
|---|---|
| `GCP_PROJECT_ID` | o ID do projeto (ex.: `fidc-ouribank-teste`) |

## 5. Primeira publicação

O deploy roda a cada push no branch. Para disparar a primeira vez: me avise que eu faço um push, ou, na aba
**Actions** do GitHub, abra a última execução de "Publicar no Cloud Run" e clique em **Re-run all jobs**.
Leva ~15 min (o ETL baixa o histórico da CVM dentro do build). O link aparece no resumo da execução e também em
**Cloud Run** no console do Google.

Trocar a senha: atualize o secret `FIDC_SENHA` e rode de novo a publicação. Quem estava logado precisa entrar outra vez.

---

## O que muda em relação ao Codespace

- **Dados**: a base vai pronta dentro da imagem e é refeita a cada publicação. A rodada noturna de IA faz push todo
  dia, então o link amanhece atualizado. O agendamento diário às 7h do workflow (e o botão "Run workflow") só passam a
  valer quando o arquivo do workflow estiver no branch `main`, regra do GitHub.
- **Notas, carteira, watchlist e troca manual de categoria** ficam gravados no disco temporário do Cloud Run e
  **somem quando a instância reinicia ou há nova publicação**. Na fase de testes, use o botão Feedback (que vai para a
  planilha) para tudo que precisa ficar registrado.
- **Primeiro acesso depois de um tempo parado** leva alguns segundos (a instância desliga sem uso, por isso o custo é
  baixo).

## Custos (estimativa)

- **Cloud Run** em `us-central1`: cota grátis mensal de 2 milhões de requisições, 180 mil vCPU-segundos e 360 mil
  GiB-segundos ([preços](https://cloud.google.com/run/pricing)). Com 1 vCPU e 2 GiB, isso dá ~50 horas de
  processamento ativo por mês (só conta enquanto uma tela está carregando). Uso de um time em teste deve caber.
- **Artifact Registry**: 0,5 GB grátis e ~US$ 0,10 por GB-mês acima disso
  ([preços](https://cloud.google.com/artifact-registry/pricing)). A imagem tem ~1 GB e guardamos 2: na ordem de
  US$ 0,15/mês.
- **GitHub Actions**: o repositório privado tem uma cota mensal grátis de minutos; cada publicação usa ~15 min.
- Se o Google mostrar erro de política da organização ao liberar acesso público (`allUsers`), o projeto foi criado
  dentro de uma organização com restrição: crie-o com uma conta pessoal ou fale com o TI.
