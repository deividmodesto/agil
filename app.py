import streamlit as st
import requests
import base64
import time, datetime
import pandas as pd 
from io import BytesIO
from PIL import Image
from streamlit_option_menu import option_menu
import graphviz
import os # <--- NOVO
from dotenv import load_dotenv # <--- NOVO

# =====================================================
# CARREGAR VARIÁVEIS DE AMBIENTE (.ENV)
# =====================================================
load_dotenv()

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

# =====================================================
# CONFIGURAÇÕES DE API (VIA .ENV)
# =====================================================
# Aqui conectamos com as variáveis que definimos no arquivo .env
API_URL = os.getenv("LOCAL_URL", "http://127.0.0.1:8000") # Backend Python
EVO_URL = os.getenv("EVO_API_URL", "http://127.0.0.1:8080") # Evolution API
EVO_API_KEY = os.getenv("EVO_API_KEY", "SUA_KEY_AQUI")

HEADERS_EVO = {
    "apikey": EVO_API_KEY,
    "Content-Type": "application/json"
}

# =====================================================
# 🚨 NOVO: VERIFICAÇÃO DE RETORNO DO PAGAMENTO (CARTÃO)
# =====================================================
# Isso captura quando o usuário volta do Mercado Pago
params = st.query_params

if params.get("status_mp") == "aprovado":
    uid_pag = params.get("uid")
    plano_pag = params.get("plano")
    
    try:
        # Confirma no backend
        requests.get(f"{API_URL}/pagamento/confirmar_sucesso?uid={uid_pag}&plano={plano_pag}")
        
        st.toast("✅ Pagamento via Cartão Aprovado!", icon="💳")
        st.balloons()
        
        # Limpa URL e recarrega
        time.sleep(3)
        st.query_params.clear()
        st.rerun()
        
    except Exception as e:
        st.error(f"Erro ao validar pagamento: {e}")

elif params.get("status_mp") == "falha":
    st.error("O pagamento foi cancelado ou recusado.")
    st.query_params.clear()


# =====================================================
# FUNÇÕES ÚTEIS
# =====================================================
def verificar_status_whatsapp(instancia):
    """
    Verifica se a instância está conectada na Evolution API.
    Retorna True se estiver "open" (conectado).
    """
    try:
        url_evo = EVO_URL 
        headers_evo = {"apikey": EVO_API_KEY} 
        
        res = requests.get(f"{url_evo}/instance/connectionState/{instancia}", headers=headers_evo, timeout=2)
        
        if res.status_code == 200:
            dados = res.json()
            estado = dados.get("instance", {}).get("state") or dados.get("state")
            return estado == "open"
        return False
    except:
        return False
    
# =====================================================
# FUNÇÃO DE LOGIN COMPLETA (VISUAL + RECUPERAÇÃO 🔐)
# =====================================================
def login_sistema():
    
    # ---------------------------------------------------------
    # 1. VERIFICA SE O USUÁRIO VEIO PELO LINK DE RECUPERAÇÃO
    # ---------------------------------------------------------
    params = st.query_params
    reset_token = params.get("reset_token")

    if reset_token:
        # Fundo escuro simples para focar na redefinição
        st.markdown("""<style>.stApp {background-color: #111;}</style>""", unsafe_allow_html=True)
        
        st.write(""); st.write("")
        c1, c2, c3 = st.columns([1, 1, 1])
        with c2:
            st.info("🔐 Criar Nova Senha")
            with st.form("form_nova_senha"):
                st.caption("Digite sua nova senha abaixo:")
                nova_senha = st.text_input("Nova Senha", type="password")
                confirma_senha = st.text_input("Confirme a Senha", type="password")
                
                if st.form_submit_button("💾 Salvar Nova Senha", type="primary", use_container_width=True):
                    if nova_senha != confirma_senha:
                        st.error("As senhas não coincidem.")
                    elif len(nova_senha) < 4:
                        st.error("A senha deve ter no mínimo 4 caracteres.")
                    else:
                        try:
                            res = requests.post(f"{API_URL}/publico/recuperar-senha/confirmar", 
                                                json={"token": reset_token, "nova_senha": nova_senha})
                            
                            if res.status_code == 200:
                                st.success("✅ Senha alterada com sucesso!")
                                time.sleep(2)
                                st.query_params.clear() # Limpa URL
                                st.rerun() # Recarrega para ir ao login
                            else:
                                erro_msg = res.json().get('detail', 'Erro desconhecido.')
                                st.error(f"Erro: {erro_msg}")
                        except Exception as e:
                            st.error(f"Erro de conexão: {e}")
            
            if st.button("Cancelar / Voltar ao Login"):
                st.query_params.clear()
                st.rerun()
        return # Interrompe a função aqui para não mostrar o resto

    # ---------------------------------------------------------
    # 2. TELA DE LOGIN PADRÃO
    # ---------------------------------------------------------
    if "pagina_atual" not in st.session_state: st.session_state.pagina_atual = "login"
    if "esqueci_senha_mode" not in st.session_state: st.session_state.esqueci_senha_mode = False

    # CSS (Seu estilo original + Ajustes)
    st.markdown("""
    <style>
    /* Imagem de Fundo */
    .stApp {
        background-image: linear-gradient(rgba(0, 0, 0, 0.75), rgba(0, 0, 0, 0.85)), 
        url("https://images.unsplash.com/photo-1451187580459-43490279c0fa?q=80&w=2072&auto=format&fit=crop");
        background-size: cover; background-position: center; background-attachment: fixed;
    }
    
    /* Textos em Branco */
    h1, h2, h3, h4, h5, p, label, span { color: #FFFFFF !important; }
    .stTextInput label p { font-size: 14px !important; }
    
    /* Container de Login Escuro */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background-color: rgba(20, 20, 20, 0.95);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 30px;
    }
    
    /* BOTÃO SECUNDÁRIO (Ghost Button - Criar Conta) */
    [data-testid="stBaseButton-secondary"] {
        background-color: transparent !important;
        border: 1px solid rgba(255, 255, 255, 0.5) !important;
        color: #FFFFFF !important;
    }
    [data-testid="stBaseButton-secondary"]:hover {
        background-color: rgba(255, 255, 255, 0.1) !important;
        border-color: #FFFFFF !important;
        color: #FFFFFF !important;
    }

    header {visibility: hidden;}
    </style>
    """, unsafe_allow_html=True)

    if st.session_state.pagina_atual == "login":
        st.write(""); st.write("") 

        c_esq, c_centro, c_dir = st.columns([1, 1.2, 1])

        with c_centro:
            
            # --- MODO 1: RECUPERAR SENHA (DIGITAR EMAIL) ---
            if st.session_state.esqueci_senha_mode:
                 # Logo Pequena
                cl_1, cl_2, cl_3 = st.columns([1, 1, 1])
                with cl_2:
                    try: st.image("logo.png", width=80)
                    except: st.markdown("<h1 style='text-align: center;'>🔐</h1>", unsafe_allow_html=True)

                st.markdown("<h3 style='text-align: center;'>Recuperar Acesso</h3>", unsafe_allow_html=True)
                
                with st.container(border=True):
                    st.info("Informe seu e-mail. Enviaremos um link seguro para você redefinir sua senha.")
                    email_recup = st.text_input("Seu E-mail Cadastrado")
                    
                    st.write("")
                    if st.button("📩 Enviar Link de Recuperação", type="primary", use_container_width=True):
                        if not email_recup:
                            st.warning("Por favor, digite o e-mail.")
                        else:
                            with st.spinner("Verificando..."):
                                try:
                                    res = requests.post(f"{API_URL}/publico/recuperar-senha/solicitar", json={"email": email_recup})
                                    if res.status_code == 200:
                                        st.success("✅ E-mail enviado! Verifique sua caixa de entrada e spam.")
                                    else:
                                        st.error("Erro ao solicitar. Tente novamente.")
                                except Exception as e:
                                    st.error(f"Erro de conexão: {e}")

                    if st.button("⬅️ Voltar ao Login"):
                        st.session_state.esqueci_senha_mode = False
                        st.rerun()

            # --- MODO 2: LOGIN NORMAL ---
            else:
                # Logo Grande
                cl_1, cl_2, cl_3 = st.columns([1, 1, 1])
                with cl_2:
                    try: st.image("logo.png", width=100)
                    except: st.markdown("<h1 style='text-align: center;'>🚀</h1>", unsafe_allow_html=True)

                st.markdown("<h2 style='text-align: center; margin-bottom: 20px;'>Acesso ao Sistema</h2>", unsafe_allow_html=True)
                
                with st.container(border=True):
                    login_input = st.text_input("Usuário", placeholder="Seu login")
                    senha_input = st.text_input("Senha", type="password", placeholder="••••••")
                    
                    st.write("")
                    
                    # BOTÃO ENTRAR
                    if st.button("🔐 ENTRAR", type="primary", use_container_width=True):
                        if not login_input or not senha_input:
                            st.warning("Preencha todos os campos.")
                        else:
                            with st.spinner("Conectando..."):
                                sucesso = False
                                
                                # 1. TENTATIVA ADMIN
                                try:
                                    r_adm = requests.post(f"{API_URL}/login", json={"login": login_input, "senha": senha_input}, timeout=5)
                                    if r_adm.status_code == 200:
                                        dados = r_adm.json().get('usuario', {})
                                        status = dados.get("status_conta")
                                        
                                        if status == "ativo" or status == "pendente": # Pendente pode logar pra pagar
                                            st.session_state.user_info = dados
                                            st.session_state.user_info['tipo_acesso'] = 'admin'
                                            st.session_state.autenticado = True
                                            sucesso = True
                                        elif status == "bloqueado":
                                            st.error("🚫 Conta Bloqueada.")
                                            sucesso = True # Para não tentar logar como equipe
                                        elif status == "vencido":
                                            st.warning("⚠️ Conta Vencida. Renove seu plano.")
                                            st.session_state.user_info = dados
                                            st.session_state.user_info['tipo_acesso'] = 'admin'
                                            st.session_state.autenticado = True
                                            sucesso = True
                                except: pass

                                # 2. TENTATIVA EQUIPE
                                if not sucesso:
                                    try:
                                        r_func = requests.post(f"{API_URL}/equipe/login", json={"usuario": login_input, "senha": senha_input}, timeout=5)
                                        if r_func.status_code == 200:
                                            dados = r_func.json()
                                            dados['instancia_wa'] = dados.get('instancia')
                                            dados['nome_cliente'] = dados.get('nome')
                                            dados['tipo_acesso'] = 'funcionario'
                                            
                                            st.session_state.user_info = dados
                                            st.session_state.autenticado = True
                                            sucesso = True
                                    except: pass

                                if sucesso and st.session_state.autenticado:
                                    st.toast(f"Bem-vindo, {st.session_state.user_info.get('nome_cliente')}!")
                                    time.sleep(0.5)
                                    st.rerun()
                                elif not sucesso:
                                    st.error("❌ Usuário ou senha incorretos.")

                    # LINK ESQUECI A SENHA (Discreto)
                    col_esq, col_dir = st.columns([1.5, 1])
                    with col_dir:
                        if st.button("Esqueci minha senha", key="btn_forgot"):
                            st.session_state.esqueci_senha_mode = True
                            st.rerun()

                # BOTÃO CRIAR CONTA (CSS Customizado Ghost)
                st.markdown("---") 
                st.markdown("<div style='text-align: center; color: #cccccc; font-size: 13px; margin-bottom: 5px;'>Não tem conta?</div>", unsafe_allow_html=True)
                
                if st.button("✨ Criar Nova Conta (Admin)", use_container_width=True):
                    st.session_state.pagina_atual = "registro"
                    st.rerun()

    # ==========================================================
    # 📝 TELA DE REGISTRO (CORRIGIDA E BLINDADA)
    # ==========================================================
    elif st.session_state.pagina_atual == "registro":
        st.write("") 

        c1, c2, c3 = st.columns([1, 2, 1]) 
        
        with c2:
            with st.container(border=True):
                
                # Variável para controlar o link do Cartão
                if "reg_card_url" not in st.session_state: 
                    st.session_state.reg_card_url = None

                # --- CENÁRIO 1: LINK DE CARTÃO GERADO (MOSTRA O BOTÃO) ---
                if st.session_state.reg_card_url:
                    st.success("✅ Pré-cadastro realizado!")
                    st.info("Clique no botão abaixo para finalizar o pagamento seguro:")
                    
                    st.markdown("### 👇")
                    st.link_button("💳 PAGAR COM CARTÃO AGORA", st.session_state.reg_card_url, type="primary", use_container_width=True)
                    st.markdown("### 👆")
                    
                    st.markdown("---")
                    st.caption("Ao clicar, você será levado ao Mercado Pago.")
                    
                    if st.button("🔄 Cancelar / Voltar"):
                        st.session_state.reg_card_url = None
                        st.rerun()

                # --- CENÁRIO 2: PIX GERADO (MOSTRA O QR CODE) ---
                elif "dados_pix" in st.session_state:
                    st.success("✅ Conta criada com sucesso!")
                    st.markdown("<p style='text-align:center'>Escaneie o QR Code abaixo para liberar seu acesso.</p>", unsafe_allow_html=True)
                    
                    pix_data = st.session_state.dados_pix
                    val_final = pix_data.get('valor_final')
                    
                    if val_final:
                        st.markdown(f"<h1 style='text-align: center; color: #4cd137 !important;'>R$ {val_final:.2f}</h1>", unsafe_allow_html=True)

                    c_qr1, c_qr2, c_qr3 = st.columns([1, 2, 1])
                    with c_qr2:
                        try:
                            img_data = base64.b64decode(pix_data['qr_base64'])
                            st.image(BytesIO(img_data), caption="QR Code Pix", use_container_width=True)
                        except:
                            st.warning("QR Code visual indisponível.")

                    st.text_area("Copia e Cola:", value=pix_data['qr_code'])
                    
                    if st.button("🚀 Já Paguei! Acessar Sistema", type="primary", use_container_width=True):
                        del st.session_state.dados_pix
                        st.session_state.pagina_atual = "login"
                        st.rerun()

                # --- CENÁRIO 3: FORMULÁRIO DE CADASTRO ---
                else:
                    st.markdown("### ✨ Crie sua conta")
                    
                    # 1. Busca Planos e Regras do Backend
                    try:
                        res = requests.get(f"{API_URL}/planos/listar")
                        lista_db = res.json() if res.status_code == 200 else []
                    except: lista_db = []

                    # 2. Processa os Detalhes para Exibir
                    detalhes_planos = {}
                    if lista_db and isinstance(lista_db, list):
                        for p in lista_db:
                            if p.get('ativo', True):
                                regras = p.get('regras', {})
                                itens = []
                                
                                # -- Traduzindo as regras do banco para texto --
                                
                                # Gatilhos
                                gat = int(regras.get('max_gatilhos', 5))
                                itens.append(f"🤖 **{gat if gat > 0 else 'Ilimitados'}** Gatilhos Inteligentes")
                                
                                # Atendentes / Equipe
                                users = int(regras.get('max_atendentes', 1))
                                itens.append(f"👥 Equipe: **{users}** usuário(s)")
                                
                                # Conexões de WhatsApp
                                conns = int(regras.get('max_conexoes', 1))
                                itens.append(f"📱 Conexões: **{conns}** WhatsApp(s)")

                                # Funcionalidades Booleanas (Sim/Não)
                                if regras.get('permite_disparos'): itens.append("📢 Disparos em Massa")
                                if regras.get('atendimento_humano'): itens.append("🎧 Chat Humano")
                                if regras.get('acesso_crm'): itens.append("📊 CRM & Funil de Vendas")
                                
                                detalhes_planos[p['nome']] = {"valor": float(p['valor']), "itens": itens}
                    
                    # Fallback caso não tenha nada no banco
                    if not detalhes_planos:
                        detalhes_planos = {"Padrão": {"valor": 0.0, "itens": ["Sem detalhes"]}}
                    
                    # --- INTERFACE DE SELEÇÃO ---
                    cp1, cp2 = st.columns([1.5, 1])
                    with cp1:
                        plano_selecionado = st.selectbox("Escolha o Plano Ideal", list(detalhes_planos.keys()))
                    with cp2:
                        val = detalhes_planos[plano_selecionado]['valor']
                        # --- CORREÇÃO VISUAL (DARK MODE) ---
                        # Fundo escuro translúcido com texto verde neon
                        st.markdown(f"""
                        <div style='border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 8px; padding: 10px; text-align: center; background-color: rgba(0, 0, 0, 0.2);'>
                            <span style='color: #4cd137; font-size: 24px; font-weight: bold;'>R$ {val:.2f}</span>
                            <span style='font-size: 12px; color: #cccccc;'> /mês</span>
                        </div>
                        """, unsafe_allow_html=True)
                    
                    # --- 🌟 AQUI ESTÁ A MÁGICA: EXIBIR OS BENEFÍCIOS ---
                    with st.container(border=True):
                        st.caption(f"Incluso no plano **{plano_selecionado}**:")
                        
                        # Divide os itens em 2 colunas para ficar elegante
                        lista_itens = detalhes_planos[plano_selecionado]['itens']
                        ci1, ci2 = st.columns(2)
                        
                        for i, item in enumerate(lista_itens):
                            # Alterna entre coluna 1 e 2
                            coluna = ci1 if i % 2 == 0 else ci2
                            coluna.markdown(f"✅ {item}")

                    st.markdown("---")

                    # FORMULÁRIO DE DADOS PESSOAIS
                    with st.form("form_reg"):
                        c_form1, c_form2 = st.columns(2)
                        with c_form1:
                            nome = st.text_input("Nome Completo")
                            zap = st.text_input("WhatsApp (Ex: 11999998888)")
                            instancia = st.text_input("Nome da Instância (Ex: minhaempresa)")
                        with c_form2:
                            email = st.text_input("E-mail")
                            login = st.text_input("Crie seu Login")
                            senha = st.text_input("Crie sua Senha", type="password")
                        
                        # --- SELETOR DE PAGAMENTO ROBUSTO ---
                        OPCAO_PIX = "💠 Pix (Liberado na Hora)"
                        OPCAO_CARTAO = "💳 Cartão de Crédito"
                        
                        c_pay1, c_pay2 = st.columns([1, 1])
                        with c_pay1:
                            cupom = st.text_input("🎟️ Cupom de Desconto", placeholder="Opcional")
                        with c_pay2:
                            metodo_pag = st.radio("Forma de Pagamento", [OPCAO_PIX, OPCAO_CARTAO], horizontal=True)
                        
                        st.write("")

                        if st.form_submit_button("✅ Finalizar Assinatura", type="primary", use_container_width=True):
                            # ... (O RESTO DO CÓDIGO DE ENVIO CONTINUA IGUAL AO ORIGINAL) ...
                            if not (nome and email and login and senha and instancia):
                                st.warning("⚠️ Preencha todos os campos obrigatórios!")
                            else:
                                payload = {
                                    "nome": nome, "email": email, "whatsapp": zap,
                                    "login": login, "instancia": instancia, "senha": senha,
                                    "plano": plano_selecionado, 
                                    "cupom": cupom
                                }
                                # (Mantém a lógica de envio Pix/Cartão original aqui...)
                                if metodo_pag == OPCAO_CARTAO:
                                    with st.spinner("Gerando link seguro..."):
                                        try:
                                            res = requests.post(f"{API_URL}/publico/registrar_cartao", json=payload)
                                            if res.status_code == 200:
                                                url = res.json().get("checkout_url")
                                                st.session_state.reg_card_url = url
                                                st.rerun()
                                            else:
                                                st.error(f"Erro no Cartão: {res.json().get('detail')}")
                                        except Exception as e:
                                            st.error(f"Erro de conexão (Cartão): {e}")

                                else:
                                    with st.spinner("Gerando Pix..."):
                                        try:
                                            res = requests.post(f"{API_URL}/publico/registrar", json=payload, timeout=20)
                                            if res.status_code == 200:
                                                st.session_state.dados_pix = res.json()
                                                st.rerun()
                                            else:
                                                st.error(f"Erro no Pix: {res.json().get('detail')}")
                                        except Exception as e:
                                            st.error(f"Erro de conexão (Pix): {e}")

                    if st.button("⬅️ Voltar ao Login", type="secondary", use_container_width=True):
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
        requests.post(f"{API_URL}/instance/configurar/{nome_instancia}", timeout=5)
        return True
    except Exception as e:
        print(f"Erro ao configurar auto: {e}")
        return False

