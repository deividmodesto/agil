# ==========================================================
# API BACKEND - AGIL SAAS (Versão Postgres + Webhook ON)
# ==========================================================
import os
import shutil
import json
import requests
from fastapi import FastAPI, HTTPException, UploadFile, File, Request
from pydantic import BaseModel
import psycopg2
import psycopg2.extras 
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import base64
import mercadopago
from datetime import datetime, date, timedelta
from fastapi.responses import JSONResponse

# Configure com SEU token
sdk_mp = mercadopago.SDK("APP_USR-6043577431380897-010214-6fda7216b75311bb6ead096cc799021d-83186555")

# --- CONFIGURAÇÃO DE PASTAS ---
os.makedirs("uploads", exist_ok=True)
os.environ["PYTHONIOENCODING"] = "utf-8"

app = FastAPI()

# Monta a pasta para ser acessível via URL 
app.mount("/arquivos", StaticFiles(directory="uploads"), name="arquivos")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- VARIÁVEL DE MEMÓRIA (QUEM ESTÁ ONDE) ---
# Formato: {'556499998888': ID_DO_MENU_ATUAL_INTEIRO}
user_state = {}

# --- CONFIGURAÇÕES ---
EVO_API_URL = "http://127.0.0.1:8080" # Evolution Local
EVO_API_KEY = "159632"                # Sua Key
DOMAIN_URL = "https://api.modestotech.com.br"


# Configurações do Banco (PostgreSQL)
DB_USER = "postgres"
DB_PASS = "3adefe283b724adebd02930fd4b1386c"
DB_HOST = "127.0.0.1"
DB_NAME = "evolution"
DB_PORT = "5432"

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

# ==============================================================================
# FUNÇÃO DE ENVIO V3 (CORRIGIDA: FILTRO POR INSTÂNCIA PARA NÃO MISTURAR CLIENTES)
# ==============================================================================
def enviar_mensagem_smart(instancia, numero, texto, id_gatilho_atual=None, apenas_texto=False):
    print(f"📤 Enviando para {numero}...")
    
    tem_sub_menus = False
    opcoes = []
    
    # SÓ busca opções se NÃO for 'apenas_texto'
    if not apenas_texto:
        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            
            if id_gatilho_atual:
                # Busca filhos (Sub-menus)
                cur.execute("SELECT gatilho, titulo_menu FROM respostas_automacao WHERE id_pai = %s AND instancia = %s", (id_gatilho_atual, instancia))
            else:
                # Busca Menu Principal (Raiz)
                cur.execute("SELECT gatilho, titulo_menu FROM respostas_automacao WHERE instancia = %s AND id_pai IS NULL AND gatilho != 'default'", (instancia,))
                
            opcoes = cur.fetchall()
            conn.close()
            
            if opcoes:
                tem_sub_menus = True
        except Exception as e:
            print(f"Erro ao buscar menu: {e}")

    # Monta Payload
    payload = {"number": numero, "text": texto}
    
    # Anexa o menu se tiver
    if tem_sub_menus:
        payload["text"] += "\n\n👇 *Opções:*"
        for op in opcoes:
            mostrar = op.get('titulo_menu') or op['gatilho']
            payload["text"] += f"\n*{op['gatilho']}* - {mostrar}"

    # Envia
    try:
        requests.post(
            f"{EVO_API_URL}/message/sendText/{instancia}", 
            json=payload, 
            headers={"apikey": EVO_API_KEY}, 
            timeout=10
        )
        
        # Log
        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("INSERT INTO chat_logs (instancia, remote_jid, from_me, tipo) VALUES (%s, %s, TRUE, 'texto')", (instancia, numero))
            conn.commit()
            conn.close()
        except: pass
        
    except Exception as e:
        print(f"Erro envio: {e}")

# --- TABELA DE PREÇOS OFICIAL (Backend é a autoridade) ---
PRECOS_OFICIAIS = {
    "Básico": 9.90,
    "Pro": 29.90,
    "Enterprise": 49.90
}

