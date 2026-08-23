"""
Conector com a API oficial do Mercado Livre.

Responsável por:
1. Fluxo OAuth 2.0 (Authorization Code) usando um servidor HTTP local
   efêmero apenas para capturar o `code` de retorno.
2. Refresh automático de access_token.
3. Ingestão paginada de pedidos, itens e taxas.

Referência oficial: https://developers.mercadolivre.com.br/
"""

from __future__ import annotations

import threading
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Iterator
from urllib.parse import parse_qs, urlparse

import requests

from config.settings import OAUTH_CALLBACK_PORT, OAUTH_REDIRECT_URI, get_secret, set_secret

AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
API_BASE = "https://api.mercadolibre.com"


@dataclass
class TokenBundle:
    access_token: str
    refresh_token: str
    user_id: str
    expires_at: float  # epoch seconds


class _CallbackHandler(BaseHTTPRequestHandler):
    """Handler mínimo só para capturar ?code=... no redirect do OAuth."""

    captured_code: str | None = None

    def do_GET(self):  # noqa: N802 (nome exigido pela stdlib)
        parsed = urlparse(self.path)
        if parsed.path == "/callback":
            params = parse_qs(parsed.query)
            _CallbackHandler.captured_code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(
                "<html><body><h2>Autenticação concluída. "
                "Pode fechar esta aba e voltar ao Agente ML.</h2></body></html>".encode("utf-8")
            )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):  # silencia log padrão do BaseHTTPRequestHandler
        return


class MercadoLivreConnector:
    def __init__(self):
        self.client_id = get_secret("ml_client_id")
        self.client_secret = get_secret("ml_client_secret")
        self._tokens: TokenBundle | None = None

    # ------------------------------------------------------------------ #
    # Autenticação
    # ------------------------------------------------------------------ #
    def build_auth_url(self) -> str:
        return (
            f"{AUTH_URL}?response_type=code"
            f"&client_id={self.client_id}"
            f"&redirect_uri={OAUTH_REDIRECT_URI}"
        )

    def login_interactive(self, timeout_seconds: int = 120) -> TokenBundle:
        """
        Abre o navegador do usuário para autorizar o app, sobe um servidor HTTP
        local temporário só para capturar o `code`, e troca o code por tokens.
        """
        _CallbackHandler.captured_code = None
        server = HTTPServer(("localhost", OAUTH_CALLBACK_PORT), _CallbackHandler)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()

        webbrowser.open(self.build_auth_url())

        waited = 0
        while _CallbackHandler.captured_code is None and waited < timeout_seconds:
            time.sleep(0.5)
            waited += 0.5

        server.shutdown()
        server_thread.join(timeout=2)

        if _CallbackHandler.captured_code is None:
            raise TimeoutError("Login não concluído: tempo esgotado aguardando autorização do usuário.")

        return self._exchange_code_for_token(_CallbackHandler.captured_code)

    def _exchange_code_for_token(self, code: str) -> TokenBundle:
        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "redirect_uri": OAUTH_REDIRECT_URI,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._tokens = TokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            user_id=str(payload["user_id"]),
            expires_at=time.time() + payload["expires_in"],
        )
        # refresh_token é persistido criptografado; access_token fica só em memória
        set_secret("ml_refresh_token", self._tokens.refresh_token)
        set_secret("ml_user_id", self._tokens.user_id)
        return self._tokens

    def _refresh_access_token(self) -> TokenBundle:
        refresh_token = get_secret("ml_refresh_token")
        if not refresh_token:
            raise RuntimeError("Nenhum refresh_token salvo. É necessário logar novamente.")

        resp = requests.post(
            TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": refresh_token,
            },
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        self._tokens = TokenBundle(
            access_token=payload["access_token"],
            refresh_token=payload["refresh_token"],
            user_id=str(payload["user_id"]),
            expires_at=time.time() + payload["expires_in"],
        )
        set_secret("ml_refresh_token", self._tokens.refresh_token)
        return self._tokens

    def _ensure_valid_token(self) -> str:
        if self._tokens is None or time.time() >= self._tokens.expires_at - 30:
            self._refresh_access_token()
        return self._tokens.access_token

    # ------------------------------------------------------------------ #
    # Chamadas de API
    # ------------------------------------------------------------------ #
    def _get(self, path: str, params: dict | None = None) -> dict:
        token = self._ensure_valid_token()
        resp = requests.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
            params=params or {},
            timeout=20,
        )
        resp.raise_for_status()
        return resp.json()

    def iter_orders(self, since: str | None = None, page_size: int = 50) -> Iterator[dict]:
        """
        Itera todos os pedidos do vendedor autenticado, paginando automaticamente.
        `since` no formato ISO 8601 permite sincronização incremental.
        """
        user_id = get_secret("ml_user_id")
        offset = 0
        while True:
            params = {
                "seller": user_id,
                "limit": page_size,
                "offset": offset,
                "sort": "date_desc",
            }
            if since:
                params["order.date_created.from"] = since

            data = self._get("/orders/search", params=params)
            results = data.get("results", [])
            if not results:
                break
            for order in results:
                yield order
            offset += page_size
            if offset >= data.get("paging", {}).get("total", 0):
                break

    def get_item(self, item_id: str) -> dict:
        return self._get(f"/items/{item_id}")

    def get_billing_summary(self, group_id: str, period_from: str, period_to: str) -> dict:
        """Taxas e cobranças do período (endpoint de billing/faturas do ML)."""
        return self._get(
            f"/billing/integration/group/{group_id}/periods",
            params={"date_from": period_from, "date_to": period_to},
        )