# =====================================================
# TELA DE GESTÃO DE EQUIPE (FUNÇÃO)
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
        res = requests.get(f"{API_URL}/equipe/listar/{instancia}")
        equipe = res.json() if res.status_code == 200 else []
    except: equipe = []

    # Layout: Coluna 1 (Lista) | Coluna 2 (Cadastro)
    col_lista, col_form = st.columns([1.5, 1])

    with col_lista:
        st.markdown("### 📋 Atendentes Ativos")
        if not equipe:
            st.info("Nenhum atendente cadastrado.")
        else:
            for func in equipe:
                with st.container(border=True):
                    c1, c2, c3 = st.columns([0.5, 2, 1])
                    c1.markdown("## 👤")
                    with c2:
                        st.write(f"**{func['nome']}**")
                        st.caption(f"Login: `{func['usuario']}`")
                    with c3:
                        st.write("") 
                        if st.button("🗑️", key=f"del_team_{func['id']}", help="Remover acesso"):
                            try:
                                res = requests.delete(f"{API_URL}/equipe/excluir/{func['id']}")
                                if res.status_code == 200:
                                    st.toast(f"{func['nome']} removido!")
                                    time.sleep(1)
                                    st.rerun()
                                else:
                                    st.error("Erro ao excluir.")
                            except Exception as e:
                                st.error(f"Erro: {e}")

    with col_form:
        with st.container(border=True):
            st.markdown("### ➕ Novo Acesso")
            with st.form("novo_atendente"):
                nome = st.text_input("Nome do Funcionário", placeholder="Ex: Maria")
                usuario = st.text_input("Login de Acesso", placeholder="Ex: maria.vendas")
                senha = st.text_input("Senha", type="password")
                
                if st.form_submit_button("🚀 Criar Acesso", type="primary", use_container_width=True):
                    if nome and usuario and senha:
                        payload = {
                            "admin_id": u.get('id', 1),
                            "nome": nome, "usuario": usuario, "senha": senha,
                            "instancia": instancia
                        }
                        try:
                            r = requests.post(f"{API_URL}/equipe/criar", json=payload)
                            if r.status_code == 200:
                                st.success("Atendente cadastrado!")
                                time.sleep(1)
                                st.rerun()
                            else:
                                erro = r.json().get('detail', 'Erro ao criar')
                                st.error(f"Erro: {erro}")
                        except Exception as e:
                            st.error(f"Erro de conexão: {e}")
                    else:
                        st.warning("Preencha todos os campos.")

# =====================================================
# COMPONENTE: CHAT COM AUTO-REFRESH 🔄
# =====================================================
@st.fragment(run_every=3) 
def painel_mensagens_auto(instancia, cliente, nome_usuario):
    chat_container = st.container(height=500)
    
    with chat_container:
        try:
            r = requests.get(f"{API_URL}/chat/local/{instancia}/{cliente['remote_jid']}")
            msgs = r.json() if r.status_code == 200 else []
            
            if not msgs: 
                st.info("👋 Histórico vazio. Mande a primeira mensagem!")
            
            for m in msgs:
                role = "assistant" if m['fromMe'] else "user"
                avatar = "👨‍💻" if m['fromMe'] else "👤"
                texto = m['text'] or ""
                
                display_text = ""
                if m['fromMe']:
                    nome_msg = m.get('nome_atendente') or "Atendente"
                    display_text = f"**{nome_msg}:**"

                with st.chat_message(role, avatar=avatar):
                    if display_text: st.markdown(display_text)
                    
                    eh_img = "http" in texto and any(x in texto for x in [".jpg", ".png", ".jpeg"])
                    eh_audio = "http" in texto and any(x in texto for x in [".mp3", ".ogg", ".wav"])
                    
                    if eh_img: st.image(texto, width=400)
                    elif eh_audio: st.audio(texto)
                    else: st.markdown(texto)
                    
                    if m.get('timestamp'):
                        try:
                            ts = pd.to_datetime(m['timestamp']).strftime('%H:%M')
                            st.caption(f"_{ts}_")
                        except: pass
        except Exception as e:
            st.error(f"Erro chat: {e}")


