import streamlit as st
import requests
import base64
import time, datetime
import pandas as pd 
from io import BytesIO
from PIL import Image
from streamlit_option_menu import option_menu
import graphviz

# =====================================================
# CONFIGURAÇÃO E ESTILO
# =====================================================
st.set_page_config(
    page_title="Agil | Automação Inteligente",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =====================================================
# ESTILO: ESCONDER MARCAS DO STREAMLIT (WHITELABEL)
# =====================================================
hide_streamlit_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            .block-container {
                padding-top: 1rem;
                padding-bottom: 0rem;
            }
            </style>
            """
st.markdown(hide_streamlit_style, unsafe_allow_html=True)

st.markdown("""
    <style>
    .metric-card {
        background-color: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 10px;
        padding: 20px;
        box-shadow: 2px 2px 10px rgba(0,0,0,0.05);
        text-align: center;
    }
    .metric-label { font-size: 14px; color: #888; margin-bottom: 5px; }
    .metric-value { font-size: 28px; font-weight: bold; color: #333; }
    .status-ok { color: #28a745; font-weight: bold; }
    .status-err { color: #dc3545; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# Configurações de API
API_URL = "http://127.0.0.1:8000" # <-- AJUSTADO PARA A PORTA DO SEU BACKEND
EVO_URL = "http://127.0.0.1:8080"
EVO_API_KEY = "159632"

HEADERS_EVO = {
    "apikey": EVO_API_KEY,
    "Content-Type": "application/json"
}

# =====================================================
# FUNÇÕES ÚTEIS (Cole logo no início do arquivo)
# =====================================================
def verificar_status_whatsapp(instancia):
    """
    Verifica se a instância está conectada na Evolution API.
    Retorna True se estiver "open" (conectado).
    """
    try:
        # Tenta conectar direto na Evolution (ou use sua rota do backend se tiver)
        # Ajuste o URL abaixo se sua Evolution não estiver na porta 8080
        url_evo = "http://127.0.0.1:8080" 
        headers_evo = {"apikey": "159632"} # Sua API KEY da Evolution
        
        res = requests.get(f"{url_evo}/instance/connectionState/{instancia}", headers=headers_evo, timeout=2)
        
        if res.status_code == 200:
            # A estrutura pode variar levemente dependendo da versão (v1 ou v2)
            dados = res.json()
            estado = dados.get("instance", {}).get("state") or dados.get("state")
            return estado == "open"
        return False
    except:
        return False
    
# =====================================================
# FUNÇÃO DE LOGIN (CORRIGIDA E COM DEBUG 🕵️‍♂️)
# =====================================================
def login_sistema():
    if "pagina_atual" not in st.session_state:
        st.session_state.pagina_atual = "login"

    # CSS (Mantendo o visual bonito)
    st.markdown("""
    <style>
    .stApp {
        background-image: linear-gradient(rgba(0, 0, 0, 0.7), rgba(0, 0, 0, 0.8)), 
        url("https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop");
        background-size: cover; background-position: center; background-attachment: fixed;
    }
    h1, h2, h3, h4, h5, p, label { color: #FFFFFF !important; }
    .stTextInput label p { font-size: 14px !important; }
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: rgba(20, 20, 20, 0.9);
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 12px;
        padding: 30px;
    }
    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

    if st.session_state.pagina_atual == "login":
        st.write("") 
        st.write("") 

        c_esq, c_centro, c_dir = st.columns([1, 1.2, 1])

        with c_centro:
            # Logo
            cl_1, cl_2, cl_3 = st.columns([1, 1, 1])
            with cl_2:
                try: st.image("logo.png", width=120)
                except: st.markdown("# 🚀")

            st.markdown("<h2 style='text-align: center; margin-top: -10px;'>Acesso ao Sistema</h2>", unsafe_allow_html=True)
            
            with st.container(border=True):
                login_input = st.text_input("Usuário", placeholder="admin")
                senha_input = st.text_input("Senha", type="password", placeholder="••••••")
                
                # Checkbox para ver o erro (Se precisar debugar)
                debug_mode = st.checkbox("Mostrar erros técnicos (Debug)", value=False)
                
                st.write("")
                
                if st.button("ENTRAR", type="primary", use_container_width=True):
                    if not login_input or not senha_input:
                        st.warning("Preencha todos os campos.")
                    else:
                        with st.spinner("Autenticando..."):
                            sucesso = False
                            
                            # =================================================
                            # TENTATIVA 1: ADMIN (Rota Antiga)
                            # =================================================
                            try:
                                # CORREÇÃO AQUI: Mudamos 'email' de volta para 'login'
                                payload_adm = {"login": login_input, "senha": senha_input}
                                
                                r_adm = requests.post(f"{API_URL}/login", json=payload_adm, timeout=5)
                                
                                if debug_mode: st.code(f"Admin: {r_adm.status_code} - {r_adm.text}")

                                if r_adm.status_code == 200:
                                    # Pega o objeto 'usuario' de dentro da resposta
                                    dados = r_adm.json().get('usuario', {})
                                    
                                    if dados.get("status_conta") == "ativo" or dados.get("status_conta") is None:
                                        st.session_state.user_info = dados
                                        st.session_state.user_info['tipo_acesso'] = 'admin'
                                        st.session_state.autenticado = True
                                        sucesso = True
                                    else:
                                        st.error("⚠️ Conta inativa.")
                                        sucesso = True # Impede de tentar logar como func
                            except Exception as e:
                                if debug_mode: st.error(f"Erro Conexão Admin: {e}")

                            # =================================================
                            # TENTATIVA 2: EQUIPE (Rota Nova)
                            # =================================================
                            if not sucesso:
                                try:
                                    payload_func = {"usuario": login_input, "senha": senha_input}
                                    
                                    r_func = requests.post(f"{API_URL}/equipe/login", json=payload_func, timeout=5)
                                    
                                    if debug_mode: st.code(f"Equipe: {r_func.status_code} - {r_func.text}")

                                    if r_func.status_code == 200:
                                        dados = r_func.json()
                                        
                                        # Padroniza dados
                                        dados['instancia_wa'] = dados.get('instancia') or dados.get('instancia_vinculada')
                                        dados['nome_cliente'] = dados.get('nome')
                                        dados['tipo_acesso'] = 'funcionario'
                                        
                                        st.session_state.user_info = dados
                                        st.session_state.autenticado = True
                                        sucesso = True
                                except Exception as e:
                                    if debug_mode: st.error(f"Erro Conexão Equipe: {e}")

                            # =================================================
                            # RESULTADO
                            # =================================================
                            if sucesso and st.session_state.autenticado:
                                st.toast(f"Bem-vindo, {st.session_state.user_info.get('nome_cliente')}!")
                                time.sleep(1)
                                st.rerun()
                            elif not sucesso:
                                st.error("❌ Usuário ou senha incorretos.")

                st.divider()
                if st.button("Criar Nova Conta (Admin)", use_container_width=True):
                    st.session_state.pagina_atual = "registro"
                    st.rerun()
    
    elif st.session_state.pagina_atual == "registro":
        if 'registro_sistema' in globals(): registro_sistema()
        else:
            st.info("Tela de registro.")
            if st.button("Voltar"): 
                st.session_state.pagina_atual = "login"
                st.rerun()



    # ==========================================================
    # 📝 TELA DE REGISTRO (PREÇO DINÂMICO E VANTAGENS)
    # ==========================================================
    elif st.session_state.pagina_atual == "registro":
        st.write("") 

        c1, c2, c3 = st.columns([1, 2, 1]) 
        
        with c2:
            with st.container(border=True):
                
                # --- FASE 1: FORMULÁRIO ---
                if "dados_pix" not in st.session_state:
                    st.markdown("### ✨ Crie sua conta")
                    
                    # --- CONFIGURAÇÃO DOS PLANOS (TEXTO CORRIGIDO) ---
                    detalhes_planos = {
                        "Básico": {
                            "valor": 19.90,
                            "itens": [
                                "🤖 Cria até 5 Menus/Gatilhos", 
                                "📝 CRM Básico", 
                                "❌ Sem Disparos em Massa"
                            ]
                        },
                        "Pro": {
                            "valor": 39.90,
                            "itens": [
                                "🤖 Cria até 10 Menus/Gatilhos", 
                                "🚀 Disparos em Massa", 
                                "📊 CRM Avançado (Funil)"
                            ]
                        },
                        "Enterprise": {
                            "valor": 49.90,
                            "itens": [
                                "🤖 Menus e Gatilhos Ilimitados", 
                                "🚀 Disparos em Massa", 
                                "💎 Suporte Prioritário"
                            ]
                        }
                    }
                    
                    # SELEÇÃO (Fora do Form para atualizar instantaneamente)
                    cp1, cp2 = st.columns([1.5, 1])
                    with cp1:
                        plano_selecionado = st.selectbox("Escolha o Plano", list(detalhes_planos.keys()), index=1)
                    
                    # Pega dados do plano atual
                    info_atual = detalhes_planos[plano_selecionado]
                    valor_original = info_atual['valor']
                    itens_plano = info_atual['itens']
                    
                    with cp2:
                        st.markdown(f"<br><h3 style='text-align:right; color:#4cd137 !important; margin:0'>R$ {valor_original:.2f}</h3>", unsafe_allow_html=True)
                        st.markdown(f"<p style='text-align:right; font-size:12px; margin:0'>mensal</p>", unsafe_allow_html=True)
                    
                    # MOSTRA VANTAGENS
                    st.markdown("---")
                    col_v1, col_v2, col_v3 = st.columns(3)
                    for i, item in enumerate(itens_plano):
                        col_usada = [col_v1, col_v2, col_v3][i % 3]
                        col_usada.markdown(f"<div class='vantagem-item'>{item}</div>", unsafe_allow_html=True)
                    st.markdown("---")

                    # --- FORMULÁRIO DE DADOS ---
                    with st.form("form_reg"):
                        c_form1, c_form2 = st.columns(2)
                        with c_form1:
                            nome = st.text_input("Nome Completo")
                            zap = st.text_input("WhatsApp (com DDD)")
                            instancia = st.text_input("Nome da Instância (Ex: loja)")
                        with c_form2:
                            email = st.text_input("E-mail")
                            login = st.text_input("Login desejado")
                            senha = st.text_input("Crie uma Senha", type="password")
                        
                        cupom = st.text_input("🎟️ Cupom de Desconto", placeholder="Tem um código? Digite aqui")
                        
                        st.write("")

                        if st.form_submit_button("Gerar Pix e Criar Conta", type="primary", use_container_width=True):
                            if not (nome and email and login and senha and instancia):
                                st.warning("⚠️ Preencha todos os campos obrigatórios!")
                            else:
                                payload = {
                                    "nome": nome, "email": email, "whatsapp": zap,
                                    "login": login, "instancia": instancia, "senha": senha,
                                    "plano": plano_selecionado, 
                                    "cupom": cupom
                                }
                                
                                try:
                                    with st.spinner("Gerando Pix..."):
                                        res = requests.post(f"{API_URL}/publico/registrar", json=payload, timeout=20) # Timeout alto
                                        
                                        if res.status_code == 200:
                                            dados_res = res.json()
                                            st.session_state.dados_pix = dados_res
                                            
                                            valor_final = dados_res.get('valor_final')
                                            if valor_final and valor_final < valor_original:
                                                st.toast(f"🎉 Cupom aplicado! R${valor_final}", icon="🤑")
                                            
                                            time.sleep(1)
                                            st.rerun()
                                        else:
                                            detalhe = res.json().get('detail', res.text)
                                            st.error(f"Erro: {detalhe}")
                                            
                                except Exception as e:
                                    st.error(f"Erro de conexão: {e}")

                    if st.button("⬅️ Voltar ao Login", type="secondary", use_container_width=True):
                        st.session_state.pagina_atual = "login"
                        st.rerun()

                # --- FASE 2: TELA DO QR CODE ---
                else:
                    st.success("✅ Conta criada com sucesso!")
                    st.markdown("<p style='text-align:center'>Faça o pagamento para liberar seu acesso imediatamente.</p>", unsafe_allow_html=True)
                    
                    pix_data = st.session_state.dados_pix
                    val_final = pix_data.get('valor_final')
                    
                    if val_final:
                        st.markdown(f"<h1 style='text-align: center; color: #4cd137 !important;'>R$ {val_final:.2f}</h1>", unsafe_allow_html=True)

                    c_qr1, c_qr2, c_qr3 = st.columns([1, 2, 1])
                    with c_qr2:
                        try:
                            # Decodifica base64 para mostrar a imagem
                            img_data = base64.b64decode(pix_data['qr_base64'])
                            st.image(BytesIO(img_data), caption="Escaneie no App do Banco", use_container_width=True)
                        except:
                            st.warning("QR Code visual indisponível.")

                    st.text_area("Copia e Cola:", value=pix_data['qr_code'])
                    st.info("ℹ️ Após pagar, aguarde 10 segundos e clique no botão abaixo.")
                    
                    if st.button("🚀 Já Paguei! Acessar Sistema", type="primary", use_container_width=True):
                        del st.session_state.dados_pix
                        st.session_state.pagina_atual = "login"
                        st.rerun()
# =====================================================
# FUNÇÃO AUXILIAR: CONFIGURAÇÃO AUTOMÁTICA ⚙️
# =====================================================
def configurar_instancia_auto(nome_instancia):
    """
    Chama o backend para forçar a configuração de Mídia e Webhook.
    O cliente não vê isso acontecendo, é silencioso.
    """
    try:
        # Chama a rota inteligente que criamos no main.py
        # Ela ativa: Download de Mídia + Webhook + Leitura de Msg
        requests.post(f"{API_URL}/instance/configurar/{nome_instancia}", timeout=5)
        return True
    except Exception as e:
        print(f"Erro ao configurar auto: {e}")
        return False

# =====================================================
# TELA DE GESTÃO DE EQUIPE (Adicione isso no seu código)
# =====================================================
def tela_gestao_equipe():
    st.header("👥 Gestão de Equipe")
    
    if 'user_info' not in st.session_state:
        st.error("Sessão inválida.")
        return
        
    u = st.session_state.user_info
    instancia = u.get('instancia_wa')
    
    # 1. LISTAGEM DA EQUIPE
    try:
        # Busca a lista no backend
        res = requests.get(f"{API_URL}/equipe/listar/{instancia}")
        equipe = res.json() if res.status_code == 200 else []
    except: equipe = []

    if equipe:
        st.info("Abaixo estão os atendentes que têm acesso ao chat.")
        # Mostra tabela simples
        st.dataframe(equipe, use_container_width=True)
    else:
        st.warning("Você ainda não tem atendentes cadastrados.")

    st.divider()

    # 2. FORMULÁRIO DE CRIAÇÃO
    st.subheader("➕ Novo Atendente")
    
    with st.form("form_novo_atendente"):
        c1, c2 = st.columns(2)
        nome = c1.text_input("Nome do Funcionário")
        usuario = c2.text_input("Usuário de Login (ex: maria.vendas)")
        senha = st.text_input("Senha de Acesso", type="password")
        
        if st.form_submit_button("Cadastrar Atendente", type="primary"):
            if nome and usuario and senha:
                payload = {
                    "admin_id": u.get('id', 1), # Tenta pegar o ID, se não tiver usa 1
                    "nome": nome,
                    "usuario": usuario,
                    "senha": senha,
                    "instancia": instancia
                }
                
                try:
                    r = requests.post(f"{API_URL}/equipe/criar", json=payload)
                    if r.status_code == 200:
                        st.success(f"✅ Atendente {nome} criado com sucesso!")
                        time.sleep(1.5)
                        st.rerun()
                    else:
                        erro_msg = r.json().get('erro', 'Erro desconhecido')
                        st.error(f"Erro ao criar: {erro_msg}")
                except Exception as e:
                    st.error(f"Erro de conexão: {e}")
            else:
                st.warning("Preencha todos os campos.")

# =====================================================
# TELA ATENDENTE (VERSÃO VISUAL NATIVO + MÍDIA) 📸
# =====================================================
def tela_atendente():
    if 'user_info' not in st.session_state: return

    u = st.session_state.user_info
    instancia = u.get('instancia_wa')
    
    # Header Limpo
    c1, c2 = st.columns([6, 1])
    c1.markdown(f"### 🎧 Painel: {u.get('nome_cliente')}")
    if c2.button("Sair", key="sair_atend"):
        st.session_state.autenticado = False
        st.rerun()
    st.divider()

    # Layout: 30% Fila | 70% Chat
    col_fila, col_chat = st.columns([1, 2.5])
    
    # --- ESQUERDA: FILA ---
    with col_fila:
        st.markdown("#### 📩 Aguardando")
        if st.button("🔄 Atualizar"): st.rerun()
        
        try:
            res = requests.get(f"{API_URL}/atendimentos/{instancia}")
            fila = res.json() if res.status_code == 200 else []
        except: fila = []
        
        if not fila: st.caption("Ninguém na fila.")
        
        for item in fila:
            tel = item['remote_jid'].split('@')[0]
            # Botão muda de cor se estiver selecionado
            ativo = st.session_state.get('chat_atual', {}).get('id') == item['id']
            tipo_btn = "primary" if ativo else "secondary"
            
            if st.button(f"👤 {tel}", key=f"chat_{item['id']}", type=tipo_btn, use_container_width=True):
                st.session_state.chat_atual = item
                st.rerun()

    # --- DIREITA: CHAT ---
    with col_chat:
        if "chat_atual" in st.session_state:
            cliente = st.session_state.chat_atual
            tel_visual = cliente['remote_jid'].split('@')[0]
            
            # Barra de Topo do Chat
            topo_c1, topo_c2 = st.columns([3, 1])
            topo_c1.markdown(f"### 💬 {tel_visual}")
            if topo_c2.button("✅ Encerrar", type="primary"):
                requests.delete(f"{API_URL}/atendimentos/{cliente['id']}")
                del st.session_state.chat_atual
                st.rerun()
            
            # Área de Mensagens (Container com Scroll)
            chat_container = st.container(height=500)
            
            with chat_container:
                try:
                    r = requests.get(f"{API_URL}/chat/local/{instancia}/{cliente['remote_jid']}")
                    msgs = r.json() if r.status_code == 200 else []
                    
                    if not msgs: st.info("Histórico vazio.")
                    
                    for m in msgs:
                        # Define quem mandou (Visual diferente)
                        if m['fromMe']:
                            avatar = "👨‍💻" # Você
                            role = "assistant"
                        else:
                            avatar = "👤" # Cliente
                            role = "user"
                            
                        texto = m['text'] or ""
                        
                        # Renderiza o balão
                        with st.chat_message(role, avatar=avatar):
                            # Tenta detectar Mídia pelo texto (Link)
                            eh_img = "http" in texto and (".jpg" in texto or ".png" in texto or ".jpeg" in texto)
                            eh_audio = "http" in texto and (".mp3" in texto or ".ogg" in texto)
                            
                            if eh_img:
                                st.image(texto, width=300)
                                st.caption("📸 Imagem enviada")
                            elif eh_audio:
                                st.audio(texto)
                                st.caption("🎤 Áudio enviado")
                            else:
                                st.write(texto)
                                
                except Exception as e:
                    st.error(f"Erro chat: {e}")

            # Input de Resposta
            resposta = st.chat_input(f"Responder {tel_visual}...")
            if resposta:
                # 1. Envia Whats
                msg_formatada = f"*[Atend. {u.get('nome') or 'Humano'}]:* {resposta}"
                requests.post(f"{EVO_URL}/message/sendText/{instancia}", 
                              json={"number": cliente['remote_jid'], "text": msg_formatada}, 
                              headers=HEADERS_EVO)
                
                # 2. Salva Local
                payload = {"instancia": instancia, "remote_jid": cliente['remote_jid'], "texto": msg_formatada}
                requests.post(f"{API_URL}/chat/salvar_manual", json=payload)
                time.sleep(0.5)
                st.rerun()
        
        else:
            st.info("👈 Selecione um cliente ao lado.")

# =====================================================
# CONTROLE DE ACESSO (O SEGREDO DO LOGIN)
# =====================================================

# 1. Inicializa variáveis de sessão se não existirem
if "autenticado" not in st.session_state:
    st.session_state.autenticado = False

if "user_info" not in st.session_state:
    st.session_state.user_info = {}

# 2. Se NÃO estiver autenticado, mostra o Login e PARA o script
if not st.session_state.autenticado:
    login_sistema()
    st.stop() # 🛑 AQUI É A TRAVA: Se não logou, o código para aqui e não carrega o painel.

# =====================================================
# SE CHEGOU AQUI, O USUÁRIO ESTÁ LOGADO! 👇
# =====================================================

user_info = st.session_state.user_info

# Recupera dados vitais com segurança (.get evita erros se o campo vier vazio)
instancia_selecionada = user_info.get("instancia_wa")
login_usuario = user_info.get("login")
status_conta = user_info.get("status_conta", "ativo") # Padrão 'ativo' se não vier nada

# 3. LÓGICA DE BLOQUEIO (INADIMPLÊNCIA / VENCIDO)
bloqueado = False

if status_conta == 'vencido':
    st.error("⚠️ SUA ASSINATURA EXPIROU. Funcionalidades bloqueadas até a renovação.")
    bloqueado = True # Isso vai restringir o menu lateral lá embaixo
elif status_conta == 'bloqueado':
    st.error("🚫 CONTA BLOQUEADA PELO ADMINISTRADOR.")
    bloqueado = True

# Debug (Opcional - pode remover depois)
# st.write(f"Logado como: {login_usuario} | Status: {status_conta}")

# =====================================================
# SIDEBAR E MENU DE NAVEGAÇÃO (CORRIGIDO)
# =====================================================
with st.sidebar:
    st.title("Painel de Controle")
    st.write(f"Bem-vindo, **{user_info.get('nome_cliente', 'Usuário')}**")
    
    # Status da Conexão
    if verificar_status_whatsapp(instancia_selecionada):
        st.markdown("Status: <span class='status-ok'>Online 🟢</span>", unsafe_allow_html=True)
    else:
        st.markdown("Status: <span class='status-err'>Offline 🔴</span>", unsafe_allow_html=True)
        
    st.divider()

    # =====================================================
    # LÓGICA DO MENU LATERAL (COM PERMISSÕES) 🛡️
    # =====================================================
    
    # 1. Recupera dados da sessão
    u = st.session_state.user_info
    tipo_acesso = u.get('tipo_acesso', 'admin') # Se não tiver, assume admin
    
    # 2. Definição das Listas (Vazias inicialmente)
    opcoes = []
    icones = []

    # --- CENÁRIO A: USUÁRIO BLOQUEADO (INADIMPLENTE) ---
    if bloqueado:
        st.error("⚠️ Conta Suspensa")
        opcoes = ["Minha Assinatura", "Atendimento Humano"]
        icones = ["credit-card", "headset"]

    # --- CENÁRIO B: FUNCIONÁRIO (ATENDENTE) ---
    elif tipo_acesso == 'funcionario':
        st.info(f"👤 {u.get('nome')}")
        # Funcionário só vê Chat e Sair (nada de financeiro ou config)
        opcoes = ["Atendimento Humano"]
        icones = ["headset"]

    # --- CENÁRIO C: ADMIN (DONO DA CONTA) ---
    else:
        # Menu Completo
        opcoes = [
            "Dashboard", 
            "Meus Gatilhos", 
            "Menu Principal", 
            "Mapa Mental", 
            "Simulador", 
            "Conexão", 
            "Atendimento Humano", 
            "CRM & Disparos", 
            "Gestão de Equipe",     # <--- NOVO
            "Minha Assinatura"
        ]
        
        # Correção da quantidade de ícones (tinha 9 para 10 itens)
        icones = [
            "speedometer2", 
            "lightning-charge", 
            "house", 
            "diagram-3", 
            "chat-dots", 
            "qr-code", 
            "headset", 
            "megaphone", 
            "people-fill",         # <--- Ícone para Equipe
            "credit-card"
        ]
        
        # Se for VOCÊ (Super Admin do SaaS)
        if login_usuario == "admin": 
            opcoes.append("Gestão de Clientes")
            icones.append("person-badge")

    # --- RENDERIZA O MENU ---
    selected = option_menu(
        menu_title="Navegação",
        options=opcoes,
        icons=icones,
        menu_icon="cast",
        default_index=0,
        orientation="vertical",
        styles={
            "container": {"padding": "0!important", "background-color": "transparent"},
            "icon": {"color": "orange", "font-size": "18px"}, 
            "nav-link": {"font-size": "16px", "text-align": "left", "margin":"0px", "--hover-color": "#eee"},
            "nav-link-selected": {"background-color": "#02ab21"},
        }
    )
    
    st.divider()
    
    # Botão de Sair no final da Sidebar
    if st.button("Sair", key="btn_logout_sidebar", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.user_info = {}
        st.rerun()



# =====================================================
# ABA 1: DASHBOARD CRM 🚀
# =====================================================
if selected == "Dashboard":
    st.subheader("📊 Visão Geral do Negócio")
    
    # 1. Carrega Dados
    metricas = {}
    conectado = False
    
    try:
        # Verifica Conexão
        conectado = verificar_status_whatsapp(instancia_selecionada)
        
        # Busca Métricas Avançadas
        res_met = requests.get(f"{API_URL}/metricas/{instancia_selecionada}")
        if res_met.status_code == 200:
            metricas = res_met.json()
    except:
        pass

    # --- LINHA 1: STATUS E ALERTAS ---
    if conectado:
        st.success(f"🟢 **WhatsApp Conectado:** Instância {instancia_selecionada} rodando.")
    else:
        st.error(f"🔴 **WhatsApp Desconectado:** {instancia_selecionada} parada. Vá em 'Conexão' para resolver.")

    st.markdown("---")

    # --- LINHA 2: KPIs (INDICADORES CHAVE) ---
    c1, c2, c3, c4 = st.columns(4)
    
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">👥 Base de Clientes</div>
            <div class="metric-value">{metricas.get('total_clientes', 0)}</div>
            <div style="font-size:12px; color:gray">Total Cadastrado</div>
        </div>""", unsafe_allow_html=True)

    with c2:
        # Calcula crescimento (Novos / Total) apenas visual
        novos = metricas.get('novos_clientes_mes', 0)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">🚀 Novos (Mês)</div>
            <div class="metric-value" style="color: #28a745;">+{novos}</div>
            <div style="font-size:12px; color:gray">Crescimento Recente</div>
        </div>""", unsafe_allow_html=True)
        
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">🤖 Mensagens Enviadas</div>
            <div class="metric-value">{metricas.get('total_mensagens_bot', 0)}</div>
            <div style="font-size:12px; color:gray">Pelo Robô</div>
        </div>""", unsafe_allow_html=True)

    with c4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">⚡ Gatilhos Ativos</div>
            <div class="metric-value">{metricas.get('total_gatilhos', 0)}</div>
            <div style="font-size:12px; color:gray">Respostas Auto</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # --- LINHA 3: GRÁFICOS ---
    col_g1, col_g2 = st.columns([2, 1])

    with col_g1:
        st.markdown("##### 📈 Volume de Conversas (7 Dias)")
        dados_msg = metricas.get("grafico_mensagens", [])
        if dados_msg:
            df_msg = pd.DataFrame(dados_msg)
            st.bar_chart(df_msg.set_index("Data"), color="#00C853")
        else:
            st.info("Sem dados de mensagens recentes.")

    with col_g2:
        st.markdown("##### 🏷️ Clientes por Etiqueta")
        dados_tags = metricas.get("grafico_etiquetas", [])
        if dados_tags:
            df_tags = pd.DataFrame(dados_tags)
            # Exibe como tabela simples ou dataframe colorido
            st.dataframe(
                df_tags, 
                column_config={
                    "Etiqueta": "Segmento",
                    "Quantidade": st.column_config.ProgressColumn(
                        "Volume", format="%d", min_value=0, max_value=max([d['Quantidade'] for d in dados_tags])
                    )
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.caption("Cadastre etiquetas nos clientes para ver a segmentação aqui.")


elif selected == "Gestão de Equipe":
        # Verificação extra de segurança (só admin acessa)
        if u.get('tipo_acesso', 'admin') == 'admin':
            tela_gestao_equipe()
        else:
            st.error("Acesso Negado. Apenas administradores podem gerenciar a equipe.")
    # 👆👆👆 FIM DO BLOCO 👇👇👇

# =====================================================
# ABA 2: MEUS GATILHOS (ATUALIZADO COM TÍTULO)
# =====================================================
elif selected == "Meus Gatilhos":
    st.subheader("⚡ Gerenciar Respostas Automáticas")
    
    c1, c2 = st.columns([1, 2])
    
    # Formulário
    # Formulário
    with c1:
        with st.container(border=True):
            st.markdown("##### ➕ Novo Gatilho")
            
            # --- VERIFICAÇÃO DE PLANO NO FRONTEND ---
            plano_user = user_info.get('plano', 'Básico')
            
            # Define limites visuais
            limite_gatilhos = 5 if plano_user == "Básico" else 9999
            permite_midia = False if plano_user == "Básico" else True
            
            # Conta gatilhos atuais (Gambiarra rápida: conta quantos vieram na lista da API)
            try:
                res_count = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
                qtd_atual = len(res_count.json()) if res_count.status_code == 200 else 0
            except:
                qtd_atual = 0

            # Barra de progresso do plano
            if plano_user == "Básico":
                st.progress(min(qtd_atual / limite_gatilhos, 1.0), text=f"Uso do Plano: {qtd_atual}/{limite_gatilhos}")
                if qtd_atual >= limite_gatilhos:
                    st.error("🔒 Limite atingido! Faça Upgrade para criar mais.")
            else:
                st.caption(f"💎 Plano {plano_user}: Gatilhos Ilimitados")

            # ----------------------------------------
            
            # Busca pais
            opcoes_pais = {'Nenhum (Menu Principal)': None}
            try:
                r_pais = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
                if r_pais.status_code == 200:
                    for p in r_pais.json():
                        if p['id_pai'] is None and p['gatilho'] != 'default':
                            opcoes_pais[f"{p['gatilho']}"] = p['id']
            except:
                pass
            
            escolha_pai = st.selectbox("Este gatilho pertence a qual menu?", list(opcoes_pais.keys()))
            id_pai_selecionado = opcoes_pais[escolha_pai]

            novo_gatilho = st.text_input("Gatilho (O que o cliente digita)", placeholder="Ex: 1")
            novo_titulo = st.text_input("Título do Item (Opcional)", placeholder="Ex: Financeiro")
            nova_resposta = st.text_area("Resposta do Robô", height=100)
            
            # --- LÓGICA DA MÍDIA ---
            arquivo_enviado = None
            if permite_midia:
                arquivo_enviado = st.file_uploader("Anexar Mídia", type=["png", "jpg", "jpeg", "pdf", "mp4"])
            else:
                st.info(f"🔒 Mídia bloqueada no plano {plano_user}")
            # -----------------------
            
            tipo_msg = "texto"
            url_final = None

            # Botão Salvar (Desabilita se estourou limite do Básico)
            botao_desabilitado = (plano_user == "Básico" and qtd_atual >= limite_gatilhos)
            
            if st.button("💾 Salvar Gatilho", use_container_width=True, disabled=botao_desabilitado):
                if novo_gatilho and nova_resposta:
                    
                    # Upload (Só acontece se o plano permitir e tiver arquivo)
                    if arquivo_enviado and permite_midia:
                        with st.spinner("Enviando arquivo..."):
                            files = {"file": (arquivo_enviado.name, arquivo_enviado, arquivo_enviado.type)}
                            try:
                                res_up = requests.post(f"{API_URL}/upload", files=files)
                                if res_up.status_code == 200:
                                    url_final = res_up.json()["url"]
                                    if arquivo_enviado.type.startswith("image"): tipo_msg = "image"
                                    elif arquivo_enviado.type.startswith("video"): tipo_msg = "video"
                                    elif "pdf" in arquivo_enviado.type: tipo_msg = "document"
                            except Exception as e:
                                st.error(f"Erro upload: {e}")
                                st.stop()

                    payload = {
                        "instancia": instancia_selecionada, 
                        "gatilho": novo_gatilho, 
                        "resposta": nova_resposta,
                        "titulo_menu": novo_titulo if novo_titulo else "Geral",
                        "categoria": "Atendimento",
                        "tipo_midia": tipo_msg,
                        "url_midia": url_final,
                        "id_pai": id_pai_selecionado
                    }
                    
                    res_salvar = requests.post(f"{API_URL}/salvar", json=payload)
                    
                    if res_salvar.status_code == 200:
                        st.success("Salvo!")
                        time.sleep(1)
                        st.rerun()
                    elif res_salvar.status_code == 403:
                        st.error(res_salvar.json()['detail']) # Mostra mensagem de erro do plano
                    else:
                        st.error("Erro ao salvar.")

    # Tabela Hierárquica Visual
    with c2:
        st.markdown("### 🗂️ Seus Menus")
        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        
        if res.status_code == 200:
            dados = res.json()
            if dados:
                dados_visuais = dados
                
                pais = [d for d in dados_visuais if d['id_pai'] is None]
                filhos = [d for d in dados_visuais if d['id_pai'] is not None]

                for pai in pais:
                    # Mostra o Título se tiver
                    titulo_exibicao = f" - {pai['titulo_menu']}" if pai.get('titulo_menu') and pai['titulo_menu'] != "Geral" else ""
                    
                    with st.expander(f"📂 **{pai['gatilho']}** {titulo_exibicao}"):
                        st.write(f"📝 {pai['resposta']}")
                        if st.button("🗑️ Excluir Menu", key=f"del_pai_{pai['id']}"):
                            requests.delete(f"{API_URL}/excluir/{pai['id']}")
                            st.rerun()

                        meus_filhos = [f for f in filhos if f['id_pai'] == pai['id']]
                        if meus_filhos:
                            st.markdown("---")
                            for filho in meus_filhos:
                                with st.container():
                                    c_f1, c_f2 = st.columns([4, 1])
                                    
                                    titulo_filho = f" ({filho['titulo_menu']})" if filho.get('titulo_menu') and filho['titulo_menu'] != "Geral" else ""
                                    
                                    c_f1.info(f"🔹 **{filho['gatilho']}**{titulo_filho}: {filho['resposta']}")
                                    if c_f2.button("❌", key=f"del_filho_{filho['id']}"):
                                        requests.delete(f"{API_URL}/excluir/{filho['id']}")
                                        st.rerun()
                        else:
                            st.caption("Sem sub-opções.")
            else:
                st.info("Nenhum gatilho cadastrado.")

# =====================================================
# ABA 3: MENU PRINCIPAL
# =====================================================
elif selected == "Menu Principal":
    st.subheader("🏠 Configurar Menu Inicial")
    st.info("Esta mensagem será enviada quando o cliente disser 'Oi', 'Menu' ou algo que o robô não entenda.")
    
    texto_atual = ""
    try:
        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        if res.status_code == 200:
            for item in res.json():
                if item['gatilho'] == 'default':
                    texto_atual = item['resposta']
                    break
    except:
        pass

    with st.container(border=True):
        st.markdown("**Mensagem de Boas-Vindas / Menu:**")
        novo_texto = st.text_area("Digite o menu aqui:", value=texto_atual, height=200, placeholder="Ex: Olá! Sou o assistente virtual. Digite 1 para Cardápio...")
        
        if st.button("💾 Atualizar Menu Principal", type="primary"):
            payload = {
                "instancia": instancia_selecionada, 
                "gatilho": "default", 
                "resposta": novo_texto,
                "titulo_menu": "Geral",
                "categoria": "Geral",
                "tipo_midia": "texto",
                "url_midia": None,
                "id_pai": None
            }
            requests.post(f"{API_URL}/salvar", json=payload)
            st.success("Menu Principal atualizado com sucesso!")
            time.sleep(1)
            st.rerun()

# =====================================================
# ABA 4: MAPA MENTAL (VISUAL PREMIUM 🧠)
# =====================================================
elif selected == "Mapa Mental":
    st.subheader("🧠 Fluxo de Conversa")
    st.caption("Visualização gráfica da inteligência do seu robô.")

    # Funçãozinha para quebrar texto longo (para o balão não ficar gigante)
    import textwrap
    def quebrar_texto(texto, largura=30):
        return "<br/>".join(textwrap.wrap(texto, width=largura))

    try:
        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        gatilhos = res.json() if res.status_code == 200 else []

        if not gatilhos:
            c_vazio1, c_vazio2 = st.columns([1, 2])
            with c_vazio1:
                st.image("https://cdn-icons-png.flaticon.com/512/7486/7486744.png", width=150)
            with c_vazio2:
                st.warning("Seu mapa está vazio!")
                st.info("Vá em 'Meus Gatilhos' e cadastre a primeira regra para ver a mágica acontecer.")
        else:
            # --- CONFIGURAÇÃO DO DESIGN DO GRÁFICO ---
            graph = graphviz.Digraph()
            
            # Layout Horizontal (LR) com linhas curvas e design limpo
            graph.attr(rankdir='LR', splines='curved', bgcolor='transparent')
            
            # Estilo Padrão dos Nós (Caixinhas)
            graph.attr('node', 
                       shape='box', 
                       style='filled,rounded', # Arredondado e preenchido
                       fontname='Helvetica', 
                       penwidth='0', # Sem borda preta grossa
                       margin='0.2'
            )
            
            # Estilo das Setas (Linhas)
            graph.attr('edge', 
                       arrowhead='vee', 
                       arrowsize='0.8', 
                       color='#555555', 
                       fontname='Helvetica', 
                       fontsize='10'
            )

            # 1. NÓ INICIAL (CLIENTE)
            graph.node('CLIENTE', 
                       label=f'<<B>📱 INÍCIO</B><BR/><FONT POINT-SIZE="10">Cliente manda "Oi"</FONT>>', 
                       fillcolor='#2ecc71', # Verde WhatsApp
                       fontcolor='white',
                       shape='circle' # Redondo
            )
            
            ids_existentes = {g['id'] for g in gatilhos}

            for item in gatilhos:
                # Prepara o Texto (Título + Resposta resumida)
                gatilho_txt = item['gatilho'].upper()
                titulo_menu = item.get('titulo_menu', '')
                
                # Se tiver título bonito, usa ele. Se não, usa o gatilho.
                header = titulo_menu if (titulo_menu and titulo_menu != "Geral") else gatilho_txt
                
                # Resposta resumida e quebrada
                resposta_curta = quebrar_texto(item['resposta'][:60] + ("..." if len(item['resposta']) > 60 else ""))

                # --- LÓGICA DE ESTILO POR TIPO DE NÓ ---
                
                # A. MENU PRINCIPAL (DEFAULT)
                if item['gatilho'] == 'default':
                    label_html = f'''<
                        <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">
                        <TR><TD><B>🏠 MENU PRINCIPAL</B></TD></TR>
                        <TR><TD><FONT POINT-SIZE="10" COLOR="#444444">{resposta_curta}</FONT></TD></TR>
                        </TABLE>
                    >'''
                    
                    graph.node(f"G_{item['id']}", label=label_html, fillcolor='#ffcb2b', fontcolor='black') # Amarelo
                    graph.edge('CLIENTE', f"G_{item['id']}", color="#2ecc71", penwidth="2.0")

                # B. SUB-MENUS E RESPOSTAS
                else:
                    id_pai = item['id_pai']
                    
                    # Define cor baseada se é "Pai" (tem filhos) ou "Folha" (fim da linha)
                    # (Lógica simplificada: se tem id_pai, é cinza claro, se é submenu importante, azul)
                    cor_fundo = '#E3F2FD' # Azul clarinho padrão
                    icone = "💬"
                    
                    # Se tiver mídia, muda ícone
                    if item.get('url_midia'):
                        icone = "📸"

                    label_html = f'''<
                        <TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0">
                        <TR><TD ALIGN="LEFT"><B>{icone} {header}</B></TD></TR>
                        <TR><TD ALIGN="LEFT"><FONT POINT-SIZE="9" COLOR="#666666">Gatilho: "{item['gatilho']}"</FONT></TD></TR>
                        <TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{resposta_curta}</FONT></TD></TR>
                        </TABLE>
                    >'''
                    
                    graph.node(f"G_{item['id']}", label=label_html, fillcolor=cor_fundo, fontcolor='black')

                    # CRIA AS CONEXÕES (LINHAS)
                    if id_pai is None:
                        # Atalho direto do início (Menu oculto)
                        graph.edge('CLIENTE', f"G_{item['id']}", style="dashed", label="Palavra-chave", color="#999999")
                    elif id_pai in ids_existentes:
                        # Conexão Pai -> Filho
                        graph.edge(f"G_{id_pai}", f"G_{item['id']}")

            # Renderiza o gráfico
            st.graphviz_chart(graph, use_container_width=True)
            
            # Legenda simples
            st.caption("Legenda: 🟢 Início | 🟡 Menu Principal | 🔵 Respostas | 📸 Contém Imagem/Vídeo")

    except Exception as e:
        st.error(f"Erro ao gerar mapa: {e}")

# =====================================================
# ABA 5: SIMULADOR
# =====================================================
elif selected == "Simulador":
    st.subheader("💬 Teste seu Robô")
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("Digite algo..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        resposta_robo = "..."
        
        if res.status_code == 200:
            gatilhos = res.json()
            encontrou = False
            
            # Busca exata
            for g in gatilhos:
                if g['gatilho'].lower() in prompt.lower() and g['gatilho'] != 'default':
                    resposta_robo = g['resposta']
                    encontrou = True
                    break
            
            # Busca Default
            if not encontrou:
                for g in gatilhos:
                    if g['gatilho'] == 'default':
                        resposta_robo = g['resposta']
                        break
        
        time.sleep(0.5)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_robo})
        with st.chat_message("assistant"):
            st.markdown(resposta_robo)

# =====================================================
# ABA 6: CONEXÃO
# =====================================================
elif selected == "Conexão":
    st.subheader("📱 Conexão com WhatsApp")
    
    status_texto = "..."
    try:
        r_check = requests.get(f"{EVO_URL}/instance/connectionState/{instancia_selecionada}", headers=HEADERS_EVO, timeout=2)
        if r_check.status_code == 200:
            state = r_check.json().get('instance', {}).get('state', 'close')
            if state == 'open':
                st.success(f"Status: ONLINE ({state})")
            else:
                st.warning(f"Status: DESCONECTADO ({state})")
        else:
            st.error("Status: Erro na API")
    except:
        st.error("Status: API Offline ou Bloqueada")

    st.divider()
    
    col_qr, col_sts = st.columns(2)
    
    with col_qr:
        if st.button("🔄 Gerar QR Code", use_container_width=True):
            # 👇👇👇 AUTOMAÇÃO INVISÍVEL AO CLIENTE 👇👇👇
            with st.status("Preparando sua instância...", expanded=False) as status:
                st.write("Configurando servidor de mídia...")
                # Chama a rota nova que criamos no passo 1
                requests.post(f"{API_URL}/instance/configurar/{instancia_selecionada}")
                time.sleep(2) # Dá um tempinho para o reinício rápido
                status.update(label="Gerando QR Code...", state="running")
            # 👆👆👆 FIM DA AUTOMAÇÃO 👆👆👆
            with st.spinner("Solicitando QR Code..."):
                try:
                    res = requests.get(f"{EVO_URL}/instance/connect/{instancia_selecionada}", headers=HEADERS_EVO, timeout=10)
                    if res.status_code == 200:
                        data = res.json()
                        if "base64" in data:
                            img = Image.open(BytesIO(base64.b64decode(data["base64"].split(",")[1])))
                            st.image(img, caption="Leia no seu WhatsApp")
                        elif "qrcode" in data:
                            st.code(data["qrcode"])
                        else:
                            st.warning("Já conectado.")
                    else:
                        st.error(f"Erro QR Code: {res.status_code}")
                except Exception as e:
                    st.error(f"Falha de conexão: {e}")
    
    with col_sts:
        st.info("Diagnóstico")
        if st.button("🔌 Forçar Reativação do Webhook"):
            try:
                with st.spinner("Configurando..."):
                    sucesso, mensagem = ativar_webhook(instancia_selecionada)
                    if sucesso:
                        st.success(mensagem)
                        st.balloons()
                    else:
                        st.error(f"❌ Falha: {mensagem}")            
            except Exception as e:
                st.error(f"Erro ao conectar: {e}")

        if st.button("📊 Ver JSON Status"):
            try:
                res = requests.get(f"{EVO_URL}/instance/connectionState/{instancia_selecionada}", headers=HEADERS_EVO, timeout=5)
                st.json(res.json())
            except:
                st.error("Erro ao buscar JSON")

# =====================================================
# ABA ADMIN: GESTÃO DE CLIENTES + CUPONS + PLANOS
# =====================================================
elif selected == "Gestão de Clientes":
    st.subheader("👥 Gestão Administrativa")
    
    # AGORA SÃO 4 ABAS (Adicionei a última para Configuração)
    aba_cad, aba_list, aba_cupom, aba_planos = st.tabs(["➕ Novo Cliente", "📋 Listagem e Edição", "🎟️ Cupons", "⚙️ Configurar Planos"])

    # -----------------------------------------------------
    # ABA 1: CADASTRO
    # -----------------------------------------------------
    with aba_cad:
        with st.container(border=True):
            st.markdown("### 👤 Dados de Acesso")
            col1, col2 = st.columns(2)
            nome = col1.text_input("Nome do Cliente", placeholder="Ex: João Silva")
            login = col1.text_input("Login", placeholder="joao123")
            senha = col2.text_input("Senha", type="password")
            instancia = col2.text_input("Instância WhatsApp", help="Sem espaços. Ex: joaowhats")

            st.markdown("### 📞 Contato e Cobrança")
            c_cont1, c_cont2 = st.columns(2)
            whatsapp = c_cont1.text_input("WhatsApp (Cobrança)", placeholder="5511999998888")
            email = c_cont2.text_input("E-mail", placeholder="cliente@email.com")

            st.markdown("### 💰 Plano")
            c_fin1, c_fin2, c_fin3 = st.columns(3)
            plano = c_fin1.selectbox("Plano", ["Básico", "Pro", "Enterprise"])
            valor = c_fin2.number_input("Valor (R$)", min_value=0.0, value=99.90, step=10.0, format="%.2f")
            vencimento = c_fin3.date_input("Vencimento")

            st.markdown("---")
            if st.button("🚀 Criar Cliente", type="primary", use_container_width=True):
                if nome and login and instancia:
                    payload = {
                        "nome_cliente": nome, "login": login, "senha": senha, 
                        "instancia_wa": instancia.strip(), "plano": plano, 
                        "valor_mensal": valor, "data_vencimento": str(vencimento),
                        "whatsapp": whatsapp, "email": email
                    }
                    try:
                        res = requests.post(f"{API_URL}/usuarios/cadastrar", json=payload)
                        if res.status_code == 200:
                            st.balloons()
                            st.success("Cliente cadastrado com sucesso!")
                            time.sleep(1)
                            st.rerun()
                        else:
                            st.error(f"Erro: {res.text}")
                    except Exception as e:
                        st.error(f"Erro conexão: {e}")
                else:
                    st.warning("Preencha Nome, Login e Instância.")

    # -----------------------------------------------------
    # ABA 2: LISTAGEM E EDIÇÃO
    # -----------------------------------------------------
    with aba_list:
        try:
            res = requests.get(f"{API_URL}/usuarios/listar")
            if res.status_code == 200:
                usuarios = res.json()
                if not usuarios:
                    st.info("Nenhum cliente encontrado.")
                
                for user in usuarios:
                    status_icon = "🔴" if user.get('status_conta') == 'bloqueado' else "🟢"
                    if user.get('status_conta') == 'vencido': status_icon = "⚠️"
                    
                    with st.expander(f"{status_icon} {user['nome_cliente']} ({user['plano']})"):
                        # Formulário de Edição
                        with st.form(key=f"form_edit_{user['id']}"):
                            c1, c2 = st.columns(2)
                            ed_nome = c1.text_input("Nome", value=user['nome_cliente'])
                            ed_login = c2.text_input("Login", value=user['login'])
                            
                            c3, c4 = st.columns(2)
                            ed_senha = c3.text_input("Senha", value=user['senha'], type="password")
                            ed_zap = c4.text_input("WhatsApp", value=user.get('whatsapp', ''))
                            
                            c5, c6 = st.columns(2)
                            ed_email = c5.text_input("Email", value=user.get('email', ''))
                            # Lógica para selecionar o índice correto do plano
                            lista_planos = ["Básico", "Pro", "Enterprise"]
                            idx_plano = lista_planos.index(user['plano']) if user['plano'] in lista_planos else 0
                            ed_plano = c6.selectbox("Plano", lista_planos, index=idx_plano)
                            
                            c7, c8 = st.columns(2)
                            ed_valor = c7.number_input("Valor (R$)", value=float(user.get('valor_mensal', 0) or 0), step=10.0)
                            
                            # Tratamento Seguro de Data
                            data_banco = user.get('data_vencimento')
                            val_data = None
                            if data_banco:
                                try:
                                    val_data = pd.to_datetime(data_banco).date()
                                except: pass
                            
                            ed_venc = c8.date_input("Vencimento", value=val_data)

                            # Botões de Ação
                            st.markdown("---")
                            col_b1, col_b2 = st.columns([1, 1])
                            
                            if col_b1.form_submit_button("💾 Salvar Alterações", type="primary"):
                                payload_edit = {
                                    "nome_cliente": ed_nome, "login": ed_login, "senha": ed_senha,
                                    "plano": ed_plano, "valor_mensal": ed_valor, 
                                    "data_vencimento": str(ed_venc) if ed_venc else None,
                                    "whatsapp": ed_zap, "email": ed_email
                                }
                                try:
                                    r_edit = requests.put(f"{API_URL}/usuarios/editar/{user['id']}", json=payload_edit)
                                    if r_edit.status_code == 200:
                                        st.success("Atualizado!")
                                        time.sleep(1)
                                        st.rerun()
                                    else:
                                        st.error(f"Erro: {r_edit.text}")
                                except Exception as e:
                                    st.error(f"Erro: {e}")
                        
                        # Botão de Excluir (Fora do form)
                        col_del1, col_del2 = st.columns([4,1])
                        if col_del2.button("🗑️ Excluir", key=f"del_{user['id']}", type="secondary"):
                            requests.delete(f"{API_URL}/usuarios/excluir/{user['id']}")
                            try:
                                requests.delete(f"{EVO_URL}/instance/delete/{user['instancia_wa']}", headers=HEADERS_EVO)
                            except: pass
                            st.rerun()

            else:
                st.error("Erro ao carregar lista de usuários.")
        except Exception as e:
            st.error(f"Erro ao conectar: {e}")

    # -----------------------------------------------------
    # ABA 3: CUPONS
    # -----------------------------------------------------
    with aba_cupom:
        st.markdown("### 🎟️ Gerenciar Cupons de Desconto")
        
        # 1. Criar Cupom
        with st.container(border=True):
            st.write("Novo Cupom")
            with st.form("form_cupom"):
                cc1, cc2 = st.columns([3, 1])
                novo_codigo = cc1.text_input("Código (Ex: PROMO10)", placeholder="SEM ESPAÇOS")
                novo_desc = cc2.number_input("Desconto (%)", min_value=1, max_value=100, value=10)
                
                if st.form_submit_button("Criar Cupom"):
                    if novo_codigo:
                        try:
                            res = requests.post(f"{API_URL}/cupons", json={"codigo": novo_codigo, "desconto": novo_desc})
                            if res.status_code == 200:
                                st.success("Cupom criado!")
                                st.rerun()
                            else:
                                st.error("Erro ao criar (talvez já exista).")
                        except Exception as e:
                            st.error(f"Erro: {e}")
        
        st.divider()
        
        # 2. Listar Cupons
        st.write("Cupons Ativos:")
        try:
            res_cp = requests.get(f"{API_URL}/cupons")
            if res_cp.status_code == 200:
                lista_cupons = res_cp.json()
                if lista_cupons:
                    for cp in lista_cupons:
                        c_list1, c_list2 = st.columns([4, 1])
                        c_list1.info(f"🏷️ **{cp['codigo']}** - {cp['desconto_porcentagem']}% de Desconto")
                        if c_list2.button("🗑️", key=f"del_cp_{cp['codigo']}"):
                            requests.delete(f"{API_URL}/cupons/{cp['codigo']}")
                            st.rerun()
                else:
                    st.caption("Nenhum cupom cadastrado.")
        except:
            st.error("Não foi possível carregar os cupons.")

    # -----------------------------------------------------
    # ABA 4: CONFIGURAR PLANOS (COM LIMITES NUMÉRICOS) 🔢
    # -----------------------------------------------------
    with aba_planos:
        st.markdown("### ⚙️ Regras e Limites por Plano")
        st.info("Defina o que é permitido (✅) e os limites numéricos (🔢).")

        try:
            # 1. Busca as regras
            res = requests.get(f"{API_URL}/admin/regras")
            
            if res.status_code == 200:
                dados_regras = res.json()
                
                if dados_regras:
                    df = pd.DataFrame(dados_regras)
                    
                    # --- TABELA 1: FUNCIONALIDADES (SIM/NÃO) ---
                    st.markdown("#### 🔓 Funcionalidades (Ativar/Desativar)")
                    # Filtra só o que NÃO começa com 'max_'
                    df_bool = df[~df['funcionalidade'].str.startswith('max_')]
                    
                    col_cfg_bool = {}
                    if not df_bool.empty:
                        df_pivot_bool = df_bool.pivot(index='funcionalidade', columns='plano', values='ativo')
                        col_cfg_bool = {c: st.column_config.CheckboxColumn(c) for c in df_pivot_bool.columns}
                        
                        edit_bool = st.data_editor(
                            df_pivot_bool, column_config=col_cfg_bool, use_container_width=True, key="edit_bool"
                        )
                    else:
                        edit_bool = pd.DataFrame()
                    
                    st.divider()

                    # --- TABELA 2: LIMITES NUMÉRICOS ---
                    st.markdown("#### 🔢 Limites de Quantidade")
                    # Filtra só o que COMEÇA com 'max_'
                    df_num = df[df['funcionalidade'].str.startswith('max_')]
                    
                    if not df_num.empty:
                        df_pivot_num = df_num.pivot(index='funcionalidade', columns='plano', values='limite')
                        col_cfg_num = {c: st.column_config.NumberColumn(c, step=1, min_value=0) for c in df_pivot_num.columns}
                        
                        edit_num = st.data_editor(
                            df_pivot_num, column_config=col_cfg_num, use_container_width=True, key="edit_num"
                        )
                    else:
                        edit_num = pd.DataFrame()

                    st.markdown("---")

                    # 4. BOTÃO SALVAR TUDO
                    if st.button("💾 Salvar Todas as Regras", type="primary"):
                        lista_envio = []
                        
                        # Processa Booleanos
                        if not edit_bool.empty:
                            for func, row in edit_bool.iterrows():
                                for plano in edit_bool.columns:
                                    lista_envio.append({
                                        "plano": plano, "funcionalidade": func, 
                                        "ativo": bool(row[plano]), "limite": 0
                                    })
                        
                        # Processa Numéricos
                        if not edit_num.empty:
                            for func, row in edit_num.iterrows():
                                for plano in edit_num.columns:
                                    lista_envio.append({
                                        "plano": plano, "funcionalidade": func, 
                                        "ativo": True, "limite": int(row[plano])
                                    })
                        
                        # Envia
                        try:
                            r_save = requests.post(f"{API_URL}/admin/regras", json={"regras": lista_envio})
                            if r_save.status_code == 200:
                                st.toast("✅ Regras e Limites salvos!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                st.error("Erro ao salvar.")
                        except Exception as e:
                            st.error(f"Erro: {e}")

                else:
                    st.warning("Tabela vazia. (Rode o SQL de configuração inicial no Banco)")
            else:
                st.error("Erro no servidor.")
                
        except Exception as e:
            st.error(f"Erro: {e}")

    # Exibe Pix se gerado
    if "pix_renovacao" in st.session_state:
        pix = st.session_state.pix_renovacao
        st.info("Pague para liberar instantaneamente:")
        
        # Mostra valor final se disponível
        if 'valor_final' in pix:
            st.markdown(f"### Total a Pagar: R$ {pix['valor_final']:.2f}")

        try:
            img = base64.b64decode(pix['qr_base64'])
            st.image(BytesIO(img), width=250)
        except: pass
        
        st.text_area("Copia e Cola", pix['qr_code'])
        
        if st.button("Já Paguei (Atualizar)"):
             st.session_state.autenticado = False
             st.rerun()



elif selected == "Atendimento Humano":
    # Chama a função completa que criamos lá em cima
    tela_atendente()

    try:
        # Busca quem está na tabela de pausa
        # Precisamos criar essa rota no backend primeiro? Podemos fazer query direta aqui ou criar rota
        # Vamos fazer rota direta aqui pra ser rápido (mas o ideal é rota na API)
        
        # ROTA RÁPIDA (Gambiarra permitida para MVP)
        # Vamos adicionar essa rota no backend rapidinho abaixo
        res = requests.get(f"{API_URL}/atendimentos/{instancia_selecionada}")
        
        if res.status_code == 200:
            lista = res.json()
            if not lista:
                st.success("Nenhum cliente aguardando. O Robô está cuidando de tudo! 🤖")
            
            for item in lista:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    
                    # Formata telefone
                    tel = item['remote_jid'].split('@')[0]
                    c1.markdown(f"**Cliente:** {tel}")
                    c1.caption(f"Desde: {item['data_inicio']}")
                    
                    c2.markdown("Status: 🔴 **Em Atendimento Humano**")
                    
                    if c3.button("✅ Encerrar / Reativar Bot", key=f"fim_{item['id']}"):
                        requests.delete(f"{API_URL}/atendimentos/{item['id']}")
                        st.toast("Bot reativado para este cliente!")
                        time.sleep(1)
                        st.rerun()
        else:
            st.error("Erro ao buscar atendimentos.")

    except Exception as e:
        st.error(f"Erro: {e}")


# =====================================================
# ABA: CRM & DISPAROS (NOVO)
# =====================================================
elif selected == "CRM & Disparos":
    st.subheader("📢 Gestão de Clientes e Disparos")
    
    tab_crm, tab_disparo = st.tabs(["📇 Meus Clientes", "🚀 Novo Disparo"])
    
    # -----------------------------------------------
    # 1. CADASTRO DE CLIENTES
    # -----------------------------------------------
    with tab_crm:
        with st.expander("➕ Adicionar Novo Cliente", expanded=False):
            with st.form("form_crm"):
                c1, c2 = st.columns(2)
                crm_nome = c1.text_input("Nome", placeholder="Ex: Maria Silva")
                crm_tel = c2.text_input("WhatsApp (com 55)", placeholder="5511999998888")
                
                c3, c4 = st.columns(2)
                crm_dia = c3.number_input("Dia de Vencimento", min_value=1, max_value=31, value=10)
                crm_tags = c4.text_input("Etiquetas", placeholder="Ex: musculação, manhã")
                
                if st.form_submit_button("Salvar Cliente"):
                    if crm_nome and crm_tel:
                        payload = {
                            "instancia": instancia_selecionada,
                            "nome": crm_nome,
                            "telefone": crm_tel,
                            "dia_vencimento": crm_dia,
                            "etiquetas": crm_tags
                        }
                        requests.post(f"{API_URL}/crm/clientes", json=payload)
                        st.success("Salvo!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.warning("Nome e Telefone são obrigatórios.")

        
       
        
        st.divider()
        
        # ==========================================
        # 📂 IMPORTAÇÃO VIA EXCEL/CSV (COM BLOQUEIO PRO) 🔒
        # ==========================================
        with st.expander("📂 Importar Lista de Contatos (Excel/CSV)"):
            
            # 1. VERIFICA O PLANO
            plano_user = st.session_state.user_info.get('plano', 'Básico')
            
            # SE FOR BÁSICO -> BLOQUEIA
            if plano_user == "Básico":
                st.error("🔒 Funcionalidade Exclusiva do Plano PRO")
                st.info("No plano Básico, o cadastro é manual.")
                st.markdown("### 🚀 Quer importar milhares de contatos em segundos?")
                st.write("Faça o upgrade para o **Plano Pro** e economize horas de trabalho manual.")
                
                if st.button("💎 Quero fazer Upgrade para Importar", type="primary"):
                     st.session_state.selected = "Minha Assinatura"
                     st.rerun()
            
            # SE FOR PRO/ENTERPRISE -> LIBERA
            else:
                st.info("💡 A planilha deve ter duas colunas: **Nome** e **Telefone**.")
                
                arquivo_import = st.file_uploader("Selecione o arquivo", type=["csv", "xlsx"])
                
                if arquivo_import:
                    if st.button("Processar Importação"):
                        try:
                            # Lê o arquivo
                            if arquivo_import.name.endswith('.csv'):
                                df_import = pd.read_csv(arquivo_import)
                            else:
                                df_import = pd.read_excel(arquivo_import)
                            
                            # ... (O RESTO DO CÓDIGO DE IMPORTAÇÃO CONTINUA IGUAL AQUI) ...
                            # Padroniza nomes das colunas
                            df_import.columns = [c.lower() for c in df_import.columns]
                            
                            col_nome = next((c for c in df_import.columns if 'nom' in c), None)
                            col_tel = next((c for c in df_import.columns if 'tel' in c or 'cel' in c or 'what' in c), None)
                            
                            if col_nome and col_tel:
                                barra_imp = st.progress(0, text="Importando...")
                                total = len(df_import)
                                sucesso = 0
                                
                                for i, row in df_import.iterrows():
                                    nome = str(row[col_nome])
                                    tel_raw = str(row[col_tel])
                                    
                                    tel_clean = "".join([c for c in tel_raw if c.isdigit()])
                                    
                                    if len(tel_clean) < 10: continue 
                                    if not tel_clean.startswith("55") and len(tel_clean) > 9:
                                        tel_clean = "55" + tel_clean
                                        
                                    if "@" not in tel_clean:
                                        tel_clean += "@s.whatsapp.net"
                                        
                                    payload = {
                                        "instancia": instancia_selecionada,
                                        "nome": nome,
                                        "telefone": tel_clean,
                                        "dia_vencimento": 1,
                                        "etiquetas": "importado_excel"
                                    }
                                    requests.post(f"{API_URL}/crm/clientes", json=payload)
                                    
                                    sucesso += 1
                                    barra_imp.progress((i + 1) / total)
                                    
                                st.success(f"✅ Importação finalizada! {sucesso} contatos adicionados.")
                                time.sleep(2)
                                st.rerun()
                                
                            else:
                                st.error("❌ Não encontrei as colunas 'Nome' e 'Telefone'.")
                                
                        except Exception as e:
                            st.error(f"Erro ao ler arquivo: {e}")
                        
        
        # Lista Clientes
        st.divider()
        st.markdown("### 📋 Gerenciamento de Contatos")

        # --- CONTROLE DE PAGINAÇÃO E BUSCA ---
        if "crm_pagina" not in st.session_state: st.session_state.crm_pagina = 1
        if "crm_busca" not in st.session_state: st.session_state.crm_busca = ""

        c_filt1, c_filt2, c_filt3 = st.columns([2, 1, 1])
        texto_busca = c_filt1.text_input("🔍 Buscar (Nome ou Tel)", value=st.session_state.crm_busca, placeholder="Enter para buscar...")
        
        # Se mudou a busca, volta pra página 1
        if texto_busca != st.session_state.crm_busca:
            st.session_state.crm_busca = texto_busca
            st.session_state.crm_pagina = 1
            st.rerun()

        # --- BUSCA DADOS NO BACKEND ---
        try:
            params = {
                "pagina": st.session_state.crm_pagina,
                "itens_por_pagina": 20, # Pode aumentar se quiser
                "busca": st.session_state.crm_busca if st.session_state.crm_busca else None
            }
            # Passa params via query string é melhor, mas requests aceita params=...
            res = requests.get(f"{API_URL}/crm/clientes/{instancia_selecionada}", params=params)
            
            if res.status_code == 200:
                payload = res.json()
                lista_clientes = payload['data']
                total_paginas = payload['total_paginas']
                total_itens = payload['total']
                
                if lista_clientes:
                    # Prepara DataFrame
                    df = pd.DataFrame(lista_clientes)
                    
                    # Limpeza Visual do Telefone (Igual antes)
                    df['telefone_visual'] = df['telefone'].astype(str).str.replace('@s.whatsapp.net', '')
                    
                    # Organiza Colunas para o Editor
                    # Ocultamos o ID e o Telefone Original (usamos o visual para leitura, mas o original é chave)
                    df_editor = df[['id', 'nome', 'telefone_visual', 'dia_vencimento', 'etiquetas', 'telefone']]
                    
                    # --- TABELA EDITÁVEL (EXCEL LIKE) ---
                    st.caption(f"Total: {total_itens} clientes | Página {st.session_state.crm_pagina} de {total_paginas}")
                    st.info("💡 Clique duas vezes na célula para editar Nome, Dia ou Etiquetas.")

                    editado = st.data_editor(
                        df_editor,
                        column_config={
                            # AQUI ESTÁ A CORREÇÃO 👇
                            "id": st.column_config.NumberColumn("ID", width="small", disabled=True, format="%d"),
                            # -----------------------
                            "telefone": None, # Esconde Telefone Real (interno)
                            "telefone_visual": st.column_config.TextColumn("WhatsApp", disabled=True),
                            "nome": st.column_config.TextColumn("Nome"),
                            "dia_vencimento": st.column_config.NumberColumn("Dia Venc.", min_value=1, max_value=31, format="%d"),
                            "etiquetas": st.column_config.TextColumn("Etiquetas")
                        },
                        hide_index=True,
                        use_container_width=True,
                        key=f"editor_crm_{st.session_state.crm_pagina}"
                    )

                    # --- DETECTA MUDANÇAS E SALVA ---
                    # st.data_editor não salva sozinho no banco. Precisamos pegar as mudanças.
                    # Mas para simplificar a UX, vamos adicionar um botão de "Salvar Alterações" se detectar mudança?
                    # O Streamlit atualiza o 'editado' em tempo real. Vamos checar diferenças.
                    
                    # Lógica de Salvar Edição:
                    # O 'editado' retorna o dataframe com as mudanças aplicadas visualmente.
                    # Vamos iterar sobre o DF editado e comparar com o original? 
                    # Não, o jeito mais fácil no Streamlit é pegar o evento de mudança, mas requer session_state complexo.
                    # Vamos fazer algo mais simples: Um botão "Atualizar Linha" dentro de um Expander ou processar em lote.
                    
                    # MELHOR ABORDAGEM: Botão para processar alterações
                    # O user edita, clica em "Salvar Edições".
                    
                    if st.button("💾 Salvar Alterações da Tabela"):
                        # O Streamlit devolve o DF editado completo em 'editado'
                        # Vamos varrer e mandar updates (idealmente só dos alterados, mas pra MVP manda tudo da página é rápido)
                        
                        barra = st.progress(0, text="Salvando...")
                        for index, row in editado.iterrows():
                            # Pega ID original
                            cid = row['id']
                            
                            # Trata Dia Vencimento (Pode ser NaN/None)
                            dia = row['dia_vencimento']
                            if pd.isna(dia) or dia == 0 or str(dia).strip() == "":
                                dia = None
                            else:
                                dia = int(dia)

                            payload_up = {
                                "nome": row['nome'],
                                "dia_vencimento": dia,
                                "etiquetas": row['etiquetas']
                            }
                            requests.put(f"{API_URL}/crm/clientes/{cid}", json=payload_up)
                            barra.progress((index + 1) / len(editado))
                        
                        st.success("Dados atualizados!")
                        time.sleep(1)
                        st.rerun()

                    # --- PAGINAÇÃO (BOTÕES) ---
                    c_ant, c_pag, c_prox = st.columns([1, 2, 1])
                    
                    if c_ant.button("⬅️ Anterior", disabled=(st.session_state.crm_pagina <= 1)):
                        st.session_state.crm_pagina -= 1
                        st.rerun()
                        
                    if c_prox.button("Próxima ➡️", disabled=(st.session_state.crm_pagina >= total_paginas)):
                        st.session_state.crm_pagina += 1
                        st.rerun()
                        
                    # --- BOTÃO DE EXCLUIR (AINDA ÚTIL) ---
                    st.divider()
                    with st.expander("🗑️ Zona de Perigo (Excluir)"):
                        c_del1, c_del2 = st.columns([3, 1])
                        id_del = c_del1.number_input("ID para apagar", min_value=0)
                        if c_del2.button("Excluir Cliente"):
                            requests.delete(f"{API_URL}/crm/clientes/{id_del}")
                            st.rerun()

                else:
                    st.info("Nenhum cliente encontrado com esses filtros.")
            else:
                st.error("Erro ao conectar com servidor.")

        except Exception as e:
            st.error(f"Erro: {e}")
    # -----------------------------------------------
    # 2. DISPARADOR (COM BLOQUEIO DE PLANO 🔒)
    # -----------------------------------------------
    with tab_disparo:
        # 1. VERIFICA O PLANO
        plano_atual = st.session_state.user_info.get('plano', 'Básico')
        
        # Se for Básico, BLOQUEIA TUDO e mostra propaganda
        if plano_atual == "Básico":
            st.empty() # Limpa qualquer coisa anterior
            st.error("🔒 Funcionalidade Bloqueada no Plano Básico")
            
            c_lock1, c_lock2 = st.columns([1, 2])
            with c_lock1:
                st.markdown("# 🚀")
            with c_lock2:
                st.markdown("### Quer vender mais com Disparos em Massa?")
                st.write("O plano Básico é focado apenas em atendimento receptivo.")
                st.write("Faça o upgrade para o **Plano Pro** e libere campanhas ilimitadas!")
                
                if st.button("💎 Quero fazer Upgrade agora", type="primary"):
                    st.session_state.selected = "Minha Assinatura" # Redireciona (precisa ajustar lógica de nav se quiser auto)
                    st.info("Vá na aba 'Minha Assinatura' para trocar de plano.")
        
        # Se for Pro ou Enterprise, LIBERA O CONTEÚDO
        else:
            st.info("💡 Use filtros para selecionar quem vai receber a mensagem hoje.")
            
            # --- CÓDIGO ORIGINAL DO DISPARADOR AQUI ---
            try:
                params_todos = {"itens_por_pagina": 10000, "pagina": 1}
                res = requests.get(f"{API_URL}/crm/clientes/{instancia_selecionada}", params=params_todos)
                
                todos_clientes = []
                if res.status_code == 200:
                    payload = res.json()
                    if isinstance(payload, dict):
                        todos_clientes = payload.get('data', [])
                    elif isinstance(payload, list):
                        todos_clientes = payload
            except:
                todos_clientes = []
                
            if not todos_clientes:
                st.warning("Nenhum cliente cadastrado ou erro ao carregar.")
                st.stop()

            col_f1, col_f2 = st.columns(2)
            filtro_dia = col_f1.checkbox("Filtrar por Dia de Vencimento?")
            dia_selecionado = 0
            if filtro_dia:
                dia_selecionado = col_f1.number_input("Qual dia?", 1, 31, 10)
                
            filtro_tag = col_f2.text_input("Filtrar por Etiqueta (Opcional)", placeholder="Ex: devedor")

            # APLICA FILTRO
            lista_final = []
            for c in todos_clientes:
                passou_dia = True
                passou_tag = True
                
                dia_cliente = c.get('dia_vencimento')
                if not dia_cliente: dia_cliente = 0
                
                if filtro_dia and int(dia_cliente) != dia_selecionado: passou_dia = False
                
                tags_cliente = c.get('etiquetas') or ""
                if filtro_tag and filtro_tag.lower() not in tags_cliente.lower(): passou_tag = False
                
                if passou_dia and passou_tag:
                    lista_final.append(c)
            
            st.markdown(f"### 🎯 Destinatários Selecionados: **{len(lista_final)}**")
            
            if lista_final:
                with st.expander("Ver lista"):
                    for i in lista_final:
                        tel_visual = str(i['telefone']).replace('@s.whatsapp.net', '')
                        st.caption(f"- {i['nome']} ({tel_visual})")

                st.divider()

                # COMPOSITOR
                st.markdown("### ✍️ Conteúdo do Disparo")
                st.caption("Dica: Use **{nome}** para personalizar.")
                
                texto_padrao = "Olá {nome}, confira nossa oferta especial!"
                mensagem = st.text_area("Texto / Legenda:", value=texto_padrao, height=150)
                
                st.markdown("📷 **Imagem ou Vídeo (Opcional)**")
                arquivo_disparo = st.file_uploader("Anexar arquivo", type=["png", "jpg", "jpeg", "pdf", "mp4"], key="up_mass")
                
                usar_menu = st.checkbox("Incluir dica de Menu no final?", value=False)
                
                if st.button(f"🔥 Disparar para {len(lista_final)} pessoas", type="primary"):
                    
                    # A. UPLOAD
                    url_final = None
                    tipo_msg = "texto"
                    
                    if arquivo_disparo:
                        with st.spinner("Subindo arquivo..."):
                            files = {"file": (arquivo_disparo.name, arquivo_disparo, arquivo_disparo.type)}
                            try:
                                res_up = requests.post(f"{API_URL}/upload", files=files)
                                if res_up.status_code == 200:
                                    url_final = res_up.json()["url"]
                                    if arquivo_disparo.type.startswith("image"): tipo_msg = "image"
                                    elif arquivo_disparo.type.startswith("video"): tipo_msg = "video"
                                    elif "pdf" in arquivo_disparo.type: tipo_msg = "document"
                            except:
                                st.error("Erro upload.")
                                st.stop()

                    # B. ENVIA
                    ids = [c['id'] for c in lista_final]
                    payload_mass = {
                        "instancia": instancia_selecionada,
                        "mensagem": mensagem,
                        "lista_ids": ids,
                        "incluir_menu": usar_menu,
                        "url_midia": url_final,
                        "tipo_midia": tipo_msg
                    }
                    
                    with st.spinner(f"Enviando..."):
                        try:
                            r_disp = requests.post(f"{API_URL}/disparo/em-massa", json=payload_mass)
                            if r_disp.status_code == 200:
                                d = r_disp.json()
                                st.balloons()
                                st.success(f"Enviados: {d['enviados']} | Erros: {d['erros']}")
                            else:
                                st.error("Erro no envio.")
                        except Exception as e:
                            st.error(f"Erro: {e}")
            else:
                st.warning("Nenhum cliente corresponde aos filtros.")

# =====================================================
# ABA: MINHA ASSINATURA (FINANCEIRO) 💳
# =====================================================
elif selected == "Minha Assinatura":
    st.subheader("💳 Gestão Financeira")
    
    # Verifica se user_info existe para evitar erros
    if "user_info" in st.session_state:
        u = st.session_state.user_info
    else:
        st.error("Erro: Usuário não carregado. Faça login novamente.")
        st.stop()

    # Cartão de Status
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        col1.metric("Plano Atual", u.get('plano', 'Básico'))
        
        # Tratamento de data para exibir bonito
        venc = u.get('data_vencimento')
        d_venc = "N/A"
        if venc:
            try:
                # Tenta converter se for string isoformat ou datetime
                d_venc = pd.to_datetime(venc).strftime('%d/%m/%Y')
            except:
                d_venc = str(venc)

        col2.metric("Vencimento", d_venc)
        
        status_conta = u.get('status_conta', 'ativo')
        status_cor = "🟢 Ativo" if status_conta == 'ativo' else "🔴 Vencido/Bloqueado"
        col3.metric("Status", status_cor)

    st.divider()
    
    st.markdown("### 🔄 Renovar ou Fazer Upgrade")
    
    # Colunas para o formulário
    c_form1, c_form2 = st.columns([2, 1])

    with c_form1:
        # 1. Seleção de Plano
        lista_planos = ["Básico", "Pro", "Enterprise"]
        plano_atual = u.get('plano', 'Básico')
        # Garante que o plano atual esteja na lista, se não, usa o primeiro (0)
        idx_plano = lista_planos.index(plano_atual) if plano_atual in lista_planos else 0
        
        novo_plano = st.selectbox("Escolha o plano:", lista_planos, index=idx_plano)
        
        # 2. Campo de Cupom
        cupom_renov = st.text_input("🎟️ Cupom de Desconto", placeholder="Tem um código? Digite aqui.")

    with c_form2:
        # 3. Preço e Botão
        # Atualizado com seus preços novos:
        precos = {"Básico": 19.90, "Pro": 39.90, "Enterprise": 49.90} 
        valor_tabela = precos.get(novo_plano, 0.0)
        
        st.markdown(f"<br>**Valor Tabela:** R$ {valor_tabela:.2f}", unsafe_allow_html=True)

        if st.button("Gerar Pagamento", type="primary", use_container_width=True):
            payload = {
                "user_id": u.get('id'),
                "plano": novo_plano,
                "valor": valor_tabela,
                "cupom": cupom_renov
            }
            
            with st.spinner("Processando..."):
                try:
                    res = requests.post(f"{API_URL}/pagamento/gerar", json=payload, timeout=10)
                    
                    if res.status_code == 200:
                        data = res.json()
                        
                        # CASO 1: 100% OFF (Aprovado direto)
                        if data.get("status") == "aprovado_direto":
                            st.balloons()
                            st.success("🎉 Cupom de 100% aplicado! Plano renovado!")
                            
                            # Atualiza sessão local
                            u['status_conta'] = 'ativo'
                            u['plano'] = novo_plano
                            st.session_state.user_info = u
                            time.sleep(2)
                            st.rerun()
                        
                        # CASO 2: PIX GERADO
                        else:
                            st.session_state.pix_renovacao = data
                            valor_final_api = data.get('valor_final', valor_tabela)
                            
                            if valor_final_api < valor_tabela:
                                st.toast(f"🤑 Desconto aplicado! De R${valor_tabela} por R${valor_final_api}", icon="🎉")
                            
                            st.rerun()
                    else:
                        erro_msg = res.json().get('detail', res.text)
                        st.error(f"Erro: {erro_msg}")

                except Exception as e:
                    st.error(f"Erro de conexão: {e}")

    # Exibe Pix se gerado (Persistente na sessão)
    if "pix_renovacao" in st.session_state:
        pix = st.session_state.pix_renovacao
        st.divider()
        st.info("Pague para liberar instantaneamente:")
        
        col_px1, col_px2 = st.columns([1, 2])
        
        with col_px1:
            try:
                img = base64.b64decode(pix['qr_base64'])
                st.image(BytesIO(img), caption="QR Code Pix", use_container_width=True)
            except: 
                st.warning("QR Code imagem indisponível")
        
        with col_px2:
            if 'valor_final' in pix:
                st.markdown(f"### Total a Pagar: R$ {pix['valor_final']:.2f}")
            st.text_area("Copia e Cola", pix['qr_code'])
            
            if st.button("✅ Já Paguei (Atualizar Status)", type="primary"):
                 # Força logout para relogar e atualizar o status vindo do banco
                 st.session_state.autenticado = False
                 st.rerun()

# =====================================================
# TELA DE GESTÃO DE EQUIPE
# =====================================================
def tela_gestao_equipe():
    st.header("👥 Gestão de Equipe")
    u = st.session_state.user_info
    
    # Lista
    try:
        r = requests.get(f"{API_URL}/equipe/listar/{u.get('instancia_wa')}")
        equipe = r.json() if r.status_code == 200 else []
    except: equipe = []
    
    if equipe:
        st.dataframe(equipe)
    else:
        st.info("Nenhum atendente cadastrado.")
    
    st.divider()
    st.subheader("Novo Atendente")
    with st.form("novo_atendente"):
        nome = st.text_input("Nome")
        usuario = st.text_input("Usuário Login")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Cadastrar"):
            payload = {
                "admin_id": u.get('id', 1),
                "nome": nome,
                "usuario": usuario,
                "senha": senha,
                "instancia": u.get('instancia_wa')
            }
            try:
                requests.post(f"{API_URL}/equipe/criar", json=payload)
                st.success("Criado!")
                time.sleep(1)
                st.rerun()
            except: st.error("Erro ao criar")