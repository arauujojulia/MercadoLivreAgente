import base64
import hashlib
import requests
import streamlit as st
import wandb

st.set_page_config(page_title="Agente ML — Mercado Livre", layout="wide")

def get_secret(key):
    if key in st.secrets:
        return st.secrets[key]
    return st.session_state.get(key)

def set_secret(key, value):
    st.session_state[key] = value

def has_all_required_secrets():
    required = ["ml_client_id", "ml_client_secret", "OAUTH_REDIRECT_URI", "groq_api_key"]
    return all(get_secret(k) for k in required)

class Agent:
    def __init__(self):
        # Inicializa o Wandb se a chave estiver presente
        wandb_key = get_secret("wandb_api_key")
        if wandb_key and not wandb.run:
            try:
                wandb.login(key=wandb_key)
                wandb.init(project="agente-mercado-livre", reinit=True, mode="online")
            except Exception as e:
                print(f"Erro ao inicializar Wandb: {e}")

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
        
        headers = {"accept": "application/json", "content-type": "application/x-www-form-urlencoded"}
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
        groq_api_key = get_secret("groq_api_key")
        
        headers_ml = {"Authorization": f"Bearer {access_token}"}
        
        user_info = {}
        res_user = requests.get("https://api.mercadolibre.com/users/me", headers=headers_ml)
        if res_user.status_code == 200:
            user_info = res_user.json()

        items_data = {}
        res_items = requests.get(f"https://api.mercadolibre.com/users/{user_id}/items/search", headers=headers_ml)
        if res_items.status_code == 200:
            items_data = res_items.json()

        orders_data = {}
        res_orders = requests.get(f"https://api.mercadolibre.com/orders/search?seller={user_id}", headers=headers_ml)
        if res_orders.status_code == 200:
            orders_data = res_orders.json()

        ml_context = f"""
        [DADOS REAIS DA CONTA DO MERCADO LIVRE]
        - Informações da Conta: {user_info}
        - IDs dos Anúncios/Itens: {items_data}
        - Pedidos/Vendas: {orders_data}
        """

        headers_groq = {"Authorization": f"Bearer {groq_api_key}", "Content-Type": "application/json"}
        messages = [
            {"role": "system", "content": "Você é um agente de IA especialista em e-commerce e Mercado Livre."},
            {"role": "system", "content": ml_context},
            {"role": "user", "content": prompt}
        ]

        payload = {"model": "openai/gpt-oss-120b", "messages": messages, "temperature": 0.7}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", json=payload, headers=headers_groq)
        
        if response.status_code == 200:
            answer = response.json()["choices"][0]["message"]["content"]
            
            # Loga a interação no Weights & Biases
            if wandb.run:
                wandb.log({
                    "prompt": prompt,
                    "response": answer,
                    "user_id": user_id
                })
                
            return answer
        else:
            return f"Erro na API do Groq: {response.text}"

def render_dashboard(agent: Agent):
    st.title("🤖 Agente IA — Mercado Livre")
    st.success("Conectado ao Mercado Livre, Groq e Wandb!")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    if prompt := st.chat_input("Faça uma pergunta sobre sua loja..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Processando e registrando no Wandb..."):
                response = agent.run_agent(prompt)
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})

def main():
    if not has_all_required_secrets():
        st.title("Configuração de Credenciais")
        st.error("Faltam variáveis nas Secrets do Streamlit.")
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