# =====================================================
# TELA ATENDENTE 6.0 (CRM COMPLETO + HISTÓRICO) 🌟
# =====================================================
def tela_atendente():
    if 'user_info' not in st.session_state: return

    u = st.session_state.user_info
    nome_usuario = u.get('nome') or u.get('nome_cliente') or u.get('usuario') or "Atendente"
    instancia = u.get('instancia_wa')
    
    c_head1, c_head2 = st.columns([6, 1])
    c_head1.markdown(f"### 🎧 Workspace: {nome_usuario}")
    if c_head2.button("Sair", key="logout_atend"):
        st.session_state.autenticado = False
        st.rerun()
    st.divider()

    col_lista, col_chat = st.columns([1.3, 2.5])
    
    # --- COLUNA ESQUERDA ---
    with col_lista:
        tab_ativos, tab_encerrados, tab_contatos = st.tabs(["📥 Em Aberto", "🏁 Encerrados", "📒 Contatos"])
        
        with tab_ativos:
            if st.button("🔄 Atualizar", key="btn_at_1", use_container_width=True): st.rerun()
            try:
                res = requests.get(f"{API_URL}/atendimentos/{instancia}")
                ativos = res.json() if res.status_code == 200 else []
            except: ativos = []
            
            if not ativos: st.info("Nenhum atendimento ativo.")
            
            for item in ativos:
                telefone = item['remote_jid'].split('@')[0]
                nome_crm = item.get('nome_crm') 
                titulo = f"👤 {nome_crm}" if nome_crm else f"📱 {telefone}"
                subtitulo = f"📱 {telefone}" if nome_crm else "Sem nome salvo"

                hora = pd.to_datetime(item['data_inicio']).strftime('%H:%M')
                selecionado = st.session_state.get('chat_atual', {}).get('id') == item['id']
                borda = "2px solid #00C853" if selecionado else "1px solid #ddd"
                bg = "#e8f5e9" if selecionado else "transparent"
                
                with st.container():
                    st.markdown(f"""
                    <div style="border: {borda}; background-color: {bg}; border-radius: 8px; padding: 10px; margin-bottom: 8px; cursor: pointer;">
                        <strong>{titulo}</strong><br>
                        <span style="font-size: 12px; color: #555;">{subtitulo}</span><br>
                        <span style="font-size: 11px; color: gray;">⏳ Aberto às {hora}</span>
                    </div>""", unsafe_allow_html=True)
                    
                    if st.button(f"Abrir", key=f"open_{item['id']}", use_container_width=True):
                        if nome_crm: item['nome_crm'] = nome_crm
                        st.session_state.chat_atual = item
                        st.rerun()

        with tab_encerrados:
            c_filtro, c_refresh = st.columns([3, 1])
            with c_filtro:
                import datetime as dt_module
                hoje = dt_module.datetime.now()
                data_busca = st.date_input("Filtrar por data", value=hoje, label_visibility="collapsed")
            with c_refresh:
                if st.button("🔄", key="btn_at_2", use_container_width=True): st.rerun()

            try:
                params = {"data": str(data_busca)}
                res = requests.get(f"{API_URL}/atendimentos/concluidos/{instancia}", params=params)
                encerrados = res.json() if res.status_code == 200 else []
            except: encerrados = []
            
            if not encerrados: st.info(f"Nenhum atendimento finalizado em {data_busca.strftime('%d/%m')}.")
            else:
                for item in encerrados:
                    tel = item['remote_jid'].split('@')[0]
                    quem_fechou = item.get('nome_atendente') or "Sistema"
                    hora_fim = pd.to_datetime(item['data_fim']).strftime('%H:%M')
                    nome_crm = item.get('nome_crm')
                    titulo = f"🏁 {nome_crm}" if nome_crm else f"🏁 {tel}"
                    
                    with st.container():
                        st.markdown(f"""
                        <div style="border: 1px solid #eee; border-radius: 6px; padding: 8px; margin-bottom: 8px; background-color: #f9f9f9; display: flex; justify-content: space-between;">
                            <div>
                                <span style="font-weight: bold; font-size: 14px; color: #333;">{titulo}</span><br>
                                <span style="font-size: 12px; color: #666;">Por: {quem_fechou}</span>
                            </div>
                            <span style="font-size: 11px; color: gray;">{hora_fim}</span>
                        </div>""", unsafe_allow_html=True)
                        
                        if st.button("↺ Reabrir", key=f"reopen_{item['id']}", use_container_width=True):
                            requests.post(f"{API_URL}/atendimentos/reabrir", json={"instancia": instancia, "remote_jid": item['remote_jid']})
                            st.toast(f"Conversa reaberta!")
                            time.sleep(0.5)
                            st.rerun()

        with tab_contatos:
            busca = st.text_input("🔍 Buscar...", placeholder="Nome ou telefone")
            try:
                params = {"busca": busca, "itens_por_pagina": 20} if busca else {"itens_por_pagina": 50}
                res_crm = requests.get(f"{API_URL}/crm/clientes/{instancia}", params=params)
                contatos = res_crm.json().get('data', []) if res_crm.status_code == 200 else []
            except: contatos = []
            
            if not contatos: st.caption("Vazio.")
            for c in contatos:
                with st.expander(f"👤 {c['nome']}"):
                    st.caption(f"Tel: {c['telefone'].split('@')[0]}")
                    if st.button("💬 Chamar", key=f"start_{c['id']}"):
                        requests.post(f"{API_URL}/atendimentos/abrir", json={"instancia": instancia, "remote_jid": c['telefone']})
                        st.rerun()

    # --- COLUNA DIREITA ---
    with col_chat:
        if "chat_atual" in st.session_state:
            cliente = st.session_state.chat_atual
            nome_topo = cliente.get('nome_crm') or cliente['remote_jid'].split('@')[0]
            tel_topo = cliente['remote_jid'].split('@')[0]
            
            topo_c1, topo_c2, topo_c3 = st.columns([0.5, 4, 2])
            topo_c1.markdown("## 👤")
            
            with topo_c2:
                col_n, col_e = st.columns([3, 1])
                col_n.markdown(f"### {nome_topo}")
                with col_e:
                    with st.popover("✏️", help="Editar Nome"):
                        novo_nome = st.text_input("Nome:", value=nome_topo if cliente.get('nome_crm') else "")
                        if st.button("💾 Salvar"):
                            if novo_nome:
                                r = requests.post(f"{API_URL}/crm/salvar_nome_rapido", json={"instancia": instancia, "remote_jid": cliente['remote_jid'], "nome": novo_nome})
                                if r.status_code == 200:
                                    st.toast("Nome salvo!")
                                    st.session_state.chat_atual['nome_crm'] = novo_nome
                                    time.sleep(1)
                                    st.rerun()

            with topo_c3:
                with st.popover("🏁 Finalizar", use_container_width=True):
                    if st.button("👋 Tchau e Arquivar", use_container_width=True):
                        msg = f"*{nome_usuario}:* Atendimento encerrado. Obrigado!"
                        requests.post(f"{EVO_URL}/message/sendText/{instancia}", json={"number": cliente['remote_jid'], "text": msg}, headers=HEADERS_EVO)
                        requests.post(f"{API_URL}/chat/salvar_manual", json={"instancia": instancia, "remote_jid": cliente['remote_jid'], "texto": msg, "nome_atendente": nome_usuario})
                        requests.post(f"{API_URL}/atendimentos/finalizar/{cliente['id']}", json={"nome_atendente": nome_usuario})
                        del st.session_state.chat_atual
                        st.rerun()

                    if st.button("🤫 Só Arquivar", use_container_width=True):
                        requests.post(f"{API_URL}/atendimentos/finalizar/{cliente['id']}", json={"nome_atendente": nome_usuario})
                        del st.session_state.chat_atual
                        st.rerun()

            if cliente.get('nome_crm'): st.caption(f"📞 WhatsApp: {tel_topo}")
            st.divider()
            
            painel_mensagens_auto(instancia, cliente, nome_usuario)

            with st.container():
                c_anexo, c_input = st.columns([1, 10])
                with c_anexo:
                    with st.popover("📎"):
                        tab_up, tab_mic = st.tabs(["Arquivo", "Áudio"])
                        with tab_up:
                            arq = st.file_uploader("Arquivo", key="up_pop_final")
                            if arq and st.button("Enviar 📤", key="btn_up_final"):
                                files = {"file": (arq.name, arq, arq.type)}
                                r_up = requests.post(f"{API_URL}/upload", files=files)
                                if r_up.status_code == 200:
                                    url_m = r_up.json()["url"]
                                    arq.seek(0)
                                    b64 = base64.b64encode(arq.read()).decode('utf-8')
                                    tipo = "image" if "image" in arq.type else "document"
                                    requests.post(f"{EVO_URL}/message/sendMedia/{instancia}", 
                                                  json={"number": cliente['remote_jid'], "media": b64, "mediatype": tipo, "mimetype": arq.type, "fileName": arq.name, "caption": f"*{nome_usuario}:* Arquivo"}, headers=HEADERS_EVO)
                                    requests.post(f"{API_URL}/chat/salvar_manual", 
                                                  json={"instancia": instancia, "remote_jid": cliente['remote_jid'], "texto": url_m, "tipo": "imagem" if "image" in arq.type else "documento", "nome_atendente": nome_usuario})
                                    st.rerun()
                        with tab_mic:
                            audio = st.audio_input("Gravar")
                            if audio and st.button("Enviar 🎤", key="btn_mic_final"):
                                files = {"file": ("voz.wav", audio, "audio/wav")}
                                r_up = requests.post(f"{API_URL}/upload", files=files)
                                if r_up.status_code == 200:
                                    url_a = r_up.json()["url"]
                                    audio.seek(0)
                                    b64 = base64.b64encode(audio.read()).decode('utf-8')
                                    requests.post(f"{EVO_URL}/message/sendWhatsAppAudio/{instancia}", 
                                                  json={"number": cliente['remote_jid'], "audio": b64, "encoding": True}, headers=HEADERS_EVO)
                                    requests.post(f"{API_URL}/chat/salvar_manual", 
                                                  json={"instancia": instancia, "remote_jid": cliente['remote_jid'], "texto": url_a, "tipo": "audio", "nome_atendente": nome_usuario})
                                    st.rerun()

                if prompt := st.chat_input("Mensagem...", key="chat_in_final"):
                    msg_fmt = f"*{nome_usuario}:* {prompt}"
                    requests.post(f"{EVO_URL}/message/sendText/{instancia}", json={"number": cliente['remote_jid'], "text": msg_fmt}, headers=HEADERS_EVO)
                    requests.post(f"{API_URL}/chat/salvar_manual", json={"instancia": instancia, "remote_jid": cliente['remote_jid'], "texto": prompt, "nome_atendente": nome_usuario})
                    time.sleep(0.5)
                    st.rerun()
        else:
            with st.container(border=True):
                st.markdown("### 👋 Bem-vindo")
                st.info("Selecione um chat ativo ou reabra um encerrado.")


def tela_agenda_tarefas():
    st.header("📅 Agenda de Follow-up")
    st.caption("Gerencie todos os seus compromissos e retornos em um só lugar.")
    
    if 'user_info' not in st.session_state: return
    instancia = st.session_state.user_info.get('instancia_wa')
    
    # 1. Filtros e Métricas
    col_kpi, col_filtro = st.columns([2, 1])
    
    with col_filtro:
        ver_tudo = st.toggle("Mostrar tarefas concluídas", value=False)
    
    # 2. Busca Dados
    try:
        url = f"{API_URL}/crm/tarefas/todas/{instancia}"
        if not ver_tudo: url += "?apenas_pendentes=true"
        
        # Anti-cache
        import random
        res = requests.get(f"{url}&_={random.randint(1,9999)}" if "?" in url else f"{url}?_={random.randint(1,9999)}")
        tarefas = res.json() if res.status_code == 200 else []
    except: tarefas = []
    
    # Cálculos Rápidos
    import datetime
    hoje = datetime.datetime.now()
    atrasadas = [t for t in tarefas if not t['concluido'] and pd.to_datetime(t['data_limite']) < hoje]
    hoje_tasks = [t for t in tarefas if not t['concluido'] and pd.to_datetime(t['data_limite']).date() == hoje.date()]
    
    with col_kpi:
        c1, c2, c3 = st.columns(3)
        c1.metric("🔥 Atrasadas", len(atrasadas))
        c2.metric("📅 Para Hoje", len(hoje_tasks))
        c3.metric("📝 Total Pendente", len([t for t in tarefas if not t['concluido']]))

    st.divider()

    if not tarefas:
        st.info("🎉 Nenhuma tarefa pendente! Você está em dia.")
        return

    # 3. Agrupamento por Data (Estilo Agenda)
    df = pd.DataFrame(tarefas)
    df['dt_obj'] = pd.to_datetime(df['data_limite'])
    df['data_str'] = df['dt_obj'].dt.strftime('%d/%m/%Y (%A)')
    df['hora_str'] = df['dt_obj'].dt.strftime('%H:%M')
    
    # Ordena
    df = df.sort_values('dt_obj')
    
    # Pega datas únicas ordenadas
    datas_unicas = df['data_str'].unique()
    
    for dia in datas_unicas:
        # Filtra tarefas deste dia
        tasks_dia = df[df['data_str'] == dia]
        
        # Cabeçalho do Dia (Destaque se for hoje)
        dia_obj = tasks_dia.iloc[0]['dt_obj'].date()
        cor_dia = "#333"
        icone_dia = "📅"
        
        if dia_obj < hoje.date(): 
            cor_dia = "#d63031" # Vermelho (Passado)
            icone_dia = "⚠️"
        elif dia_obj == hoje.date():
            cor_dia = "#27ae60" # Verde (Hoje)
            icone_dia = "🔥HOJE"
            
        st.markdown(f"### {icone_dia} {dia}")
        
        for index, row in tasks_dia.iterrows():
            with st.container(border=True):
                c_check, c_hora, c_desc, c_cli, c_zap = st.columns([0.5, 0.8, 4, 2, 1])
                
                # Checkbox de Conclusão
                concluido = row['concluido']
                icon = "✅" if concluido else "🔲"
                if c_check.button(icon, key=f"ag_chk_{row['id']}"):
                    requests.put(f"{API_URL}/crm/tarefas/{row['id']}/toggle")
                    time.sleep(0.2)
                    st.rerun()
                
                # Hora
                hora_style = "color:red; font-weight:bold" if (not concluido and row['dt_obj'] < hoje) else "color:gray"
                c_hora.markdown(f"<span style='{hora_style}'>{row['hora_str']}</span>", unsafe_allow_html=True)
                
                # Descrição
                riscado = "text-decoration: line-through; color: gray;" if concluido else "font-weight: bold; font-size:16px;"
                c_desc.markdown(f"<span style='{riscado}'>{row['descricao']}</span>", unsafe_allow_html=True)
                
                # Cliente
                c_cli.caption(f"👤 {row['nome_cliente']}")
                
                # --- NOVO: BOTÃO DE AÇÃO (Popover com Escolha) ---
                with c_zap.popover("💬", help="Entrar em contato"):
                    st.markdown("Como deseja chamar?")
                    
                    # Opção 1: Abrir na Plataforma (Atendimento Humano)
                    if st.button("🎧 Abrir no Painel", key=f"btn_painel_{row['id']}", use_container_width=True):
                        # Usa a rota que já existe para abrir atendimento manual
                        payload_abrir = {"instancia": instancia, "remote_jid": row['telefone']}
                        try:
                            r = requests.post(f"{API_URL}/atendimentos/abrir", json=payload_abrir)
                            if r.status_code == 200:
                                st.toast("Atendimento aberto! Vá para a aba 'Atendimento Humano'.")
                                time.sleep(2)
                            else:
                                erro = r.json().get('msg', 'Erro ao abrir')
                                st.warning(f"{erro}")
                        except Exception as e:
                            st.error(f"Erro: {e}")

                    # Opção 2: Abrir no WhatsApp Web/App
                    zap_limpo = "".join(filter(str.isdigit, str(row['telefone'])))
                    link_wa = f"https://wa.me/{zap_limpo}"
                    st.link_button("📱 Abrir no WhatsApp", link_wa, use_container_width=True)

# =====================================================
# TELA DE AJUDA (CORRIGIDA: SÓ SUPER-ADMIN EDITA 🔒)
# =====================================================
def tela_ajuda():
    st.markdown("## 🎓 Central de Ajuda & Tutoriais")
    st.caption("Aprenda a usar todas as funcionalidades do sistema.")
    st.markdown("---")

    # 🔒 CORREÇÃO DE SEGURANÇA AQUI:
    # Antes verificava se era 'admin' (qualquer cliente é admin da própria conta).
    # Agora verifica se o LOGIN é 'admin' (você, o dono do SaaS).
    # Se seu login mestre não for "admin", troque a palavra abaixo.
    eh_super_admin = st.session_state.user_info.get('login') == 'admin'

    # --- ÁREA DO ADMIN: ADICIONAR NOVO ---
    if eh_super_admin:
        with st.expander("➕ Adicionar Novo Artigo (Apenas Super Admin)", expanded=False):
            with st.form("form_add_ajuda"):
                novo_titulo = st.text_input("Título do Artigo")
                novo_cat = st.selectbox("Categoria", ["Início", "Conexão", "Automação", "Financeiro", "Dicas"])
                novo_conteudo = st.text_area("Conteúdo (Suporta Markdown)", height=200, help="Use # para títulos, * para listas.")
                
                if st.form_submit_button("💾 Salvar Artigo"):
                    try:
                        res = requests.post(f"{API_URL}/ajuda/salvar", json={
                            "titulo": novo_titulo, 
                            "conteudo": novo_conteudo, 
                            "categoria": novo_cat
                        })
                        if res.status_code == 200:
                            st.success("Artigo criado!")
                            time.sleep(1)
                            st.rerun()
                    except Exception as e:
                        st.error(f"Erro: {e}")

    # --- LISTAGEM DE ARTIGOS ---
    try:
        res = requests.get(f"{API_URL}/ajuda/listar")
        artigos = res.json() if res.status_code == 200 else []
    except:
        # st.error("Não foi possível carregar a ajuda.")
        artigos = []

    if not artigos:
        st.info("Nenhum tutorial encontrado.")
    
    # Agrupa por Categoria
    for artigo in artigos:
        c1, c2 = st.columns([5, 1])
        with c1:
            with st.expander(f"📚 {artigo['titulo']} ({artigo['categoria']})"):
                st.markdown(artigo['conteudo'])
                st.markdown("---")
        
        # Botão de Excluir (Só Super Admin vê)
        with c2:
            if eh_super_admin:
                st.write("") 
                if st.button("🗑️", key=f"del_help_{artigo['id']}", help="Excluir Artigo"):
                    requests.delete(f"{API_URL}/ajuda/{artigo['id']}")
                    st.rerun()



