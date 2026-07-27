"""
crm_agent.py — Integração com Google Sheets para a Agência CRM Guanabara.

Usado por agencia_crm.py para salvar as campanhas agendadas em uma planilha.
Expõe duas funções que o agencia_crm.py espera:
    - connect_to_sheets() -> client gspread autenticado
    - setup_sheet(client) -> worksheet pronta (com cabeçalho)

Credenciais (conta de serviço do Google), em ordem de prioridade:
    1) env GOOGLE_CREDENTIALS_JSON  (o JSON inteiro da conta de serviço)
    2) env GOOGLE_CREDENTIALS_FILE  (caminho para o arquivo .json)
    3) arquivo local 'credenciais.json' ao lado deste script (NÃO versionar)

Planilha:
    - env SPREADSHEET_ID     (recomendado; o ID que aparece na URL da planilha)
      ou SPREADSHEET_NAME    (nome; será criada se não existir)
    - env WORKSHEET_NAME     (aba; padrão 'Agendamentos')
"""

import os
import json

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError as e:
    raise ImportError(
        "Dependências ausentes. Rode: pip install gspread google-auth"
    ) from e

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# Deve bater com a ordem das colunas montadas em agencia_crm.py
CABECALHO = ["Status", "Data/Hora", "Canal", "Segmento", "Campanha ID",
             "Titulo", "Mensagem", "Imagem", "Link"]


def _carregar_credenciais():
    raw = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if raw:
        return json.loads(raw)

    caminho = os.environ.get("GOOGLE_CREDENTIALS_FILE")
    if not caminho:
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credenciais.json")
        if os.path.exists(local):
            caminho = local

    if caminho and os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)

    raise RuntimeError(
        "Credenciais do Google não encontradas. Defina GOOGLE_CREDENTIALS_JSON "
        "(o JSON da conta de serviço) ou GOOGLE_CREDENTIALS_FILE (caminho do arquivo)."
    )


def connect_to_sheets():
    info = _carregar_credenciais()
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


def setup_sheet(client):
    sheet_id = os.environ.get("SPREADSHEET_ID")
    sheet_name = os.environ.get("SPREADSHEET_NAME", "Agenda CRM Guanabara")
    aba = os.environ.get("WORKSHEET_NAME", "Agendamentos")

    if sheet_id:
        planilha = client.open_by_key(sheet_id)
    else:
        try:
            planilha = client.open(sheet_name)
        except gspread.SpreadsheetNotFound:
            planilha = client.create(sheet_name)

    try:
        ws = planilha.worksheet(aba)
    except gspread.WorksheetNotFound:
        ws = planilha.add_worksheet(title=aba, rows=2000, cols=len(CABECALHO))

    # Garante o cabeçalho na primeira linha (agencia_crm.py insere a partir da linha 2)
    if not ws.get_all_values():
        ws.append_row(CABECALHO)

    return ws


if __name__ == "__main__":
    # Teste rápido de conexão
    try:
        c = connect_to_sheets()
        w = setup_sheet(c)
        print(f"[OK] Conectado. Planilha: '{w.spreadsheet.title}' / aba: '{w.title}'")
    except Exception as e:
        print(f"[ERRO] {e}")
