import sys
from pathlib import Path

# Ajusta path para importar src
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src.services.tiktok_browser_publisher import TikTokBrowserPublisher

def upload_tiktok_video(
    video_path: Path,
    title: str = "Dicas de Alta Performance e Foco #01",
    tags: list = None,
    headless: bool = False
) -> bool:
    tags = tags or ["cortes", "podcast", "viral", "foco"]
    publisher = TikTokBrowserPublisher(headless=headless)

    if not publisher.is_authenticated():
        print("❌ Sessão do TikTok não encontrada!")
        print("Execute primeiro: LOGIN_TIKTOK.bat ou python scripts/tiktok_login.py para fazer login uma única vez.")
        return False

    if not video_path.exists():
        print(f"❌ Vídeo não encontrado: {video_path}")
        return False

    print("=" * 65)
    print("🚀 INICIANDO UPLOAD NO TIKTOK VIA TIKTOK BROWSER PUBLISHER")
    print("=" * 65)
    print(f"📁 Vídeo: {video_path.name}")
    print(f"📝 Título: {title}")
    print(f"🏷️ Tags: {tags}")
    print(f"🖥️ Modo Visível: {'Sim' if not headless else 'Não (Headless)'}")
    print("=" * 65 + "\n")

    try:
        res = publisher.publish_video(
            video_path=video_path,
            title=title,
            tags=tags,
            clip_uid=f"manual_{video_path.stem[:8]}"
        )
        print(f"✅ Vídeo publicado com sucesso! Post ID: {res.get('tiktok_post_id')}")
        return True
    except Exception as e:
        print(f"❌ Erro ao publicar no TikTok: {e}")
        return False

if __name__ == "__main__":
    clips_dir = Path("data/clips_exportados")
    mp4s = list(clips_dir.glob("*.mp4"))
    if not mp4s:
        print("Nenhum vídeo mp4 encontrado em data/clips_exportados")
        sys.exit(1)

    target_video = mp4s[0]
    upload_tiktok_video(video_path=target_video, headless=False)