# =====================================================
# CONTROLE DE ACESSO
# =====================================================
if "autenticado" not in st.session_state: st.session_state.autenticado = False
if "user_info" not in st.session_state: st.session_state.user_info = {}

if not st.session_state.autenticado:
    login_sistema()
    st.stop()

user_info = st.session_state.user_info
instancia_selecionada = user_info.get("instancia_wa")
login_usuario = user_info.get("login")
status_conta = user_info.get("status_conta", "ativo")

bloqueado = False
if status_conta == 'vencido':
    st.error("⚠️ SUA ASSINATURA EXPIROU. Funcionalidades bloqueadas até a renovação.")
    bloqueado = True
elif status_conta == 'bloqueado':
    st.error("🚫 CONTA BLOQUEADA PELO ADMINISTRADOR.")
    bloqueado = True

# =====================================================
# SIDEBAR (LOGO + TÍTULO 📸)
# =====================================================
with st.sidebar:
    # --- 1. LOGO DO SISTEMA ---
    # Tenta pegar a logo personalizada (Whitelabel)
    logo_custom = user_info.get('app_logo_url')
    
    # Colunas para ajustar o tamanho/centralização da logo
    col_logo, col_rest = st.columns([1, 0.1]) 
    
    with col_logo:
        if logo_custom:
            st.image(logo_custom, width=150)
        else:
            try:
                # Tenta carregar a logo padrão local
                st.image("logo.png", width=120)
            except:
                # Se não tiver imagem nenhuma, mostra um ícone grande
                st.markdown("# 🚀")

    # --- 2. TÍTULO E BOAS-VINDAS ---
    st.title("Painel de Controle")
    st.write(f"Olá, **{user_info.get('nome_cliente', 'Usuário')}**")
    
    # Status da Conexão
    if verificar_status_whatsapp(instancia_selecionada):
        st.markdown("Status: <span class='status-ok'>Online 🟢</span>", unsafe_allow_html=True)
    else:
        st.markdown("Status: <span class='status-err'>Offline 🔴</span>", unsafe_allow_html=True)
    
    st.divider()

    u = st.session_state.user_info
    tipo_acesso = u.get('tipo_acesso', 'admin')
    
    opcoes = []
    icones = []

    # --- 3. MENU DINÂMICO ---
    if bloqueado:
        st.error("⚠️ Conta Suspensa")
        opcoes = ["Minha Assinatura", "Ajuda", "Atendimento Humano"]
        icones = ["credit-card", "book", "headset"]
    elif tipo_acesso == 'funcionario':
        st.info(f"👤 {u.get('nome')}")
        opcoes = ["Atendimento Humano", "CRM & Disparos", "Ajuda"]
        icones = ["headset", "megaphone", "book"]
    else:
        opcoes = [
            "Dashboard", 
            "Meus Gatilhos", 
            "Mapa Mental", 
            "Simulador", 
            "Conexão", 
            "Atendimento Humano", 
            "CRM & Disparos", 
            "Agenda de Tarefas",
            "Gestão de Equipe", 
            "Ajuda", 
            "Minha Assinatura"
        ]
        icones = [
            "speedometer2", "lightning-charge", "diagram-3", 
            "chat-dots", "qr-code", "headset", "megaphone", "calendar-check", 
            "people-fill", "book", "credit-card"
        ]
        
        # Super Admin
        if login_usuario == "admin": 
            opcoes.append("Gestão de Clientes")
            icones.append("person-badge")

    selected = option_menu(
        menu_title=None, # Deixamos None para não repetir título
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
    if st.button("Sair", key="btn_logout_sidebar", use_container_width=True):
        st.session_state.autenticado = False
        st.session_state.user_info = {}
        st.rerun()

# =====================================================
# ROTEAMENTO DE ABAS
# =====================================================

if selected == "Dashboard":
    st.subheader("📊 Centro de Comando")
    c_filt, c_refresh = st.columns([4, 1])
    with c_filt:
        periodo = st.selectbox("Período de Análise", [7, 15, 30, 90], index=2, format_func=lambda x: f"Últimos {x} dias")
    with c_refresh:
        if st.button("🔄 Atualizar"): st.rerun()

    instancia_selecionada = user_info.get("instancia_wa")
    try:
        res = requests.get(f"{API_URL}/metricas/{instancia_selecionada}", params={"dias": periodo})
        dados = res.json() if res.status_code == 200 else {}
    except: dados = {}

    if not dados:
        st.warning("Sem dados suficientes para gerar gráficos ainda.")
    else:
        kpis = dados.get('kpis', {})
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown(f"""<div class="metric-card"><div class="metric-label">👥 Total de Leads</div><div class="metric-value">{kpis.get('clientes', 0)}</div></div>""", unsafe_allow_html=True)
        with col2:
            st.markdown(f"""<div class="metric-card"><div class="metric-label">✅ Atendimentos (Período)</div><div class="metric-value">{kpis.get('atendimentos_mes', 0)}</div></div>""", unsafe_allow_html=True)
        with col3:
            atendimentos = kpis.get('atendimentos_mes', 0) or 0
            media = int(atendimentos / periodo)
            st.markdown(f"""<div class="metric-card"><div class="metric-label">📅 Média Diária</div><div class="metric-value">{media}</div></div>""", unsafe_allow_html=True)

        st.markdown("---")
        c_g1, c_g2 = st.columns([2, 1])
        with c_g1:
            st.markdown("##### 📈 Volume de Mensagens")
            diario = dados.get('diario', [])
            if diario:
                df_dia = pd.DataFrame(diario)
                if 'data' in df_dia.columns and 'qtd' in df_dia.columns:
                    df_dia = df_dia.rename(columns={'data': 'Data', 'qtd': 'Mensagens'})
                    st.area_chart(df_dia.set_index("Data"), color="#00C853")
                else: st.info("Estrutura de dados incorreta para gráfico.")
            else: st.info("Sem dados de volume.")

        with c_g2:
            st.markdown("##### 🏆 Top Atendentes")
            ranking = dados.get('ranking', [])
            if ranking:
                df_rank = pd.DataFrame(ranking)
                max_val = 1
                if not df_rank.empty and 'qtd' in df_rank.columns: max_val = df_rank['qtd'].max()
                st.dataframe(df_rank, column_config={"nome_atendente": "Nome", "qtd": st.column_config.ProgressColumn("Atendimentos", format="%d", min_value=0, max_value=int(max_val))}, hide_index=True, use_container_width=True)
            else: st.caption("Nenhum atendimento finalizado.")

        st.markdown("---")
        st.markdown("##### 🔥 Horários de Pico (Calor)")
        horarios = dados.get('horario', [])
        if horarios:
            df_full = pd.DataFrame({"hora": range(24)})
            df_real = pd.DataFrame(horarios)
            if not df_real.empty:
                df_real['hora'] = df_real['hora'].astype(int)
                df_heat = pd.merge(df_full, df_real, on="hora", how="left").fillna(0)
            else:
                df_heat = df_full
                df_heat['qtd'] = 0
            st.bar_chart(df_heat.set_index("hora"), color="#FF5722")
        else: st.info("Aguardando dados de mensagens...")


# === NOVO: WIDGET DE LEMBRETES NO DASHBOARD ===
    st.markdown("---")
    st.subheader("📅 Sua Agenda Hoje")
    
    try:
        # Busca tarefas pendentes
        r_tasks = requests.get(f"{API_URL}/crm/tarefas/todas/{instancia_selecionada}?apenas_pendentes=true")
        tasks_dash = r_tasks.json() if r_tasks.status_code == 200 else []
        
        # Filtra para Hoje e Atrasadas
        hoje = datetime.datetime.now().date()
        tasks_hoje = []
        tasks_atrasadas = []
        
        for t in tasks_dash:
            dt_t = pd.to_datetime(t['data_limite']).date()
            if dt_t < hoje: tasks_atrasadas.append(t)
            elif dt_t == hoje: tasks_hoje.append(t)
            
        col_d1, col_d2 = st.columns(2)
        
        with col_d1:
            with st.container(border=True):
                st.markdown(f"**🔥 Atrasadas ({len(tasks_atrasadas)})**")
                if not tasks_atrasadas: st.caption("Tudo em dia!")
                for t in tasks_atrasadas[:5]: # Mostra só as 5 primeiras
                    st.error(f"{t['descricao']} (Cliente: {t['nome_cliente']})")
                    
        with col_d2:
            with st.container(border=True):
                st.markdown(f"**✅ Para Hoje ({len(tasks_hoje)})**")
                if not tasks_hoje: st.caption("Livre por hoje!")
                for t in tasks_hoje[:5]:
                    st.info(f"{t['descricao']} ({pd.to_datetime(t['data_limite']).strftime('%H:%M')})")
                    
    except Exception as e:
        st.error(f"Erro ao carregar agenda: {e}")

        
elif selected == "Meus Gatilhos":
    st.subheader("⚡ Configuração do Robô")
    st.caption("Defina como o robô inicia a conversa e como ele responde.")

    # ==========================================================
    # 1. ÁREA DO MENU PRINCIPAL (BOAS-VINDAS) 🏠
    # ==========================================================
    texto_atual_menu = ""
    try:
        # Busca gatilhos para achar o default
        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        todos_gatilhos = res.json() if res.status_code == 200 else []
        
        # Filtra o texto do menu principal
        for item in todos_gatilhos:
            if item['gatilho'] == 'default':
                texto_atual_menu = item['resposta']
                break
    except: todos_gatilhos = []

    with st.expander("🏠 Editar Mensagem de Boas-Vindas (Menu Principal)", expanded=True):
        c_menu1, c_menu2 = st.columns([3, 1])
        with c_menu1:
            st.info("Esta mensagem será enviada quando o cliente disser 'Oi', 'Olá' ou iniciar a conversa.")
            novo_texto_menu = st.text_area("Texto de Boas-Vindas:", value=texto_atual_menu, height=150, placeholder="Olá! Sou o assistente virtual. Digite:\n1. Financeiro\n2. Suporte")
        
        with c_menu2:
            st.write("") # Espaçamento
            st.write("") 
            if st.button("💾 Salvar Início", type="primary", use_container_width=True):
                payload = {
                    "instancia": instancia_selecionada, "gatilho": "default", "resposta": novo_texto_menu,
                    "titulo_menu": "Geral", "categoria": "Geral", "tipo_midia": "texto", "url_midia": None, "id_pai": None
                }
                requests.post(f"{API_URL}/salvar", json=payload)
                st.toast("Menu Principal atualizado!")
                time.sleep(1)
                st.rerun()

    st.divider()

    # ==========================================================
    # 2. ÁREA DE CRIAÇÃO DE NOVOS GATILHOS ➕
    # ==========================================================
    st.markdown("### 🔗 Criar Novas Respostas (Opções)")
    
    c1, c2 = st.columns([1, 1.5])
    
    # --- COLUNA DA ESQUERDA: FORMULÁRIO ---
    with c1:
        with st.container(border=True):
            st.markdown("##### ➕ Novo Gatilho")
            
            # Verificação de Limites do Plano
            plano_user = user_info.get('plano', 'Básico')
            limite_gatilhos = 5 if plano_user == "Básico" else 9999
            permite_midia = False if plano_user == "Básico" else True
            
            qtd_atual = len(todos_gatilhos)
            
            # Barra de Progresso do Plano
            if plano_user == "Básico":
                st.progress(min(qtd_atual / limite_gatilhos, 1.0), text=f"Uso do Plano: {qtd_atual}/{limite_gatilhos}")
                if qtd_atual >= limite_gatilhos: st.error("🔒 Limite atingido! Faça Upgrade.")
            else: 
                st.caption(f"💎 Plano {plano_user}: Gatilhos Ilimitados")

            # Inputs do Gatilho
            novo_gatilho = st.text_input("Se o cliente digitar...", placeholder="Ex: 1")
            nova_resposta = st.text_area("O Robô responde...", height=100, placeholder="Ex: Para boleto acesse...")
            
            # Configuração de Pai (Submenu)
            opcoes_pais = {'Nenhum (Responde no Menu Principal)': None}
            for p in todos_gatilhos:
                if p['id_pai'] is None and p['gatilho'] != 'default':
                    opcoes_pais[f"Dentro de '{p['gatilho']}'"] = p['id']
            
            escolha_pai = st.selectbox("Onde essa opção aparece?", list(opcoes_pais.keys()))
            id_pai_selecionado = opcoes_pais[escolha_pai]
            
            novo_titulo = st.text_input("Título no Botão (Opcional)", placeholder="Ex: 2ª Via")

            # Upload de Mídia
            arquivo_enviado = None
            if permite_midia: 
                arquivo_enviado = st.file_uploader("Anexar Imagem/PDF/Áudio", type=["png", "jpg", "jpeg", "pdf", "mp4", "mp3"])
            elif plano_user == "Básico":
                st.caption("🔒 Mídia bloqueada no plano Básico")
            
            # Botão Salvar
            botao_desabilitado = (plano_user == "Básico" and qtd_atual >= limite_gatilhos)
            
            if st.button("💾 Adicionar Resposta", use_container_width=True, disabled=botao_desabilitado):
                if novo_gatilho and nova_resposta:
                    # Lógica de Upload
                    url_final = None
                    tipo_msg = "texto"
                    
                    if arquivo_enviado and permite_midia:
                        with st.spinner("Enviando arquivo..."):
                            files = {"file": (arquivo_enviado.name, arquivo_enviado, arquivo_enviado.type)}
                            try:
                                res_up = requests.post(f"{API_URL}/upload", files=files)
                                if res_up.status_code == 200:
                                    url_final = res_up.json()["url"]
                                    if "image" in arquivo_enviado.type: tipo_msg = "image"
                                    elif "video" in arquivo_enviado.type: tipo_msg = "video"
                                    elif "pdf" in arquivo_enviado.type: tipo_msg = "document"
                                    elif "audio" in arquivo_enviado.type: tipo_msg = "audio"
                            except Exception as e:
                                st.error(f"Erro upload: {e}")
                                st.stop()

                    payload = {
                        "instancia": instancia_selecionada, "gatilho": novo_gatilho, "resposta": nova_resposta,
                        "titulo_menu": novo_titulo if novo_titulo else "Geral", "categoria": "Atendimento",
                        "tipo_midia": tipo_msg, "url_midia": url_final, "id_pai": id_pai_selecionado
                    }
                    res_salvar = requests.post(f"{API_URL}/salvar", json=payload)
                    if res_salvar.status_code == 200:
                        st.success("Salvo!")
                        time.sleep(0.5)
                        st.rerun()
                    elif res_salvar.status_code == 403:
                        st.error(res_salvar.json()['detail'])
                    else: st.error("Erro ao salvar.")

    # --- COLUNA DA DIREITA: LISTAGEM VISUAL ---
    with c2:
        st.markdown("##### 🗂️ Estrutura Atual")
        
        if todos_gatilhos:
            # Separa Pais e Filhos para exibição organizada
            pais = [d for d in todos_gatilhos if d['id_pai'] is None and d['gatilho'] != 'default']
            filhos = [d for d in todos_gatilhos if d['id_pai'] is not None]

            if not pais:
                st.info("Nenhuma opção cadastrada. Use o formulário ao lado.")

            for pai in pais:
                titulo_exibicao = f" - {pai['titulo_menu']}" if pai.get('titulo_menu') and pai['titulo_menu'] != "Geral" else ""
                
                with st.expander(f"🔹 **{pai['gatilho']}** {titulo_exibicao}", expanded=False):
                    st.write(f"💬 {pai['resposta']}")
                    if pai.get('url_midia'): st.caption("📎 Contém anexo")
                    
                    c_del_p, _ = st.columns([1, 4])
                    if c_del_p.button("🗑️ Apagar", key=f"del_pai_{pai['id']}"):
                        requests.delete(f"{API_URL}/excluir/{pai['id']}")
                        st.rerun()

                    # Mostra os filhos deste pai
                    meus_filhos = [f for f in filhos if f['id_pai'] == pai['id']]
                    if meus_filhos:
                        st.markdown("---")
                        st.markdown("**Sub-opções:**")
                        for filho in meus_filhos:
                            with st.container():
                                c_f1, c_f2 = st.columns([4, 1])
                                titulo_filho = f" ({filho['titulo_menu']})" if filho.get('titulo_menu') and filho['titulo_menu'] != "Geral" else ""
                                c_f1.caption(f"↳ **{filho['gatilho']}**{titulo_filho}: {filho['resposta'][:30]}...")
                                if c_f2.button("❌", key=f"del_filho_{filho['id']}"):
                                    requests.delete(f"{API_URL}/excluir/{filho['id']}")
                                    st.rerun()
        else:
            st.info("Nenhum gatilho cadastrado.")

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
    except: pass

    with st.container(border=True):
        st.markdown("**Mensagem de Boas-Vindas / Menu:**")
        novo_texto = st.text_area("Digite o menu aqui:", value=texto_atual, height=200, placeholder="Ex: Olá! Sou o assistente virtual. Digite 1 para Cardápio...")
        if st.button("💾 Atualizar Menu Principal", type="primary"):
            payload = {
                "instancia": instancia_selecionada, "gatilho": "default", "resposta": novo_texto,
                "titulo_menu": "Geral", "categoria": "Geral", "tipo_midia": "texto", "url_midia": None, "id_pai": None
            }
            requests.post(f"{API_URL}/salvar", json=payload)
            st.success("Menu Principal atualizado com sucesso!")
            time.sleep(1)
            st.rerun()

elif selected == "Mapa Mental":
    st.subheader("🧠 Fluxo de Conversa")
    st.caption("Visualização gráfica da inteligência do seu robô.")
    import textwrap
    def quebrar_texto(texto, largura=30): return "<br/>".join(textwrap.wrap(texto, width=largura))

    try:
        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        gatilhos = res.json() if res.status_code == 200 else []

        if not gatilhos:
            c_vazio1, c_vazio2 = st.columns([1, 2])
            with c_vazio1: st.image("https://cdn-icons-png.flaticon.com/512/7486/7486744.png", width=150)
            with c_vazio2:
                st.warning("Seu mapa está vazio!")
                st.info("Vá em 'Meus Gatilhos' e cadastre a primeira regra para ver a mágica acontecer.")
        else:
            graph = graphviz.Digraph()
            graph.attr(rankdir='LR', splines='curved', bgcolor='transparent')
            graph.attr('node', shape='box', style='filled,rounded', fontname='Helvetica', penwidth='0', margin='0.2')
            graph.attr('edge', arrowhead='vee', arrowsize='0.8', color='#555555', fontname='Helvetica', fontsize='10')

            graph.node('CLIENTE', label=f'<<B>📱 INÍCIO</B><BR/><FONT POINT-SIZE="10">Cliente manda "Oi"</FONT>>', fillcolor='#2ecc71', fontcolor='white', shape='circle')
            ids_existentes = {g['id'] for g in gatilhos}

            for item in gatilhos:
                gatilho_txt = item['gatilho'].upper()
                titulo_menu = item.get('titulo_menu', '')
                header = titulo_menu if (titulo_menu and titulo_menu != "Geral") else gatilho_txt
                resposta_curta = quebrar_texto(item['resposta'][:60] + ("..." if len(item['resposta']) > 60 else ""))

                if item['gatilho'] == 'default':
                    label_html = f'''<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0"><TR><TD><B>🏠 MENU PRINCIPAL</B></TD></TR><TR><TD><FONT POINT-SIZE="10" COLOR="#444444">{resposta_curta}</FONT></TD></TR></TABLE>>'''
                    graph.node(f"G_{item['id']}", label=label_html, fillcolor='#ffcb2b', fontcolor='black')
                    graph.edge('CLIENTE', f"G_{item['id']}", color="#2ecc71", penwidth="2.0")
                else:
                    id_pai = item['id_pai']
                    cor_fundo = '#E3F2FD'
                    icone = "📸" if item.get('url_midia') else "💬"
                    label_html = f'''<<TABLE BORDER="0" CELLBORDER="0" CELLSPACING="0"><TR><TD ALIGN="LEFT"><B>{icone} {header}</B></TD></TR><TR><TD ALIGN="LEFT"><FONT POINT-SIZE="9" COLOR="#666666">Gatilho: "{item['gatilho']}"</FONT></TD></TR><TR><TD ALIGN="LEFT"><FONT POINT-SIZE="10">{resposta_curta}</FONT></TD></TR></TABLE>>'''
                    graph.node(f"G_{item['id']}", label=label_html, fillcolor=cor_fundo, fontcolor='black')

                    if id_pai is None:
                        graph.edge('CLIENTE', f"G_{item['id']}", style="dashed", label="Palavra-chave", color="#999999")
                    elif id_pai in ids_existentes:
                        graph.edge(f"G_{id_pai}", f"G_{item['id']}")

            st.graphviz_chart(graph, use_container_width=True)
            st.caption("Legenda: 🟢 Início | 🟡 Menu Principal | 🔵 Respostas | 📸 Contém Imagem/Vídeo")
    except Exception as e: st.error(f"Erro ao gerar mapa: {e}")

elif selected == "Simulador":
    st.subheader("💬 Teste seu Robô")
    if "chat_history" not in st.session_state: st.session_state.chat_history = []

    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if prompt := st.chat_input("Digite algo..."):
        st.session_state.chat_history.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)

        res = requests.get(f"{API_URL}/listar/{instancia_selecionada}")
        resposta_robo = "..."
        if res.status_code == 200:
            gatilhos = res.json()
            encontrou = False
            for g in gatilhos:
                if g['gatilho'].lower() in prompt.lower() and g['gatilho'] != 'default':
                    resposta_robo = g['resposta']
                    encontrou = True
                    break
            if not encontrou:
                for g in gatilhos:
                    if g['gatilho'] == 'default':
                        resposta_robo = g['resposta']
                        break
        
        time.sleep(0.5)
        st.session_state.chat_history.append({"role": "assistant", "content": resposta_robo})
        with st.chat_message("assistant"): st.markdown(resposta_robo)

