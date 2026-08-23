import base64
import hashlib
import os
import requests
import streamlit as st

st.set_page_config(page_title="Agente ML — Mercado Livre", layout="wide")

# --- GERENCIAMENTO DE SEGREDOS E ESTADO ---
def get_secret(key):
    """Busca a chave primeiro nas secrets do Streamlit, depois na sessão."""
    if key in st.secrets:
        return st.secrets[key]
    return st.session_state.get(key)

def set_secret(key, value):
    st.session_state[key] = value

def has_all_required_secrets():
    required = ["ml_client_id", "ml_client_secret", "OAUTH_REDIRECT_URI"]
    return all(get_secret(k) for k in required)

# --- LÓGICA DO AGENTE (AUTENTICAÇÃO) ---
def generate_pkce_pair():
    verifier_bytes = os.urandom(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b'=').decode('utf-8')
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge

class Agent:
    def get_auth_url(self):
        client_id = get_secret("ml_client_id")
        redirect_uri = get_secret("OAUTH_REDIRECT_URI")
        
        auth_url = (
            f"https://auth.mercadolivre.com.br/authorization"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
        )
        return auth_url

    def exchange_token(self, code):
        client_id = get_secret("ml_client_id")
        client_secret = get_secret("ml_client_secret")
        redirect_uri = get_secret("OAUTH_REDIRECT_URI")

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri
        }
        
        headers = {
            "accept": "application/json",
            "content-type": "application/x-www-form-urlencoded"
        }
        
        response = requests.post("https://api.mercadolibre.com/oauth/token", data=payload, headers=headers)
        
        if response.status_code == 200:
            tokens = response.json()
            set_secret("ml_access_token", tokens.get("access_token"))
            set_secret("ml_refresh_token", tokens.get("refresh_token"))
            set_secret("ml_user_id", str(tokens.get("user_id")))
        else:
            raise Exception(f"Erro na API do ML: {response.text}")

# --- INTERFACE DE USUÁRIO ---
def render_onboarding():
    st.title("Configuração de Credenciais")
    st.warning("Configure as chaves no painel do Streamlit (Settings > Secrets).")
    st.write("Variáveis necessárias:")
    st.code('ml_client_id = "SEU_ID"\nml_client_secret = "SEU_SECRET"\nOAUTH_REDIRECT_URI = "SUA_URL_AQUI"', language='toml')

def render_login(agent: Agent):
    st.title("Agente ML — Mercado Livre")
    
    # 1. Verifica se estamos voltando do ML com o código
    if "code" in st.query_params:
        code = st.query_params["code"]
        with st.spinner("Autenticando..."):
            try:
                agent.exchange_token(code)
                st.session_state["logged_in"] = True
                st.query_params.clear() 
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao autenticar: {e}")
                return

    st.write("Conecte sua conta do Mercado Livre para começar.")
    
    # 2. Mostra botão de login
    auth_url = agent.get_auth_url()
    st.link_button("Conectar conta ML", auth_url, type="primary")

def render_dashboard(agent: Agent):
    st.title("📊 Painel da Loja")
    st.success("Login feito com sucesso! O token já está na sessão.")
    # Aqui entra o resto do seu dashboard depois.

def main():
    if not has_all_required_secrets():
        render_onboarding()
        return

    agent = Agent()

    if not st.session_state.get("logged_in") and not get_secret("ml_refresh_token"):
        render_login(agent)
    else:
        st.session_state["logged_in"] = True
        render_dashboard(agent)

if __name__ == "__main__":
    main()