@app.post("/publico/registrar")
async def registrar_publico(dados: dict):
    print(f"💰 Novo registro: {dados['nome']} | Plano: {dados['plano']}")
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # 1. Verifica duplicidade
        cur.execute("SELECT id FROM usuarios WHERE login = %s OR instancia_wa = %s", (dados['login'], dados['instancia']))
        if cur.fetchone():
            raise HTTPException(status_code=400, detail="Login ou Instância já existem.")

        # 2. CALCULA O VALOR REAL (Segurança)
        valor_base = PRECOS_OFICIAIS.get(dados['plano'], 99.90)
        valor_final = valor_base
        cupom_aplicado = None

        # 3. VERIFICA CUPOM
        if dados.get('cupom'):
            cupom_codigo = dados['cupom'].upper().strip()
            cur.execute("SELECT desconto_porcentagem FROM cupons WHERE codigo = %s AND ativo = TRUE", (cupom_codigo,))
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

        # --- NOVO: TRATAMENTO PARA CUPOM DE 100% (GRÁTIS) ---
        if valor_final <= 0:
            print("🎁 Cupom de 100% detectado! Liberando acesso direto...")
            
            # Insere já como ATIVO e com 30 dias de validade
            cur.execute("""
                INSERT INTO usuarios (nome_cliente, login, senha, instancia_wa, plano, valor_mensal, email, whatsapp, status_conta, data_vencimento, id_pagamento_mp) 
                VALUES (%s, %s, %s, %s, %s, 0.00, %s, %s, 'ativo', CURRENT_DATE + INTERVAL '30 days', 'CUPOM_100_OFF')
            """, (
                dados['nome'], dados['login'], dados['senha'], dados['instancia'], 
                dados['plano'], dados['email'], dados['whatsapp']
            ))
            conn.commit()
            
            # Opcional: Aqui você poderia já chamar a criação da instância na Evolution se quisesse
            
            conn.close()
            return {"status": "ativado_direto", "valor_final": 0.00}
        # ----------------------------------------------------

        # 4. Gera o Pagamento no Mercado Pago
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
        
        # --- BLOCO DE DEBUG DETALHADO ---
        if status_mp not in [200, 201]:
            print("❌ O MERCADO PAGO RECUSOU!")
            print(f"🔍 Motivo: {pagamento}")
            
            msg_erro = pagamento.get('message', 'Erro desconhecido no Mercado Pago')
            if 'cause' in pagamento and len(pagamento['cause']) > 0:
                msg_erro = pagamento['cause'][0].get('description', msg_erro)

            raise HTTPException(status_code=400, detail=f"Falha no Pagamento: {msg_erro}")
        # --------------------------------

        id_mp = str(pagamento['id'])
        qr_code = pagamento['point_of_interaction']['transaction_data']['qr_code']
        qr_code_base64 = pagamento['point_of_interaction']['transaction_data']['qr_code_base64']

        # 5. Salva no Banco como PENDENTE
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
        print(f"Erro: {e}")
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
                                      json={"webhook": {"enabled": True, "url": webhook_url, "events": ["MESSAGES_UPSERT"]}}, 
                                      headers={"apikey": EVO_API_KEY})
                        print("🚀 Instância criada automaticamente!")
                    except Exception as evo_err:
                        print(f"⚠️ Erro ao criar instância auto: {evo_err}")

                conn.close()

        return {"status": "ok"}
    except Exception as e:
        print(f"Erro Webhook MP: {e}")
        return {"status": "error"}