elif selected == "Conexão":
    st.subheader("📱 Conexão e Configuração")
    
    if "user_info" in st.session_state: u = st.session_state.user_info
    else: st.error("Sessão expirada."); st.stop()
        
    instancia_selecionada = u.get("instancia_wa", "").strip()
    
    # --- 1. STATUS DO ROBÔ ---
    with st.container(border=True):
        c_switch, c_desc = st.columns([1, 4])
        try:
            r_st = requests.get(f"{API_URL}/usuarios/status-bot/{instancia_selecionada}")
            status_atual = r_st.json().get('bot_ativo', True)
        except: status_atual = True
        
        with c_switch:
            novo_status = st.toggle("🤖 Robô Ativo", value=status_atual)
        with c_desc:
            st.caption("Quando ligado, o robô responde automaticamente.")

        if novo_status != status_atual:
            requests.post(f"{API_URL}/usuarios/mudar-status-bot", json={"instancia": instancia_selecionada, "ativo": novo_status})
            time.sleep(0.5); st.rerun()
            
    st.divider()

    # --- 2. PAINEL DE CONEXÃO E QR CODE ---
    st.markdown("### 🔗 Conexão com WhatsApp")
    col_con1, col_con2 = st.columns(2)
    
    with col_con1:
        if st.button("🔄 Gerar QR Code / Reconectar", type="primary", use_container_width=True):
            # Garante configuração (com Integration corrigido)
            requests.post(f"{API_URL}/instance/configurar/{instancia_selecionada}")
            
            with st.spinner("Buscando QR Code..."):
                try:
                    res = requests.get(f"{EVO_URL}/instance/connect/{instancia_selecionada}", headers=HEADERS_EVO, timeout=20)
                    
                    # AUTO-REPARO SE NÃO EXISTIR
                    if res.status_code == 404:
                        st.warning("Recriando instância...")
                        try: requests.delete(f"{EVO_URL}/instance/delete/{instancia_selecionada}", headers=HEADERS_EVO); time.sleep(1)
                        except: pass
                        
                        payload_create = {
                            "instanceName": instancia_selecionada, "token": u.get("senha", "123456"), 
                            "qrcode": True, "integration": "WHATSAPP-BAILEYS"
                        }
                        requests.post(f"{EVO_URL}/instance/create", json=payload_create, headers=HEADERS_EVO)
                        time.sleep(3)
                        res = requests.get(f"{EVO_URL}/instance/connect/{instancia_selecionada}", headers=HEADERS_EVO, timeout=20)

                    if res.status_code == 200:
                        data = res.json()
                        if "base64" in data:
                            img_b64 = data["base64"].replace("data:image/png;base64,", "")
                            img = Image.open(BytesIO(base64.b64decode(img_b64)))
                            st.image(img, caption="Escaneie Agora", width=250)
                        elif "qrcode" in data: st.code(data["qrcode"])
                        else: st.success("✅ WhatsApp Conectado!")
                    else: st.error(res.text)
                except Exception as e: st.error(f"Erro: {e}")

    with col_con2:
        if st.button("🚪 Desconectar (Reset Total)", type="secondary", use_container_width=True):
            with st.spinner("Resetando..."):
                requests.delete(f"{EVO_URL}/instance/logout/{instancia_selecionada}", headers=HEADERS_EVO)
                requests.delete(f"{EVO_URL}/instance/delete/{instancia_selecionada}", headers=HEADERS_EVO)
                st.success("Limpeza concluída. Gere um novo QR Code."); time.sleep(2); st.rerun()

    st.divider()

    # --- 3. DIAGNÓSTICO DE WEBHOOK (AQUI ESTÁ A SOLUÇÃO) 📡 ---
    st.subheader("📡 Diagnóstico de Webhook (Onde as mensagens chegam)")
    
    with st.expander("🕵️ Ver Configuração Atual", expanded=True):
        # 1. Busca onde a Evolution está mandando as mensagens hoje
        webhook_atual = "Desconhecido"
        try:
            r_find = requests.get(f"{EVO_URL}/webhook/find/{instancia_selecionada}", headers=HEADERS_EVO)
            if r_find.status_code == 200:
                webhook_atual = r_find.json().get("webhook", {}).get("url") or "Não configurado"
            else: webhook_atual = f"Erro API: {r_find.status_code}"
        except: webhook_atual = "API Offline"

        st.info(f"📍 A Evolution está enviando para: **{webhook_atual}**")
        
        # 2. Formulário para Corrigir Manualmente
        st.markdown("##### 🔧 Corrigir Endereço")
        st.caption("Se o endereço acima estiver errado (ex: localhost) ou vazio, o sistema não recebe o 'Oi'.")
        
        # Sugere o endereço correto baseado na URL do navegador (Streamlit não pega URL do browser fácil, então sugerimos o do .env)
        url_sugerida = API_URL.replace("/api", "") # Tenta deduzir
        if "localhost" in url_sugerida: url_sugerida = "http://SEU_IP_AQUI:8000"
        
        novo_webhook = st.text_input("Qual o endereço do seu Backend (API)?", value=f"{url_sugerida}/webhook/whatsapp")
        
        if st.button("💾 Salvar Webhook Manualmente"):
            payload_hook = {
                "webhook": {
                    "enabled": True,
                    "url": novo_webhook,
                    "events": ["MESSAGES_UPSERT", "MESSAGES_UPDATE", "SEND_MESSAGE", "CONNECTION_UPDATE"]
                }
            }
            try:
                r_set = requests.post(f"{EVO_URL}/webhook/set/{instancia_selecionada}", json=payload_hook, headers=HEADERS_EVO)
                # Aceita 200 (OK) ou 201 (Created) como sucesso
                if r_set.status_code in [200, 201]:
                    st.success(f"✅ Webhook atualizado para: {novo_webhook}")
                    time.sleep(1); st.rerun()
                else:
                    st.error(f"Erro ao salvar: {r_set.text}")
            except Exception as e:
                st.error(f"Erro de conexão: {e}")

