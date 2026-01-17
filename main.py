# ==========================================================
# API BACKEND - AGIL SAAS (Versão Segura .ENV)
# ==========================================================
import os
import shutil
import json
import requests
import urllib.parse
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
import psycopg2
import psycopg2.extras 
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import base64
import uuid 
import mercadopago
from datetime import datetime, date, timedelta
from fastapi.responses import JSONResponse
import time
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart


# --- NOVO: IMPORTAR O DOTENV ---
from dotenv import load_dotenv


# No topo do arquivo, junto com os outros os.getenv
FRONTEND_URL = os.getenv("FRONTEND_URL", "https://agil.modestotech.com.br")

# Força o Python a procurar o .env na mesma pasta deste arquivo (main.py)
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)

# --- DEBUG DE SEGURANÇA (VAI APARECER NO TERMINAL) ---
print(f"📂 Procurando .env em: {env_path}")
mp_token = os.getenv("MP_ACCESS_TOKEN")

# --- BIBLIOTECAS DE CRIPTOGRAFIA ---
try:
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
    TEM_CRYPTOGRAPHY = True
except ImportError:
    print("❌ ALERTA: Biblioteca 'cryptography' não instalada!")
    print("❌ As imagens ficarão em baixa qualidade. Rode: pip install cryptography")
    TEM_CRYPTOGRAPHY = False

# --- CONFIGURAÇÃO MERCADO PAGO ---
# Agora pega do arquivo .env
mp_token = os.getenv("MP_ACCESS_TOKEN")
if not mp_token:
    print("⚠️ AVISO: Token do Mercado Pago não encontrado no .env")
sdk_mp = mercadopago.SDK(mp_token)

# --- CONFIGURAÇÃO DE PASTAS ---
os.makedirs("uploads", exist_ok=True)
os.environ["PYTHONIOENCODING"] = "utf-8"

app = FastAPI()

# Monta a pasta para ser acessível via URL 
app.mount("/arquivos", StaticFiles(directory="uploads"), name="arquivos")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VARIÁVEL DE MEMÓRIA ---
user_state = {}
msg_cache = {} # <--- ADICIONE ISSO PARA O ANTI-DUPLICIDADE

# --- CONFIGURAÇÕES DO SISTEMA (Via .env) ---
EVO_API_URL = os.getenv("EVO_API_URL")
EVO_API_KEY = os.getenv("EVO_API_KEY")
DOMAIN_URL  = os.getenv("DOMAIN_URL")
LOCAL_URL   = os.getenv("LOCAL_URL")

# --- CONFIGURAÇÕES DO BANCO DE DADOS (Via .env) ---
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")
DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_PORT = os.getenv("DB_PORT")

def get_connection():
    try:
        dsn = f"host={DB_HOST} port={DB_PORT} dbname={DB_NAME} user={DB_USER} password={DB_PASS} connect_timeout=10"
        conn = psycopg2.connect(dsn)
        conn.set_client_encoding('UTF8')
        return conn
    except Exception as e:
        print(f"ERRO NA CONEXÃO: {str(e)}")
        raise e

# --- MODELOS ---
class Gatilho(BaseModel):
    instancia: str
    gatilho: str
    resposta: str
    titulo_menu: Optional[str] = "Geral"
    categoria: Optional[str] = "Atendimento"
    tipo_midia: Optional[str] = "texto"
    url_midia: Optional[str] = None
    id_pai: Optional[int] = None 

class ConsultaGatilho(BaseModel):
    instancia: str
    mensagem: str
    numero: str 

# Função para enviar mensagem para o cliente
def enviar_mensagem_smart(instancia, numero, texto, id_gatilho_atual=None, apenas_texto=False):
    instancia = str(instancia).strip()
    print(f"🚀 Enviando para {numero}...")

    opcoes = []
    if not apenas_texto:
        try:
            conn = get_connection()
            cur = conn.cursor()
            
            if id_gatilho_atual:
                cur.execute("SELECT gatilho, titulo_menu FROM respostas_automacao WHERE id_pai = %s AND instancia = %s", (id_gatilho_atual, instancia))
            else:
                cur.execute("SELECT gatilho, titulo_menu FROM respostas_automacao WHERE instancia = %s AND (id_pai IS NULL OR id_pai = 0) AND gatilho != 'default'", (instancia,))
            
            lista_raw = cur.fetchall()
            conn.close()
            
            for row in lista_raw:
                opcoes.append({"gatilho": row[0], "titulo": row[1]})

        except Exception as e:
            print(f"❌ Erro no menu: {e}")

    texto_final = texto
    if opcoes:
        texto_final += "\n\n👇 *Opções:*"
        for op in opcoes:
            label = op['titulo'] if op['titulo'] else op['gatilho']
            texto_final += f"\n*{op['gatilho']}* - {label}"

    try:
        payload = {"number": numero, "text": texto_final}
        requests.post(f"{EVO_API_URL}/message/sendText/{instancia}", json=payload, headers={"apikey": EVO_API_KEY}, timeout=5)
        
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO historico_mensagens (instancia, remote_jid, from_me, tipo, conteudo) VALUES (%s, %s, TRUE, 'texto', %s)", (instancia, numero, texto_final))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Erro envio: {e}")


@app.post("/publico/registrar")
async def registrar_publico(dados: dict):
    print(f"💰 Novo registro Pix: {dados['nome']} | Plano: {dados['plano']}")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # 1. Verifica duplicidade
        cur.execute("SELECT id FROM usuarios WHERE login = %s OR instancia_wa = %s", (dados['login'], dados['instancia']))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Login ou Instância já existem.")

        # 2. CALCULA O VALOR REAL (BUSCANDO DO BANCO) 🏦
        # Busca o valor na tabela de planos. Se não achar, usa 99.90 como segurança.
        cur.execute("SELECT valor FROM planos_comerciais WHERE nome = %s", (dados['plano'],))
        res_plano = cur.fetchone()
        
        if res_plano:
            valor_base = float(res_plano[0])
        else:
            print(f"⚠️ Plano {dados['plano']} não encontrado. Usando valor padrão.")
            valor_base = 99.90 
            
        valor_final = valor_base
        cupom_aplicado = None

        # 3. VERIFICA CUPOM
        if dados.get('cupom'):
            cupom_codigo = dados['cupom'].upper().strip()
            cur.execute("SELECT desconto_porcentagem FROM cupons WHERE codigo = %s", (cupom_codigo,))
            res_cupom = cur.fetchone()
            
            if res_cupom:
                desconto = res_cupom[0]
                desconto_reais = (valor_base * desconto) / 100
                valor_final = valor_base - desconto_reais
                cupom_aplicado = f"{cupom_codigo} ({desconto}%)"
                print(f"🎟️ Cupom {cupom_codigo} aplicado! De {valor_base} por {valor_final}")
            else:
                print(f"⚠️ Cupom inválido: {cupom_codigo}")

        # Garante 2 casas decimais
        valor_final = round(valor_final, 2)

        # --- CASO GRÁTIS (100% OFF) ---
        if valor_final <= 0:
            print("🎁 Cupom de 100% detectado! Liberando acesso direto...")
            cur.execute("""
                INSERT INTO usuarios (nome_cliente, login, senha, instancia_wa, plano, valor_mensal, email, whatsapp, status_conta, data_vencimento, id_pagamento_mp) 
                VALUES (%s, %s, %s, %s, %s, 0.00, %s, %s, 'ativo', CURRENT_DATE + INTERVAL '30 days', 'CUPOM_100_OFF')
            """, (
                dados['nome'], dados['login'], dados['senha'], dados['instancia'], 
                dados['plano'], dados['email'], dados['whatsapp']
            ))
            conn.commit()
            conn.close()
            return {"status": "ativado_direto", "valor_final": 0.00}

        # 4. GERA PIX NO MERCADO PAGO
        payment_data = {
            "transaction_amount": valor_final,
            "description": f"Assinatura {dados['plano']} - {dados['nome']} {f'- Cupom {cupom_aplicado}' if cupom_aplicado else ''}",
            "payment_method_id": "pix",
            "payer": {
                "email": dados['email'],
                "first_name": dados['nome']
            },
            "notification_url": f"{DOMAIN_URL}/webhook/pagamento"
        }
        
        print(f"📡 Enviando para Mercado Pago (R$ {valor_final})...")
        payment_response = sdk_mp.payment().create(payment_data)
        pagamento = payment_response.get("response", {})
        status_mp = payment_response.get("status")
        
        if status_mp not in [200, 201]:
            msg_erro = pagamento.get('message', 'Erro desconhecido no Mercado Pago')
            raise HTTPException(status_code=400, detail=f"Falha no Pagamento: {msg_erro}")

        id_mp = str(pagamento['id'])
        qr_code = pagamento['point_of_interaction']['transaction_data']['qr_code']
        qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']

        # 5. SALVA NO BANCO (PENDENTE)
        cur.execute("""
            INSERT INTO usuarios (nome_cliente, login, senha, instancia_wa, plano, valor_mensal, email, whatsapp, status_conta, id_pagamento_mp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pendente', %s)
        """, (
            dados['nome'], dados['login'], dados['senha'], dados['instancia'], 
            dados['plano'], valor_final, dados['email'], dados['whatsapp'], id_mp
        ))
        conn.commit()
        conn.close()
        
        return {
            "status": "aguardando_pagamento",
            "qr_code": qr_code,
            "qr_base64": qr_code_base64,
            "valor_final": valor_final
        }

    except HTTPException as he:
        raise he
    except Exception as e:
        print(f"Erro Registro Pix: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/webhook/pagamento")
async def webhook_pagamento(request: Request):
    try:
        # O MP manda variações, as vezes vem no query, as vezes no body
        params = request.query_params
        topic = params.get("topic") or params.get("type")
        id_obj = params.get("id") or params.get("data.id")

        if topic == "payment":
            print(f"🔔 Notificação de Pagamento ID: {id_obj}")

            # Consulta status atual no MP
            payment_info = sdk_mp.payment().get(id_obj)
            status = payment_info["response"]["status"]

            if status == "approved":
                conn = get_connection()
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

                # Busca o usuário dono desse pagamento
                cur.execute("SELECT * FROM usuarios WHERE id_pagamento_mp = %s", (str(id_obj),))
                user = cur.fetchone()

                if user and user['status_conta'] == 'pendente':
                    print(f"✅ Pagamento Aprovado para {user['nome_cliente']}! Ativando...")

                    # 1. Ativa no Banco
                    cur.execute("UPDATE usuarios SET status_conta = 'ativo' WHERE id = %s", (user['id'],))
                    conn.commit()

                    # 2. Cria Instância na Evolution (Auto-Provisionamento)
                    try:
                        # Cria Instância
                        requests.post(f"{EVO_API_URL}/instance/create", 
                                      json={"instanceName": user['instancia_wa'], "token": user['senha'], "qrcode": True}, 
                                      headers={"apikey": EVO_API_KEY})

                        # Configura Webhook
                        webhook_url = f"{DOMAIN_URL}/webhook/whatsapp"
                        requests.post(f"{EVO_API_URL}/webhook/set/{user['instancia_wa']}", 
                                      json={"webhook": {"enabled": True, "url": webhook_url, "events": ["messages.upsert"]}}, 
                                      headers={"apikey": EVO_API_KEY})
                        print("🚀 Instância criada automaticamente!")
                    except Exception as evo_err:
                        print(f"⚠️ Erro ao criar instância auto: {evo_err}")

                conn.close()

        return {"status": "ok"}
    except Exception as e:
        print(f"Erro Webhook MP: {e}")
        return {"status": "error"}

# ==========================================================
# FUNÇÃO AUXILIAR: RESGATE INTELIGENTE (MULTI-ROTA)
# ==========================================================
def recuperar_midia_por_id(instancia, key_data):
    # Lista de tentativas (Rotas conhecidas da Evolution)
    rotas_possiveis = [
        f"/chat/retrieveMediaMessage/{instancia}",    # V2 Padrão (Mais provável)
        f"/chat/retrieverMediaMessage/{instancia}",   # V1 / Forks antigos
        f"/message/retrieveMediaMessage/{instancia}", # V2 Alternativa
        f"/chat/getBase64FromMediaMessage/{instancia}" # Variação
    ]

    payload = {
        "key": {
            "remoteJid": key_data.get("remoteJid"),
            "fromMe": key_data.get("fromMe"),
            "id": key_data.get("id")
        },
        # Alguns endpoints pedem "message" em vez de "key", então mandamos os dois para garantir
        "message": {
            "key": key_data
        },
        "convertToMp4": False
    }

    print(f"⏳ [Smart Fetch] Aguardando 3s para garantir o download...")
    time.sleep(3) 

    # --- LOOP DE TENTATIVAS ---
    for url_suffix in rotas_possiveis:
        full_url = f"{EVO_API_URL}{url_suffix}"
        print(f"🕵️ Testando rota: {url_suffix} ...")
        
        try:
            resp = requests.post(full_url, json=payload, headers={"apikey": EVO_API_KEY}, timeout=30)
            
            if resp.status_code == 200:
                print(f"✅ ROTA ENCONTRADA! ({url_suffix})")
                data = resp.json()
                
                # Procura o bendito Base64
                if data.get("base64"): return data.get("base64")
                
                # Procura aninhado
                msg = data.get("message", {}) or data
                if msg.get("imageMessage", {}).get("base64"): return msg["imageMessage"]["base64"]
                if msg.get("audioMessage", {}).get("base64"): return msg["audioMessage"]["base64"]
                
                print("⚠️ Conectou, mas JSON veio sem base64.")
                return None
            
            elif resp.status_code == 404:
                continue # Tenta a próxima rota
            else:
                print(f"❌ Erro na API ({resp.status_code}): {resp.text}")
                # Se não for 404, é outro erro, então não adianta tentar outras rotas
                return None
                
        except Exception as e:
            print(f"⚠️ Erro de conexão: {e}")

    print("❌ Todas as tentativas de rota falharam.")
    return None
