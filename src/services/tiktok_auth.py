"""
Utilitário de Autenticação OAuth2 do TikTok.
Inicia um servidor local simples para receber o callback de autorização e trocar pelo Access Token oficial.
"""
import urllib.parse
import webbrowser
import http.server
import socketserver
import requests
import json
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"
TOKEN_FILE = CONFIG_DIR / "tiktok_token.json"

PORT = 8088
REDIRECT_URI = "https://blackshazm.github.io/autoclip-pipeline/callback.html"

class TikTokAuthHandler(http.server.SimpleHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/callback":
            params = urllib.parse.parse_qs(parsed.query)
            TikTokAuthHandler.auth_code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>Autenticacao TikTok Concluida!</h1><p>Pode fechar esta janela e voltar ao terminal.</p>")
        else:
            self.send_response(404)
            self.end_headers()

def authenticate_tiktok(client_key: str, client_secret: str, code: str = None):
    """
    Gera URL de autorização do TikTok e aguarda o código de autorização para trocar pelo Access Token.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    scopes = "user.info.basic,video.upload,video.publish"
    
    auth_url = (
        f"https://www.tiktok.com/v2/auth/authorize/?"
        f"client_key={client_key}&"
        f"scope={scopes}&"
        f"response_type=code&"
        f"redirect_uri={urllib.parse.quote(REDIRECT_URI)}&"
        f"state=you1_state"
    )

    if not code:
        print("\n" + "=" * 65)
        print("🔗 LINK DE AUTORIZAÇÃO DO TIKTOK:")
        print(auth_url)
        print("=" * 65 + "\n")
        print("1. Abra o link acima no seu navegador (caso não abra sozinho).")
        print("2. Faça login e autorize o aplicativo.")
        print("3. Você será redirecionado para a página do GitHub Pages com seu código.")
        
        try:
            webbrowser.open(auth_url)
        except Exception:
            pass

        code = input("\n👉 Cole o código de autorização aqui (ou pressione Enter se já configurou): ").strip()

    if not code:
        print("❌ Código de autorização não fornecido.")
        return None

    print(f"\n[OK] Processando código de autorização: {code[:10]}...")

    # Troca code por access_token
    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    payload = {
        "client_key": client_key,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    res = requests.post(token_url, data=payload, headers=headers)
    if res.status_code == 200:
        data = res.json()
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        access_token = data.get("access_token") or data.get("data", {}).get("access_token")
        open_id = data.get("open_id") or data.get("data", {}).get("open_id")

        print(f"\n✅ Token salvo com sucesso em: {TOKEN_FILE}")
        print("\nCopie e cole no seu arquivo .env:")
        print(f"TIKTOK_ACCESS_TOKEN={access_token}")
        print(f"TIKTOK_OPEN_ID={open_id}\n")
        return data
    else:
        print(f"\n❌ Erro ao obter token do TikTok ({res.status_code}): {res.text}")
        return None

if __name__ == "__main__":
    import sys
    import argparse
    import os

    parser = argparse.ArgumentParser(description="Autenticador TikTok OAuth2")
    parser.add_argument("--key", default=os.getenv("TIKTOK_CLIENT_KEY", ""), help="TikTok Client Key")
    parser.add_argument("--secret", default=os.getenv("TIKTOK_CLIENT_SECRET", ""), help="TikTok Client Secret")
    parser.add_argument("--code", default=None, help="Código de autorização retornado pela URL")
    args = parser.parse_args()

    ck = args.key or input("Digite seu Client Key do TikTok: ").strip()
    cs = args.secret or input("Digite seu Client Secret do TikTok: ").strip()
    
    if ck and cs:
        authenticate_tiktok(ck, cs, code=args.code)
    else:
        print("Client Key ou Client Secret vazios.")
