"""
Utilitário de Autenticação OAuth2 do YouTube.
Permite conectar o canal do YouTube gerando config/youtube_token.json via navegador.
"""
import os
import sys
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("youtube_auth")

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly"
]

def authenticate_youtube():
    client_secrets = settings.YOUTUBE_CLIENT_SECRETS
    token_path = settings.YOUTUBE_TOKEN_PATH

    client_secrets.parent.mkdir(parents=True, exist_ok=True)
    token_path.parent.mkdir(parents=True, exist_ok=True)

    if not client_secrets.exists():
        print(f"\n❌ Arquivo de credenciais não encontrado: {client_secrets}")
        print("Para conectar seu canal do YouTube:")
        print("1. Acesse o Google Cloud Console: https://console.cloud.google.com/")
        print("2. Crie um projeto e ative a 'YouTube Data API v3'.")
        print("3. Crie uma credencial OAuth 2.0 (Aplicativo para Computador).")
        print(f"4. Baixe o JSON e salve como: {client_secrets.resolve()}\n")
        return False

    print("\nIniciando fluxo de login do YouTube...")
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), SCOPES)
    auth_url, _ = flow.authorization_url(prompt="consent", access_type="offline")
    print(f"\n=======================================================")
    print(f"🔗 LINK DE AUTORIZAÇÃO DO GOOGLE:")
    print(f"{auth_url}")
    print(f"=======================================================\n")
    print("Aguardando consentimento no navegador...")

    creds = flow.run_local_server(port=8080, prompt="consent", open_browser=True)

    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())

    print(f"\n✅ Canal autenticado com sucesso! Token salvo em: {token_path}")
    return True

if __name__ == "__main__":
    authenticate_youtube()
