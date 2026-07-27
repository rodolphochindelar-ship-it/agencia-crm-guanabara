# Agência CRM Guanabara

Ferramenta interna da área de CRM: cria o calendário mensal de ações, campanhas avulsas
e briefings de design (WhatsApp, Email, App Push, Web Push), com geração de copy por IA
(Gemini), revisão automática e agendamento no Google Sheets.

## Arquitetura
- `dashboard_agencia.html` — front-end (estático). A prévia do calendário roda no navegador,
  sem servidor. Login, geração de copy e briefings de design usam a API.
- `agencia_crm.py` — API em Python (biblioteca padrão). Endpoints de login, calendário,
  campanha avulsa, briefing de design e salvamento no Sheets.
- `crm_agent.py` — integração com Google Sheets (não incluído aqui; suas credenciais).

## Rodar localmente
1. Crie `secrets.local.json` a partir de `secrets.local.json.example` e coloque sua `GEMINI_API_KEY`.
2. (Opcional) Crie `users.json` a partir de `users.json.example` para exigir login.
   Gere o hash da senha com:
   `python -c "import hashlib;print(hashlib.sha256('MINHASENHA'.encode()).hexdigest())"`
3. Rode: `python agencia_crm.py`
4. Acesse `http://localhost:8080/`

Sem `users.json`, o acesso fica liberado (modo local). Com usuários cadastrados, exige login.

## Variáveis de ambiente (produção)
| Variável | Descrição |
|---|---|
| `GEMINI_API_KEY` | Chave do Gemini (obrigatória) |
| `GEMINI_MODEL` | Modelo (padrão: gemini-2.5-flash) |
| `AUTH_SECRET` | Segredo para assinar tokens de sessão (defina um valor longo e aleatório) |
| `USERS_JSON` | JSON de usuários `{ "user": "sha256senha" }` |
| `ALLOWED_ORIGIN` | Domínio do dashboard para o CORS (ex: `https://usuario.github.io`) |
| `TOKEN_TTL_SEGUNDOS` | Validade do login em segundos (padrão 43200 = 12h) |
| `PORT` | Porta (as plataformas definem sozinhas) |

## Deploy: API no Render (plano free) + Dashboard no GitHub Pages

### 1. Suba o código no GitHub
- Confirme que `secrets.local.json`, `users.json` e credenciais **não** foram versionados
  (o `.gitignore` já cuida disso). Se a chave antiga do Gemini já vazou, **revogue e gere outra**.

### 2. API no Render
1. render.com → New → Web Service → conecte o repositório.
2. Runtime Python. Build: `pip install -r requirements.txt`. Start: `python agencia_crm.py`.
3. Em Environment, defina: `GEMINI_API_KEY`, `AUTH_SECRET`, `USERS_JSON`, `ALLOWED_ORIGIN`.
4. Deploy. Anote a URL pública (ex: `https://agencia-crm.onrender.com`).
   Obs.: no free, o serviço "dorme" após inatividade e leva alguns segundos para acordar.

### 3. Dashboard no GitHub Pages
1. No `dashboard_agencia.html`, troque:
   `const API_BASE = "http://localhost:8080/api";`
   pela URL do Render + `/api`, ex:
   `const API_BASE = "https://agencia-crm.onrender.com/api";`
2. Settings → Pages → Deploy from branch. Anote a URL (ex: `https://usuario.github.io/repo`).
3. No Render, ajuste `ALLOWED_ORIGIN` para exatamente essa URL do Pages.

### 4. Usuários
- Gere o hash de cada senha e monte o `USERS_JSON`, ex:
  `{"rodolpho":"<sha256>","maria":"<sha256>"}`
- Coloque em `USERS_JSON` no Render. Cada pessoa entra com seu usuário e senha.

## Segurança
- Nenhum segredo fica no código: tudo por variável de ambiente / arquivos não versionados.
- Tokens de sessão são assinados (HMAC) e expiram.
- Em produção, sempre defina `ALLOWED_ORIGIN` (não deixe `*`) e um `AUTH_SECRET` forte.
- As credenciais do Google Sheets (`crm_agent`) também não podem ir para o repositório.

## Integração com Google Sheets (crm_agent.py)
Para o botão "Agendar no Sheets" funcionar, você precisa de uma conta de serviço do Google:

1. console.cloud.google.com → crie um projeto (ou use um existente).
2. Ative as APIs "Google Sheets API" e "Google Drive API".
3. IAM & Admin → Service Accounts → Create service account. Depois, na conta criada,
   Keys → Add key → JSON. Baixe o arquivo (é a credencial).
4. Abra a planilha no Google Sheets e compartilhe com o e-mail da conta de serviço
   (algo como `...@...iam.gserviceaccount.com`), com permissão de Editor.
5. Configuração:
   - Local: salve o JSON como `credenciais.json` ao lado dos scripts (o .gitignore já o ignora).
   - Render: cole o conteúdo do JSON na variável `GOOGLE_CREDENTIALS_JSON` e defina
     `SPREADSHEET_ID` (o ID que aparece na URL da planilha).
6. Teste local: `python crm_agent.py` deve imprimir "[OK] Conectado...".

Variáveis de ambiente do Sheets:
| Variável | Descrição |
|---|---|
| `GOOGLE_CREDENTIALS_JSON` | JSON completo da conta de serviço (produção) |
| `GOOGLE_CREDENTIALS_FILE` | Caminho do arquivo de credenciais (alternativa) |
| `SPREADSHEET_ID` | ID da planilha (recomendado) |
| `SPREADSHEET_NAME` | Nome da planilha (se não usar o ID) |
| `WORKSHEET_NAME` | Nome da aba (padrão: Agendamentos) |
