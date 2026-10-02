"""
Script para testar a postagem de 1 clipe no TikTok utilizando o TikTokBrowserPublisher.
"""
import sys
from pathlib import Path

# Adiciona o diretório raiz ao sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from src.services.tiktok_browser_publisher import TikTokBrowserPublisher
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("test_post_tiktok")

def test_single_upload(headless: bool = False):
    clips_dir = Path("data/clips_exportados")
    available_mp4s = list(clips_dir.glob("*.mp4"))

    if not available_mp4s:
        print(f"❌ Nenhum vídeo encontrado em {clips_dir}")
        return False

    video_path = available_mp4s[0]
    clip_uid = f"test_{video_path.stem[:12]}"

    print("=" * 65)
    print("🎬 TESTE DE POSTAGEM REAL NO TIKTOK STUDIO")
    print("=" * 65)
    print(f"📁 Vídeo selecionado: {video_path.name}")
    print(f"📦 Tamanho: {round(video_path.stat().st_size / (1024*1024), 2)} MB")
    print(f"🖥️ Modo Navegador: {'Visível (você verá na tela)' if not headless else 'Invisível (Headless)'}")
    print("=" * 65 + "\n")

    publisher = TikTokBrowserPublisher(headless=headless)

    if not publisher.is_authenticated():
        print("❌ Sessão do TikTok não encontrada!")
        print("Execute primeiro LOGIN_TIKTOK.bat")
        return False

    try:
        title = "Mentalidade e Foco Inabalável para Vencer Desafios"
        tags = ["foco", "disciplina", "mindset", "cortes", "podcast", "shorts"]

        print(f"📝 Legenda planejada: {publisher.format_caption(title, tags)}")
        print("🚀 Enviando para o TikTok Studio...")

        result = publisher.publish_video(
            video_path=video_path,
            title=title,
            tags=tags,
            clip_uid=clip_uid
        )

        print("\n" + "=" * 65)
        print("🎉 SUCESSO! RESULTADO DA PUBLICAÇÃO NO TIKTOK:")
        print("=" * 65)
        print(f"Status: {result.get('status')}")
        print(f"Post ID: {result.get('tiktok_post_id')}")
        print(f"Plataforma: {result.get('platform')}")
        print("=" * 65)
        return True

    except Exception as e:
        print(f"\n❌ Falha na publicação de teste: {e}")
        logger.error(f"Erro no teste de upload TikTok: {e}", exc_info=True)
        return False

if __name__ == "__main__":
    test_single_upload(headless=False)