@app.post("/webhook/whatsapp")
async def receber_webhook(request: Request):
    try:
        body = await request.json()
        
        # Filtros Básicos
        evento = body.get("event", "")
        if evento and evento != "messages.upsert": return {"status": "ignored_event"}
        
        data = body.get("data", {})
        instancia = body.get("instance")
        key = data.get("key", {})
        remote_jid = key.get("remoteJid")
        from_me = key.get("fromMe", False)

        if from_me: return {"status": "ignored_me"} 

        # =================================================================
        # EXTRAÇÃO INTELIGENTE (TEXTO + MÍDIA) 📸 🎤
        # =================================================================
        msg_text = ""
        msg_type = data.get("messageType", "unknown")
        # Pega o objeto message com segurança (.get) para não dar erro se vier vazio
        message_content = data.get("message", {}) 
        
        # 1. TEXTOS COMUNS
        if msg_type == "conversation":
            msg_text = message_content.get("conversation", "")
        elif msg_type == "extendedTextMessage":
            msg_text = message_content.get("extendedTextMessage", {}).get("text", "")
        elif msg_type == "buttonsResponseMessage":
             msg_text = message_content.get("buttonsResponseMessage", {}).get("selectedDisplayText", "")
        elif msg_type == "listResponseMessage":
            msg_text = message_content.get("listResponseMessage", {}).get("title", "")
            
        # 2. IMAGENS (AQUI ESTÁ A MÁGICA 📸)
        elif msg_type == "imageMessage":
            img_data = message_content.get("imageMessage", {})
            # ADICIONE ESTE PRINT PARA DEBUGAR 👇
            print(f"🔍 DADOS DA IMAGEM: {img_data.keys()}") 
            # Isso vai mostrar no terminal se está vindo 'base64' ou só 'url'
            url = img_data.get("url")     # O link da imagem na web
            caption = img_data.get("caption", "") # A legenda
            
            # Se tiver URL, salvamos ela (pro Streamlit mostrar a foto)
            # Se não tiver URL, tentamos salvar a legenda.
            if url:
                msg_text = url 
            else:
                msg_text = caption if caption else "[Imagem Recebida]"

        # 3. ÁUDIOS (AQUI ESTÁ A MÁGICA 🎤)
        elif msg_type == "audioMessage":
            audio_data = message_content.get("audioMessage", {})
            url = audio_data.get("url")
            # Se tiver URL, salva. Senão avisa.
            msg_text = url if url else "[Áudio Recebido]"

        elif msg_type == "stickerMessage":
            msg_text = "[Figurinha]"
        # =================================================================

        # Se for mensagem vazia e não for mídia conhecida, ignora
        if not msg_text: return {"status": "no_text"}

        # Pega o Nome do Cliente (PushName)
        push_name = data.get("pushName") or "Cliente WhatsApp"

        print(f"📩 [{instancia}] {push_name} ({remote_jid}): {msg_text}")
        msg_clean = msg_text.strip()
        msg_lower = msg_clean.lower()

        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # =================================================================
        # 💾 GRAVA NO SEU BANCO LOCAL
        # =================================================================
        try:
            # Descobre se a mensagem é MINHA (do atendente/robô) ou do CLIENTE
            # (Já pegamos key e from_me lá em cima)

            # Insere na tabela 'historico_mensagens'
            # Dica: O tipo 'texto' aqui é genérico. O Streamlit vai decidir se é foto pelo conteúdo (http...)
            cur.execute("""
                INSERT INTO historico_mensagens (instancia, remote_jid, from_me, tipo, conteudo)
                VALUES (%s, %s, %s, 'texto', %s)
            """, (instancia, remote_jid, from_me, msg_text))
            
            conn.commit() 
            # print("✅ Histórico gravado") 

        except Exception as e:
            print(f"❌ Erro ao gravar histórico local: {e}")
            conn.rollback()

        # ==========================================================
        # 🆕 CRM AUTOMÁTICO
        # ==========================================================
        try:
            cur.execute("SELECT id FROM clientes_finais WHERE instancia = %s AND telefone = %s", (instancia, remote_jid))
            cliente_existente = cur.fetchone()
            
            if not cliente_existente:
                print(f"🆕 Novo Lead Detectado: {push_name}. Salvando no CRM...")
                cur.execute("""
                    INSERT INTO clientes_finais (instancia, nome, telefone, dia_vencimento, etiquetas)
                    VALUES (%s, %s, %s, %s, %s)
                """, (instancia, push_name, remote_jid, 1, 'captura_automatica'))
                conn.commit()
        except Exception as e_crm:
            print(f"⚠️ Erro CRM: {e_crm}")
            conn.rollback()

        # 📝 SALVA LOG (Chat Logs antigos, se ainda usar)
        try:
            cur.execute("INSERT INTO chat_logs (instancia, remote_jid, from_me, tipo) VALUES (%s, %s, FALSE, 'texto')", (instancia, remote_jid))
            conn.commit()
        except: pass

        # ==========================================================
        # 🚦 1. CHECAGEM DE TRANSBORDO (ATENDIMENTO HUMANO)
        # ==========================================================
        cur.execute("SELECT id FROM atendimentos_ativos WHERE instancia = %s AND remote_jid = %s", (instancia, remote_jid))
        esta_em_atendimento = cur.fetchone()

        if esta_em_atendimento:
            if msg_lower in ["/encerrar", "/voltar", "/bot"]:
                cur.execute("DELETE FROM atendimentos_ativos WHERE instancia = %s AND remote_jid = %s", (instancia, remote_jid))
                conn.commit()
                enviar_mensagem_smart(instancia, remote_jid, "🤖 Robô reativado! Estou de volta.")
                conn.close()
                return {"status": "bot_reactivated"}
            else:
                conn.close()
                return {"status": "human_mode"}

        # ==========================================================
        # 🚨 2. GATILHO PARA CHAMAR HUMANO
        # ==========================================================
        palavras_transbordo = ["atendente", "falar com", "human", "suporte", "pesso"]
        if any(p in msg_lower for p in palavras_transbordo):
            try:
                cur.execute("INSERT INTO atendimentos_ativos (instancia, remote_jid) VALUES (%s, %s)", (instancia, remote_jid))
                conn.commit()
            except: pass
            
            enviar_mensagem_smart(instancia, remote_jid, "🔕 *Robô Pausado.* Um atendente humano foi notificado.\n_(Aguarde ou digite /voltar)_")
            conn.close()
            return {"status": "handed_off"}

        # ==========================================================
        # 🤖 3. LÓGICA DO ROBÔ (MENUS)
        # ==========================================================

        # A. RESET
        if msg_lower in ["inicio", "início", "menu", "home", "oi", "ola", "olá"]:
            if remote_jid in user_state: del user_state[remote_jid]
            cur.execute("SELECT * FROM respostas_automacao WHERE gatilho = 'default' AND instancia = %s", (instancia,))
            default = cur.fetchone()
            if default: enviar_mensagem_smart(instancia, remote_jid, default['resposta'], default['id'])
            conn.close()
            return {"status": "home"}

        if msg_lower in ["sair", "encerrar", "tchau"]:
            if remote_jid in user_state: del user_state[remote_jid]
            requests.post(f"{EVO_API_URL}/message/sendText/{instancia}", 
                          json={"number": remote_jid, "text": "👋 Até logo!"}, headers={"apikey": EVO_API_KEY})
            conn.close()
            return {"status": "end"}

        # B. VOLTAR
        if msg_lower == "voltar":
            current_id = user_state.get(remote_jid)
            if current_id:
                cur.execute("SELECT id_pai FROM respostas_automacao WHERE id = %s", (current_id,))
                res_pai = cur.fetchone()
                if res_pai and res_pai['id_pai']:
                    novo_pai = res_pai['id_pai']
                    user_state[remote_jid] = novo_pai 
                    cur.execute("SELECT * FROM respostas_automacao WHERE id = %s", (novo_pai,))
                    item_pai = cur.fetchone()
                    enviar_mensagem_smart(instancia, remote_jid, item_pai['resposta'], novo_pai)
                else:
                    if remote_jid in user_state: del user_state[remote_jid]
                    cur.execute("SELECT * FROM respostas_automacao WHERE gatilho = 'default' AND instancia = %s", (instancia,))
                    default = cur.fetchone()
                    if default: enviar_mensagem_smart(instancia, remote_jid, default['resposta'], None)
            else:
                cur.execute("SELECT * FROM respostas_automacao WHERE gatilho = 'default' AND instancia = %s", (instancia,))
                default = cur.fetchone()
                if default: enviar_mensagem_smart(instancia, remote_jid, default['resposta'], None)
            
            conn.close()
            return {"status": "back"}

        # C. BUSCA INTELIGENTE
        id_pai_atual = user_state.get(remote_jid)
        res = None
        
        if id_pai_atual:
            cur.execute("SELECT * FROM respostas_automacao WHERE instancia = %s AND gatilho ILIKE %s AND id_pai = %s", (instancia, msg_clean, id_pai_atual))
            res = cur.fetchone()
        else:
            cur.execute("SELECT * FROM respostas_automacao WHERE instancia = %s AND gatilho ILIKE %s AND id_pai IS NULL", (instancia, msg_clean))
            res = cur.fetchone()

        # D. RESPOSTA
        if res:
            cur.execute("SELECT id FROM respostas_automacao WHERE id_pai = %s LIMIT 1", (res['id'],))
            tem_sub_menus = cur.fetchone()

            if tem_sub_menus: user_state[remote_jid] = res['id']
            else: 
                if remote_jid in user_state: del user_state[remote_jid]

            enviar_mensagem_smart(instancia, remote_jid, res['resposta'], res['id'])
            
            # Mídia (Envia arquivo se tiver no cadastro da resposta)
            if res.get('url_midia') and len(res['url_midia']) > 10:
                try:
                    nome_arquivo = res['url_midia'].split("/")[-1]
                    caminho_local = f"uploads/{nome_arquivo}"
                    if os.path.exists(caminho_local):
                        with open(caminho_local, "rb") as f:
                            b64 = base64.b64encode(f.read()).decode('utf-8')
                        ext = nome_arquivo.split('.')[-1].lower()
                        mime = "image/jpeg"
                        tipo = "image"
                        if ext == "pdf": mime="application/pdf"; tipo="document"
                        elif ext == "mp4": mime="video/mp4"; tipo="video"
                        
                        requests.post(f"{EVO_API_URL}/message/sendMedia/{instancia}",
                                      json={"number": remote_jid, "media": b64, "mediatype": tipo, "mimetype": mime, "caption": res['resposta'], "fileName": nome_arquivo},
                                      headers={"apikey": EVO_API_KEY})
                except Exception as e_midia:
                    print(f"Erro mídia: {e_midia}")
        else:
            # Não entendeu
            if id_pai_atual:
                enviar_mensagem_smart(instancia, remote_jid, "❌ Opção inválida.", id_pai_atual)
            else:
                cur.execute("SELECT * FROM respostas_automacao WHERE gatilho = 'default' AND instancia = %s", (instancia,))
                default = cur.fetchone()
                if default: enviar_mensagem_smart(instancia, remote_jid, default['resposta'], None)
        
        cur.close()
        conn.close()
        return {"status": "processed"}

    except Exception as e:
        print(f"💥 ERRO CRÍTICO: {e}")
        return {"status": "error"}

