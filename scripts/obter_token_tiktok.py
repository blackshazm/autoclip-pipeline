"""
Script para trocar o Authorization Code pelo Access Token do TikTok e atualizar o .env e config/tiktok_token.json automaticamente.
"""
import sys
import json
import argparse
import requests
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

CONFIG_DIR = ROOT_DIR / "config"
TOKEN_FILE = CONFIG_DIR / "tiktok_token.json"
ENV_FILE = ROOT_DIR / ".env"

CLIENT_KEY = os.getenv("TIKTOK_CLIENT_KEY", "").strip()
CLIENT_SECRET = os.getenv("TIKTOK_CLIENT_SECRET", "").strip()
REDIRECT_URI = os.getenv("TIKTOK_REDIRECT_URI", "https://blackshazm.github.io/autoclip-pipeline/callback.html").strip()

def exchange_code_for_token(code: str):
    code = code.strip()
    if not code:
        print("❌ Código de autorização não fornecido.")
        return False

    token_url = "https://open.tiktokapis.com/v2/oauth/token/"
    payload = {
        "client_key": CLIENT_KEY,
        "client_secret": CLIENT_SECRET,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    print(f"🔄 Solicitando Access Token para o TikTok...")
    res = requests.post(token_url, data=payload, headers=headers, timeout=30)
    
    if res.status_code == 200:
        data = res.json()
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        access_token = data.get("access_token") or data.get("data", {}).get("access_token")
        open_id = data.get("open_id") or data.get("data", {}).get("open_id")

        if not access_token:
            print(f"⚠️ Resposta da API não continha access_token: {data}")
            return False

        # Atualiza o arquivo .env
        if ENV_FILE.exists():
            env_content = ENV_FILE.read_text(encoding="utf-8")
            
            # Substitui ou adiciona TIKTOK_ACCESS_TOKEN
            if "TIKTOK_ACCESS_TOKEN=" in env_content:
                lines = env_content.splitlines()
                new_lines = []
                for line in lines:
                    if line.startswith("TIKTOK_ACCESS_TOKEN="):
                        new_lines.append(f"TIKTOK_ACCESS_TOKEN={access_token}")
                    elif line.startswith("TIKTOK_OPEN_ID="):
                        new_lines.append(f"TIKTOK_OPEN_ID={open_id}")
                    else:
                        new_lines.append(line)
                ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
            else:
                with open(ENV_FILE, "a", encoding="utf-8") as f:
                    f.write(f"\nTIKTOK_ACCESS_TOKEN={access_token}\nTIKTOK_OPEN_ID={open_id}\n")

        print(f"\n✅ Token obtido e salvo com sucesso!")
        print(f"📄 Arquivo salvo: {TOKEN_FILE}")
        print(f"📄 .env atualizado com TIKTOK_ACCESS_TOKEN!")
        return True
    else:
        print(f"\n❌ Erro ao obter token do TikTok ({res.status_code}):")
        print(res.text)
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Troca código de autorização pelo Access Token do TikTok")
    parser.add_argument("code", nargs="?", default=None, help="Código de autorização retornado na URL de callback")
    args = parser.parse_args()

    code_input = args.code or input("👉 Cole o código de autorização obtido na tela do GitHub Pages: ").strip()
    exchange_code_for_token(code_input)
