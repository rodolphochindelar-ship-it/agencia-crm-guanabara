import http.server
import json
import urllib.request
import ssl
import sys
import os
import time
import random
import calendar
import hashlib
import hmac
import base64
from datetime import date

# Configura o terminal para UTF-8 (Windows)
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

# =====================================================================================
# CONFIGURAÇÃO / SEGREDOS
# Nunca deixe segredos fixos no código. A ordem de leitura é:
#   1) variável de ambiente
#   2) arquivo local NÃO versionado (secrets.local.json) para desenvolvimento
# =====================================================================================
def _carregar_secrets_locais():
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets.local.json")
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Falha ao ler secrets.local.json: {e}")
    return {}

_SECRETS_LOCAIS = _carregar_secrets_locais()

def get_secret(nome, default=""):
    return os.environ.get(nome) or _SECRETS_LOCAIS.get(nome) or default

# Configurações do Gemini
GEMINI_API_KEY = get_secret("GEMINI_API_KEY", "")
GEMINI_MODEL = get_secret("GEMINI_MODEL", "gemini-2.5-flash")
URL_GEMINI = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"

# Chave para assinar os tokens de sessão (defina AUTH_SECRET no ambiente em produção)
AUTH_SECRET = get_secret("AUTH_SECRET", "troque-este-segredo-em-producao")
TOKEN_TTL_SEGUNDOS = int(get_secret("TOKEN_TTL_SEGUNDOS", "43200"))  # 12h

# CORS: em produção, defina ALLOWED_ORIGIN com o domínio do dashboard (ex: https://usuario.github.io)
ALLOWED_ORIGIN = get_secret("ALLOWED_ORIGIN", "*")

if not GEMINI_API_KEY:
    print("[!] AVISO: GEMINI_API_KEY não definida. Defina a variável de ambiente ou secrets.local.json.")