# --- ROTA DE MÉTRICAS PARA O DASHBOARD ---
@app.get("/metricas/{instancia}")
def obter_metricas(instancia: str):
    print(f"📊 Calculando métricas para: '{instancia}'") # Debug
    
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # 1. TOTAL DE MENSAGENS
        cur.execute("SELECT COUNT(*) FROM chat_logs WHERE instancia = %s AND from_me = TRUE", (instancia,))
        total_msgs = cur.fetchone()['count']
        print(f"   -> Msgs Bot: {total_msgs}")

        # 2. TOTAL DE CLIENTES
        cur.execute("SELECT COUNT(*) FROM clientes_finais WHERE instancia = %s", (instancia,))
        total_clientes = cur.fetchone()['count']
        print(f"   -> Clientes: {total_clientes}")

        # 3. NOVOS (Tenta com data_cadastro, se falhar usa 0)
        novos_mes = 0
        try:
            hoje = datetime.now()
            primeiro_dia = hoje.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            cur.execute("""
                SELECT COUNT(*) FROM clientes_finais 
                WHERE instancia = %s AND data_cadastro >= %s
            """, (instancia, primeiro_dia))
            novos_mes = cur.fetchone()['count']
        except Exception as e:
            print(f"⚠️ Erro ao calcular novos (falta coluna data_cadastro?): {e}")
            conn.rollback() # Destrava o banco

        # 4. GATILHOS
        cur.execute("SELECT COUNT(*) FROM respostas_automacao WHERE instancia = %s", (instancia,))
        total_gatilhos = cur.fetchone()['count']

        # 5. GRÁFICO DIÁRIO
        data_limite = datetime.now() - timedelta(days=7)
        cur.execute("""
            SELECT DATE(data_hora) as dia, COUNT(*) as qtd 
            FROM chat_logs 
            WHERE instancia = %s AND data_hora >= %s 
            GROUP BY dia ORDER BY dia
        """, (instancia, data_limite))
        dados_grafico = cur.fetchall()
        grafico_fmt = [{"Data": str(d['dia']), "Mensagens": d['qtd']} for d in dados_grafico]

        # 6. ETIQUETAS
        cur.execute("""
            SELECT etiquetas, COUNT(*) as qtd 
            FROM clientes_finais 
            WHERE instancia = %s 
            GROUP BY etiquetas
        """, (instancia,))
        dados_etiquetas = cur.fetchall()
        
        etiquetas_fmt = []
        for item in dados_etiquetas:
            nome_tag = item['etiquetas'] if item['etiquetas'] else "Sem Etiqueta"
            etiquetas_fmt.append({"Etiqueta": nome_tag, "Quantidade": item['qtd']})

        conn.close()
        
        return {
            "total_mensagens_bot": total_msgs,
            "total_clientes": total_clientes,
            "novos_clientes_mes": novos_mes,
            "total_gatilhos": total_gatilhos,
            "grafico_mensagens": grafico_fmt,
            "grafico_etiquetas": etiquetas_fmt
        }
        
    except Exception as e:
        print(f"💥 ERRO GERAL MÉTRICAS: {e}")
        return {"total_clientes": 0, "erro": str(e)}
    