# ==========================================================
# 🔐 FUNÇÃO MÁGICA: DESCRIPTOGRAFIA (CORRIGIDA PARA DICT)
# ==========================================================
def baixar_e_descriptografar_media(media_url, media_key_obj, tipo_media):
    if not TEM_CRYPTOGRAPHY: 
        print("❌ Biblioteca 'cryptography' não instalada.")
        return None
    
    try:
        # 1. Info Strings do WhatsApp
        app_info = {
            "image": b"WhatsApp Image Keys",
            "video": b"WhatsApp Video Keys",
            "audio": b"WhatsApp Audio Keys",
            "document": b"WhatsApp Document Keys"
        }.get(tipo_media, b"WhatsApp Image Keys")

        # 2. Tratamento da Chave (AQUI ESTAVA O ERRO)
        media_key = None
        
        if isinstance(media_key_obj, str):
            # Se for texto Base64
            media_key = base64.b64decode(media_key_obj)
        elif isinstance(media_key_obj, dict):
            # Se for Dicionário/Buffer {0: 255, 1: 10...}
            try:
                # Tenta ordenar pelas chaves para garantir a sequência correta
                lista_bytes = [media_key_obj[str(k)] for k in sorted(map(int, media_key_obj.keys()))]
                media_key = bytes(lista_bytes)
            except:
                # Se falhar a ordenação, pega os valores direto
                media_key = bytes(list(media_key_obj.values()))
        
        if not media_key or len(media_key) != 32:
            print(f"❌ Erro: MediaKey inválida ou tamanho incorreto ({len(media_key) if media_key else 0}).")
            return None

        # 3. Download (.enc)
        print(f"🌍 Baixando binário criptografado de: {media_url[:30]}...")
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(media_url, headers=headers, timeout=15)
        if response.status_code != 200:
            print(f"❌ Erro download do WhatsApp: {response.status_code}")
            return None
        
        enc_data = response.content

        # 4. Matemática da Chave (HKDF)
        hkdf = HKDF(
            algorithm=hashes.SHA256(),
            length=112,
            salt=None,
            info=app_info,
            backend=default_backend()
        )
        media_key_expanded = hkdf.derive(media_key)
        
        iv = media_key_expanded[:16]
        cipher_key = media_key_expanded[16:48]

        # 5. Descriptografar
        cipher = Cipher(algorithms.AES(cipher_key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()
        
        # Remove os últimos 10 bytes (checksum)
        decrypted_data = decryptor.update(enc_data[:-10]) + decryptor.finalize()

        print(f"🔓 Sucesso! Imagem HD gerada ({len(decrypted_data)} bytes).")
        return decrypted_data

    except Exception as e:
        print(f"❌ Erro CRÍTICO na descriptografia: {e}")
        return None
# ==========================================================
# WEBHOOK CAÇA-NÚMEROS (CORREÇÃO DO ERRO 'NONE')
# ==========================================================
# Função para processar as mensagens de entrada do cliente
@app.post("/webhook/whatsapp")
async def receber_webhook(request: Request):
    try:
        body = await request.json()
        if body.get("event") != "messages.upsert": return {"status": "ignored"}
        
        data = body.get("data", {})
        instancia = body.get("instance")
        key = data.get("key", {})
        remote_jid = key.get("remoteJid")

        if key.get("fromMe", False): return {"status": "ignored_me"}

        # Extraí o texto da mensagem
        msg_text = ""
        msg_content = data.get("message", {})
        if "conversation" in msg_content: msg_text = msg_content["conversation"]
        elif "extendedTextMessage" in msg_content: msg_text = msg_content["extendedTextMessage"].get("text", "")
        
        if not msg_text: return {"status": "no_text"}
        
        msg_clean = msg_text.strip()
        print(f"📩 [{instancia}] Recebido: {msg_clean}")

        conn = get_connection()
        cur = conn.cursor()

        # Verifica se o bot está ativo
        cur.execute("SELECT bot_ativo FROM usuarios WHERE instancia_wa = %s", (instancia,))
        r_st = cur.fetchone()
        if r_st and not r_st[0]:  # Se o bot estiver desativado
            conn.close(); return {"status": "bot_off"}

        # Verifica se já existe um atendimento ativo
        cur.execute("SELECT id FROM atendimentos_ativos WHERE instancia = %s AND remote_jid = %s", (instancia, remote_jid))
        if cur.fetchone():
            if msg_clean.lower() in ["/encerrar", "/voltar"]:
                cur.execute("DELETE FROM atendimentos_ativos WHERE instancia = %s AND remote_jid = %s", (instancia, remote_jid))
                conn.commit(); conn.close()
                enviar_mensagem_smart(instancia, remote_jid, "🤖 Robô voltou!", None)
                return {"status": "reactivated"}
            conn.close(); return {"status": "human_mode"}

        # Processa a opção de menu
        if msg_clean.lower() in ["oi", "olá", "menu", "inicio"]:
            if remote_jid in user_state: del user_state[remote_jid]
            cur.execute("SELECT * FROM respostas_automacao WHERE gatilho = 'default' AND instancia = %s", (instancia,))
            res = cur.fetchone()
            if res: enviar_mensagem_smart(instancia, remote_jid, res[3], None)
            conn.close()
            return {"status": "home"}

        # Processa a navegação através das opções
        pai_atual = user_state.get(remote_jid)
        if pai_atual:
            cur.execute("SELECT * FROM respostas_automacao WHERE instancia = %s AND gatilho ILIKE %s AND id_pai = %s", 
                        (instancia, msg_clean, pai_atual))
        else:
            cur.execute("SELECT * FROM respostas_automacao WHERE instancia = %s AND gatilho ILIKE %s AND id_pai IS NULL", 
                        (instancia, msg_clean))

        res = cur.fetchone()

        if res:
            novo_id = res[0]  # id
            texto_resp = res[3]  # resposta

            # Verifica se há submenus ou se é o fim da conversa
            cur.execute("SELECT id FROM respostas_automacao WHERE id_pai = %s LIMIT 1", (novo_id,))
            if cur.fetchone(): 
                user_state[remote_jid] = novo_id
            else: 
                if remote_jid in user_state: del user_state[remote_jid]

            enviar_mensagem_smart(instancia, remote_jid, texto_resp, novo_id)
        else:
            if pai_atual: enviar_mensagem_smart(instancia, remote_jid, "❌ Opção inválida.", pai_atual, True)

        cur.close(); conn.close()
        return {"status": "ok"}

    except Exception as e:
        print(f"🔥 Erro crítico: {e}")
        return {"status": "error"}
    

# ==========================================================
# ROTA: MÉTRICAS AVANÇADAS PARA O DASHBOARD VIVO 📊
# ==========================================================
@app.get("/metricas/{instancia}")
def obter_metricas(instancia: str, dias: int = 30):
    # Calcula data de corte
    data_corte = datetime.now() - timedelta(days=dias)
    
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    try:
        # 1. TOTAIS GERAIS (KPIs)
        # Total Clientes
        cur.execute("SELECT COUNT(*) FROM clientes_finais WHERE instancia = %s", (instancia,))
        total_clientes = cur.fetchone()['count']
        
        # Total Atendimentos Concluídos
        cur.execute("SELECT COUNT(*) FROM atendimentos_concluidos WHERE instancia = %s AND data_fim >= %s", (instancia, data_corte))
        total_atendimentos = cur.fetchone()['count']
        
        # 2. RANKING DE ATENDENTES 🏆
        # Quem fechou mais chamados?
        cur.execute("""
            SELECT nome_atendente, COUNT(*) as qtd 
            FROM atendimentos_concluidos 
            WHERE instancia = %s AND data_fim >= %s
            GROUP BY nome_atendente 
            ORDER BY qtd DESC LIMIT 5
        """, (instancia, data_corte))
        ranking_atendentes = cur.fetchall()
        
        # 3. VOLUME DIÁRIO (Últimos dias) 📈
        cur.execute("""
            SELECT DATE(data_hora) as data, COUNT(*) as qtd
            FROM chat_logs 
            WHERE instancia = %s AND data_hora >= %s
            GROUP BY data ORDER BY data ASC
        """, (instancia, data_corte))
        grafico_diario = cur.fetchall()
        # Converte datas para string
        for g in grafico_diario: g['data'] = str(g['data'])

        # 4. MAPA DE CALOR (HORÁRIOS DE PICO) 🔥
        # Extrai a hora (0-23) e conta as mensagens
        cur.execute("""
            SELECT EXTRACT(HOUR FROM data_hora) as hora, COUNT(*) as qtd
            FROM chat_logs
            WHERE instancia = %s AND data_hora >= %s
            GROUP BY hora ORDER BY hora ASC
        """, (instancia, data_corte))
        grafico_horario = cur.fetchall()

        # 5. funil de etiquetas (CRM)
        cur.execute("""
            SELECT etiquetas, COUNT(*) as qtd 
            FROM clientes_finais 
            WHERE instancia = %s 
            GROUP BY etiquetas
        """, (instancia,))
        grafico_etiquetas = cur.fetchall()

        return {
            "kpis": {
                "clientes": total_clientes,
                "atendimentos_mes": total_atendimentos,
            },
            "ranking": ranking_atendentes,
            "diario": grafico_diario,
            "horario": grafico_horario,
            "etiquetas": grafico_etiquetas
        }
        
    except Exception as e:
        print(f"Erro métricas: {e}")
        return {}
    finally:
        conn.close()
    
# ==============================================================================
# 3. ROTAS DE CADASTRO E LOGIN (NECESSÁRIAS PARA O PAINEL)
# ==============================================================================

# --- CONFIGURAÇÃO DOS LIMITES ---
LIMITES = {
    "Básico": {"max_gatilhos": 5, "permite_midia": False},
    "Pro": {"max_gatilhos": 99999, "permite_midia": True},
    "Enterprise": {"max_gatilhos": 99999, "permite_midia": True}
}

# Função para registrar um novo gatilho
@app.post("/salvar")
async def salvar_gatilho(item: Gatilho):
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("SELECT plano FROM usuarios WHERE instancia_wa = %s", (item.instancia,))
        user_data = cur.fetchone()
        plano_atual = user_data[0] if user_data else "Básico"
        
        regras = LIMITES.get(plano_atual, LIMITES["Básico"])

        cur.execute("""SELECT id FROM respostas_automacao WHERE instancia = %s AND gatilho = %s AND id_pai IS NOT DISTINCT FROM %s""", 
                     (item.instancia, item.gatilho, item.id_pai))
        existe = cur.fetchone()

        if item.url_midia and not regras["permite_midia"]:
            raise HTTPException(status_code=403, detail=f"O plano {plano_atual} não permite envio de mídia (Áudio/Imagem/Vídeo). Faça um Upgrade!")

        if not existe:
            cur.execute("SELECT COUNT(*) FROM respostas_automacao WHERE instancia = %s", (item.instancia,))
            qtd_atual = cur.fetchone()[0]
            
            if qtd_atual >= regras["max_gatilhos"]:
                raise HTTPException(status_code=403, detail=f"Você atingiu o limite de {regras['max_gatilhos']} gatilhos do plano {plano_atual}. Contrate o Pro!")

        if existe:
            cur.execute("""UPDATE respostas_automacao SET resposta=%s, tipo_midia=%s, url_midia=%s, id_pai=%s, titulo_menu=%s, categoria=%s WHERE id=%s""", 
                         (item.resposta, item.tipo_midia, item.url_midia, item.id_pai, item.titulo_menu, item.categoria, existe[0]))
        else:
            cur.execute("""INSERT INTO respostas_automacao (instancia, gatilho, resposta, titulo_menu, categoria, tipo_midia, url_midia, id_pai) 
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""", 
                         (item.instancia, item.gatilho, item.resposta, item.titulo_menu, item.categoria, item.tipo_midia, item.url_midia, item.id_pai))
        
        conn.commit()
        conn.close()
        return {"status": "sucesso"}

    except HTTPException as he:
        raise he
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/listar/{instancia}")
async def listar_gatilhos(instancia: str):
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, gatilho, resposta, tipo_midia, url_midia, id_pai FROM respostas_automacao WHERE instancia = %s ORDER BY id_pai ASC, id ASC", (instancia,))
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception:
        return []

@app.delete("/excluir/{id}")
async def excluir_gatilho(id: int):
    try:
        conn = get_connection()
        cur = conn.cursor()
        # Deleta filhos primeiro para não dar erro de chave estrangeira
        cur.execute("DELETE FROM respostas_automacao WHERE id_pai = %s", (id,))
        cur.execute("DELETE FROM respostas_automacao WHERE id = %s", (id,))
        conn.commit()
        conn.close()
        return {"status": "sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload")
async def upload_arquivo(file: UploadFile = File(...)):
    with open(f"uploads/{file.filename}", "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    # Retorna URL HTTPS para o WhatsApp conseguir baixar
    return {"url": f"{DOMAIN_URL}/arquivos/{file.filename}"}

# --- 1. LOGIN ATUALIZADO (Verifica Vencimento) ---
@app.post("/login")
async def login(dados: dict):
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Busca usuário
        cur.execute("""
            SELECT id, nome_cliente, login, senha, instancia_wa, status_conta, plano, valor_mensal, data_vencimento 
            FROM usuarios WHERE login = %s
        """, (dados['login'],))
        user = cur.fetchone()
        
        if not user:
             raise HTTPException(status_code=404, detail="Usuário não encontrado")
             
        if user['senha'] == dados['senha']:
            # LÓGICA DE VENCIMENTO
            if user['data_vencimento']:
                hoje = date.today()
                vencimento = user['data_vencimento'] # Já vem como objeto date do banco
                
                # Se venceu ontem ou antes, marca como vencido
                if hoje > vencimento:
                    cur.execute("UPDATE usuarios SET status_conta = 'vencido' WHERE id = %s", (user['id'],))
                    conn.commit()
                    user['status_conta'] = 'vencido' # Atualiza objeto local
            
            # Converte Decimals e Dates para string/float pro JSON não quebrar
            if user.get('valor_mensal'): user['valor_mensal'] = float(user['valor_mensal'])
            if user.get('data_vencimento'): user['data_vencimento'] = str(user['data_vencimento'])

            conn.close()
            return {"status": "sucesso", "usuario": user}
        else:
            conn.close()
            raise HTTPException(status_code=401, detail="Senha incorreta")
            
    except Exception as e:
        print(f"Erro Login: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --- 2. GESTÃO DE CUPONS (Admin) ---
@app.get("/cupons")
def listar_cupons():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM cupons")
    cupons = cur.fetchall()
    conn.close()
    return cupons

@app.post("/cupons")
def criar_cupom(dados: dict):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO cupons (codigo, desconto_porcentagem) VALUES (%s, %s)", 
                   (dados['codigo'].upper(), dados['desconto']))
        conn.commit()
        return {"status": "criado"}
    except Exception as e:
        return {"status": "erro", "detalhe": str(e)}
    finally:
        conn.close()

@app.delete("/cupons/{codigo}")
def deletar_cupom(codigo: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM cupons WHERE codigo = %s", (codigo,))
    conn.commit()
    conn.close()
    return {"status": "deletado"}


# ==========================================================
# 3. RENOVAÇÃO / UPGRADE (Versão Blindada 🛡️)
# ==========================================================
@app.post("/pagamento/gerar")
async def gerar_pagamento_usuario(dados: dict):
    # dados espera: { "user_id": 1, "plano": "Pro", "cupom": "CODIGO" }
    # Nota: Ignoramos o campo 'valor' que vem do front, por segurança.
    print(f"🔄 Processando renovação para User ID {dados.get('user_id')}")
    
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # 1. Pega dados do usuário
        cur.execute("SELECT * FROM usuarios WHERE id = %s", (dados['user_id'],))
        user = cur.fetchone()
        
        if not user:
            raise HTTPException(status_code=404, detail="Usuário não encontrado.")

        # 2. BUSCA PREÇO REAL NO BANCO 🏦
        # AQUI ESTÁ A SEGURANÇA: O valor vem do banco, não do JSON do cliente.
        cur.execute("SELECT valor FROM planos_comerciais WHERE nome = %s", (dados['plano'],))
        res_plano = cur.fetchone()
        
        if res_plano:
            valor_base = float(res_plano['valor'])
        else:
            print(f"⚠️ Plano {dados['plano']} não encontrado. Usando valor de segurança.")
            valor_base = 99.90 # Valor alto de segurança se o plano não existir
            
        valor_final = valor_base
        cupom_aplicado_txt = ""

        # 3. LÓGICA DO CUPOM
        if dados.get('cupom'):
            codigo = dados['cupom'].strip().upper()
            cur.execute("SELECT desconto_porcentagem FROM cupons WHERE codigo = %s", (codigo,))
            res_cupom = cur.fetchone()
            
            if res_cupom:
                desconto = res_cupom['desconto_porcentagem']
                desconto_reais = (valor_base * desconto) / 100
                valor_final = valor_base - desconto_reais
                cupom_aplicado_txt = f"- Cupom {codigo} ({desconto}%)"
                print(f"🎟️ Cupom {codigo} aplicado na renovação!")
            else:
                print(f"⚠️ Cupom de renovação inválido: {codigo}")
        
        valor_final = round(valor_final, 2)

        # 4. SE VALOR FOR ZERO (100% OFF)
        if valor_final <= 0:
            print("🎁 Renovação Gratuita (100% OFF)")
            # Verifica se já venceu para calcular a nova data
            hoje = date.today()
            venc_atual = user['data_vencimento']
            
            if venc_atual and venc_atual > hoje:
                nova_data = venc_atual + timedelta(days=30)
            else:
                nova_data = hoje + timedelta(days=30)

            cur.execute("""
                UPDATE usuarios SET 
                status_conta='ativo', 
                data_vencimento = %s, 
                plano=%s,
                valor_mensal=%s,
                id_pagamento_mp='CUPOM_100_OFF'
                WHERE id=%s
            """, (nova_data, dados['plano'], 0.00, user['id']))
            conn.commit()
            conn.close()
            return {"status": "aprovado_direto", "mensagem": "Plano renovado com sucesso (100% OFF)!"}

        # 5. GERA PIX NO MERCADO PAGO
        payment_data = {
            "transaction_amount": valor_final,
            "description": f"Renovação {dados['plano']} - {user['nome_cliente']} {cupom_aplicado_txt}",
            "payment_method_id": "pix",
            "payer": {"email": user['email'] or "cliente@email.com", "first_name": user['nome_cliente']},
            "notification_url": f"{DOMAIN_URL}/webhook/pagamento"
        }
        
        print(f"📡 Gerando Pix Renovação: R$ {valor_final}")
        resp = sdk_mp.payment().create(payment_data)
        pagamento = resp.get("response", {})
        
        if resp["status"] not in [200, 201]:
             err_msg = pagamento.get('message', 'Erro MP')
             raise HTTPException(status_code=400, detail=f"Erro Mercado Pago: {err_msg}")
             
        # Salva o ID do pagamento novo
        cur.execute("UPDATE usuarios SET id_pagamento_mp = %s, plano = %s, valor_mensal = %s WHERE id = %s", 
                    (str(pagamento['id']), dados['plano'], valor_final, user['id']))
        conn.commit()
        conn.close()
        
        return {
            "status": "aguardando",
            "qr_code": pagamento['point_of_interaction']['transaction_data']['qr_code'],
            "qr_base64": pagamento['point_of_interaction']['transaction_data']['qr_code_base64'],
            "valor_final": valor_final
        }

    except Exception as e:
        print(f"Erro Renovação: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/usuarios/cadastrar")
async def cadastrar_usuario(dados: dict):
    print(f"📝 Iniciando cadastro: {dados['login']}")

    # --- PASSO 1 E 2: EVOLUTION (MANTENHA SEU CÓDIGO AQUI) ---
    # (Estou resumindo para focar no banco, mas não apague a parte da Evolution!)
    try:
        url_create = f"{EVO_API_URL}/instance/create"
        payload_create = {
            "instanceName": dados['instancia_wa'],
            "token": dados['senha'], 
            "qrcode": True,
            "integration": "WHATSAPP-BAILEYS"
        }
        resp = requests.post(url_create, json=payload_create, headers={"apikey": EVO_API_KEY})
        
        # Configura Webhook
        webhook_url = f"{DOMAIN_URL}/webhook/whatsapp"
        requests.post(f"{EVO_API_URL}/webhook/set/{dados['instancia_wa']}", 
                      json={"webhook": {"enabled": True, "url": webhook_url, "events": ["messages.upsert"]}}, 
                      headers={"apikey": EVO_API_KEY})
    except Exception as e:
        print(f"⚠️ Erro Evolution: {e}")

    # --- PASSO 3: SALVAR NO BANCO (ATUALIZADO) ---
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Note o 'ativo' adicionado na lista de valores
        cur.execute("""
            INSERT INTO usuarios (login, senha, instancia_wa, nome_cliente, plano, valor_mensal, data_vencimento, whatsapp, email, status_conta) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'ativo')
        """, (
            dados['login'], dados['senha'], dados['instancia_wa'], dados['nome_cliente'], 
            dados['plano'], dados.get('valor_mensal', 0), dados.get('data_vencimento', None),
            dados.get('whatsapp', ''), dados.get('email', '')
        ))
        
        conn.commit()
        conn.close()
        return {"status": "sucesso"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/usuarios/listar")
async def listar_usuarios():
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # SQL ATUALIZADO: Trazendo plano, valor, vencimento, zap e email
        # O COALESCE serve para garantir que se estiver vazio (NULL), venha um valor padrão
        cur.execute("""
            SELECT 
                id, 
                login, 
                senha,
                instancia_wa, 
                nome_cliente,
                COALESCE(plano, 'Básico') as plano,
                COALESCE(valor_mensal, 0.00) as valor_mensal,
                data_vencimento,
                COALESCE(whatsapp, '') as whatsapp,
                COALESCE(email, '') as email
            FROM usuarios
            ORDER BY id ASC
        """)
        
        users = cur.fetchall()
        conn.close()
        return users
    except Exception as e:
        print(f"Erro ao listar: {e}")
        return []
    
@app.delete("/usuarios/excluir/{id}")
async def excluir_usuario(id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return {"status": "sucesso"}

@app.post("/verificar_gatilho")
async def verificar_gatilho(dados: ConsultaGatilho):
    # Simulador do Painel
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM respostas_automacao WHERE instancia = %s AND gatilho ILIKE %s", (dados.instancia, dados.mensagem.strip()))
    res = cur.fetchone()
    conn.close()
    if res:
        return {"encontrou": True, "resposta": res['resposta'], "tipo_midia": res['tipo_midia'], "url_midia": res['url_midia']}
    else:
        return {"encontrou": False, "resposta": "Não entendi."}


# ==========================================================
# LISTAR ATENDIMENTOS (AGORA TRAZ O NOME DO CRM JUNTO!)
# ==========================================================
@app.get("/atendimentos/{instancia}")
def listar_atendimentos(instancia: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # O Pulo do Gato: LEFT JOIN com a tabela de clientes para pegar o nome
    cur.execute("""
        SELECT a.*, c.nome as nome_crm 
        FROM atendimentos_ativos a
        LEFT JOIN clientes_finais c ON a.remote_jid = c.telefone AND a.instancia = c.instancia
        WHERE a.instancia = %s 
        ORDER BY a.data_inicio DESC
    """, (instancia,))
    
    dados = cur.fetchall()
    conn.close()
    
    for d in dados:
        if d['data_inicio']: d['data_inicio'] = str(d['data_inicio'])
    return dados
# ==========================================================
# GESTÃO DE ATENDIMENTOS (ATIVOS E CONCLUÍDOS)
# ==========================================================

# 1. FINALIZAR (MOVE PARA CONCLUÍDOS) - Substitua a rota antiga @app.delete("/atendimentos/{id}")
class FinalizarReq(BaseModel):
    nome_atendente: str  # Precisamos saber quem fechou

@app.post("/atendimentos/finalizar/{id_atendimento}")
def finalizar_atendimento_v2(id_atendimento: int, dados: FinalizarReq):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # A. Pega os dados do atendimento atual antes de apagar
        cur.execute("SELECT * FROM atendimentos_ativos WHERE id = %s", (id_atendimento,))
        atendimento = cur.fetchone()
        
        if atendimento:
            # B. Salva na tabela de concluídos (Histórico)
            cur.execute("""
                INSERT INTO atendimentos_concluidos (instancia, remote_jid, nome_atendente, data_inicio)
                VALUES (%s, %s, %s, %s)
            """, (atendimento['instancia'], atendimento['remote_jid'], dados.nome_atendente, atendimento['data_inicio']))
            
            # C. Remove da tabela de ativos (Libera o cliente para o Robô)
            cur.execute("DELETE FROM atendimentos_ativos WHERE id = %s", (id_atendimento,))
            conn.commit()
            return {"status": "ok", "msg": "Atendimento movido para histórico."}
        else:
            return {"status": "erro", "msg": "Atendimento não encontrado."}
    except Exception as e:
        conn.rollback()
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()

# ==========================================================
# LISTAR CONCLUÍDOS (AGORA COM NOME DO CLIENTE 👤)
# ==========================================================
@app.get("/atendimentos/concluidos/{instancia}")
def listar_atendimentos_concluidos(instancia: str, data: Optional[str] = None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    # Base da Query com LEFT JOIN para pegar o nome (c.nome)
    sql_base = """
        SELECT a.*, c.nome as nome_crm 
        FROM atendimentos_concluidos a
        LEFT JOIN clientes_finais c ON a.remote_jid = c.telefone AND a.instancia = c.instancia
        WHERE a.instancia = %s 
    """
    
    try:
        if data:
            # Filtra pelo dia específico
            cur.execute(sql_base + " AND DATE(a.data_fim) = %s ORDER BY a.data_fim DESC", (instancia, data))
        else:
            # Padrão: Últimos 50
            cur.execute(sql_base + " ORDER BY a.data_fim DESC LIMIT 50", (instancia,))
            
        dados = cur.fetchall()
        
        # Formata datas
        for d in dados:
            if d['data_fim']: d['data_fim'] = str(d['data_fim'])
            if d['data_inicio']: d['data_inicio'] = str(d['data_inicio'])
            
        return dados
    except Exception as e:
        print(f"Erro ao listar concluídos: {e}")
        return []
    finally:
        conn.close()

# 3. REABRIR (DO HISTÓRICO PARA ATIVO) (NOVA ROTA)
class ReabrirReq(BaseModel):
    instancia: str
    remote_jid: str

@app.post("/atendimentos/reabrir")
def reabrir_atendimento(dados: ReabrirReq):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Verifica se já não está aberto (para não duplicar)
        cur.execute("SELECT id FROM atendimentos_ativos WHERE instancia=%s AND remote_jid=%s", (dados.instancia, dados.remote_jid))
        if cur.fetchone():
            return {"status": "ok", "msg": "Já está aberto."}

        # Insere em ativos novamente
        cur.execute("INSERT INTO atendimentos_ativos (instancia, remote_jid) VALUES (%s, %s)", (dados.instancia, dados.remote_jid))
        conn.commit()
        return {"status": "ok", "msg": "Reaberto com sucesso!"}
    except Exception as e:
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()

# --- ROTA: LER HISTÓRICO LOCAL (CORRIGIDA E OTIMIZADA) ---
@app.get("/chat/local/{instancia}/{remote_jid}")
def ler_historico_local(instancia: str, remote_jid: str):
    # Garante o formato do JID
    jid_busca = remote_jid if "@" in remote_jid else f"{remote_jid}@s.whatsapp.net"
    
    conn = get_connection() 
    # Usar RealDictCursor é MUITO mais seguro que índices [0], [1]...
    cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Busca as últimas 50 mensagens COM O NOME
        cursor.execute("""
            SELECT 
                from_me as "fromMe", 
                conteudo as "text", 
                data_hora as "timestamp",
                nome_atendente  -- <--- AGORA SIM!
            FROM historico_mensagens 
            WHERE instancia = %s AND remote_jid = %s
            ORDER BY data_hora DESC 
            LIMIT 50
        """, (instancia, jid_busca))
        
        msgs = cursor.fetchall()
        
        # O RealDictCursor já devolve no formato certo, só precisa converter data
        for m in msgs:
            if m['timestamp']: m['timestamp'] = str(m['timestamp'])

        # Inverte para mostrar cronológico (Antigo -> Novo) na tela
        return msgs[::-1] 
    except Exception as e:
        print(f"Erro leitura chat: {e}")
        return []
    finally:
        cursor.close()
        conn.close()


# 1. ATUALIZE A CLASSE (Isso define o que o Backend aceita receber)
class MsgManual(BaseModel):
    instancia: str
    remote_jid: str
    texto: str
    tipo: Optional[str] = "texto"
    nome_atendente: Optional[str] = None # <--- OBRIGATÓRIO

# ==========================================================
# ROTA: ENVIAR MENSAGEM MANUAL (COM TRAVA ANTI-DUPLICIDADE) 🛡️
# ==========================================================
# ==========================================================
# ENVIO MANUAL (CORRIGIDA: URL V2)
# ==========================================================
@app.post("/chat/salvar_manual")
def salvar_mensagem_manual(dados: MsgManual):
    global msg_cache
    chave = f"{dados.instancia}_{dados.remote_jid}_{dados.texto}"
    if chave in msg_cache and (time.time() - msg_cache[chave] < 5): return {"status": "ignorado"}
    msg_cache[chave] = time.time()

    jid = dados.remote_jid if "@" in dados.remote_jid else f"{dados.remote_jid}@s.whatsapp.net"
    
    try:
        # --- CORREÇÃO DA URL AQUI TAMBÉM ---
        url = f"{EVO_API_URL}/message/sendText/{dados.instancia}"
        
        payload = {"number": jid, "text": dados.texto}
        r = requests.post(url, json=payload, headers={"apikey": EVO_API_KEY}, timeout=10)
        
        if r.status_code != 200:
            print(f"⚠️ Erro API Evolution: {r.text}")
            
        # Salva no banco mesmo se der erro na API, para log
        conn = get_connection(); cur = conn.cursor()
        cur.execute("INSERT INTO historico_mensagens (instancia, remote_jid, from_me, tipo, conteudo, nome_atendente) VALUES (%s, %s, %s, %s, %s, %s)", 
                   (dados.instancia, jid, True, dados.tipo, dados.texto, dados.nome_atendente))
        conn.commit(); conn.close()
        return {"status": "salvo"}
        
    except Exception as e: 
        return {"erro": str(e)}

@app.put("/usuarios/editar/{user_id}")
async def editar_usuario(user_id: int, dados: dict):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Atualiza os dados do cliente
        cur.execute("""
            UPDATE usuarios SET 
            nome_cliente=%s, login=%s, senha=%s, plano=%s, 
            valor_mensal=%s, data_vencimento=%s, whatsapp=%s, email=%s
            WHERE id=%s
        """, (
            dados['nome_cliente'], dados['login'], dados['senha'], 
            dados['plano'], dados['valor_mensal'], dados['data_vencimento'],
            dados.get('whatsapp', ''), dados.get('email', ''),
            user_id
        ))
        
        conn.commit()
        conn.close()
        return {"status": "sucesso"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
# =====================================================
# 📂 CRM & DISPAROS (NOVO)
# =====================================================

# 1. ATUALIZAR CLIENTE (NOVA ROTA)
@app.put("/crm/clientes/{id}")
def atualizar_cliente_final(id: int, dados: dict):
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Monta a query dinâmica (só atualiza o que vier)
        # Nota: dia_vencimento pode vir None
        cur.execute("""
            UPDATE clientes_finais 
            SET nome = %s, dia_vencimento = %s, etiquetas = %s
            WHERE id = %s
        """, (dados['nome'], dados.get('dia_vencimento'), dados.get('etiquetas'), id))
        
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}
    
# 1. Cadastrar Cliente Final
@app.post("/crm/clientes")
def cadastrar_cliente_final(dados: dict):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO clientes_finais (instancia, nome, telefone, dia_vencimento, etiquetas)
            VALUES (%s, %s, %s, %s, %s)
        """, (dados['instancia'], dados['nome'], dados['telefone'], dados['dia_vencimento'], dados['etiquetas']))
        conn.commit()
        conn.close()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}



# 3. Excluir Cliente
@app.delete("/crm/clientes/{id}")
def excluir_cliente_final(id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM clientes_finais WHERE id = %s", (id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


# 2. LISTAR COM PAGINAÇÃO (MODIFICADA)
@app.get("/crm/clientes/{instancia}")
def listar_clientes_finais(instancia: str, pagina: int = 1, itens_por_pagina: int = 50, busca: str = None):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    offset = (pagina - 1) * itens_por_pagina
    
    # Query Base
    sql_base = "FROM clientes_finais WHERE instancia = %s"
    params = [instancia]
    
    # Filtro de Busca (Nome ou Telefone)
    if busca:
        sql_base += " AND (nome ILIKE %s OR telefone ILIKE %s)"
        params.extend([f"%{busca}%", f"%{busca}%"])
    
    # 1. Conta Total (para saber quantas páginas existem)
    cur.execute(f"SELECT COUNT(*) {sql_base}", tuple(params))
    total_itens = cur.fetchone()['count']
    
    # 2. Busca os Itens da Página
    cur.execute(f"SELECT * {sql_base} ORDER BY id DESC LIMIT %s OFFSET %s", tuple(params + [itens_por_pagina, offset]))
    itens = cur.fetchall()
    
    conn.close()
    
    return {
        "data": itens,
        "total": total_itens,
        "pagina_atual": pagina,
        "total_paginas": -(-total_itens // itens_por_pagina) # Arredonda pra cima
    }

# 4. 🚀 O DISPARADOR EM MASSA
@app.post("/disparo/em-massa")
def disparo_em_massa(dados: dict):
    instancia = dados['instancia']
    texto_base = dados['mensagem']
    lista_ids = dados['lista_ids']
    incluir_menu = dados.get('incluir_menu', False)
    
    # NOVOS CAMPOS PARA MÍDIA
    url_midia = dados.get('url_midia')     # Ex: http://.../uploads/foto.jpg
    tipo_midia = dados.get('tipo_midia')   # image, video, document
    
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    if not lista_ids: return {"status": "vazio"}
    
    format_strings = ','.join(['%s'] * len(lista_ids))
    cur.execute(f"SELECT nome, telefone FROM clientes_finais WHERE id IN ({format_strings})", tuple(lista_ids))
    destinatarios = cur.fetchall()
    conn.close()
    
    enviados = 0
    erros = 0
    
    # ---------------------------------------------------------
    # PREPARAÇÃO DA MÍDIA (SE HOUVER)
    # ---------------------------------------------------------
    base64_midia = None
    nome_arquivo = "arquivo"
    mimetype = "image/jpeg" # Padrão
    
    if url_midia:
        try:
            # Pega o nome do arquivo da URL (ex: .../uploads/promo.jpg -> promo.jpg)
            nome_arquivo = url_midia.split("/")[-1]
            caminho_local = f"uploads/{nome_arquivo}"
            
            # Lê o arquivo do disco e converte pra Base64 UMA VEZ SÓ (Performance 🚀)
            if os.path.exists(caminho_local):
                with open(caminho_local, "rb") as f:
                    base64_midia = base64.b64encode(f.read()).decode('utf-8')
                
                # Define mimetype básico
                ext = nome_arquivo.split('.')[-1].lower()
                if ext == "png": mimetype = "image/png"
                elif ext == "pdf": mimetype = "application/pdf"
                elif ext == "mp4": mimetype = "video/mp4"
            else:
                print(f"⚠️ Arquivo não encontrado no servidor: {caminho_local}")
        except Exception as e:
            print(f"Erro ao processar mídia: {e}")

    print(f"🚀 Iniciando disparo (Mídia: {bool(base64_midia)})...")

    # ---------------------------------------------------------
    # LOOP DE ENVIO
    # ---------------------------------------------------------
    for pessoa in destinatarios:
        try:
            # Personaliza o texto
            msg_final = texto_base.replace("{nome}", pessoa['nome'])
            
            # Se pediu menu, anexa no final
            # (Aqui fazemos manual pq vamos usar sendMedia, não a função smart)
            if incluir_menu:
                # Nota: Buscar o menu no banco 500x é pesado. 
                # Idealmente buscaria fora do loop, mas vamos simplificar.
                msg_final += "\n\n(Digite 'Menu' para ver as opções)"

            # DECISÃO: MANDA MÍDIA OU TEXTO?
            if base64_midia:
                # ENVIA COM IMAGEM
                payload = {
                    "number": pessoa['telefone'],
                    "media": base64_midia,
                    "mediatype": tipo_midia,
                    "mimetype": mimetype,
                    "caption": msg_final, # O texto vira legenda
                    "fileName": nome_arquivo
                }
                requests.post(f"{EVO_API_URL}/message/sendMedia/{instancia}", json=payload, headers={"apikey": EVO_API_KEY})
            else:
                # ENVIA SÓ TEXTO (Usa a função smart que já temos, ou direto)
                # Vamos usar direto pra garantir controle total
                payload = {"number": pessoa['telefone'],"text": msg_final}
                requests.post(f"{EVO_API_URL}/message/send/text/{instancia}", json=payload, headers={"apikey": EVO_API_KEY})
            
            # Log (Opcional)
            # ... código de log aqui ...

            enviados += 1
            time.sleep(1) # Delay anti-bloqueio
            
        except Exception as e:
            print(f"Erro envio {pessoa['nome']}: {e}")
            erros += 1
            
    return {"status": "concluido", "enviados": enviados, "erros": erros}


# =====================================================
# 📥 IMPORTAÇÃO DE CONTATOS (VERSÃO CHAVE MESTRA 🗝️)
# =====================================================
@app.post("/crm/importar_whatsapp")
def importar_contatos_whatsapp(dados: dict):
    instancia = dados.get("instancia")
    headers = {"apikey": EVO_API_KEY, "Content-Type": "application/json"}
    
    print(f"📥 Iniciando varredura de rotas para: {instancia}")

    # Lista de todas as possibilidades conhecidas (Método, Endpoint)
    rotas_possiveis = [
        ("GET",  f"/chat/find/{instancia}"),          # Mais provável (v1.8+)
        ("GET",  f"/chat/retriever/{instancia}"),     # Alternativa comum
        ("GET",  f"/chat/findChats/{instancia}"),     # v2.0+ (já falhou, mas deixamos aqui)
        ("POST", f"/chat/find/{instancia}"),          # Antiga (já falhou, mas vai que...)
        ("GET",  f"/contact/find/{instancia}"),       # Contatos v1
        ("POST", f"/contact/find/{instancia}"),       # Contatos v1 (POST)
        ("GET",  f"/contact/findAll/{instancia}"),    # Contatos v2
    ]

    chats = []
    sucesso = False
    rota_funcionou = ""

    # --- LOOP DE TENTATIVAS ---
    for metodo, endpoint in rotas_possiveis:
        url = f"{EVO_API_URL}{endpoint}"
        print(f"🕵️ Testando: {metodo} {endpoint} ...", end="")
        
        try:
            if metodo == "GET":
                res = requests.get(url, headers=headers, timeout=10)
            else:
                res = requests.post(url, json={"where": {}}, headers=headers, timeout=10)
            
            if res.status_code == 200:
                print(" ✅ SUCESSO!")
                payload = res.json()
                
                # Normaliza o retorno (pode vir lista direta ou dict)
                if isinstance(payload, list):
                    chats = payload
                elif isinstance(payload, dict):
                    chats = payload.get('data') or payload.get('chats') or payload.get('contacts') or []
                
                sucesso = True
                rota_funcionou = endpoint
                break # Para o loop se funcionou
            else:
                print(f" ❌ ({res.status_code})")
                
        except Exception as e:
            print(f" ⚠️ Erro: {e}")

    # --- SE TUDO FALHAR ---
    if not sucesso:
        return {"status": "error", "detail": "Nenhuma rota compatível encontrada. Atualize sua Evolution API."}

    if not chats:
        return {"status": "error", "detail": "Rota encontrada, mas retornou lista vazia (sem conversas)."}

    print(f"🎉 Rota vencedora: {rota_funcionou} | Encontrados: {len(chats)}")

    # =====================================================
    # PROCESSAMENTO / BANCO
    # =====================================================
    try:
        conn = get_connection()
        cur = conn.cursor()

        importados = 0
        ignorados = 0

        for c in chats:
            # Tenta pegar ID de todas as formas possíveis
            jid = c.get("id") or c.get("jid") or c.get("remoteJid")
            if not jid and 'key' in c: jid = c['key'].get('remoteJid')

            # Tenta pegar Nome
            nome = c.get("pushName") or c.get("name") or c.get("verifiedName") or c.get("notify") or "Cliente WhatsApp"

            # 🛡️ Filtros
            if not jid: continue
            if "@g.us" in jid or "@broadcast" in jid or "status@" in jid: continue

            # Verifica duplicidade
            cur.execute("SELECT id FROM clientes_finais WHERE instancia=%s AND telefone=%s", (instancia, jid))
            if not cur.fetchone():
                cur.execute("""
                    INSERT INTO clientes_finais (instancia, nome, telefone, dia_vencimento, etiquetas)
                    VALUES (%s, %s, %s, %s, %s)
                """, (instancia, nome, jid, NULL, "importado_whatsapp"))
                importados += 1
            else:
                ignorados += 1

        conn.commit()
        conn.close()

        return {"status": "ok", "novos": importados, "existentes": ignorados}

    except Exception as e:
        print(f"💥 Erro banco: {e}")
        return {"status": "error", "detail": str(e)}

# =====================================================
# ⚙️ ADMINISTRAÇÃO DE PLANOS
# =====================================================

# 1. LISTAR REGRAS (Para montar a tabela no painel)
@app.get("/admin/regras")
def listar_regras_planos():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    
    cur.execute("SELECT * FROM regras_planos ORDER BY funcionalidade, plano")
    regras = cur.fetchall()
    
    conn.close()
    return regras

# 2. SALVAR REGRAS (Recebe a lista atualizada e salva)
@app.post("/admin/regras")
def atualizar_regras_planos(dados: dict):
    # O front vai mandar algo como: {"regras": [{"plano": "Básico", "func": "x", "ativo": true}, ...]}
    lista_regras = dados.get("regras", [])
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        for item in lista_regras:
            cur.execute("""
                INSERT INTO regras_planos (plano, funcionalidade, ativo)
                VALUES (%s, %s, %s)
                ON CONFLICT (plano, funcionalidade) 
                DO UPDATE SET ativo = EXCLUDED.ativo
            """, (item['plano'], item['funcionalidade'], item['ativo']))
        
        conn.commit()
        return {"status": "ok", "msg": "Regras atualizadas!"}
    except Exception as e:
        conn.rollback()
        return {"status": "error", "detail": str(e)}
    finally:
        conn.close()

# 3. VERIFICADOR DE PERMISSÃO (Para você usar no código depois)
# Exemplo de uso: verificar_permissao('Básico', 'disparos_massa')
def verificar_permissao_backend(nome_plano, funcionalidade_chave):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT ativo FROM regras_planos WHERE plano = %s AND funcionalidade = %s", (nome_plano, funcionalidade_chave))
    res = cur.fetchone()
    conn.close()
    
    if res and res[0] == True:
        return True
    return False

# --- MODELS ---
class AtendenteCreate(BaseModel):
    admin_id: int
    nome: str
    usuario: str
    senha: str
    instancia: str

class LoginAtendente(BaseModel):
    usuario: str
    senha: str

# --- ROTA 1: CRIAR ATENDENTE (ADMIN) ---
@app.post("/equipe/criar")
def criar_atendente(d: AtendenteCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Verifica se usuário já existe
        cur.execute("SELECT id FROM atendentes WHERE usuario = %s", (d.usuario,))
        if cur.fetchone():
            return JSONResponse(status_code=400, content={"erro": "Este usuário já existe."})

        # Insere
        cur.execute("""
            INSERT INTO atendentes (admin_id, nome, usuario, senha, instancia_vinculada)
            VALUES (%s, %s, %s, %s, %s)
        """, (d.admin_id, d.nome, d.usuario, d.senha, d.instancia))
        conn.commit()
        return {"status": "criado", "usuario": d.usuario}
    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        cur.close()
        conn.close()

# --- ROTA 2: LISTAR EQUIPE (ADMIN) ---
@app.get("/equipe/listar/{instancia}")
def listar_equipe(instancia: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, nome, usuario, ativo FROM atendentes WHERE instancia_vinculada = %s", (instancia,))
        return cur.fetchall()
    finally:
        cur.close()
        conn.close()

# --- ROTA 3: LOGIN DO FUNCIONÁRIO ---
@app.post("/equipe/login")
def login_atendente(d: LoginAtendente):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # AQUI ESTÁ A MÁGICA: JOIN com a tabela 'usuarios' (u)
        # para pegar o 'plano' do dono da conta (admin_id)
        cur.execute("""
            SELECT 
                a.id, 
                a.nome, 
                a.usuario, 
                a.instancia_vinculada,
                u.plano as plano_admin  -- <--- Pega o plano do Chefe
            FROM atendentes a
            JOIN usuarios u ON a.admin_id = u.id
            WHERE a.usuario = %s AND a.senha = %s AND a.ativo = TRUE
        """, (d.usuario, d.senha))
        
        user = cur.fetchone()
        
        if user:
            return {
                "autenticado": True,
                "tipo": "funcionario",
                "nome": user['nome'],
                "instancia": user['instancia_vinculada'],
                "id_atendente": user['id'],
                "plano": user['plano_admin'] # <--- Envia como se fosse o plano dele
            }
        else:
            return JSONResponse(status_code=401, content={"erro": "Login ou senha inválidos"})
    except Exception as e:
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        cur.close()
        conn.close()


# =====================================================
# VERIFICAÇÃO DE LIMITES DO PLANO 🚦
# =====================================================
@app.get("/automacao/verificar-limite/{instancia}")
def verificar_limite_automacao(instancia: str, plano: str):
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # 1. Conta quantos gatilhos o usuário JÁ TEM
        cur.execute("SELECT COUNT(*) FROM respostas_automacao WHERE instancia = %s", (instancia,))
        qtd_atual = cur.fetchone()['count']

        # 2. Busca qual é o LIMITE do plano dele
        # (Se não achar regra, definimos um padrão seguro, ex: 5)
        cur.execute("""
            SELECT limite FROM regras_planos 
            WHERE plano = %s AND funcionalidade = 'max_gatilhos'
        """, (plano,))
        res_limite = cur.fetchone()
        
        # Se o plano for Enterprise ou não tiver limite definido, usamos 9999
        limite_max = res_limite['limite'] if res_limite else 5

        conn.close()

        return {
            "qtd_atual": qtd_atual,
            "limite_max": limite_max,
            "bloqueado": qtd_atual >= limite_max,
            "porcentagem": min(int((qtd_atual / limite_max) * 100), 100) if limite_max > 0 else 0
        }

    except Exception as e:
        return {"error": str(e), "bloqueado": True} # Na dúvida, bloqueia
    



# =====================================================
# BLOCO DE GESTÃO DE EQUIPE (COLE NO MAIN.PY)
# =====================================================

# --- MODELOS DE DADOS ---
class AtendenteCreate(BaseModel):
    admin_id: int
    nome: str
    usuario: str
    senha: str
    instancia: str

class LoginAtendente(BaseModel):
    usuario: str
    senha: str

# --- ROTA 1: CRIAR NOVO ATENDENTE ---
@app.post("/equipe/criar")
def criar_atendente(d: AtendenteCreate):
    conn = get_connection() # Cuidado: verifique se sua função chama get_connection ou get_db_connection
    cur = conn.cursor()
    try:
        # Verifica se usuário já existe para evitar duplicidade
        cur.execute("SELECT id FROM atendentes WHERE usuario = %s", (d.usuario,))
        if cur.fetchone():
            return JSONResponse(status_code=400, content={"erro": "Este usuário já existe."})

        # Insere na tabela
        cur.execute("""
            INSERT INTO atendentes (admin_id, nome, usuario, senha, instancia_vinculada)
            VALUES (%s, %s, %s, %s, %s)
        """, (d.admin_id, d.nome, d.usuario, d.senha, d.instancia))
        
        conn.commit()
        return {"status": "criado", "usuario": d.usuario}
        
    except Exception as e:
        print(f"❌ Erro ao criar atendente: {e}") # Print no terminal para ajudar a debugar
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        cur.close()
        conn.close()

# --- ROTA 2: LISTAR EQUIPE ---
@app.get("/equipe/listar/{instancia}")
def listar_equipe(instancia: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT id, nome, usuario, ativo FROM atendentes WHERE instancia_vinculada = %s", (instancia,))
        return cur.fetchall()
    except Exception as e:
         return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        cur.close()
        conn.close()

# --- ROTA 3: LOGIN DE ATENDENTE ---
@app.post("/equipe/login")
def login_atendente(d: LoginAtendente):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, nome, usuario, instancia_vinculada 
            FROM atendentes 
            WHERE usuario = %s AND senha = %s AND ativo = TRUE
        """, (d.usuario, d.senha))
        user = cur.fetchone()
        
        if user:
            return {
                "autenticado": True,
                "tipo": "funcionario",
                "nome": user['nome'],
                "instancia": user['instancia_vinculada'],
                "id_atendente": user['id']
            }
        else:
            return JSONResponse(status_code=401, content={"erro": "Login inválido"})
    finally:
        cur.close()
        conn.close()


# ==========================================================
# ROTA AUTOMÁTICA: CONFIGURA E REINICIA (CORRIGIDA) 🚀
# ==========================================================
@app.post("/instance/configurar/{instancia}")
def configurar_instancia_automatica(instancia: str):
    print(f"⚙️ [AUTO] Configurando instância: {instancia}...")
    
    # 1. DEFINE A URL DO WEBHOOK CORRETA (Usa DOMAIN_URL preferencialmente)
    # Se DOMAIN_URL estiver vazio, tenta LOCAL_URL, senão usa localhost como fallback
    base_url = DOMAIN_URL or LOCAL_URL or "http://localhost:8000"
    
    # Remove barra final se tiver para não duplicar
    if base_url.endswith("/"): base_url = base_url[:-1]
    
    webhook_url = f"{base_url}/webhook/whatsapp"

    print(f"🔗 Apontando Webhook para: {webhook_url}")

    # Payload "Blindado"
    payload = {
        "reject_call": False,
        "always_online": True,
        "read_messages": True,
        "read_status": False,
        "webhook": {
            "enabled": True,
            "url": webhook_url,
            "download_media": True, 
            "base64": True,         
            "upload_media": True,
            "auto_download": True,
            "byEvents": False,
            "events": [
                "messages.upsert",
                "MESSAGES_UPDATE",
                "SEND_MESSAGE",
                "CONNECTION_UPDATE"
            ]
        }
    }

    headers = {
        "apikey": EVO_API_KEY,
        "Content-Type": "application/json"
    }

    try:
        # 1. Configura Webhook (Rota V1)
        requests.post(f"{EVO_API_URL}/webhook/set/{instancia}", 
                      json={"webhook": payload["webhook"]}, headers=headers)
        
        # 2. Configura Geral (Rota V2)
        requests.post(f"{EVO_API_URL}/instance/settings/{instancia}", 
                      json=payload, headers=headers)

        return {"status": "sucesso", "msg": f"Webhook apontado para {webhook_url}"}

    except Exception as e:
        print(f"❌ Erro config auto: {e}")
        return JSONResponse(status_code=500, content={"erro": str(e)})
    


# ==========================================================
# ROTA: ABRIR ATENDIMENTO MANUALMENTE (DA LISTA DE CONTATOS)
# ==========================================================
class AbrirConversa(BaseModel):
    instancia: str
    remote_jid: str

@app.post("/atendimentos/abrir")
def abrir_atendimento_manual(dados: AbrirConversa):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Verifica se já não está aberto
        cur.execute("SELECT id FROM atendimentos_ativos WHERE instancia = %s AND remote_jid = %s", 
                    (dados.instancia, dados.remote_jid))
        if cur.fetchone():
            return {"status": "ja_existe", "msg": "Chat já está aberto."}

        # 2. Insere na tabela de ativos
        cur.execute("INSERT INTO atendimentos_ativos (instancia, remote_jid) VALUES (%s, %s)", 
                    (dados.instancia, dados.remote_jid))
        conn.commit()
        return {"status": "sucesso", "msg": "Conversa iniciada!"}
    except Exception as e:
        print(f"Erro ao abrir: {e}") # Adicionei um print para debug
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()


# ==========================================================
# ROTA: VERIFICAR STATUS DO ROBÔ (CORRIGIDA - SEM ERRO DE TUPLA)
# ==========================================================
# ==========================================================
# ROTA: VERIFICAR STATUS DO ROBÔ (CORRIGIDA - SEM ERRO DE TUPLA)
# ==========================================================
@app.get("/usuarios/status-bot/{instancia}")
def get_status_bot(instancia: str):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT bot_ativo FROM usuarios WHERE instancia_wa = %s", (instancia,))
        res = cur.fetchone()
        
        # AQUI ESTAVA O ERRO NO ARQUIVO ANTIGO
        # Antes: status = res['bot_ativo'] (Isso trava o sistema)
        # Agora: status = res[0] (Isso funciona)
        status = res[0] if res else True
        
        return {"bot_ativo": status}
    except:
        return {"bot_ativo": True}
    finally:
        conn.close()
        
# GRAVAÇÃO
class StatusBot(BaseModel):
    instancia: str
    ativo: bool

@app.post("/usuarios/mudar-status-bot")
def set_status_bot(dados: StatusBot):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET bot_ativo = %s WHERE instancia_wa = %s", 
                    (dados.ativo, dados.instancia))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"erro": str(e)}
    finally:
        conn.close()

# ==========================================================
# ROTA: SALVAR NOME DO CONTATO (CRM RÁPIDO) ✏️
# ==========================================================
class SalvarContatoReq(BaseModel):
    instancia: str
    remote_jid: str
    nome: str

@app.post("/crm/salvar_nome_rapido")
def salvar_nome_rapido(dados: SalvarContatoReq):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Tenta atualizar se já existe
        cur.execute("SELECT id FROM clientes_finais WHERE instancia=%s AND telefone=%s", (dados.instancia, dados.remote_jid))
        existe = cur.fetchone()
        
        if existe:
            cur.execute("UPDATE clientes_finais SET nome=%s WHERE id=%s", (dados.nome, existe[0]))
        else:
            # 2. Se não existe, cria novo
            cur.execute("""
                INSERT INTO clientes_finais (instancia, nome, telefone, dia_vencimento, etiquetas)
                VALUES (%s, %s, %s, 1, 'atendimento')
            """, (dados.instancia, dados.nome, dados.remote_jid))
            
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()


# ==========================================================
# ROTA: ALTERAR STATUS DO USUÁRIO (BLOQUEAR/DESBLOQUEAR)
# ==========================================================
class StatusUsuarioReq(BaseModel):
    status: str # 'ativo', 'bloqueado', 'vencido', 'pendente'

@app.put("/usuarios/status/{user_id}")
def alterar_status_usuario(user_id: int, dados: StatusUsuarioReq):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE usuarios SET status_conta = %s WHERE id = %s", 
                    (dados.status, user_id))
        conn.commit()
        return {"status": "ok", "msg": f"Status alterado para {dados.status}"}
    except Exception as e:
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()


# ==========================================================
# GESTÃO AVANÇADA DE PLANOS + REGRAS (INTEGRAÇÃO TOTAL) 🤝
# ==========================================================

# Modelo para receber dados completos (Info + Regras)
class PlanoCompleto(BaseModel):
    nome: str
    valor: float
    descricao: str
    ativo: bool
    # Regras Opcionais (Dicionário chave: valor)
    limites: dict = {} 

# 1. Rota para Buscar Detalhes (Plano + Suas Regras)
@app.get("/planos/{id_plano}/detalhes")
def obter_plano_detalhes(id_plano: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # Pega dados do plano
        cur.execute("SELECT * FROM planos_comerciais WHERE id = %s", (id_plano,))
        plano = cur.fetchone()
        
        if not plano: return JSONResponse(status_code=404, content={"erro": "Plano não achado"})

        # Pega regras vinculadas a este plano (pelo nome, pois sua tabela 'regras' usa o nome)
        cur.execute("SELECT funcionalidade, ativo, limite FROM regras WHERE plano = %s", (plano['nome'],))
        regras_db = cur.fetchall()
        
        # Formata para o Front
        regras_formatadas = {}
        for r in regras_db:
            # Se for numérico usa o limite, se for booleano usa o ativo
            chave = r['funcionalidade']
            valor = r['limite'] if 'max_' in chave else r['ativo']
            regras_formatadas[chave] = valor

        return {"plano": plano, "regras": regras_formatadas}
    finally:
        conn.close()

# 2. Rota para Criação Inteligente (Cria Plano + Regras Iniciais)
@app.post("/planos/criar_completo")
def criar_plano_completo(p: PlanoCompleto):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Cria o Plano
        cur.execute("""
            INSERT INTO planos_comerciais (nome, valor, descricao, ativo)
            VALUES (%s, %s, %s, %s) RETURNING id
        """, (p.nome, p.valor, p.descricao, p.ativo))
        new_id = cur.fetchone()[0]

        # 2. Insere as Regras que vieram do formulário
        for func, val in p.limites.items():
            eh_limite = 'max_' in func
            cur.execute("""
                INSERT INTO regras (plano, funcionalidade, ativo, limite)
                VALUES (%s, %s, %s, %s)
            """, (p.nome, func, bool(val) if not eh_limite else True, int(val) if eh_limite else 0))
        
        conn.commit()
        return {"status": "criado", "id": new_id}
    except Exception as e:
        conn.rollback()
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        conn.close()

# 3. Rota para Edição Completa (Atualiza Nome/Preço E as Regras)
@app.put("/planos/{id_plano}/editar_completo")
def editar_plano_completo(id_plano: int, p: PlanoCompleto):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Pega nome antigo para atualizar na tabela de regras se mudar
        cur.execute("SELECT nome FROM planos_comerciais WHERE id = %s", (id_plano,))
        res = cur.fetchone()
        if not res: return JSONResponse(status_code=404, content={"erro": "Plano sumiu"})
        nome_antigo = res[0]

        # 2. Atualiza Tabela Planos
        cur.execute("""
            UPDATE planos_comerciais 
            SET nome=%s, valor=%s, descricao=%s, ativo=%s
            WHERE id=%s
        """, (p.nome, p.valor, p.descricao, p.ativo, id_plano))

        # 3. Se o nome mudou, atualiza na tabela de regras também
        if nome_antigo != p.nome:
            cur.execute("UPDATE regras SET plano=%s WHERE plano=%s", (p.nome, nome_antigo))

        # 4. Atualiza ou Cria as Regras Individuais
        for func, val in p.limites.items():
            eh_limite = 'max_' in func
            
            # Upsert (Atualiza se existe, Cria se não)
            # Verifica se já existe
            cur.execute("SELECT 1 FROM regras WHERE plano=%s AND funcionalidade=%s", (p.nome, func))
            if cur.fetchone():
                cur.execute("""
                    UPDATE regras SET ativo=%s, limite=%s 
                    WHERE plano=%s AND funcionalidade=%s
                """, (bool(val) if not eh_limite else True, int(val) if eh_limite else 0, p.nome, func))
            else:
                cur.execute("""
                    INSERT INTO regras (plano, funcionalidade, ativo, limite)
                    VALUES (%s, %s, %s, %s)
                """, (p.nome, func, bool(val) if not eh_limite else True, int(val) if eh_limite else 0))

        conn.commit()
        return {"status": "atualizado"}
    except Exception as e:
        conn.rollback()
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        conn.close()

# ==========================================================
# ROTA: EXCLUIR PLANO COM SEGURANÇA 🛡️
# ==========================================================
@app.delete("/planos/excluir/{id}")
def excluir_plano(id: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Descobre o nome do plano antes de excluir
        cur.execute("SELECT nome FROM planos_comerciais WHERE id = %s", (id,))
        res = cur.fetchone()
        
        if not res:
            return JSONResponse(status_code=404, content={"detail": "Plano não encontrado."})
        
        nome_plano = res[0]

        # 2. VERIFICAÇÃO DE SEGURANÇA: Tem usuários usando?
        cur.execute("SELECT COUNT(*) FROM usuarios WHERE plano = %s", (nome_plano,))
        qtd_usuarios = cur.fetchone()[0]

        if qtd_usuarios > 0:
            # Retorna erro 400 (Bad Request) para o frontend mostrar o alerta
            return JSONResponse(
                status_code=400, 
                content={"detail": f"Impossível excluir! Existem {qtd_usuarios} usuários neste plano. Mude o plano deles antes."}
            )

        # 3. Limpa as Regras associadas (Necessário para não dar erro de chave estrangeira)
        cur.execute("DELETE FROM regras WHERE plano = %s", (nome_plano,))

        # 4. Agora sim, exclui o Plano
        cur.execute("DELETE FROM planos_comerciais WHERE id = %s", (id,))
        
        conn.commit()
        return {"status": "sucesso", "msg": f"Plano {nome_plano} excluído!"}

    except Exception as e:
        conn.rollback()
        print(f"Erro ao excluir plano: {e}")
        return JSONResponse(status_code=500, content={"detail": str(e)})
    finally:
        conn.close()


# ==========================================================
# ROTA DE EMERGÊNCIA: CONSERTAR BANCO DE DADOS 🚑
# ==========================================================
@app.get("/setup/reparar-banco")
def reparar_banco_dados():
    conn = get_connection()
    cur = conn.cursor()
    log = []
    try:
        # 1. Cria Tabela de Planos Comerciais (Se não existir)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS planos_comerciais (
                id SERIAL PRIMARY KEY,
                nome VARCHAR(50) UNIQUE NOT NULL,
                valor DECIMAL(10, 2) NOT NULL,
                descricao TEXT,
                ativo BOOLEAN DEFAULT TRUE
            );
        """)
        log.append("✅ Tabela 'planos_comerciais' verificada.")

        # 2. Cria Tabela de Regras (Se não existir)
        # IMPORTANTE: Adicionamos ON DELETE CASCADE para limpar regras se o plano for excluído
        cur.execute("""
            CREATE TABLE IF NOT EXISTS regras (
                id SERIAL PRIMARY KEY,
                plano VARCHAR(50) NOT NULL,
                funcionalidade VARCHAR(50) NOT NULL,
                ativo BOOLEAN DEFAULT FALSE,
                limite INTEGER DEFAULT 0,
                CONSTRAINT uk_regra_plano UNIQUE (plano, funcionalidade)
            );
        """)
        log.append("✅ Tabela 'regras' verificada.")

        # 3. Insere Planos Padrão (Só se estiver vazio)
        cur.execute("SELECT COUNT(*) FROM planos_comerciais")
        if cur.fetchone()[0] == 0:
            cur.execute("""
                INSERT INTO planos_comerciais (nome, valor, descricao) VALUES 
                ('Básico', 19.90, '🤖 5 Gatilhos'),
                ('Pro', 39.90, '🚀 Disparos e CRM'),
                ('Enterprise', 99.90, '💎 Tudo Ilimitado');
            """)
            log.append("➕ Planos padrão inseridos.")

        conn.commit()
        return {"status": "Sucesso", "log": log}

    except Exception as e:
        conn.rollback()
        return {"erro": str(e), "detalhe": "Erro ao criar tabelas"}
    finally:
        conn.close()


# ==========================================================
# 3. Listar Planos (AGORA COM REGRAS INCLUSAS) 📦
# ==========================================================
@app.get("/planos/listar")
def listar_planos():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        # 1. Busca os Planos
        cur.execute("SELECT * FROM planos_comerciais ORDER BY valor ASC")
        planos = cur.fetchall()

        # 2. Busca TODAS as Regras
        cur.execute("SELECT * FROM regras")
        todas_regras = cur.fetchall()

        # 3. Organiza as regras num dicionário auxiliar
        # Estrutura: {'Nome do Plano': {'max_gatilhos': 10, 'permite_disparos': True}}
        mapa_regras = {}
        for r in todas_regras:
            nome_plano = r['plano']
            func = r['funcionalidade']
            
            # Se for regra numérica, pega o limite. Se for booleana, pega o ativo.
            valor = r['limite'] if 'max_' in func else r['ativo']
            
            if nome_plano not in mapa_regras:
                mapa_regras[nome_plano] = {}
            
            mapa_regras[nome_plano][func] = valor

        # 4. Anexa as regras dentro de cada plano
        for p in planos:
            # Pega as regras desse plano ou usa vazio {} se não tiver
            p['regras'] = mapa_regras.get(p['nome'], {})

        return planos

    except psycopg2.errors.UndefinedTable:
        return [] # Se tabela não existe, retorna vazio (o auto-reparo faria o resto em outra rota)
    except Exception as e:
        print(f"Erro listar planos: {e}")
        return []
    finally:
        cur.close()
        conn.close()




# --- MODELO PARA PAGAMENTO CARTÃO ---
class PedidoCartao(BaseModel):
    user_id: int
    plano: str
    valor: float
    email: str

# ==========================================================
# 💳 ROTAS PARA CARTÃO DE CRÉDITO (MERCADO PAGO)
# ==========================================================

@app.post("/pagamento/mp-cartao")
def criar_link_mp(pedido: PedidoCartao):
    print(f"💳 Renovação via Cartão para User {pedido.user_id}")
    
    conn = get_connection()
    cur = conn.cursor()
    
    try:
        # 1. BUSCA PREÇO REAL NO BANCO
        cur.execute("SELECT valor FROM planos_comerciais WHERE nome = %s", (pedido.plano,))
        res_plano = cur.fetchone()
        
        if res_plano:
            valor_base = float(res_plano[0])
        else:
            valor_base = 99.90
        
        valor_final = valor_base
        cupom_desc = ""

        # --- 2. LÓGICA DO CUPOM (O Frontend não manda o código do cupom no PedidoCartao hoje) ---
        # Se você quiser cupom na renovação de cartão, o Frontend precisa mandar o código.
        # Como o seu modelo PedidoCartao atual não tem campo 'cupom', vamos assumir
        # que na renovação via cartão você está cobrando o valor cheio OU
        # que você vai confiar no 'pedido.valor' APENAS SE for menor que o do banco (desconto).
        
        # AJUSTE INTELIGENTE: Se o valor que veio do front for MENOR que o do banco,
        # significa que o front já aplicou um cupom visualmente.
        # Vamos validar se essa diferença faz sentido?
        # Para simplificar e resolver AGORA: Vamos aceitar o valor do 'pedido.valor' 
        # SE ele for menor que o valor do banco (assumindo que o front calculou o cupom).
        
        if pedido.valor < valor_base:
            # O front calculou desconto. Vamos usar o valor do pedido, 
            # mas idealmente deveríamos revalidar o cupom aqui.
            print(f"⚠️ Usando valor com desconto enviado pelo front: {pedido.valor}")
            valor_final = float(pedido.valor)
        else:
            # Se for igual ou maior, usa o do banco pra garantir
            valor_final = valor_base

        # Configura URLs
        base_url = "https://agil.modestotech.com.br"
        plano_safe = urllib.parse.quote(str(pedido.plano))
        uid_safe = str(pedido.user_id)
        
        preference_data = {
            "items": [
                {
                    "title": f"Renovação Plano {pedido.plano}",
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": valor_final
                }
            ],
            "payer": {
                "email": pedido.email
            },
            "external_reference": str(pedido.user_id),
            "back_urls": {
                "success": f"{base_url}/?status_mp=aprovado&uid={uid_safe}&plano={plano_safe}",
                "failure": f"{base_url}/?status_mp=falha",
                "pending": f"{base_url}/?status_mp=pendente"
            },
            "auto_return": "approved",
            "statement_descriptor": "AGIL SAAS"
        }

        resultado = sdk_mp.preference().create(preference_data)
        
        status = resultado.get("status")
        if status not in [200, 201]:
            print(f"❌ Erro MP Renovação: {resultado.get('response')}")
            return JSONResponse(status_code=400, content={"erro": "Mercado Pago recusou", "detalhe": resultado.get('response')})

        link = resultado.get("response", {}).get("init_point")
        
        return {"checkout_url": link}

    except Exception as e:
        print(f"❌ Erro Interno Link MP: {e}")
        return JSONResponse(status_code=500, content={"erro": str(e)})
    finally:
        conn.close()


# 2. CONFIRMAR SUCESSO (Chamado pelo Front quando o cliente volta aprovado)
@app.get("/pagamento/confirmar_sucesso")
def confirmar_pagamento_manual(uid: int, plano: str):
    print(f"✅ Confirmando pagamento CARTÃO para User {uid}...")
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Pega data atual
        cur.execute("SELECT data_vencimento, plano FROM usuarios WHERE id = %s", (uid,))
        user = cur.fetchone()
        
        if not user: return {"erro": "Usuário não achado"}
        
        # 2. Lógica de Data: 
        # Se já venceu, soma 30 dias a partir de hoje. 
        # Se não venceu ainda, soma 30 dias na data que ele já tem.
        hoje = date.today()
        vencimento_atual = user[0]
        
        if vencimento_atual and vencimento_atual > hoje:
            nova_data = vencimento_atual + timedelta(days=30)
        else:
            nova_data = hoje + timedelta(days=30)
            
        # 3. Atualiza no Banco
        # Definimos 'id_pagamento_mp' como 'CARTAO_CREDITO' só pra marcar
        cur.execute("""
            UPDATE usuarios 
            SET status_conta='ativo', 
                plano=%s, 
                data_vencimento=%s,
                id_pagamento_mp='CARTAO_WEB'
            WHERE id=%s
        """, (plano, nova_data, uid))
        
        conn.commit()
        return {"status": "aprovado", "novo_vencimento": str(nova_data)}

    except Exception as e:
        conn.rollback()
        return {"erro": str(e)}
    finally:
        conn.close()



@app.post("/publico/registrar_cartao")
def registrar_com_cartao(dados: dict):
    print(f"💳 Novo Registro via Cartão: {dados['nome']}")
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Verifica duplicidade
        cur.execute("SELECT id FROM usuarios WHERE login = %s OR instancia_wa = %s", (dados['login'], dados['instancia']))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Login ou Instância já existem.")

        # 2. BUSCA PREÇO REAL NO BANCO
        cur.execute("SELECT valor FROM planos_comerciais WHERE nome = %s", (dados['plano'],))
        res_plano = cur.fetchone()
        
        if res_plano:
            valor_base = float(res_plano[0])
        else:
            valor_base = 99.90 

        valor_final = valor_base
        cupom_desc = ""

        # --- 3. APLICA CUPOM (AQUI ESTAVA FALTANDO) ---
        if dados.get('cupom'):
            codigo = dados['cupom'].strip().upper()
            # Busca o cupom
            cur.execute("SELECT desconto_porcentagem FROM cupons WHERE codigo = %s", (codigo,))
            res_cupom = cur.fetchone()
            
            if res_cupom:
                porcentagem = float(res_cupom[0])
                desconto_reais = (valor_base * porcentagem) / 100
                valor_final = valor_base - desconto_reais
                cupom_desc = f" (Cupom {codigo} -{int(porcentagem)}%)"
                print(f"✅ Cupom {codigo} aplicado! De {valor_base} por {valor_final}")
            else:
                print(f"⚠️ Cupom não encontrado: {codigo}")

        # Arredonda
        valor_final = round(valor_final, 2)

        # 4. Insere no Banco como PENDENTE
        # Atenção: Salvamos o 'valor_mensal' já com desconto para futuras renovações manterem o preço? 
        # Geralmente sim, ou salva o preço cheio. Aqui vou salvar com desconto.
        cur.execute("""
            INSERT INTO usuarios (nome_cliente, login, senha, instancia_wa, plano, valor_mensal, email, whatsapp, status_conta, id_pagamento_mp) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pendente', 'CARTAO_PENDENTE') RETURNING id
        """, (
            dados['nome'], dados['login'], dados['senha'], dados['instancia'], 
            dados['plano'], valor_final, dados['email'], dados['whatsapp']
        ))
        user_id = cur.fetchone()[0]
        conn.commit()

        # 5. Gera o Link do Mercado Pago
        base_url = "https://agil.modestotech.com.br" # SEU DOMÍNIO AQUI
        
        plano_safe = urllib.parse.quote(str(dados['plano']))
        uid_safe = str(user_id)

        preference_data = {
            "items": [
                {
                    "title": f"Assinatura {dados['plano']}{cupom_desc}",
                    "quantity": 1,
                    "currency_id": "BRL",
                    "unit_price": float(valor_final) # Manda o valor já descontado
                }
            ],
            "payer": {
                "email": dados['email'],
                "name": dados['nome']
            },
            "external_reference": str(user_id),
            "back_urls": {
                "success": f"{base_url}/?status_mp=aprovado&uid={uid_safe}&plano={plano_safe}",
                "failure": f"{base_url}/?status_mp=falha",
                "pending": f"{base_url}/?status_mp=pendente"
            },
            "auto_return": "approved",
            "statement_descriptor": "AGIL SAAS"
        }

        resultado = sdk_mp.preference().create(preference_data)
        
        if resultado.get("status") not in [200, 201]:
            print(f"❌ Erro MP: {resultado}")
            cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
            conn.commit()
            raise HTTPException(status_code=400, detail="Erro ao gerar link MP")

        link = resultado.get("response", {}).get("init_point")

        if not link:
            cur.execute("DELETE FROM usuarios WHERE id = %s", (user_id,))
            conn.commit()
            raise HTTPException(status_code=400, detail="Link vazio do MP")

        return {"checkout_url": link}

    except HTTPException as he:
        raise he
    except Exception as e:
        conn.rollback()
        print(f"Erro Reg Cartão: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
        



# ==========================================================
# 🔔 WEBHOOK UNIVERSAL (PIX E CARTÃO) - O GUARDIÃO 🛡️
# ==========================================================
@app.post("/webhook/pagamento")
async def webhook_pagamento(request: Request):
    try:
        # Captura os parâmetros que o MP envia
        params = request.query_params
        topic = params.get("topic") or params.get("type")
        id_obj = params.get("id") or params.get("data.id")

        if topic == "payment":
            print(f"🔔 Notificação recebida! ID: {id_obj}")

            # 1. Consulta o status oficial no Mercado Pago
            pagamento = sdk_mp.payment().get(id_obj)
            dados_pag = pagamento.get("response", {})
            status = dados_pag.get("status")
            ref_user_id = dados_pag.get("external_reference") # Aqui pegamos a etiqueta!

            if status == "approved" and ref_user_id:
                print(f"✅ Pagamento Aprovado para User ID: {ref_user_id}")
                
                conn = get_connection()
                cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
                
                try:
                    # 2. Busca o usuário
                    cur.execute("SELECT * FROM usuarios WHERE id = %s", (ref_user_id,))
                    user = cur.fetchone()
                    
                    if user:
                        # 3. Calcula nova data (Se já venceu, hoje+30. Se não, acumula)
                        hoje = date.today()
                        venc_atual = user['data_vencimento']
                        
                        # Lógica inteligente de data
                        if venc_atual and venc_atual > hoje:
                            nova_data = venc_atual + timedelta(days=30)
                        else:
                            nova_data = hoje + timedelta(days=30)

                        # 4. Atualiza no Banco
                        # Nota: id_pagamento_mp serve para evitar processar o mesmo ID duas vezes
                        if user.get('id_pagamento_mp') != str(id_obj):
                            cur.execute("""
                                UPDATE usuarios 
                                SET status_conta='ativo', 
                                    data_vencimento=%s,
                                    id_pagamento_mp=%s
                                WHERE id=%s
                            """, (nova_data, str(id_obj), ref_user_id))
                            conn.commit()
                            print("🎉 Banco de dados atualizado via Webhook!")

                            # 5. ATIVAÇÃO DE INSTÂNCIA (Apenas se era conta nova/pendente)
                            if user['status_conta'] == 'pendente':
                                print("🚀 Criando instância Evolution automaticamente...")
                                try:
                                    # Cria Instância
                                    requests.post(f"{EVO_API_URL}/instance/create", 
                                                json={"instanceName": user['instancia_wa'], "token": user['senha'], "qrcode": True}, 
                                                headers={"apikey": EVO_API_KEY})
                                    
                                    # Configura Webhook da Evolution
                                    webhook_wa = f"{DOMAIN_URL}/webhook/whatsapp"
                                    requests.post(f"{EVO_API_URL}/webhook/set/{user['instancia_wa']}", 
                                                json={"webhook": {"enabled": True, "url": webhook_wa, "events": ["messages.upsert"]}}, 
                                                headers={"apikey": EVO_API_KEY})
                                except Exception as e:
                                    print(f"⚠️ Erro ao provisionar instância: {e}")

                except Exception as db_err:
                    print(f"❌ Erro Banco Webhook: {db_err}")
                    conn.rollback()
                finally:
                    cur.close()
                    conn.close()

        return JSONResponse(status_code=200, content={"status": "recebido"})

    except Exception as e:
        print(f"❌ Erro Crítico Webhook: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})
    
# ==========================================================
# 📧 RECUPERAÇÃO DE SENHA
# ==========================================================

# Configs de Email (Carregadas do .env)
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", 587))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Suporte")

def enviar_email_simples(destinatario, assunto, corpo_html):
    try:
        msg = MIMEMultipart()
        msg['From'] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        msg['To'] = destinatario
        msg['Subject'] = assunto
        msg.attach(MIMEText(corpo_html, 'html'))

        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        text = msg.as_string()
        server.sendmail(SMTP_USER, destinatario, text)
        server.quit()
        return True
    except Exception as e:
        print(f"❌ Erro ao enviar email: {e}")
        return False

# ROTA 1: SOLICITAR RECUPERAÇÃO (Gera Token e Envia Email)
@app.post("/publico/recuperar-senha/solicitar")
def solicitar_recuperacao(dados: dict):
    # dados: {"email": "cliente@email.com"}
    email = dados.get("email")
    
    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Verifica se email existe
        cur.execute("SELECT id, nome_cliente FROM usuarios WHERE email = %s", (email,))
        user = cur.fetchone()
        
        if not user:
            # Por segurança, retornamos OK mesmo se não achar, para não revelar quem é cliente
            return {"status": "ok", "msg": "Se o e-mail existir, enviamos um link."}

        user_id, nome = user

        # 2. Gera Token Seguro e Validade (1 hora)
        token = str(uuid.uuid4())
        validade = datetime.now() + timedelta(hours=1)

        cur.execute("UPDATE usuarios SET reset_token = %s, reset_expires = %s WHERE id = %s", 
                    (token, validade, user_id))
        conn.commit()

        # 3. Envia E-mail
        link_recuperacao = f"{FRONTEND_URL}/?reset_token={token}"
        
        html = f"""
        <h2>Olá, {nome}!</h2>
        <p>Recebemos uma solicitação para redefinir sua senha.</p>
        <p>Clique no botão abaixo para criar uma nova senha:</p>
        <a href="{link_recuperacao}" style="background:#4cd137; color:white; padding:10px 20px; text-decoration:none; border-radius:5px;">REDEFINIR SENHA</a>
        <p>Se não foi você, ignore este e-mail. O link expira em 1 hora.</p>
        """
        
        if enviar_email_simples(email, "Redefinição de Senha", html):
            return {"status": "ok", "msg": "E-mail enviado!"}
        else:
            raise HTTPException(status_code=500, detail="Erro ao enviar e-mail.")

    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()

# ROTA 2: CONFIRMAR NOVA SENHA (Valida Token)
@app.post("/publico/recuperar-senha/confirmar")
def confirmar_nova_senha(dados: dict):
    # dados: {"token": "...", "nova_senha": "..."}
    token = dados.get("token")
    nova_senha = dados.get("nova_senha")

    conn = get_connection()
    cur = conn.cursor()
    try:
        # 1. Busca usuário pelo token e verifica validade
        cur.execute("""
            SELECT id FROM usuarios 
            WHERE reset_token = %s AND reset_expires > NOW()
        """, (token,))
        user = cur.fetchone()

        if not user:
            raise HTTPException(status_code=400, detail="Link inválido ou expirado.")

        # 2. Atualiza a senha e limpa o token (para não ser usado de novo)
        cur.execute("""
            UPDATE usuarios 
            SET senha = %s, reset_token = NULL, reset_expires = NULL 
            WHERE id = %s
        """, (nova_senha, user[0]))
        
        conn.commit()
        return {"status": "ok", "msg": "Senha alterada com sucesso!"}

    except HTTPException as he: raise he
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()



# ==========================================================
# 📚 BASE DE CONHECIMENTO (HELPDESK)
# ==========================================================

# 1. LISTAR ARTIGOS (Público para clientes logados)
@app.get("/ajuda/listar")
def listar_ajuda():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("SELECT * FROM base_conhecimento ORDER BY ordem ASC, id ASC")
        return cur.fetchall()
    finally:
        conn.close()

# 2. SALVAR ARTIGO (Admin) - Cria ou Edita
class ArtigoAjuda(BaseModel):
    id: Optional[int] = None
    titulo: str
    conteudo: str
    categoria: Optional[str] = "Geral"

@app.post("/ajuda/salvar")
def salvar_ajuda(dados: ArtigoAjuda):
    conn = get_connection()
    cur = conn.cursor()
    try:
        if dados.id:
            # Edição
            cur.execute("""
                UPDATE base_conhecimento SET titulo=%s, conteudo=%s, categoria=%s 
                WHERE id=%s
            """, (dados.titulo, dados.conteudo, dados.categoria, dados.id))
        else:
            # Criação
            cur.execute("""
                INSERT INTO base_conhecimento (titulo, conteudo, categoria, ordem) 
                VALUES (%s, %s, %s, 99)
            """, (dados.titulo, dados.conteudo, dados.categoria))
        
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"erro": str(e)}
    finally:
        conn.close()

# 3. EXCLUIR ARTIGO (Admin)
@app.delete("/ajuda/{id}")
def excluir_ajuda(id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM base_conhecimento WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return {"status": "ok"}


# ==========================================================
# 🧠 CRM AVANÇADO (FUNIL, NOTAS, TAREFAS)
# ==========================================================

# 1. ATUALIZAR FASE DO FUNIL (Arrastar card no Kanban)
class MudarEtapaReq(BaseModel):
    cliente_id: int
    nova_etapa: str

@app.put("/crm/mudar_etapa")
def mudar_etapa_crm(dados: MudarEtapaReq):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE clientes_finais SET etapa_funil = %s WHERE id = %s", 
                    (dados.nova_etapa, dados.cliente_id))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"erro": str(e)}
    finally:
        conn.close()

# 2. GESTÃO DE NOTAS INTERNAS
class NotaReq(BaseModel):
    cliente_id: int
    autor: str
    texto: str

@app.post("/crm/notas")
def criar_nota(dados: NotaReq):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO crm_notas (cliente_id, autor_nome, texto) VALUES (%s, %s, %s)",
                    (dados.cliente_id, dados.autor, dados.texto))
        conn.commit()
        return {"status": "ok"}
    finally:
        conn.close()

@app.get("/crm/notas/{cliente_id}")
def listar_notas(cliente_id: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM crm_notas WHERE cliente_id = %s ORDER BY data_criacao DESC", (cliente_id,))
    res = cur.fetchall()
    conn.close()
    # Converte datas
    for r in res: r['data_criacao'] = str(r['data_criacao'])
    return res

# 3. KANBAN (LISTAR TODOS AGRUPADOS)
@app.get("/crm/kanban/{instancia}")
def listar_kanban(instancia: str):
    # Retorna todos os clientes para montarmos as colunas no front
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT id, nome, telefone, etapa_funil, valor_negocio, etiquetas 
        FROM clientes_finais 
        WHERE instancia = %s 
        ORDER BY id DESC LIMIT 200
    """, (instancia,))
    res = cur.fetchall()
    conn.close()
    return res

# ==========================================================
# 📅 GESTÃO DE TAREFAS (ROTAS COMPLETAS E CORRIGIDAS)
# ==========================================================

class TarefaCreate(BaseModel):
    cliente_id: int
    descricao: str
    data_limite: str 

# 1. SALVAR TAREFA
@app.post("/crm/tarefas")
def criar_tarefa(d: TarefaCreate):
    conn = get_connection()
    cur = conn.cursor()
    try:
        # Garante a tabela
        cur.execute("""
            CREATE TABLE IF NOT EXISTS crm_tarefas (
                id SERIAL PRIMARY KEY,
                cliente_id INTEGER NOT NULL,
                descricao TEXT NOT NULL,
                data_limite TIMESTAMP WITHOUT TIME ZONE,
                concluido BOOLEAN DEFAULT FALSE,
                criado_em TIMESTAMP DEFAULT NOW()
            )
        """)
        conn.commit()

        # Converte Data
        try:
            dt_obj = datetime.strptime(d.data_limite, "%Y-%m-%d %H:%M:%S")
        except:
            return {"status": "erro", "msg": "Formato de data inválido"}

        cur.execute("""
            INSERT INTO crm_tarefas (cliente_id, descricao, data_limite, concluido)
            VALUES (%s, %s, %s, FALSE)
        """, (d.cliente_id, d.descricao, dt_obj))
        
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        conn.rollback()
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()

# 2. LISTAR TAREFAS (AQUI ESTAVA O POSSÍVEL ERRO)
@app.get("/crm/tarefas/{cliente_id}")
def listar_tarefas_cliente(cliente_id: int):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, cliente_id, descricao, data_limite, concluido 
            FROM crm_tarefas 
            WHERE cliente_id = %s 
            ORDER BY concluido ASC, data_limite ASC
        """, (cliente_id,))
        
        rows = cur.fetchall()
        
        # --- CORREÇÃO CRUCIAL: CONVERTER DATA PARA STRING ---
        for r in rows:
            if r['data_limite']: 
                r['data_limite'] = str(r['data_limite'])
        # ----------------------------------------------------
            
        return rows
    except Exception as e:
        print(f"Erro ao listar tarefas: {e}")
        return []
    finally:
        conn.close()

# 3. CONCLUIR TAREFA
@app.put("/crm/tarefas/{id_tarefa}/toggle")
def alternar_status_tarefa(id_tarefa: int):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("UPDATE crm_tarefas SET concluido = NOT concluido WHERE id = %s", (id_tarefa,))
        conn.commit()
        return {"status": "ok"}
    except Exception as e:
        return {"status": "erro", "msg": str(e)}
    finally:
        conn.close()


# --- COLE ISTO NO MAIN.PY (BACKEND) ---

@app.get("/crm/tarefas/todas/{instancia}")
def listar_todas_tarefas(instancia: str, apenas_pendentes: bool = False):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        sql = """
            SELECT t.*, c.nome as nome_cliente, c.telefone 
            FROM crm_tarefas t
            JOIN clientes_finais c ON t.cliente_id = c.id
            WHERE c.instancia = %s
        """
        if apenas_pendentes:
            sql += " AND t.concluido = FALSE"
            
        sql += " ORDER BY t.data_limite ASC"
        
        cur.execute(sql, (instancia,))
        rows = cur.fetchall()
        
        for r in rows:
            if r['data_limite']: r['data_limite'] = str(r['data_limite'])
            if r['criado_em']: r['criado_em'] = str(r['criado_em'])
            
        return rows
    except Exception as e:
        print(f"Erro agenda: {e}")
        return []
    finally:
        conn.close()