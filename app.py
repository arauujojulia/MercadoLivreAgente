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