# =====================================================================================
# AUTENTICAÇÃO POR USUÁRIO
# Usuários em users.json (NÃO versionado) ou na env USERS_JSON, no formato:
#   { "usuario": "<sha256 do password>", ... }
# Gere o hash com:  python -c "import hashlib;print(hashlib.sha256('MINHASENHA'.encode()).hexdigest())"
# =====================================================================================
def _carregar_usuarios():
    env = os.environ.get("USERS_JSON")
    if env:
        try:
            return json.loads(env)
        except Exception as e:
            print(f"[!] USERS_JSON inválido: {e}")
    caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")
    if os.path.exists(caminho):
        try:
            with open(caminho, encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Falha ao ler users.json: {e}")
    return {}

USUARIOS = _carregar_usuarios()

def _hash_senha(senha):
    return hashlib.sha256(senha.encode("utf-8")).hexdigest()

def validar_login(usuario, senha):
    esperado = USUARIOS.get(usuario)
    return bool(esperado) and hmac.compare_digest(esperado, _hash_senha(senha))

def gerar_token(usuario):
    expira = int(time.time()) + TOKEN_TTL_SEGUNDOS
    corpo = f"{usuario}:{expira}"
    assinatura = hmac.new(AUTH_SECRET.encode(), corpo.encode(), hashlib.sha256).hexdigest()
    bruto = f"{corpo}:{assinatura}".encode()
    return base64.urlsafe_b64encode(bruto).decode()

def verificar_token(token):
    try:
        entrada = token.encode()
        brutos = base64.urlsafe_b64decode(entrada)
        # rejeita token nao-canonico (lixo apos o padding, etc.)
        if base64.urlsafe_b64encode(brutos) != entrada:
            return None
        bruto = brutos.decode()
        usuario, expira, assinatura = bruto.rsplit(":", 2)
        corpo = f"{usuario}:{expira}"
        esperado = hmac.new(AUTH_SECRET.encode(), corpo.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(esperado, assinatura):
            return None
        if int(expira) < int(time.time()):
            return None
        return usuario
    except Exception:
        return None

# =====================================================================================
# GRADE FIXA DIÁRIA (derivada do operacional_julho_2026)
# -------------------------------------------------------------------------------------
# Cada slot descreve um disparo recorrente que acontece todo dia. O campo "papel"
# indica a natureza do slot e serve para escolher o tema perene com afinidade correta.
# "dias_uteis" = True significa que o slot só entra de segunda a sexta (14h/15h no CSV).
# =====================================================================================
GRADE_DIARIA = [
    {"hora": "09:00", "canal": "App Push", "plataforma": "Firebase", "segmento": "Geral",    "papel": "institucional", "dias_uteis": False},
    {"hora": "10:00", "canal": "Web Push", "plataforma": "Pushnews", "segmento": "Geral",    "papel": "campanha",      "dias_uteis": False},
    {"hora": "11:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Ativos",   "papel": "fidelidade",    "dias_uteis": False},
    {"hora": "11:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Frios",    "papel": "urgencia",      "dias_uteis": False},
    {"hora": "11:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Em queda", "papel": "campanha",      "dias_uteis": False},
    {"hora": "14:00", "canal": "Web Push", "plataforma": "Insider",  "segmento": "Mobile",   "papel": "campanha",      "dias_uteis": True},
    {"hora": "14:00", "canal": "Web Push", "plataforma": "Insider",  "segmento": "Web",      "papel": "campanha",      "dias_uteis": True},
    {"hora": "15:00", "canal": "SMS",      "plataforma": "Insider",  "segmento": "Ativos",   "papel": "campanha",      "dias_uteis": True},
    {"hora": "16:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Ativos",   "papel": "campanha",      "dias_uteis": False},
    {"hora": "16:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Frios",    "papel": "fidelidade",    "dias_uteis": False},
    {"hora": "16:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Em queda", "papel": "reativacao",    "dias_uteis": False},
    {"hora": "18:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Ativos",   "papel": "fidelidade",    "dias_uteis": False},
    {"hora": "20:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Frios",    "papel": "cupom",         "dias_uteis": False},
    {"hora": "20:00", "canal": "App Push", "plataforma": "Insider",  "segmento": "Em queda", "papel": "fidelidade",    "dias_uteis": False},
]

# Segmento textual da Insider por segmento lógico (evita IDs numéricos, proibidos pelo Reviewer)
def nome_segmento_insider(segmento, data_ref="20260127"):
    mapa = {
        "Ativos":   f"{data_ref}_Ativos_PushApp_Operacional",
        "Frios":    f"{data_ref}_BaseFria_PushApp_Operacional",
        "Em queda": f"{data_ref}_EmQueda_PushApp_Operacional",
        "Mobile":   "Mobile",
        "Web":      "Web",
        "Geral":    "Geral",
    }
    return mapa.get(segmento, segmento)

# Detalhes automáticos de contexto por papel do slot (usados na copy quando o tema é perene)
DETALHES_POR_PAPEL = {
    "institucional": "Tom institucional/comercial: destaque formas de pagamento (Pix, cartão em até 12x), praticidade e confiança da marca.",
    "campanha":      "Campanha comercial: reforçar cupom IDAEVOLTA10 com 10% OFF na ida e volta e incentivo para tirar a viagem do papel.",
    "fidelidade":    "Programa Viva Fidelidade: incentivar consulta de pontos e resgate de passagem grátis.",
    "urgencia":      "Gatilho de urgência para base fria: preço sobe, poucas vagas, antecipe agora.",
    "reativacao":    "Reativação de base em queda: tom de saudade, novidades e condições atualizadas para voltar a viajar.",
    "cupom":         "Oferta de cupom para base fria: cupom IDAEVOLTA10 ativo, incentivo direto de conversão.",
}

# Pool default de temas perenes (usado se o dashboard não enviar nenhum)
TEMAS_PERENES_DEFAULT = ["Campanha", "Viva Fidelidade", "Comercial", "Antecipação", "Rotina"]

DIAS_SEMANA = {
    "segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def conectar_sheets_e_salvar(campanha_dados):
    """Importa funções de crm_agent para salvar o agendamento aprovado na planilha"""
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import crm_agent

        client = crm_agent.connect_to_sheets()
        worksheet = crm_agent.setup_sheet(client)

        nova_linha = [
            "Agendado",
            campanha_dados.get("data_hora", ""),
            campanha_dados.get("canal", ""),
            campanha_dados.get("segmento", ""),
            campanha_dados.get("campanha_id", ""),
            campanha_dados.get("titulo", ""),
            campanha_dados.get("texto", ""),
            campanha_dados.get("imagem", ""),
            campanha_dados.get("link", "")
        ]

        worksheet.insert_row(nova_linha, index=2)
        print(f"[+] Campanha '{campanha_dados.get('campanha_id')}' salva com sucesso no Google Sheets!")
        return True
    except Exception as e:
        print(f"[-] Erro ao salvar no Google Sheets: {e}")
        return False

def salvar_campanhas_massa(lista_campanhas):
    """Salva uma lista de campanhas em lote na planilha do Google Sheets de uma só vez"""
    try:
        sys.path.append(os.path.dirname(os.path.abspath(__file__)))
        import crm_agent

        client = crm_agent.connect_to_sheets()
        worksheet = crm_agent.setup_sheet(client)

        linhas_a_inserir = []
        for c in lista_campanhas:
            linhas_a_inserir.append([
                "Agendado",
                c.get("data_hora", ""),
                c.get("canal", ""),
                c.get("segmento", ""),
                c.get("campanha_id", ""),
                c.get("titulo", ""),
                c.get("texto", ""),
                c.get("imagem", ""),
                c.get("link", "")
            ])

        # Insere todas as linhas de uma vez na planilha a partir da linha 2
        worksheet.insert_rows(linhas_a_inserir, row=2)
        print(f"[+] Sucesso: {len(linhas_a_inserir)} campanhas salvas em lote no Google Sheets!")
        return True
    except Exception as e:
        print(f"[-] Erro ao salvar campanhas em lote: {e}")
        return False

def chamar_gemini(prompt):
    payload = {
        "contents": [{
            "parts": [{
                "text": prompt
            }]
        }]
    }
    headers = {
        "Content-Type": "application/json"
    }
    data = json.dumps(payload).encode('utf-8')
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(URL_GEMINI, data=data, headers=headers, method='POST')

    for tentativa in range(3):
        try:
            with urllib.request.urlopen(req, context=ctx) as response:
                res = json.loads(response.read().decode('utf-8'))
                return res['candidates'][0]['content']['parts'][0]['text']
        except Exception as e:
            print(f"    [!] Erro de API (Tentativa {tentativa+1}/3): {e}")
            time.sleep(2)

    return f"Erro persistente na chamada do Gemini."


def _limpar_json(bruto):
    """Remove cercas de markdown e devolve o texto JSON puro."""
    limpo = bruto.strip()
    if limpo.startswith("```"):
        linhas = limpo.split("\n")
        if linhas[0].startswith("```"):
            linhas = linhas[1:]
        if linhas and linhas[-1].startswith("```"):
            linhas = linhas[:-1]
        limpo = "\n".join(linhas).strip()
    return limpo


def orquestrar_agencia(briefing):
    print("\n--- INICIANDO FLUXO DA AGÊNCIA CRM ---")

    # 1. Agente 1: Planner
    print("[*] Chamando o Campaign Planner...")
    prompt_planner = f"""
    Você é o **Campaign Planner** da Agência Guanabara.
    Com base no Briefing a seguir, crie a estratégia tática da campanha:
    - Determine o melhor canal (App Push, Web Push, SMS ou Email).
    - Determine a segmentação recomendada na Insider. IMPORTANTE: Use apenas nomes textuais exatos (ex: '20260127_Ativos_PushApp_Operacional', '20260127_BaseFria_PushApp_Operacional', '20260127_EmQueda_PushApp_Operacional'). NUNCA use IDs de segmento numéricos como 2433914.
    - Crie o cronograma e descreva a estratégia de frequência (como evitar repetição excessiva do mesmo tema dia a dia).

    BRIEFING:
    {json.dumps(briefing, ensure_ascii=False, indent=2)}

    Responda em formato markdown curto e direto.
    """
    planejamento = chamar_gemini(prompt_planner)

    # 2. Agente 2: Copywriter
    print("[*] Chamando o Copywriter...")
    prompt_copywriter = f"""
    Você é o **CRM Copywriter** da Agência Guanabara.
    Com base na estratégia do Planejador e no briefing, escreva as copies.
    - Escreva de forma humanizada, calorosa e descontraída (tom Guanabara).
    - Adeque o tom ao segmento escolhido (Ativos: promocional/engajador, Frios: cupons/urgência, Em Queda: sentimentos de 'saudade').
    - Crie 3 variações de Título e Mensagem (corpo).
    - Se aplicável, inclua o cupom de desconto com a validade correta.

    ESTRATÉGIA DO PLANEJADOR:
    {planejamento}

    BRIEFING ORIGINAL:
    {json.dumps(briefing, ensure_ascii=False, indent=2)}

    Responda em markdown fornecendo as 3 variações claramente rotuladas.
    """
    copys = chamar_gemini(prompt_copywriter)

    # 3. Agente 3: Designer
    print("[*] Chamando o Designer...")
    prompt_designer = f"""
    Você é o **CRM Designer** da Agência Guanabara.
    Com base no planejamento e nas copies, forneça o conceito visual:
    - Sugira cores harmônicas e elegantes coerentes com o tema.
    - Descreva o conceito da imagem ou layout do push/email.
    - Crie um prompt de imagem detalhado em português para ser usado em IAs geradoras de imagem (como Midjourney ou Imagen), focando na cultura e paisagens brasileiras, ônibus modernos e viagens confortáveis.

    COPIES DA CAMPANHA:
    {copys}

    Responda em markdown curto.
    """
    design = chamar_gemini(prompt_designer)

    # 4. Agente 4: Safety & Quality Reviewer (Revisão Severa)
    print("[*] Chamando o Safety Reviewer (Revisão Severa)...")
    prompt_reviewer = f"""
    Você é o **CRM Safety & Quality Reviewer (Revisor Severo)** da Agência Guanabara.
    Sua missão é auditar rigorosamente tudo o que foi produzido pelo Planner, Copywriter e Designer.

    Regras Críticas a Validar:
    1. **Ortografia e Gramática**: Verifique minuciosamente erros gramaticais nas copies geradas.
    2. **API da Insider**: O segmento de destino DEVE ser especificado apenas por seu nome textual exato (ex: '20260127_Ativos_PushApp_Operacional'). Nomes de segmento que usem apenas IDs numéricos (ex: 2433914) são terminantemente proibidos e devem ser apontados como erro de segurança crítico.
    3. **Regras de Futebol (Se aplicável)**: Campanhas de fim de jogo ou lances de futebol devem conter controle total pós-jogo e só disparar sob a condição estrita de vitória do Brasil (brasil_venceu). Em caso de empate/derrota, o disparo deve ser bloqueado totalmente.
    4. **Frequência/Temas**: Verifique se a campanha corre risco de cansar o usuário por repetição excessiva do mesmo tema dia a dia.

    CONTEÚDOS PRODUZIDOS:
    - Planejamento: {planejamento}
    - Copies: {copys}
    - Design: {design}

    Retorne a sua resposta estritamente em formato JSON com a seguinte estrutura (não coloque tags de markdown como ```json, retorne apenas o texto JSON puro):
    {{
      "status": "APROVADO" ou "REJEITADO",
      "checklist_ortografia": "Verde / Correto" ou "Vermelho / Erros encontrados (detalhar)",
      "checklist_insider": "Verde / Segmento textual válido" ou "Vermelho / ID numérico proibido detectado",
      "checklist_futebol": "Verde / Em conformidade" ou "Vermelho / Falta validação de vitória do Brasil (ou Não aplicável)",
      "checklist_mescla_temas": "Verde / Boa variação" ou "Amarelo / Risco de saturação do tema",
      "criticas_e_sugestoes": "Detalhamento severo de erros encontrados e o que deve ser ajustado antes de disparar",
      "copys_revisadas": {{
         "titulo_sugerido": "Título final corrigido/aprimorado para agendamento",
         "mensagem_sugerida": "Mensagem final corrigida/aprimorada para agendamento"
      }}
    }}
    """
    revisao_bruta = chamar_gemini(prompt_reviewer)

    revisao_dados = {}
    try:
        revisao_dados = json.loads(_limpar_json(revisao_bruta))
    except Exception as e:
        print(f"[-] Erro ao processar JSON da revisão: {e}")
        revisao_dados = {
            "status": "REJEITADO",
            "criticas_e_sugestoes": f"Falha no formato de resposta do revisor. Resposta bruta: {revisao_bruta}"
        }

    return {
        "planejamento": planejamento,
        "copys": copys,
        "design": design,
        "revisao": revisao_dados
    }

# =====================================================================================
# MOTOR DE CALENDÁRIO MENSAL
# =====================================================================================

def _normaliza_tema(t):
    """Aceita string simples ou dict e devolve um dict de tema padronizado."""
    if isinstance(t, str):
        return {"nome": t, "tipo": "perene", "datas": [], "dia_semana": "",
                "segmentos_alvo": [], "detalhes": "", "cobertura": "parcial"}
    return {
        "nome": t.get("nome", ""),
        "tipo": t.get("tipo", "perene"),                 # perene | evento | recorrente
        "datas": t.get("datas", []),                     # ["05", "13"] ou ["05/07"] p/ evento
        "dia_semana": (t.get("dia_semana", "") or "").lower(),   # p/ recorrente
        "segmentos_alvo": t.get("segmentos_alvo", []),   # vazio = todos os slots elegíveis
        "detalhes": t.get("detalhes", ""),
        "cobertura": t.get("cobertura", "parcial"),      # dia_todo | parcial
    }


def _dia_do_mes(d):
    """Extrai o número do dia de formatos '05', '05/07' ou '05/07/2026'."""
    s = str(d).strip()
    if "/" in s:
        s = s.split("/")[0]
    try:
        return int(s)
    except ValueError:
        return None


def _tema_aplica_no_slot(tema, slot):
    """Verifica se o tema pode ocupar este slot (filtro por segmento alvo)."""
    alvos = tema.get("segmentos_alvo") or []
    if not alvos:
        return True
    return slot["segmento"] in alvos


def montar_grade_mensal(mes, ano, temas):
    """
    Monta a grade de agendamento do mês inteiro sobre a GRADE_DIARIA fixa.

    Regras:
    - Temas de EVENTO (data fixa) e RECORRENTES (dia da semana) têm prioridade e
      ocupam os slots elegíveis nas suas datas. cobertura='dia_todo' ocupa todos os
      slots do dia; 'parcial' ocupa apenas os slots dos seus segmentos_alvo.
    - Os slots restantes são preenchidos por temas PERENES, escolhidos por afinidade
      com o papel do slot e sem repetir o tema anterior na mesma combinação canal+segmento.
    - Slots marcados como dias_uteis só entram de segunda a sexta.

    Retorna lista de dicts (uma linha por disparo), pronta para receber copy.
    """
    temas = [_normaliza_tema(t) for t in temas]
    perenes = [t for t in temas if t["tipo"] == "perene"] or \
              [_normaliza_tema(n) for n in TEMAS_PERENES_DEFAULT]
    eventos = [t for t in temas if t["tipo"] == "evento"]
    recorrentes = [t for t in temas if t["tipo"] == "recorrente"]

    # Indexa eventos por dia do mês
    eventos_por_dia = {}
    for ev in eventos:
        for d in ev["datas"]:
            n = _dia_do_mes(d)
            if n:
                eventos_por_dia.setdefault(n, []).append(ev)

    # Indexa recorrentes por weekday
    recorrentes_por_wd = {}
    for rc in recorrentes:
        wd = DIAS_SEMANA.get(rc["dia_semana"])
        if wd is not None:
            recorrentes_por_wd.setdefault(wd, []).append(rc)

    num_dias = calendar.monthrange(ano, mes)[1]
    historico = {}   # (hora, canal, segmento) -> último tema perene usado nesse slot
    idx_perene = {}  # (hora, canal, segmento) -> índice de rotação do slot
    grade = []

    for dia in range(1, num_dias + 1):
        wd = date(ano, mes, dia).weekday()  # 0=segunda ... 6=domingo
        especiais_hoje = eventos_por_dia.get(dia, []) + recorrentes_por_wd.get(wd, [])

        for slot in GRADE_DIARIA:
            if slot["dias_uteis"] and wd >= 5:
                continue  # pula slot de dia útil no fim de semana

            tema_escolhido = None
            natureza = "perene"
            tema_obj = None

            # 1) Prioridade: evento/recorrente que cobre este slot
            for esp in especiais_hoje:
                cobre = esp["cobertura"] == "dia_todo" or _tema_aplica_no_slot(esp, slot)
                if cobre and _tema_aplica_no_slot(esp, slot):
                    tema_escolhido = esp["nome"]
                    natureza = esp["tipo"]
                    tema_obj = esp
                    break

            # 2) Perene por afinidade de papel, sem repetir o anterior no mesmo slot
            if not tema_escolhido:
                chave = (slot["hora"], slot["canal"], slot["segmento"])
                ultimo = historico.get(chave)
                candidatos = _perenes_por_papel(perenes, slot["papel"])
                disponiveis = [t for t in candidatos if t["nome"] != ultimo] or candidatos
                i = idx_perene.get(chave, 0) % len(disponiveis)
                tema_obj = disponiveis[i]
                idx_perene[chave] = i + 1
                tema_escolhido = tema_obj["nome"]
                historico[chave] = tema_escolhido

            data_str = f"{dia:02d}/{mes:02d}"
            data_ref = f"{ano}{mes:02d}{dia:02d}"
            grade.append({
                "dia": dia,
                "data": data_str,
                "data_hora": f"{data_str} {slot['hora']}",
                "hora": slot["hora"],
                "canal": slot["canal"],
                "plataforma": slot["plataforma"],
                "segmento": slot["segmento"],
                "segmento_insider": nome_segmento_insider(slot["segmento"], data_ref),
                "papel": slot["papel"],
                "tema": tema_escolhido,
                "natureza": natureza,   # perene | evento | recorrente
                "detalhes": (tema_obj.get("detalhes") if tema_obj else "") or DETALHES_POR_PAPEL.get(slot["papel"], ""),
                "titulo": "",
                "texto": "",
                "status_revisao": "PENDENTE",
                "imagem": "",
                "link": "",
            })

    return grade


def _perenes_por_papel(perenes, papel):
    """Filtra o pool de perenes por afinidade com o papel do slot; cai no pool total se nada casar."""
    afinidade = {
        "institucional": ["comercial", "institucional", "formas de pagamento"],
        "campanha":      ["campanha", "viaje", "cupom", "desconto", "antecipação", "antecipacao", "rotina"],
        "fidelidade":    ["fidelidade", "viva", "resgate", "pontos"],
        "urgencia":      ["urgência", "urgencia", "antecipação", "antecipacao"],
        "reativacao":    ["reativação", "reativacao", "saudade"],
        "cupom":         ["cupom", "desconto", "campanha"],
    }
    chaves = afinidade.get(papel, [])
    casados = [t for t in perenes if any(k in t["nome"].lower() for k in chaves)]
    return casados or perenes


def _campanha_id(item):
    canal = item["canal"].lower().replace(" ", "")
    tema = item["tema"].lower().replace(" ", "_")
    seg = item["segmento"].lower().replace(" ", "")
    d = item["data"].replace("/", "")
    return f"2026_{canal}_{tema}_{seg}_{d}"


def gerar_variacoes_copy(tema, papel, canal, segmento, detalhes, n=6):
    """Gera N variações de título+mensagem para uma combinação, via Gemini (1 chamada)."""
    seg_ctx = {
        "Ativos": "cliente ativo, tom promocional e engajador",
        "Frios": "base fria, foco em cupom e urgência",
        "Em queda": "cliente em queda, tom de saudade e reativação",
        "Mobile": "usuário web mobile",
        "Web": "usuário web desktop",
        "Geral": "base geral",
    }.get(segmento, segmento)

    prompt = f"""
Você é a **Agência CRM da Viação Guanabara**. Gere {n} variações de copy para {canal}.
- Tema: {tema}
- Público/segmento: {segmento} ({seg_ctx})
- Contexto: {detalhes}
- Tom Guanabara: humanizado, caloroso, descontraído. Português impecável, sem erros.
- Título curto e cativante; mensagem persuasiva e curta (adequada a push/SMS).
- NUNCA use IDs numéricos de segmentação no texto.

Retorne SOMENTE um array JSON puro (sem markdown), no formato:
[{{"titulo": "...", "mensagem": "..."}}, ...]
"""
    bruto = chamar_gemini(prompt)
    try:
        dados = json.loads(_limpar_json(bruto))
        if isinstance(dados, list) and dados:
            return [{"titulo": d.get("titulo", ""), "mensagem": d.get("mensagem", "")} for d in dados]
    except Exception as e:
        print(f"    [-] Falha ao parsear variações ({tema}/{segmento}): {e}")
    # Fallback
    return [{"titulo": f"{tema}", "mensagem": f"Aproveite {tema} com a Guanabara!"}]


def revisar_combinacao(tema, canal, segmento, segmento_insider, variacoes):
    """Roda o Safety Reviewer sobre o conjunto de copies de uma combinação (1 chamada)."""
    prompt = f"""
Você é o **CRM Safety & Quality Reviewer (Revisor Severo)** da Agência Guanabara.
Audite as copies abaixo para a combinação: Tema={tema}, Canal={canal}, Segmento={segmento}
(segmento Insider textual: {segmento_insider}).

Regras críticas:
1. Ortografia e gramática impecáveis em português.
2. Segmento Insider deve ser textual (nunca ID numérico como 2433914).
3. Sem risco de saturação/repetição excessiva.
4. Se o tema envolver jogo de futebol, deve haver controle pós-jogo (disparo só se Brasil vencer).

COPIES:
{json.dumps(variacoes, ensure_ascii=False, indent=2)}

Retorne SOMENTE JSON puro (sem markdown):
{{
  "status": "APROVADO" ou "REVISAR",
  "checklist_ortografia": "Verde / Correto" ou "Vermelho / (detalhar)",
  "checklist_insider": "Verde / Segmento textual válido" ou "Vermelho / ID numérico detectado",
  "checklist_futebol": "Verde / Em conformidade" ou "Não aplicável" ou "Vermelho / (detalhar)",
  "checklist_mescla_temas": "Verde / Boa variação" ou "Amarelo / Risco de saturação",
  "criticas_e_sugestoes": "resumo objetivo"
}}
"""
    bruto = chamar_gemini(prompt)
    try:
        return json.loads(_limpar_json(bruto))
    except Exception as e:
        return {"status": "REVISAR", "criticas_e_sugestoes": f"Falha no parse do revisor: {bruto[:200]}"}


def orquestrar_calendario_mensal(req_dados):
    """
    Gera o calendário completo do mês: grade fixa + copies (Gemini) + revisão por combinação.
    req_dados:
      - mes (int), ano (int)  OU  mes_ano "MM/AAAA"
      - temas: lista de temas (perene/evento/recorrente)
      - somente_grade: bool -> se True, não chama Gemini (retorna só a grade)
      - variacoes_por_combo: int (default 6)
    """
    if "mes" in req_dados and "ano" in req_dados:
        mes, ano = int(req_dados["mes"]), int(req_dados["ano"])
    else:
        mm, aa = (req_dados.get("mes_ano", "08/2026")).split("/")
        mes, ano = int(mm), int(aa)

    temas = req_dados.get("temas", [])
    somente_grade = bool(req_dados.get("somente_grade", False))
    n_var = int(req_dados.get("variacoes_por_combo", 4))

    print(f"\n[+] Montando grade mensal de {mes:02d}/{ano} com {len(temas)} tema(s)...")
    grade = montar_grade_mensal(mes, ano, temas)
    print(f"[+] Grade gerada: {len(grade)} disparos.")

    for item in grade:
        item["campanha_id"] = _campanha_id(item)

    if somente_grade:
        return {"mes": mes, "ano": ano, "total": len(grade), "grade": grade, "combos": []}

    # Gera copy por combinação única (tema, canal, segmento) e reaproveita ao longo do mês
    combos = {}
    for item in grade:
        chave = (item["tema"], item["canal"], item["segmento"])
        combos.setdefault(chave, {"itens": [], "papel": item["papel"], "detalhes": item["detalhes"],
                                  "segmento_insider": item["segmento_insider"]})
        combos[chave]["itens"].append(item)

    print(f"[+] {len(combos)} combinações únicas. Gerando copies + revisão...")
    resumo_combos = []
    for (tema, canal, segmento), info in combos.items():
        print(f"    [*] {tema} | {canal} | {segmento} ({len(info['itens'])} disparos)")
        variacoes = gerar_variacoes_copy(tema, info["papel"], canal, segmento, info["detalhes"], n=n_var)
        revisao = revisar_combinacao(tema, canal, segmento, info["segmento_insider"], variacoes)
        status = revisao.get("status", "REVISAR")
        # Distribui as variações entre os disparos da combinação (rotação)
        for j, item in enumerate(info["itens"]):
            v = variacoes[j % len(variacoes)]
            item["titulo"] = v["titulo"]
            item["texto"] = v["mensagem"]
            item["status_revisao"] = status
        resumo_combos.append({
            "tema": tema, "canal": canal, "segmento": segmento,
            "qtd": len(info["itens"]), "variacoes": len(variacoes),
            "status": status, "revisao": revisao
        })
        time.sleep(0.4)  # rate limiting Gemini

    return {"mes": mes, "ano": ano, "total": len(grade), "grade": grade, "combos": resumo_combos}


# ---- Compat: geração em massa antiga ----
def gerar_conteudo_campanha_massa(tema, canal, segmento, data_hora, detalhes):
    """Gera uma campanha individual e roda a revisão automática (Safety Reviewer)"""
    prompt = f"""
Você é a **Agência CRM da Viação Guanabara**.
Sua tarefa é criar e revisar uma notificação push para a seguinte configuração:
- Canal: {canal}
- Segmento Insider: {segmento}
- Tema da Campanha: {tema}
- Data/Hora do Disparo: {data_hora}
- Detalhes/Contexto: {detalhes}

Requisitos textuais:
- Escrita persuasiva, humanizada, calorosa e típica do tom Guanabara.
- Sem erros ortográficos ou gramaticais na língua portuguesa.
- Sem IDs numéricos de segmentação no nome de campanha ou corpo.

Retorne a resposta estritamente em formato JSON com a seguinte estrutura (sem markdown ou texto extra):
{{
  "titulo": "Título cativante e curto para o push/mensagem",
  "mensagem": "Corpo da mensagem ou texto do push persuasivo",
  "status_ortografia": "Verde / Correto" ou "Vermelho / Erros encontrados (corrigir)",
  "status_insider": "Verde / Segmento textual seguro"
}}
"""
    resposta_bruta = chamar_gemini(prompt)

    try:
        dados = json.loads(_limpar_json(resposta_bruta))
        return {
            "data_hora": data_hora,
            "canal": canal,
            "segmento": segmento,
            "campanha_id": f"2026_{canal.lower().replace(' ', '')}_{tema.lower().replace(' ', '_')}_{data_hora.split(' ')[0].replace('/', '')}",
            "tema": tema,
            "titulo": dados.get("titulo", ""),
            "texto": dados.get("mensagem", ""),
            "status_revisao": "APROVADO" if "Verde" in dados.get("status_ortografia", "") else "REVISAR",
            "imagem": "",
            "link": ""
        }
    except Exception as e:
        print(f"[-] Erro ao parsear campanha massiva: {e}")
        return {
            "data_hora": data_hora,
            "canal": canal,
            "segmento": segmento,
            "campanha_id": "erro_geracao",
            "tema": tema,
            "titulo": f"Campanha {tema}",
            "texto": f"Aproveite as ofertas de {tema} com a Guanabara!",
            "status_revisao": "REVISAR",
            "imagem": "",
            "link": ""
        }

def orquestrar_geracao_massa(req_dados):
    mes_ano = req_dados.get("mes_ano", "08/2026")  # Formato MM/AAAA
    qtd_campanhas = int(req_dados.get("qtd", 10))
    temas = req_dados.get("temas", ["Viva Fidelidade", "Cupom Desconto", "Conforto", "Destinos"])
    detalhes_gerais = req_dados.get("detalhes_gerais", "")

    canais = ["App Push", "Web Push", "SMS", "Email"]
    segmentos = {
        "App Push": ["20260127_Ativos_PushApp_Operacional", "20260127_BaseFria_PushApp_Operacional", "20260127_EmQueda_PushApp_Operacional"],
        "Web Push": ["Mobile", "Web", "Geral"],
        "SMS": ["Ativos", "Frios"],
        "Email": ["Ativos", "Frios"]
    }

    campanhas_geradas = []
    print(f"\n[+] Iniciando geracao massiva de {qtd_campanhas} campanhas para {mes_ano}...")
    historico_temas = {}

    for i in range(qtd_campanhas):
        dia = int(1 + (i * (28 / max(1, qtd_campanhas - 1))))
        dia = min(28, max(1, dia))
        data_campanha = f"{dia:02d}/{mes_ano}"
        hora_campanha = f"{random.choice(['09:00', '11:00', '14:00', '16:00', '18:00'])}"
        data_hora = f"{data_campanha} {hora_campanha}"

        canal = canais[i % len(canais)]
        segmento = random.choice(segmentos[canal])

        chave_par = (canal, segmento)
        ultimo_tema = historico_temas.get(chave_par, "")
        temas_disponiveis = [t for t in temas if t != ultimo_tema] or temas
        tema_escolhido = random.choice(temas_disponiveis)
        historico_temas[chave_par] = tema_escolhido

        detalhes_adicionais = detalhes_gerais
        if "fidelidade" in tema_escolhido.lower():
            detalhes_adicionais += " Foco no programa Viva Fidelidade, incentivar consulta de pontos e resgate."
        elif "cupom" in tema_escolhido.lower() or "desconto" in tema_escolhido.lower():
            detalhes_adicionais += " Oferecer cupom VIAJEGUANABARA com 10% OFF."
        elif "conforto" in tema_escolhido.lower() or "frota" in tema_escolhido.lower():
            detalhes_adicionais += " Destacar tomadas USB, ar-condicionado, Wi-Fi e poltronas semi-leito."

        print(f"[*] Gerando ({i+1}/{qtd_campanhas}): {data_hora} | {canal} | {segmento} | Tema: {tema_escolhido}")
        campanha = gerar_conteudo_campanha_massa(tema_escolhido, canal, segmento, data_hora, detalhes_adicionais.strip())
        campanhas_geradas.append(campanha)
        time.sleep(1.5)

    return campanhas_geradas


# =====================================================================================
# BRIEFING PARA O TIME DE DESIGN (por canal)
# =====================================================================================
FORMATOS_CANAL = {
    "WhatsApp":  "Peca de WhatsApp (imagem 1080x1080 ou 1080x1350, ou template com botoes). Texto curto, 1 CTA claro.",
    "Email":     "E-mail marketing (largura 600px, header + hero + corpo + CTA + rodape). Suporta mais texto e secoes.",
    "App Push":  "Notificacao push do app (titulo ate ~40 caracteres, corpo ate ~120, icone/imagem opcional).",
    "Web Push":  "Notificacao web push (titulo curto, corpo curto, imagem pequena opcional, 1 CTA).",
}

def gerar_briefing_design(dados):
    """Gera um briefing de design completo por canal, para o time de criacao."""
    tema = dados.get("tema", "")
    objetivo = dados.get("objetivo", "")
    publico = dados.get("publico", "")
    oferta = dados.get("oferta", "")
    tom = dados.get("tom", "Guanabara: humanizado, caloroso, descontraido")
    obrigatorios = dados.get("obrigatorios", "")
    canais = dados.get("canais", ["WhatsApp", "Email", "App Push", "Web Push"])

    especificacoes = "\n".join(f"- {c}: {FORMATOS_CANAL.get(c, c)}" for c in canais)

    prompt = f"""
Voce e o **Diretor de Criacao da Agencia CRM da Viacao Guanabara**.
Gere um BRIEFING DE DESIGN completo, um por canal, para o time de criacao executar as pecas.

CONTEXTO DA CAMPANHA:
- Tema: {tema}
- Objetivo: {objetivo}
- Publico-alvo: {publico}
- Oferta/Cupom: {oferta}
- Tom de voz: {tom}
- Elementos obrigatorios: {obrigatorios}

CANAIS E FORMATOS:
{especificacoes}

Para CADA canal, entregue: objetivo da peca, formato/dimensoes, copy (titulo, corpo, cta),
conceito visual (descricao do layout e da imagem), paleta de cores sugerida (hex),
elementos obrigatorios, e um prompt de imagem detalhado em portugues para IA generativa
(focando cultura e paisagens brasileiras, onibus modernos, viagens confortaveis).

Retorne SOMENTE JSON puro (sem markdown), no formato:
{{
  "campanha": "{tema}",
  "pecas": [
    {{
      "canal": "WhatsApp",
      "objetivo": "...",
      "formato": "...",
      "copy": {{ "titulo": "...", "corpo": "...", "cta": "..." }},
      "conceito_visual": "...",
      "paleta": ["#RRGGBB", "#RRGGBB"],
      "elementos_obrigatorios": ["..."],
      "prompt_imagem": "..."
    }}
  ]
}}
"""
    bruto = chamar_gemini(prompt)
    try:
        return json.loads(_limpar_json(bruto))
    except Exception as e:
        print(f"[-] Falha ao parsear briefing de design: {e}")
        return {"campanha": tema, "pecas": [], "erro": f"Formato inesperado do modelo: {bruto[:200]}"}


class AgenciaCRMHandler(http.server.BaseHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', ALLOWED_ORIGIN)
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def _responder_json(self, payload, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def _usuario_autenticado(self):
        """Retorna o usuario do token valido no header Authorization, ou None.
        Se nenhum usuario estiver cadastrado (USUARIOS vazio), libera o acesso
        para facilitar o uso local. Em producao, cadastre usuarios."""
        if not USUARIOS:
            return "local"
        cabecalho = self.headers.get("Authorization", "")
        if cabecalho.startswith("Bearer "):
            return verificar_token(cabecalho[7:].strip())
        return None

    def do_GET(self):
        if self.path in ("/", "/dashboard", "/dashboard_agencia.html"):
            caminho = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_agencia.html")
            if os.path.exists(caminho):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                with open(caminho, 'rb') as f:
                    self.wfile.write(f.read())
                return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length) if content_length else b"{}"
        try:
            dados = json.loads(post_data.decode('utf-8') or "{}")
        except Exception:
            dados = {}

        # --- Rotas publicas ---
        if self.path == "/api/ping":
            self._responder_json({"ok": True, "auth_required": bool(USUARIOS)})
            return

        if self.path == "/api/login":
            usuario = dados.get("usuario", "")
            senha = dados.get("senha", "")
            if validar_login(usuario, senha):
                self._responder_json({"success": True, "token": gerar_token(usuario), "usuario": usuario})
            else:
                self._responder_json({"success": False, "erro": "Usuario ou senha invalidos."}, status=401)
            return

        # --- Daqui em diante, exige autenticacao ---
        usuario_logado = self._usuario_autenticado()
        if usuario_logado is None:
            self._responder_json({"erro": "Nao autorizado. Faca login."}, status=401)
            return

        if self.path == "/api/briefing":
            print(f"\n[+] Briefing unitario recebido: {dados.get('campanha_id')}")
            self._responder_json(orquestrar_agencia(dados))

        elif self.path == "/api/briefing_design":
            print(f"\n[+] Briefing de design solicitado: {dados.get('tema')}")
            self._responder_json(gerar_briefing_design(dados))

        elif self.path == "/api/gerar_grade":
            print(f"\n[+] Gerando grade (preview) do calendario.")
            dados["somente_grade"] = True
            self._responder_json(orquestrar_calendario_mensal(dados))

        elif self.path == "/api/gerar_calendario":
            print(f"\n[+] Gerando calendario completo (copy + revisao).")
            self._responder_json(orquestrar_calendario_mensal(dados))

        elif self.path == "/api/gerar_massa":
            print(f"\n[+] Solicitacao de geracao em massa recebida.")
            self._responder_json(orquestrar_geracao_massa(dados))

        elif self.path == "/api/save":
            print(f"\n[+] Salvando campanha unitaria no Google Sheets.")
            self._responder_json({"success": conectar_sheets_e_salvar(dados)})

        elif self.path == "/api/save_massa":
            print(f"\n[+] Salvando lote de campanhas no Google Sheets.")
            self._responder_json({"success": salvar_campanhas_massa(dados.get("campanhas", []))})

        else:
            self.send_response(404)
            self.end_headers()

def run_server(port=8080):
    server_address = ('', port)
    httpd = http.server.HTTPServer(server_address, AgenciaCRMHandler)
    print(f"\n[ON] API da Agencia de CRM Guanabara ativa na porta {port}...")
    print(f"Abra http://localhost:{port}/ no navegador para usar o dashboard.")
    httpd.serve_forever()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            pass
    run_server(port)
