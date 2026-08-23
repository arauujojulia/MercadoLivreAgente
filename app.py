from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

from settings import CREDENTIALS, get_secret, has_all_required_secrets, set_secret
from agent_core import Agent

st.set_page_config(page_title="Agente ML — Mercado Livre", layout="wide")

@st.cache_resource
def get_agent() -> Agent:
    return Agent()

def render_onboarding():
    st.title("Configuração de Credenciais")
    st.write("Como estamos na nuvem, preencha as chaves abaixo para esta sessão.")

    with st.form("onboarding_form"):
        values = {}
        for key, cred in CREDENTIALS.items():
            if not get_secret(key):
                values[key] = st.text_input(cred.prompt_label, type="password")
            else:
                st.success(f"{cred.prompt_label} já configurado via Secrets do Streamlit.")
                
        submitted = st.form_submit_button("Salvar e continuar")

    if submitted:
        for key, value in values.items():
            if value:
                set_secret(key, value)
        st.success("Credenciais temporárias salvas. Recarregando...")
        st.rerun()

def render_login(agent: Agent):
    st.title("Agente ML — Mercado Livre")
    
    # 1. Verifica se estamos voltando do ML com o código de autorização na URL
    if "code" in st.query_params:
        code = st.query_params["code"]
        with st.spinner("Autenticando..."):
            try:
                agent.exchange_token(code)
                st.session_state["logged_in"] = True
                st.query_params.clear() # Limpa a URL
                st.rerun()
            except Exception as e:
                st.error(f"Erro ao autenticar: {e}")
                return

    st.write("Conecte sua conta do Mercado Livre para começar.")
    
    # 2. Mostra o botão que leva o usuário para a tela de login do ML
    auth_url = agent.get_auth_url()
    st.link_button("Conectar conta ML", auth_url, type="primary")

def render_dashboard():
    # O SEU CÓDIGO DO DASHBOARD CONTINUA EXATAMENTE IGUAL AQUI.
    # Pode colar o código do `render_dashboard` antigo inteiro aqui para baixo.
    st.title("📊 Painel da Loja")
    st.success("Login feito com sucesso! Cole o restante do seu dashboard aqui.")

def main():
    if not has_all_required_secrets():
        render_onboarding()
        return

    agent = get_agent()

    if not st.session_state.get("logged_in") and not get_secret("ml_refresh_token"):
        render_login(agent)
    else:
        st.session_state["logged_in"] = True
        render_dashboard()

if __name__ == "__main__":
    main()
