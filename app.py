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
    required = ["ml_client_id", "ml_client_secret", "OAUTH_REDIRECT_URI", "GROQ_API_KEY"]
    return all(get_secret(k) for k in required)

class Agent:
    def get_auth_url(self):
        client_id = get_secret("ml_client_id")
        redirect_uri = get_secret("OAUTH_REDIRECT_URI")
        
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

    def run_agent(self, prompt: str) -> str:
        access_token = get_secret("ml_access_token")
        user_id = get_secret("ml_user_id")
        groq_api_key = get_secret("GROQ_API_KEY")
        
        # Coleta dados do Mercado Livre se a pergunta envolver vendas/pedidos
        ml_context = ""
        if any(w in prompt.lower() for w in ["venda", "pedido", "faturamento", "conta", "desempenho"]):
            headers_ml = {"Authorization": f"Bearer {access_token}"}
            url = f"https://api.mercadolibre.com/orders/search?seller={user_id}"
            res = requests.get(url, headers=headers_ml)
            if res.status_code == 200:
                ml_context = f"Dados brutos da API do Mercado Livre: {res.text[:1500]}"
            else:
                ml_context = f"Não foi possível buscar dados da API do ML: {res.text}"

        # Configura a requisição para a API do Groq
        headers_groq = {
            "Authorization": f"Bearer {groq_api_key}",
            "Content-Type": "application/json"
        }
        
        messages = [
            {
                "role": "system", 
                "content": "Você é um agente de IA especialista em e-commerce, análise de dados e otimização de vendas para vendedores do Mercado Livre. Forneça insights estratégicos e práticos com base nos dados fornecidos."
            }
        ]
        
        if ml_context:
            messages.append({"role": "system", "content": ml_context})
            
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": "llama-3.3-70b-versatile",
            "messages": messages,
            "temperature": 0.7
        }

        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers_groq)
        
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"]
        else:
            return f"Erro na API do Groq: {response.text}"

def render_dashboard(agent: Agent):
    st.title("🤖 Agente IA — Mercado Livre")
    st.success("Conectado ao Mercado Livre e Groq com sucesso!")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Peça uma análise ou faça uma pergunta sobre sua loja..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Gerando insights com IA..."):
                response = agent.run_agent(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

def main():
    if not has_all_required_secrets():
        st.title("Configuração de Credenciais")
        st.warning("Configure todas as chaves (incluindo GROQ_API_KEY) nas Secrets do Streamlit.")
        st.code('ml_client_id = "..."\nml_client_secret = "..."\nOAUTH_REDIRECT_URI = "..."\nGROQ_API_KEY = "gsk_..."', language='toml')
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
        st.session_state["logged_in"] = True
        render_dashboard(agent)

if __name__ == "__main__":
    main()
