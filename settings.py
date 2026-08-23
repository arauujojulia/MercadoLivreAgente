from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import streamlit as st

APP_NAME = "AgenteML"
# Diretório de dados no servidor do Streamlit
APP_DATA_DIR = Path.cwd() / f".{APP_NAME.lower()}"
APP_DATA_DIR.mkdir(exist_ok=True)

DB_PATH = APP_DATA_DIR / "agente_ml.sqlite3"
MODEL_PATH = APP_DATA_DIR / "forecast_model.pkl"

# A URL do seu app no Streamlit Cloud (você vai cadastrar essa variável lá depois)
OAUTH_REDIRECT_URI = st.secrets.get("OAUTH_REDIRECT_URI", "http://localhost:8501")

@dataclass
class Credential:
    key: str
    prompt_label: str

CREDENTIALS = {
    "ml_client_id": Credential("ml_client_id", "Client ID (Mercado Livre)"),
    "ml_client_secret": Credential("ml_client_secret", "Client Secret (Mercado Livre)"),
    "groq_api_key": Credential("groq_api_key", "Chave da API Groq"),
    "wandb_api_key": Credential("wandb_api_key", "Chave da API Weights & Biases"),
}

def get_secret(name: str) -> str | None:
    """Busca o segredo nos st.secrets (nuvem) ou na sessão do usuário."""
    if name in st.secrets:
        return st.secrets[name]
    if name in st.session_state:
        return st.session_state[name]
    return None

def set_secret(name: str, value: str) -> None:
    """Salva dados dinâmicos (como tokens do ML) na sessão atual."""
    st.session_state[name] = value

def delete_secret(name: str) -> None:
    if name in st.session_state:
        del st.session_state[name]

def has_all_required_secrets() -> bool:
    required = ["ml_client_id", "ml_client_secret", "groq_api_key"]
    return all(get_secret(name) for name in required)