elif selected == "Gestão de Clientes":
    st.subheader("👥 Gestão Administrativa")
    aba_cad, aba_list, aba_cupom, aba_planos_full = st.tabs(["➕ Novo Cliente", "📋 Listagem", "🎟️ Cupons", "💰 Planos & Limites"])

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
                        else: st.error(f"Erro: {res.text}")
                    except Exception as e: st.error(f"Erro conexão: {e}")
                else: st.warning("Preencha Nome, Login e Instância.")

    with aba_list:
        try:
            res = requests.get(f"{API_URL}/usuarios/listar")
            if res.status_code == 200:
                usuarios = res.json()
                if not usuarios: st.info("Nenhum cliente encontrado.")
                
                st.markdown("##### 📋 Clientes Cadastrados")
                c_h1, c_h2, c_h3, c_h4, c_h5 = st.columns([2, 1.5, 2, 1.5, 1])
                c_h1.caption("**Cliente / Login**")
                c_h2.caption("**Instância**")
                c_h3.caption("**Plano**")
                c_h4.caption("**Status (Clique para mudar)**")
                c_h5.caption("**Ações**")
                st.divider()

                for user in usuarios:
                    with st.container(border=True):
                        c1, c2, c3, c4, c5 = st.columns([2, 1.5, 2, 1.5, 1])
                        with c1:
                            st.write(f"**{user['nome_cliente']}**")
                            st.caption(f"👤 {user['login']}")
                        with c2: st.code(user['instancia_wa'], language="text")
                        with c3:
                            venc_txt = "Sem data"
                            if user.get('data_vencimento'):
                                try: venc_txt = pd.to_datetime(user['data_vencimento']).strftime('%d/%m/%Y')
                                except: pass
                            st.write(f"🏷️ {user.get('plano', 'Básico')}")
                            st.caption(f"Vence: {venc_txt}")
                        with c4:
                            eh_ativo = user.get('status_conta') == 'ativo'
                            novo_estado = st.toggle("Ativo" if eh_ativo else "Bloqueado", value=eh_ativo, key=f"status_toggle_{user['id']}")
                            if novo_estado != eh_ativo:
                                novo_status_bd = "ativo" if novo_estado else "bloqueado"
                                with st.spinner("Alterando..."):
                                    r = requests.put(f"{API_URL}/usuarios/status/{user['id']}", json={"status": novo_status_bd})
                                    if r.status_code == 200:
                                        st.toast(f"Status alterado para {novo_status_bd}!")
                                        time.sleep(0.5)
                                        st.rerun()
                                    else: st.error("Erro ao alterar.")
                        with c5:
                            if st.button("🗑️", key=f"btn_del_list_{user['id']}", help="Excluir Usuário"):
                                requests.delete(f"{API_URL}/usuarios/excluir/{user['id']}")
                                st.rerun()

                        with st.expander(f"✏️ Editar Dados de {user['nome_cliente']}"):
                            with st.form(key=f"form_edit_{user['id']}"):
                                ec1, ec2 = st.columns(2)
                                ed_nome = ec1.text_input("Nome", value=user['nome_cliente'])
                                ed_login = ec2.text_input("Login", value=user['login'])
                                ec3, ec4 = st.columns(2)
                                ed_senha = ec3.text_input("Senha", value=user['senha'], type="password")
                                ed_zap = ec4.text_input("WhatsApp", value=user.get('whatsapp', ''))
                                ec5, ec6 = st.columns(2)
                                ed_email = ec5.text_input("Email", value=user.get('email', ''))
                                lista_planos = ["Básico", "Pro", "Enterprise"]
                                idx_plano = lista_planos.index(user['plano']) if user['plano'] in lista_planos else 0
                                ed_plano = ec6.selectbox("Plano", lista_planos, index=idx_plano)
                                ec7, ec8 = st.columns(2)
                                ed_valor = ec7.number_input("Valor (R$)", value=float(user.get('valor_mensal', 0) or 0), step=10.0)
                                val_data = None
                                if user.get('data_vencimento'):
                                    try: val_data = pd.to_datetime(user.get('data_vencimento')).date()
                                    except: pass
                                ed_venc = ec8.date_input("Vencimento", value=val_data)

                                if st.form_submit_button("💾 Salvar Alterações"):
                                    payload_edit = {
                                        "nome_cliente": ed_nome, "login": ed_login, "senha": ed_senha,
                                        "plano": ed_plano, "valor_mensal": ed_valor, 
                                        "data_vencimento": str(ed_venc) if ed_venc else None,
                                        "whatsapp": ed_zap, "email": ed_email
                                    }
                                    requests.put(f"{API_URL}/usuarios/editar/{user['id']}", json=payload_edit)
                                    st.success("Salvo!")
                                    time.sleep(1)
                                    st.rerun()
            else: st.error("Erro ao carregar lista de usuários.")
        except Exception as e: st.error(f"Erro ao conectar: {e}")

    with aba_cupom:
        st.markdown("### 🎟️ Gerenciar Cupons de Desconto")
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
                            else: st.error("Erro ao criar (talvez já exista).")
                        except Exception as e: st.error(f"Erro: {e}")
        
        st.divider()
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
                else: st.caption("Nenhum cupom cadastrado.")
        except: st.error("Não foi possível carregar os cupons.")

    with aba_planos_full:
        st.markdown("### 💰 Gerenciador de Planos e Limites")
        
        # --- 1. MODO EDIÇÃO ---
        if "editando_plano_id" not in st.session_state: st.session_state.editando_plano_id = None

        if st.session_state.editando_plano_id:
            pid = st.session_state.editando_plano_id
            st.info(f"✏️ Editando Plano ID: {pid}")
            try:
                r = requests.get(f"{API_URL}/planos/{pid}/detalhes")
                if r.status_code == 200:
                    data = r.json()
                    p_info = data['plano']
                    p_regras = data['regras']
                else:
                    st.error("Erro ao carregar dados.")
                    p_info, p_regras = {}, {}
            except: p_info, p_regras = {}, {}

            if p_info:
                with st.form("form_editar_completo"):
                    st.markdown("#### 📝 Dados Comerciais")
                    c_basic1, c_basic2 = st.columns(2)
                    e_nome = c_basic1.text_input("Nome do Plano", value=p_info['nome'])
                    e_valor = c_basic2.number_input("Valor Mensal (R$)", value=float(p_info['valor']))
                    e_desc = st.text_area("Descrição (Vantagens)", value=p_info['descricao'], height=60)
                    
                    st.divider()
                    st.markdown("#### ⚙️ Regras e Limites")
                    col_l1, col_l2 = st.columns(2)

                    with col_l1:
                        st.caption("🤖 Automação")
                        r_gatilhos = st.number_input("Máx. Gatilhos (0 = Ilimitado)", value=int(p_regras.get('max_gatilhos', 5)))
                        r_disparos = st.checkbox("Permitir Disparos em Massa?", value=bool(p_regras.get('permite_disparos', False)))
                        r_crm = st.checkbox("Acesso ao CRM?", value=bool(p_regras.get('acesso_crm', True)))

                    with col_l2:
                        st.caption("👥 Equipe e Atendimento")
                        r_humano = st.checkbox("Permitir Atend. Humano?", value=bool(p_regras.get('atendimento_humano', True)))
                        r_atendentes = st.number_input("Máx. Usuários na Equipe", min_value=1, value=int(p_regras.get('max_atendentes', 1)))
                        r_conexoes = st.number_input("Máx. WhatsApps Conectados", min_value=1, value=int(p_regras.get('max_conexoes', 1)))

                    st.markdown("---")
                    c_b1, c_b2 = st.columns([1, 4])
                    if c_b1.form_submit_button("💾 Salvar", type="primary"):
                        payload = {
                            "nome": e_nome, "valor": e_valor, "descricao": e_desc, "ativo": True,
                            "limites": {
                                "max_gatilhos": r_gatilhos,
                                "permite_disparos": r_disparos,
                                "acesso_crm": r_crm,
                                "atendimento_humano": r_humano,
                                "max_atendentes": r_atendentes,
                                "max_conexoes": r_conexoes
                            }
                        }
                        requests.put(f"{API_URL}/planos/{pid}/editar_completo", json=payload)
                        st.success("Plano atualizado!")
                        st.session_state.editando_plano_id = None
                        st.rerun()
                    
                    if c_b2.form_submit_button("Cancelar"):
                        st.session_state.editando_plano_id = None
                        st.rerun()
        
        # --- 2. MODO LISTAGEM ---
        else:
            col_lista, col_novo = st.columns([1.5, 1])
            
            # --- COLUNA ESQUERDA: LISTA DE PLANOS ---
            with col_lista:
                st.markdown("#### Planos Existentes")
                planos = []
                try:
                    res = requests.get(f"{API_URL}/planos/listar")
                    if res.status_code == 200:
                        dados = res.json()
                        if isinstance(dados, list): planos = dados
                except: pass
                
                if not planos: st.info("Nenhum plano cadastrado.")
                else:
                    for p in planos:
                        if isinstance(p, dict):
                            with st.container(border=True):
                                cl1, cl3 = st.columns([3, 1])
                                with cl1:
                                    st.markdown(f"**{p.get('nome', 'X')}** — R$ {p.get('valor', 0):.2f}")
                                    st.caption(p.get('descricao', ''))
                                with cl3:
                                    c_btn1, c_btn2 = st.columns(2)
                                    # Botão Editar
                                    if c_btn1.button("✏️", key=f"ed_{p.get('id')}"):
                                        st.session_state.editando_plano_id = p.get('id')
                                        st.rerun()
                                    
                                    # Botão Excluir (CORRIGIDO E SEGURO 🛡️)
                                    if c_btn2.button("🗑️", key=f"del_{p.get('id')}", help="Excluir Plano"):
                                        try:
                                            res = requests.delete(f"{API_URL}/planos/excluir/{p.get('id')}")
                                            
                                            # Caso 1: Sucesso
                                            if res.status_code == 200:
                                                st.toast("✅ Plano excluído!")
                                                time.sleep(1)
                                                st.rerun()
                                                
                                            # Caso 2: Bloqueio (Tem usuários)
                                            elif res.status_code == 400:
                                                erro_txt = res.json().get('detail', 'Erro')
                                                st.error(f"⛔ {erro_txt}")
                                                
                                            # Caso 3: Erro genérico
                                            else:
                                                st.error(f"Erro: {res.text}")
                                        except Exception as e:
                                            st.error(f"Erro de conexão: {e}")

            # --- COLUNA DIREITA: CRIAR NOVO ---
            with col_novo:
                with st.container(border=True):
                    st.markdown("#### ➕ Criar Novo Plano")
                    with st.form("form_criar_full"):
                        n_nome = st.text_input("Nome (Ex: Gold)")
                        n_valor = st.number_input("Valor", value=59.90)
                        n_desc = st.text_area("Descrição", height=70)
                        st.divider()
                        st.caption("Limites Padrão:")
                        n_gatilhos = st.number_input("Max Gatilhos", value=10)
                        n_atendentes = st.number_input("Max Equipe", value=1, min_value=1)
                        c_chk1, c_chk2 = st.columns(2)
                        n_disparos = c_chk1.checkbox("Disparos?", value=False)
                        n_humano = c_chk2.checkbox("Atend. Humano?", value=True)
                        
                        if st.form_submit_button("Criar Plano", type="primary"):
                            if n_nome:
                                payload = {
                                    "nome": n_nome, "valor": n_valor, "descricao": n_desc, "ativo": True,
                                    "limites": {
                                        "max_gatilhos": n_gatilhos, "permite_disparos": n_disparos,
                                        "acesso_crm": True, "atendimento_humano": n_humano,
                                        "max_atendentes": n_atendentes, "max_conexoes": 1
                                    }
                                }
                                requests.post(f"{API_URL}/planos/criar_completo", json=payload)
                                st.success("Criado!")
                                time.sleep(1)
                                st.rerun()
                            else: st.warning("Nome obrigatório.")

                            
