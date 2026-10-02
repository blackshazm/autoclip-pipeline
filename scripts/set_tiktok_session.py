"""
Script para injetar o cookie sessionid do TikTok diretamente no config/tiktok_state.json.
Isso dispensa qualquer necessidade de login com janela ou captcha.
"""
import sys
import json
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT_DIR / "config"
STATE_FILE = CONFIG_DIR / "tiktok_state.json"
ENV_FILE = ROOT_DIR / ".env"

def create_state_from_session_id(session_id: str):
    session_id = session_id.strip().strip('"').strip("'")
    if not session_id:
        print("❌ sessionid não pode ser vazio.")
        return False

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Constrói os cookies essenciais que o TikTok usa para validar a sessão
    cookies = [
        {
            "name": "sessionid",
            "value": session_id,
            "domain": ".tiktok.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "Lax"
        },
        {
            "name": "sessionid_ss",
            "value": session_id,
            "domain": ".tiktok.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        },
        {
            "name": "sid_tt",
            "value": session_id,
            "domain": ".tiktok.com",
            "path": "/",
            "expires": -1,
            "httpOnly": True,
            "secure": True,
            "sameSite": "None"
        }
    ]

    state_data = {
        "cookies": cookies,
        "origins": [
            {
                "origin": "https://www.tiktok.com",
                "localStorage": []
            }
        ]
    }

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state_data, f, indent=2)

    print(f"✅ Arquivo de sessão gerado com sucesso em: {STATE_FILE}")

    # Atualiza o arquivo .env
    if ENV_FILE.exists():
        content = ENV_FILE.read_text(encoding="utf-8")
        if "TIKTOK_SESSION_ID=" in content:
            lines = content.splitlines()
            new_lines = [
                f"TIKTOK_SESSION_ID={session_id}" if line.startswith("TIKTOK_SESSION_ID=") else line
                for line in lines
            ]
            ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        else:
            with open(ENV_FILE, "a", encoding="utf-8") as f:
                f.write(f"\nTIKTOK_SESSION_ID={session_id}\n")

    print(f"✅ .env atualizado com TIKTOK_SESSION_ID!")
    return True

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Configura sessão do TikTok via sessionid")
    parser.add_argument("sessionid", nargs="?", default=None, help="Valor do cookie sessionid")
    args = parser.parse_args()

    sid = args.sessionid or input("👉 Cole o cookie sessionid do TikTok: ").strip()
    create_state_from_session_id(sid)