# ==============================================================================
# 3. ROTAS DE CADASTRO E LOGIN (NECESSÁRIAS PARA O PAINEL)
# ==============================================================================

# --- CONFIGURAÇÃO DOS LIMITES ---
LIMITES = {
    "Básico": {"max_gatilhos": 5, "permite_midia": False},
    "Pro": {"max_gatilhos": 99999, "permite_midia": True},
    "Enterprise": {"max_gatilhos": 99999, "permite_midia": True}
}

@app.post("/salvar")
async def salvar_gatilho(item: Gatilho):
    try:
        conn = get_connection()
        cur = conn.cursor()

        # 1. DESCOBRIR O PLANO DO CLIENTE
        cur.execute("SELECT plano FROM usuarios WHERE instancia_wa = %s", (item.instancia,))
        user_data = cur.fetchone()
        
        # Se não achar o plano, assume o Básico por segurança
        plano_atual = user_data[0] if user_data and user_data[0] else "Básico"
        regras = LIMITES.get(plano_atual, LIMITES["Básico"])

        # 2. VERIFICAR SE O GATILHO JÁ EXISTE (Para saber se é Edição ou Criação)
        cur.execute("""
            SELECT id FROM respostas_automacao 
            WHERE instancia=%s AND gatilho=%s AND id_pai IS NOT DISTINCT FROM %s
        """, (item.instancia, item.gatilho, item.id_pai))
        existe = cur.fetchone()

        # 3. BLOQUEIO DE MÍDIA (Se tentar salvar mídia no plano Básico)
        if item.url_midia and not regras["permite_midia"]:
             # Se for edição e já tinha mídia, deixa passar (ou bloqueia, você decide). 
             # Aqui vou bloquear qualquer tentativa de salvar mídia nova.
             raise HTTPException(status_code=403, detail=f"O plano {plano_atual} não permite envio de mídia (Áudio/Imagem/Vídeo). Faça um Upgrade!")

        # 4. BLOQUEIO DE QUANTIDADE (Só verifica se for NOVO cadastro)
        if not existe:
            cur.execute("SELECT COUNT(*) FROM respostas_automacao WHERE instancia = %s", (item.instancia,))
            qtd_atual = cur.fetchone()[0]
            
            if qtd_atual >= regras["max_gatilhos"]:
                raise HTTPException(status_code=403, detail=f"Você atingiu o limite de {regras['max_gatilhos']} gatilhos do plano {plano_atual}. Contrate o Pro!")

        # --- SE PASSOU NOS TESTES, GRAVA NO BANCO ---
        if existe:
             # UPDATE
             cur.execute("""
                UPDATE respostas_automacao SET 
                resposta=%s, tipo_midia=%s, url_midia=%s, id_pai=%s, titulo_menu=%s, categoria=%s
                WHERE id=%s
             """, (item.resposta, item.tipo_midia, item.url_midia, item.id_pai, item.titulo_menu, item.categoria, existe[0]))
        else:
            # INSERT
            cur.execute("""
                INSERT INTO respostas_automacao 
                (instancia, gatilho, resposta, titulo_menu, categoria, tipo_midia, url_midia, id_pai) 
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (item.instancia, item.gatilho, item.resposta, item.titulo_menu, item.categoria, item.tipo_midia, item.url_midia, item.id_pai))
        
        conn.commit()
        conn.close()
        return {"status": "sucesso"}

    except HTTPException as he:
        raise he # Repassa o erro de permissão para o painel
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


# --- 3. RENOVAÇÃO / UPGRADE (Cliente Logado) ---
@app.post("/pagamento/gerar")
async def gerar_pagamento_usuario(dados: dict):
    # dados espera: { "user_id": 1, "plano": "Pro", "valor": 99.90, "cupom": "CODIGO" }
    print(f"🔄 Processando renovação para User ID {dados['user_id']}")
    
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        
        # Pega dados do usuário
        cur.execute("SELECT * FROM usuarios WHERE id = %s", (dados['user_id'],))
        user = cur.fetchone()
        
        # Define valor base (Segurança: idealmente pegaria da tabela PRECOS_OFICIAIS, mas vamos usar o enviado por enquanto)
        valor_final = float(dados['valor'])
        cupom_aplicado_txt = ""

        # --- LÓGICA DO CUPOM ---
        if dados.get('cupom'):
            codigo = dados['cupom'].strip().upper()
            cur.execute("SELECT desconto_porcentagem FROM cupons WHERE codigo = %s AND ativo = TRUE", (codigo,))
            res_cupom = cur.fetchone()
            
            if res_cupom:
                desconto = res_cupom['desconto_porcentagem']
                desconto_reais = (valor_final * desconto) / 100
                valor_final = valor_final - desconto_reais
                cupom_aplicado_txt = f"- Cupom {codigo} ({desconto}%)"
                print(f"🎟️ Cupom {codigo} aplicado na renovação!")
            else:
                print(f"⚠️ Cupom de renovação inválido: {codigo}")
        
        valor_final = round(valor_final, 2)
        # -----------------------

        # SE VALOR FOR ZERO (100% OFF)
        if valor_final <= 0:
            print("🎁 Renovação Gratuita (100% OFF)")
            # Renova por 30 dias a partir de HOJE (ou soma a data atual se quiser acumular, aqui vamos resetar pra 30 dias)
            cur.execute("""
                UPDATE usuarios SET 
                status_conta='ativo', 
                data_vencimento = CURRENT_DATE + INTERVAL '30 days', 
                plano=%s,
                valor_mensal=%s
                WHERE id=%s
            """, (dados['plano'], 0.00, user['id']))
            conn.commit()
            conn.close()
            return {"status": "aprovado_direto", "mensagem": "Plano renovado com sucesso (100% OFF)!"}

        # SE TIVER VALOR, GERA PIX NO MERCADO PAGO
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
             
        # Salva o ID do pagamento novo para o Webhook reconhecer depois
        # Importante: Atualizamos o valor_mensal para o novo valor com desconto
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
                      json={"webhook": {"enabled": True, "url": webhook_url, "events": ["MESSAGES_UPSERT"]}}, 
                      headers={"apikey": EVO_API_KEY})
    except Exception as e:
        print(f"⚠️ Erro Evolution: {e}")

    # --- PASSO 3: SALVAR NO BANCO (ATUALIZADO) ---
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Agora salvamos whatsapp e email também
        cur.execute("""
            INSERT INTO usuarios (login, senha, instancia_wa, nome_cliente, plano, valor_mensal, data_vencimento, whatsapp, email) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
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

# --- ROTAS DE TRANSBORDO ---
@app.get("/atendimentos/{instancia}")
def listar_atendimentos(instancia: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM atendimentos_ativos WHERE instancia = %s ORDER BY data_inicio DESC", (instancia,))
    dados = cur.fetchall()
    conn.close()
    
    # Converte datetime para string
    for d in dados:
        d['data_inicio'] = str(d['data_inicio'])
    return dados

@app.delete("/atendimentos/{id}")
def encerrar_atendimento(id: int):
    conn = get_connection()
    cur = conn.cursor()
    # Pega os dados antes de apagar para mandar mensagem de aviso
    cur.execute("SELECT instancia, remote_jid FROM atendimentos_ativos WHERE id = %s", (id,))
    item = cur.fetchone()
    
    if item:
        instancia, remote_jid = item
        # Apaga
        cur.execute("DELETE FROM atendimentos_ativos WHERE id = %s", (id,))
        conn.commit()
        
        # Opcional: Avisa o cliente
        enviar_mensagem_smart(instancia, remote_jid, "✅ O atendimento humano foi finalizado. O robô assumiu novamente.")
        
    conn.close()
    return {"status": "ok"}

# --- ROTA: LER HISTÓRICO LOCAL (CORRIGIDA) ---
@app.get("/chat/local/{instancia}/{remote_jid}")
def ler_historico_local(instancia: str, remote_jid: str):
    # Garante o formato do JID
    jid_busca = remote_jid if "@" in remote_jid else f"{remote_jid}@s.whatsapp.net"
    
    # AQUI ESTAVA O ERRO: O nome certo é get_connection()
    conn = get_connection() 
    cursor = conn.cursor()
    try:
        # Busca as últimas 50 mensagens ordenadas corretamente
        cursor.execute("""
            SELECT from_me, conteudo, data_hora 
            FROM historico_mensagens 
            WHERE instancia = %s AND remote_jid = %s
            ORDER BY data_hora DESC 
            LIMIT 50
        """, (instancia, jid_busca))
        
        msgs = []
        for row in cursor.fetchall():
            msgs.append({
                "fromMe": row[0],
                "text": row[1],
                "timestamp": row[2]
            })
        
        # Inverte para mostrar cronológico (Antigo -> Novo) na tela
        return msgs[::-1] 
    except Exception as e:
        return {"erro": str(e)}
    finally:
        cursor.close()
        conn.close()


# --- CLASSE DE DADOS ---
class MsgManual(BaseModel):
    instancia: str
    remote_jid: str
    texto: str

# --- ROTA: SALVAR MENSAGEM MANUALMENTE (DO ATENDENTE) ---
@app.post("/chat/salvar_manual")
def salvar_mensagem_manual(dados: MsgManual):
    # Garante o JID
    jid = dados.remote_jid if "@" in dados.remote_jid else f"{dados.remote_jid}@s.whatsapp.net"
    
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO historico_mensagens (instancia, remote_jid, from_me, tipo, conteudo)
            VALUES (%s, %s, %s, 'texto', %s)
        """, (dados.instancia, jid, True, dados.texto)) # True = Mensagem Minha
        
        conn.commit()
        return {"status": "salvo"}
    except Exception as e:
        return {"erro": str(e)}
    finally:
        cursor.close()
        conn.close()


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
                requests.post(f"{EVO_API_URL}/message/sendText/{instancia}", json=payload, headers={"apikey": EVO_API_KEY})
            
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
        cur.execute("""
            SELECT id, nome, usuario, instancia_vinculada 
            FROM atendentes 
            WHERE usuario = %s AND senha = %s AND ativo = TRUE
        """, (d.usuario, d.senha))
        user = cur.fetchone()
        
        if user:
            # Retorna estrutura parecida com a do Admin para o front não quebrar
            return {
                "autenticado": True,
                "tipo": "funcionario", # Flag importante!
                "nome": user['nome'],
                "instancia": user['instancia_vinculada'],
                "id_atendente": user['id']
            }
        else:
            return JSONResponse(status_code=401, content={"erro": "Login ou senha inválidos"})
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
    
    # ⚠️ AQUI ESTAVA O ERRO: Garantindo que a porta seja 8000 (seu backend)
    # Se você subir para um servidor (VPS), troque isso pelo seu domínio (ex: https://api.suaempresa.com/webhook/whatsapp)
    webhook_url = "http://127.0.0.1:8000/webhook/whatsapp" 

    print(f"🔗 Apontando Webhook para: {webhook_url}")

    # Payload "Blindado"
    payload = {
        "reject_call": False,
        "always_online": True,
        "read_messages": True,
        "read_status": False,
        "webhook": {
            "enabled": True,
            "url": webhook_url,     # <--- Agora vai certo (Porta 8000)
            "download_media": True, # Baixa mídia
            "base64": True,         # Manda como Base64
            "upload_media": True,
            "auto_download": True,
            "byEvents": False,
            "events": [
                "MESSAGES_UPSERT",
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
        # 1. Configura Webhook (V1)
        requests.post(f"{EVO_URL}/webhook/set/{instancia}", 
                      json={"webhook": payload["webhook"]}, headers=headers)
        
        # 2. Configura Geral (V2)
        requests.post(f"{EVO_URL}/instance/settings/{instancia}", 
                      json=payload, headers=headers)

        # 3. Reinicia para aplicar
        print(f"🔄 [AUTO] Reiniciando {instancia}...")
        requests.post(f"{EVO_URL}/instance/restart/{instancia}", headers=headers)
        
        return {"status": "sucesso", "msg": "Configurado para Porta 8000!"}

    except Exception as e:
        print(f"❌ Erro config auto: {e}")
        return JSONResponse(status_code=500, content={"erro": str(e)})