elif selected == "CRM & Disparos":
    st.subheader("🚀 CRM Pro & Pipeline")
    
    # NOVAS ABAS: Inclui o Kanban e mantém as antigas
    tab_kanban, tab_lista, tab_disparo = st.tabs(["📊 Funil de Vendas (Kanban)", "📋 Lista/Excel", "📢 Disparos"])
    
    instancia_selecionada = user_info.get("instancia_wa")

    # ==========================================================
    # ABA 1: KANBAN BOARD (COMPLETO: SCROLL + FILTRO + AGENDA)
    # ==========================================================
    with tab_kanban:
        import datetime  # Garante que datetime está disponível aqui

        # Definição das Etapas do Funil
        etapas = ["Novo Lead", "Em Negociação", "Proposta", "Ganho", "Perdido"]
        
        # Filtros Rápidos
        c_k1, c_k2, c_k3 = st.columns([2, 1, 1])
        filtro_nome = c_k1.text_input("🔍 Filtrar no Funil", placeholder="Buscar nome ou telefone...")
        filtro_origem = c_k2.selectbox("Origem", ["Todos", "WhatsApp", "Importado", "Manual"])
        
        if c_k3.button("🔄 Atualizar Kanban", use_container_width=True):
            st.rerun()

        # Busca dados do Backend
        try:
            res = requests.get(f"{API_URL}/crm/kanban/{instancia_selecionada}")
            todos_clientes = res.json() if res.status_code == 200 else []
        except: todos_clientes = []
        
        # Cria as colunas na tela (Uma para cada etapa)
        cols = st.columns(len(etapas))
        
        for i, etapa in enumerate(etapas):
            with cols[i]:
                # --- 1. FILTRAGEM INTELIGENTE (CORREÇÃO DE DADOS) ---
                clientes_etapa = []
                for c in todos_clientes:
                    # Normaliza a etapa: Se for None ou vazia, vira "Novo Lead"
                    etapa_cliente = c.get('etapa_funil')
                    if not etapa_cliente or etapa_cliente == "None":
                        etapa_cliente = "Novo Lead"
                    
                    # Verifica se pertence a esta coluna
                    if etapa_cliente == etapa:
                        # Aplica o filtro de texto (Busca) se houver
                        if filtro_nome:
                            termo = filtro_nome.lower()
                            if termo in c['nome'].lower() or termo in c['telefone']:
                                clientes_etapa.append(c)
                        else:
                            clientes_etapa.append(c)
                
                # --- 2. CABEÇALHO FIXO (NÃO ROLA) ---
                cor_etapa = "#e0e0e0"
                if etapa == "Ganho": cor_etapa = "#4cd137"
                elif etapa == "Perdido": cor_etapa = "#ff4757"
                elif etapa == "Novo Lead": cor_etapa = "#3498db"
                
                valor_total = sum([float(c.get('valor_negocio') or 0) for c in clientes_etapa])
                
                st.markdown(f"""
                <div style="border-bottom: 4px solid {cor_etapa}; margin-bottom: 10px; padding-bottom: 5px;">
                    <strong style="font-size: 16px;">{etapa}</strong><br>
                    <span style="font-size: 13px; color: gray;">{len(clientes_etapa)} leads • R$ {valor_total:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)
                
                # --- 3. ÁREA DE ROLAGEM (SCROLL) ---
                # Aqui está a mágica: height=600 cria a barra de rolagem
                with st.container(height=600, border=False):
                    if not clientes_etapa:
                        st.caption("Vazio")
                    
                    for cli in clientes_etapa:
                        # Card do Cliente
                        with st.container(border=True):
                            st.markdown(f"**{cli['nome']}**")
                            
                            tel_clean = cli['telefone'].split('@')[0]
                            st.caption(f"📞 {tel_clean}")
                            
                            # Etiquetas (Visual extra)
                            if cli.get('etiquetas'):
                                st.caption(f"🏷️ {cli['etiquetas']}")

                            if cli.get('valor_negocio') and float(cli['valor_negocio']) > 0:
                                st.markdown(f"<div style='color:#27ae60; font-weight:bold'>R$ {float(cli['valor_negocio']):,.2f}</div>", unsafe_allow_html=True)
                            
                            st.divider()
                            
                            # Ações Rápidas
                            c_card1, c_card2 = st.columns([2, 1])
                            
                            # Dropdown para Mover
                            nova_fase = c_card1.selectbox("Mover:", etapas, index=etapas.index(etapa), key=f"move_{cli['id']}", label_visibility="collapsed")
                            
                            if nova_fase != etapa:
                                requests.put(f"{API_URL}/crm/mudar_etapa", json={"cliente_id": cli['id'], "nova_etapa": nova_fase})
                                st.toast(f"Movido para {nova_fase}!")
                                time.sleep(0.5)
                                st.rerun()
                            
                            # Botão Detalhes (Popover)
                            with c_card2.popover("📝", help="Ver Detalhes e Tarefas"):
                                # Abas para organizar o popover que ficou cheio
                                tab_dados, tab_tarefas, tab_notas = st.tabs(["👤 Dados", "📅 Agenda", "📒 Notas"])
                                
                                # --- ABA 1: DADOS BÁSICOS ---
                                with tab_dados:
                                    st.markdown(f"### {cli['nome']}")
                                    st.text_input("Telefone", value=cli['telefone'], disabled=True)
                                    
                                    novo_valor = st.number_input("Valor (R$)", value=float(cli.get('valor_negocio') or 0.0), key=f"val_{cli['id']}")
                                    if st.button("💾 Salvar Valor", key=f"btn_val_{cli['id']}"):
                                        # Backend precisa suportar update de valor, se não tiver, avise
                                        st.warning("Atualize o backend para salvar o valor.") 

                                # --- ABA 2: TAREFAS (COM CORREÇÃO DE DATA) ---
                                with tab_tarefas:
                                    st.markdown("#### Agendar Retorno")
                                    with st.form(key=f"form_task_{cli['id']}"):
                                        col_dt, col_hr = st.columns(2)
                                        
                                        # Data atual
                                        data_task = col_dt.date_input("Data", value=datetime.datetime.now())
                                        
                                        # Hora atual (SEM MICROSSEGUNDOS para evitar erro)
                                        hora_atual = datetime.datetime.now().time().replace(microsecond=0)
                                        hora_task = col_hr.time_input("Hora", value=hora_atual)
                                        
                                        desc_task = st.text_input("Descrição", placeholder="Ex: Ligar para cliente...")
                                        
                                        if st.form_submit_button("📌 Salvar Tarefa"):
                                            if not desc_task:
                                                st.warning("Escreva uma descrição.")
                                            else:
                                                # --- CORREÇÃO AQUI ---
                                                # 1. Combina Data e Hora num objeto Python
                                                data_combinada = datetime.datetime.combine(data_task, hora_task)
                                                
                                                # 2. Formata EXATAMENTE como o Backend espera (Sem microssegundos, sem erros)
                                                data_iso = data_combinada.strftime("%Y-%m-%d %H:%M:%S")
                                                
                                                try:
                                                    r = requests.post(f"{API_URL}/crm/tarefas", json={
                                                        "cliente_id": cli['id'],
                                                        "descricao": desc_task,
                                                        "data_limite": data_iso
                                                    })
                                                    
                                                    resp = r.json()
                                                    
                                                    if r.status_code == 200 and resp.get("status") == "ok":
                                                        st.toast("✅ Tarefa Salva!")
                                                        time.sleep(1)
                                                        st.rerun()
                                                    else:
                                                        msg_erro = resp.get("msg", "Erro desconhecido")
                                                        st.error(f"Falha ao salvar: {msg_erro}")
                                                
                                                except Exception as e:
                                                    st.error(f"Erro de conexão: {e}")
                                    
                                    st.divider()
                                    st.caption("Suas Tarefas:")
                                    
                                    # Busca tarefas do banco
                                    try:
                                        res_tasks = requests.get(f"{API_URL}/crm/tarefas/{cli['id']}")
                                        tasks = res_tasks.json() if res_tasks.status_code == 200 else []
                                    except: tasks = []
                                    
                                    if not tasks:
                                        st.info("Nada agendado.")
                                    else:
                                        for t in tasks:
                                            # Formatação visual
                                            concluido = t['concluido']
                                            icon = "✅" if concluido else "🔲"
                                            riscado = "text-decoration: line-through; color: gray;" if concluido else "font-weight: bold;"
                                            
                                            # Exibe a data formatada
                                            try:
                                                dt_show = pd.to_datetime(t['data_limite']).strftime('%d/%m %H:%M')
                                            except: dt_show = "S/D"

                                            c_chk, c_txt = st.columns([1, 4])
                                            if c_chk.button(icon, key=f"chk_{t['id']}", help="Marcar como feito/pendente"):
                                                requests.put(f"{API_URL}/crm/tarefas/{t['id']}/toggle")
                                                st.rerun()
                                            
                                            c_txt.markdown(f"<span style='{riscado}'>{t['descricao']}</span> <span style='font-size:11px; color:#666'>({dt_show})</span>", unsafe_allow_html=True)

                                # --- ABA 3: NOTAS (CÓDIGO ANTIGO MOVIDO PRA CÁ) ---
                                with tab_notas:
                                    st.markdown("#### Histórico")
                                    try:
                                        r_notas = requests.get(f"{API_URL}/crm/notas/{cli['id']}")
                                        notas = r_notas.json() if r_notas.status_code == 200 else []
                                    except: notas = []
                                    
                                    if notas:
                                        for n in notas:
                                            st.info(f"**{n['autor_nome']}**: {n['texto']}")
                                    else:
                                        st.caption("Nenhuma nota.")
                                    
                                    txt_nota = st.text_area("Nova Nota", key=f"txt_n_{cli['id']}")
                                    if st.button("Salvar Nota", key=f"btn_n_{cli['id']}"):
                                        requests.post(f"{API_URL}/crm/notas", json={
                                            "cliente_id": cli['id'],
                                            "autor": st.session_state.user_info.get('nome_cliente', 'Admin'),
                                            "texto": txt_nota
                                        })
                                        st.success("Salvo!")
                                        st.rerun()


    # ==========================================================
    # ABA 2: LISTA / EXCEL (MANTIDO DO ANTERIOR)
    # ==========================================================
    with tab_lista:
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
                            "instancia": instancia_selecionada, "nome": crm_nome,
                            "telefone": crm_tel, "dia_vencimento": crm_dia, "etiquetas": crm_tags
                        }
                        requests.post(f"{API_URL}/crm/clientes", json=payload)
                        st.success("Salvo!")
                        time.sleep(0.5)
                        st.rerun()
                    else: st.warning("Nome e Telefone são obrigatórios.")

        st.divider()
        with st.expander("📂 Importar Lista de Contatos (Excel/CSV)"):
            plano_user = st.session_state.user_info.get('plano', 'Básico')
            if plano_user == "Básico":
                st.error("🔒 Funcionalidade Exclusiva do Plano PRO")
                st.info("No plano Básico, o cadastro é manual.")
                st.write("Faça o upgrade para o **Plano Pro** e economize horas.")
                if st.button("💎 Quero fazer Upgrade", type="primary"):
                        st.session_state.selected = "Minha Assinatura"
                        st.rerun()
            else:
                st.info("💡 A planilha deve ter duas colunas: **Nome** e **Telefone**.")
                arquivo_import = st.file_uploader("Selecione o arquivo", type=["csv", "xlsx"])
                if arquivo_import:
                    if st.button("Processar Importação"):
                        try:
                            if arquivo_import.name.endswith('.csv'): df_import = pd.read_csv(arquivo_import)
                            else: df_import = pd.read_excel(arquivo_import)
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
                                    if not tel_clean.startswith("55") and len(tel_clean) > 9: tel_clean = "55" + tel_clean
                                    if "@" not in tel_clean: tel_clean += "@s.whatsapp.net"
                                    
                                    payload = {
                                        "instancia": instancia_selecionada, "nome": nome,
                                        "telefone": tel_clean, "dia_vencimento": 1, "etiquetas": "importado_excel"
                                    }
                                    requests.post(f"{API_URL}/crm/clientes", json=payload)
                                    sucesso += 1
                                    barra_imp.progress((i + 1) / total)
                                st.success(f"✅ Importação finalizada! {sucesso} contatos adicionados.")
                                time.sleep(2)
                                st.rerun()
                            else: st.error("❌ Não encontrei as colunas 'Nome' e 'Telefone'.")
                        except Exception as e: st.error(f"Erro ao ler arquivo: {e}")

        st.divider()
        st.markdown("### 📋 Gerenciamento de Contatos")
        if "crm_pagina" not in st.session_state: st.session_state.crm_pagina = 1
        if "crm_busca" not in st.session_state: st.session_state.crm_busca = ""

        c_filt1, c_filt2, c_filt3 = st.columns([2, 1, 1])
        texto_busca = c_filt1.text_input("🔍 Buscar (Nome ou Tel)", value=st.session_state.crm_busca, placeholder="Enter para buscar...")
        if texto_busca != st.session_state.crm_busca:
            st.session_state.crm_busca = texto_busca
            st.session_state.crm_pagina = 1
            st.rerun()

        try:
            params = {
                "pagina": st.session_state.crm_pagina, "itens_por_pagina": 20,
                "busca": st.session_state.crm_busca if st.session_state.crm_busca else None
            }
            res = requests.get(f"{API_URL}/crm/clientes/{instancia_selecionada}", params=params)
            
            if res.status_code == 200:
                payload = res.json()
                lista_clientes = payload['data']
                total_paginas = payload['total_paginas']
                total_itens = payload['total']
                
                if lista_clientes:
                    df = pd.DataFrame(lista_clientes)
                    df['telefone_visual'] = df['telefone'].astype(str).str.replace('@s.whatsapp.net', '')
                    df_editor = df[['id', 'nome', 'telefone_visual', 'dia_vencimento', 'etiquetas', 'telefone']]
                    st.caption(f"Total: {total_itens} clientes | Página {st.session_state.crm_pagina} de {total_paginas}")
                    st.info("💡 Clique duas vezes na célula para editar Nome, Dia ou Etiquetas.")

                    editado = st.data_editor(
                        df_editor,
                        column_config={
                            "id": st.column_config.NumberColumn("ID", width="small", disabled=True, format="%d"),
                            "telefone": None,
                            "telefone_visual": st.column_config.TextColumn("WhatsApp", disabled=True),
                            "nome": st.column_config.TextColumn("Nome"),
                            "dia_vencimento": st.column_config.NumberColumn("Dia Venc.", min_value=1, max_value=31, format="%d"),
                            "etiquetas": st.column_config.TextColumn("Etiquetas")
                        },
                        hide_index=True, use_container_width=True, key=f"editor_crm_{st.session_state.crm_pagina}"
                    )

                    if st.button("💾 Salvar Alterações da Tabela"):
                        barra = st.progress(0, text="Salvando...")
                        for index, row in editado.iterrows():
                            cid = row['id']
                            dia = row['dia_vencimento']
                            dia = None if pd.isna(dia) or dia == 0 or str(dia).strip() == "" else int(dia)
                            payload_up = {
                                "nome": row['nome'], "dia_vencimento": dia, "etiquetas": row['etiquetas']
                            }
                            requests.put(f"{API_URL}/crm/clientes/{cid}", json=payload_up)
                            barra.progress((index + 1) / len(editado))
                        st.success("Dados atualizados!")
                        time.sleep(1)
                        st.rerun()

                    c_ant, c_pag, c_prox = st.columns([1, 2, 1])
                    if c_ant.button("⬅️ Anterior", disabled=(st.session_state.crm_pagina <= 1)):
                        st.session_state.crm_pagina -= 1
                        st.rerun()
                    if c_prox.button("Próxima ➡️", disabled=(st.session_state.crm_pagina >= total_paginas)):
                        st.session_state.crm_pagina += 1
                        st.rerun()
                        
                    st.divider()
                    with st.expander("🗑️ Zona de Perigo (Excluir)"):
                        c_del1, c_del2 = st.columns([3, 1])
                        id_del = c_del1.number_input("ID para apagar", min_value=0)
                        if c_del2.button("Excluir Cliente"):
                            requests.delete(f"{API_URL}/crm/clientes/{id_del}")
                            st.rerun()
                else: st.info("Nenhum cliente encontrado com esses filtros.")
            else: st.error("Erro ao conectar com servidor.")
        except Exception as e: st.error(f"Erro: {e}")

    # ==========================================================
    # ABA 3: DISPAROS (COM TRAVA DE SEGURANÇA 🔒)
    # ==========================================================
    with tab_disparo:
        plano_atual = st.session_state.user_info.get('plano', 'Básico')
        
        # SE FOR BÁSICO -> BLOQUEIA
        if plano_atual == "Básico":
            st.empty()
            st.error("🔒 Funcionalidade Bloqueada no Plano Básico")
            c_lock1, c_lock2 = st.columns([1, 2])
            with c_lock1: st.markdown("# 🚀")
            with c_lock2:
                st.markdown("### Faça Upgrade para o Plano Pro")
                st.write("Libere campanhas ilimitadas e importação de Excel.")
                if st.button("💎 Quero fazer Upgrade agora", type="primary", key="btn_upg_disp"):
                    st.session_state.ir_para_assinatura = True 
                    st.rerun() 
        
        # SE FOR PRO/ENTERPRISE -> MOSTRA FERRAMENTA
        else:
            st.info("💡 Configure seu disparo em massa.")
            
            # --- PREPARAÇÃO DOS DADOS ---
            try:
                params_todos = {"itens_por_pagina": 10000, "pagina": 1}
                res = requests.get(f"{API_URL}/crm/clientes/{instancia_selecionada}", params=params_todos)
                todos_clientes = []
                if res.status_code == 200:
                    payload = res.json()
                    if isinstance(payload, dict): todos_clientes = payload.get('data', [])
                    elif isinstance(payload, list): todos_clientes = payload
            except: todos_clientes = []
            
            if not todos_clientes:
                st.warning("Nenhum cliente cadastrado ou erro ao carregar.")
                st.stop()

            # Filtros
            col_f1, col_f2 = st.columns(2)
            filtro_dia = col_f1.checkbox("Filtrar por Dia de Vencimento?")
            dia_selecionado = 0
            if filtro_dia: dia_selecionado = col_f1.number_input("Qual dia?", 1, 31, 10)
            filtro_tag = col_f2.text_input("Filtrar por Etiqueta (Opcional)", placeholder="Ex: devedor")

            # Aplica Filtros
            lista_final = []
            for c in todos_clientes:
                passou_dia = True
                passou_tag = True
                dia_cliente = c.get('dia_vencimento')
                if not dia_cliente: dia_cliente = 0
                if filtro_dia and int(dia_cliente) != dia_selecionado: passou_dia = False
                tags_cliente = c.get('etiquetas') or ""
                if filtro_tag and filtro_tag.lower() not in tags_cliente.lower(): passou_tag = False
                if passou_dia and passou_tag: lista_final.append(c)
            
            # Mostra Resumo
            st.markdown(f"### 🎯 Destinatários: **{len(lista_final)}**")
            if lista_final:
                with st.expander("Ver lista de quem vai receber"):
                    for i in lista_final:
                        tel_visual = str(i['telefone']).replace('@s.whatsapp.net', '')
                        st.caption(f"- {i['nome']} ({tel_visual})")

            st.divider()
            
            # Formulário da Mensagem
            st.markdown("### ✍️ Conteúdo do Disparo")
            st.caption("Dica: Use **{nome}** para personalizar.")
            texto_padrao = "Olá {nome}, confira nossa oferta especial!"
            mensagem = st.text_area("Texto / Legenda:", value=texto_padrao, height=150)
            
            st.markdown("📷 **Imagem ou Vídeo (Opcional)**")
            arquivo_disparo = st.file_uploader("Anexar arquivo", type=["png", "jpg", "jpeg", "pdf", "mp4"], key="up_mass")
            usar_menu = st.checkbox("Incluir dica de Menu no final?", value=False)
            
            st.divider()

            # --- LÓGICA DE TRAVA DE SEGURANÇA 🔒 ---
            if "confirmacao_disparo" not in st.session_state: 
                st.session_state.confirmacao_disparo = False

            # Botão 1: Revisar (Não envia ainda)
            if not st.session_state.confirmacao_disparo:
                if st.button(f"🚀 Revisar e Disparar ({len(lista_final)})", type="primary", use_container_width=True):
                    if not lista_final:
                        st.warning("A lista está vazia!")
                    elif not mensagem and not arquivo_disparo:
                        st.warning("Escreva uma mensagem ou anexe um arquivo.")
                    else:
                        st.session_state.confirmacao_disparo = True
                        st.rerun()

            # Botão 2: Confirmação Real (Aparece só depois de clicar no primeiro)
            else:
                with st.container(border=True):
                    st.error("⚠️ **ATENÇÃO: CONFIRMAÇÃO DE ENVIO**")
                    st.markdown(f"Você está prestes a enviar mensagens para **{len(lista_final)} pessoas**.")
                    st.markdown(f"**Mensagem:** _{mensagem[:50]}..._")
                    if arquivo_disparo: st.markdown(f"**Anexo:** {arquivo_disparo.name}")
                    
                    c_sim, c_nao = st.columns([1, 1])
                    
                    # CANCELAR
                    if c_nao.button("❌ Cancelar", use_container_width=True):
                        st.session_state.confirmacao_disparo = False
                        st.rerun()
                    
                    # ENVIAR DE VERDADE
                    if c_sim.button("✅ SIM, DISPARAR AGORA", type="primary", use_container_width=True):
                        url_final = None
                        tipo_msg = "texto"
                        
                        # Upload (só acontece aqui agora)
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

                        ids = [c['id'] for c in lista_final]
                        payload_mass = {
                            "instancia": instancia_selecionada, "mensagem": mensagem,
                            "lista_ids": ids, "incluir_menu": usar_menu,
                            "url_midia": url_final, "tipo_midia": tipo_msg
                        }
                        
                        with st.spinner(f"Enviando para {len(ids)} contatos..."):
                            try:
                                r_disp = requests.post(f"{API_URL}/disparo/em-massa", json=payload_mass)
                                if r_disp.status_code == 200:
                                    d = r_disp.json()
                                    st.balloons()
                                    st.success(f"✅ Concluído! Enviados: {d['enviados']} | Erros: {d['erros']}")
                                    st.session_state.confirmacao_disparo = False # Reseta a trava
                                    time.sleep(3)
                                    st.rerun()
                                else: 
                                    st.error("Erro no envio.")
                            except Exception as e: 
                                st.error(f"Erro: {e}")
        
elif selected == "Minha Assinatura":
    st.subheader("💳 Detalhes da Assinatura")
    
    if 'user_info' not in st.session_state:
        st.error("Faça login novamente.")
        st.stop()

    u = st.session_state.user_info
    
    # --- 1. CARTÕES DE INFORMAÇÃO ---
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        
        with c1:
            st.metric("Plano Atual", u.get("plano", "Gratuito"))
        with c2:
            val = float(u.get("valor_mensal") or 0.0)
            st.metric("Valor Mensal", f"R$ {val:.2f}")
        with c3:
            # Formata a data de vencimento
            venc_str = u.get("data_vencimento")
            if venc_str:
                try:
                    dt = pd.to_datetime(venc_str).strftime('%d/%m/%Y')
                except: dt = "Indefinido"
            else: dt = "N/A"
            st.metric("Próximo Vencimento", dt)
        with c4:
            st.write("Status:")
            status = u.get("status_conta", "ativo")
            if status == "ativo":
                st.markdown("<span class='status-ok'>Ativo ✅</span>", unsafe_allow_html=True)
            elif status == "vencido":
                st.markdown("<span class='status-err'>Vencido ⚠️</span>", unsafe_allow_html=True)
            else:
                st.write(status.upper())

    st.write("")
    st.markdown("### 🔄 Renovar ou Fazer Upgrade")
    st.caption("Escolha um novo plano ou pague o atual para renovar.")

    # --- 2. ÁREA DE RENOVAÇÃO (DINÂMICA) ---
    with st.container(border=True):
        col_opcoes, col_pagamento = st.columns([1, 1.5])
        
        # BUSCA PLANOS NO BANCO DE DADOS
        opcoes_planos = {} # Dicionário: {'Nome': Valor}
        try:
            res_planos = requests.get(f"{API_URL}/planos/listar")
            if res_planos.status_code == 200:
                lista_db = res_planos.json()
                for p in lista_db:
                    # Só mostra planos ativos
                    if p.get('ativo', True):
                        opcoes_planos[p['nome']] = float(p['valor'])
        except:
            pass
        
        # Fallback de segurança caso a API falhe ou banco esteja vazio
        if not opcoes_planos:
            opcoes_planos = {"Básico": 99.90, "Pro": 149.90}

        with col_opcoes:
            st.markdown("#### 1. Escolha o Plano")
            
            # Tenta selecionar o plano atual do usuário como padrão, se existir na lista
            plano_atual_nome = u.get("plano", "Básico")
            index_padrao = 0
            lista_nomes = list(opcoes_planos.keys())
            
            if plano_atual_nome in lista_nomes:
                index_padrao = lista_nomes.index(plano_atual_nome)

            novo_plano = st.radio("Selecione:", lista_nomes, index=index_padrao)
            
            # Pega o valor do dicionário
            valor_tabela = opcoes_planos[novo_plano]
            
            st.markdown(f"<h3 style='color:#4cd137'>R$ {valor_tabela:.2f} <span style='font-size:14px; color:gray'>/mês</span></h3>", unsafe_allow_html=True)
            
            cupom_renov = st.text_input("🎟️ Cupom de Desconto", placeholder="Tem um código?")

        with col_pagamento:
            st.markdown("#### 2. Pagamento Seguro")
            tab_pix, tab_card = st.tabs(["💠 Pix (Instantâneo)", "💳 Cartão de Crédito"])
            
            # --- ABA PIX ---
            with tab_pix:
                if st.button("Gerar QR Code Pix", type="primary", use_container_width=True):
                    payload = {
                        "user_id": u.get('id'), 
                        "plano": novo_plano, 
                        # O backend vai ignorar esse valor e recalcular, mas enviamos para referência
                        "valor": valor_tabela, 
                        "cupom": cupom_renov
                    }
                    with st.spinner("Gerando Pix..."):
                        try:
                            # Chama a rota de renovação do Backend
                            res = requests.post(f"{API_URL}/pagamento/gerar", json=payload, timeout=15)
                            if res.status_code == 200:
                                data = res.json()
                                
                                # Verifica se foi 100% OFF (Gratuito)
                                if data.get("status") == "aprovado_direto":
                                    st.balloons()
                                    st.success("✅ Cupom de 100% aplicado! Assinatura renovada.")
                                    time.sleep(2)
                                    st.rerun()
                                else:
                                    # Salva na sessão para exibir
                                    st.session_state.pix_renovacao = data
                                    
                                    # Se houve desconto no backend, avisa
                                    val_final_api = data.get('valor_final', valor_tabela)
                                    if val_final_api < valor_tabela:
                                        st.toast(f"Desconto aplicado! De {valor_tabela} por {val_final_api}", icon="🎉")
                                    
                                    st.success("QR Code Gerado!")
                                    st.rerun()
                            else:
                                erro = res.json().get('detail', res.text)
                                st.error(f"Erro: {erro}")
                        except Exception as e:
                            st.error(f"Erro de conexão: {e}")

            # --- ABA CARTÃO ---
            with tab_card:
                st.info("Você será redirecionado para o Mercado Pago.")
                if st.button("Pagar com Cartão 💳", use_container_width=True):
                    payload_card = {
                        "user_id": u.get('id'),
                        "plano": novo_plano,
                        "valor": valor_tabela,
                        "email": u.get('email', 'cliente@email.com')
                    }
                    with st.spinner("Criando link..."):
                        try:
                            res = requests.post(f"{API_URL}/pagamento/mp-cartao", json=payload_card)
                            if res.status_code == 200:
                                link = res.json().get("checkout_url")
                                st.success("Link criado!")
                                st.link_button("👉 CLIQUE PARA PAGAR NO MERCADO PAGO", link, type="primary", use_container_width=True)
                            else:
                                st.error(f"Erro: {res.text}")
                        except Exception as e:
                            st.error(f"Erro: {e}")

    # --- 3. EXIBIÇÃO DO QR CODE PIX (SE TIVER) ---
    if "pix_renovacao" in st.session_state:
        pix_data = st.session_state.pix_renovacao
        st.divider()
        with st.container(border=True):
            st.info("Escaneie para pagar e liberar na hora:")
            c_qr1, c_qr2 = st.columns([1, 2])
            
            with c_qr1:
                try:
                    img_bytes = base64.b64decode(pix_data['qr_base64'])
                    st.image(BytesIO(img_bytes), caption="QR Code Pix", use_container_width=True)
                except:
                    st.warning("Imagem QR indisponível")
            
            with c_qr2:
                val_final = pix_data.get('valor_final', 0.0)
                st.markdown(f"### Total a Pagar: R$ {val_final:.2f}")
                st.text_area("Copia e Cola:", pix_data['qr_code'], height=100)
                
                if st.button("✅ Já fiz o Pix (Atualizar Página)", type="primary"):
                    st.session_state.pix_renovacao = None # Limpa
                    st.rerun()

elif selected == "Gestão de Equipe":
    u = st.session_state.user_info
    if u.get('tipo_acesso', 'admin') == 'funcionario':
        st.error("⛔ Acesso restrito a administradores.")
    else:
        tela_gestao_equipe()

elif selected == "Atendimento Humano":
    tela_atendente()

elif selected == "Ajuda":  # <--- AGORA O LINK FUNCIONA AQUI
    tela_ajuda()

elif selected == "Agenda de Tarefas":
    tela_agenda_tarefas()
# ----------------------


