import base64
import hashlib
import requests
import streamlit as st

st.set_page_config(page_title="Agente ML — Mercado Livre", layout="wide")

def get_secret(key):
    if key in st.secrets:
        return st.secrets[key]
    return st.session_state.get(key)

def set_secret(key, value):
    st.session_state[key] = value

def has_all_required_secrets():
    return all(get_secret(k) for k in ["ml_client_id", "ml_client_secret", "OAUTH_REDIRECT_URI"])

class Agent:
    def get_auth_url(self):
        client_id = get_secret("ml_client_id")
        redirect_uri = get_secret("OAUTH_REDIRECT_URI")
        
        # Verificador determinístico para persistir entre o redirect do mobile
        code_verifier = "mercadolivre_agente_v1_secure_verifier"
        challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
        code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode('utf-8')
        
        set_secret("pkce_verifier", code_verifier)

        return (
            f"https://auth.mercadolivre.com.br/authorization"
            f"?response_type=code"
            f"&client_id={client_id}"
            f"&redirect_uri={redirect_uri}"
            f"&code_challenge={code_challenge}"
            f"&code_challenge_method=S256"
        )

    def exchange_token(self, code):
        client_id = get_secret("ml_client_id")
        client_secret = get_secret("ml_client_secret")
        redirect_uri = get_secret("OAUTH_REDIRECT_URI")
        
        # Recupera da sessão ou usa o fallback garantido
        code_verifier = get_secret("pkce_verifier") or "mercadolivre_agente_v1_secure_verifier"

        payload = {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": code_verifier
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

def main():
    if not has_all_required_secrets():
        st.title("Configuração de Credenciais")
        st.warning("Configure as chaves nas Secrets do Streamlit.")
        return

    agent = Agent()

    if "code" in st.query_params:
        code = st.query_params["code"]
        with st.spinner("Autenticando na API..."):
            try:
                agent.exchange_token(code)
                st.session_state["logged_in"] = True
                st.query_params.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Falha na troca de token: {e}")
                return

    if not st.session_state.get("logged_in") and not get_secret("ml_refresh_token"):
        st.title("Agente ML — Mercado Livre")
        auth_url = agent.get_auth_url()
        st.link_button("Conectar conta ML", auth_url, type="primary")
    else:
        st.title("Painel da Loja")
        st.success("Autenticado com sucesso! O token está ativo.")

if __name__ == "__main__":
    main()
