import base64
import hashlib
import os
import requests

from settings import get_secret, set_secret

def generate_pkce_pair():
    verifier_bytes = os.urandom(32)
    code_verifier = base64.urlsafe_b64encode(verifier_bytes).rstrip(b'=').decode('utf-8')
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode('utf-8')
    return code_verifier, code_challenge


def get_auth_url():
    """Monta o link de login do Mercado Livre."""
    client_id = get_secret("ml_client_id")
    redirect_uri = get_secret("OAUTH_REDIRECT_URI")
    
    # Gera e salva o verificador na sessão
    code_verifier, code_challenge = generate_pkce_pair()
    set_secret("pkce_verifier", code_verifier) 

    auth_url = (
        f"https://auth.mercadolivre.com.br/authorization"
        f"?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={redirect_uri}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    return auth_url


def exchange_token(code):
    """Pega o código que veio na URL e troca pelo token final."""
    client_id = get_secret("ml_client_id")
    client_secret = get_secret("ml_client_secret")
    redirect_uri = get_secret("OAUTH_REDIRECT_URI")
    code_verifier = get_secret("pkce_verifier")

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


class Agent:
    def exchange_token(self, code):
        pass

    def get_auth_url(self):
        pass
