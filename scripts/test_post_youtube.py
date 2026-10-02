"""
Script de Teste de Upload no YouTube Shorts via Playwright (Modo Visual / Headless).
Executa o fluxo completo do YouTube Studio para um corte existente.
"""
import sys
import argparse
from pathlib import Path

# Ajusta encoding para terminal Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.services.youtube_browser_publisher import YouTubeBrowserPublisher
from src.core.config import settings

def main():
    parser = argparse.ArgumentParser(description="Testar upload no YouTube Studio via Playwright")
    parser.add_argument("--video", type=str, help="Caminho do arquivo .mp4 para teste")
    parser.add_argument("--title", type=str, default="Teste Automatizado Shorts #01", help="Título do vídeo")
    parser.add_argument("--headless", action="store_true", help="Rodar em modo sem interface gráfica (headless)")
    args = parser.parse_args()

    # Busca vídeo informado ou pega o primeiro disponível em clips_exportados
    if args.video:
        video_path = Path(args.video)
    else:
        clips_dir = settings.OUTPUT_DIR
        mp4_files = list(clips_dir.glob("*.mp4"))
        if not mp4_files:
            print(f"❌ Nenhum vídeo encontrado em '{clips_dir}'.")
            print("Especifique um vídeo usando: python scripts/test_post_youtube.py --video caminho/do/video.mp4")
            sys.exit(1)
        video_path = mp4_files[0]

    print("=" * 65)
    print("🎬 TESTE DE UPLOAD NO YOUTUBE SHORTS VIA NAVEGADOR")
    print("=" * 65)
    print(f"📁 Arquivo de vídeo: {video_path}")
    print(f"📝 Título: {args.title}")
    print(f"🖥️ Modo Headless: {'Sim' if args.headless else 'Não (Janela Visível)'}")
    print("=" * 65 + "\n")

    publisher = YouTubeBrowserPublisher(headless=args.headless)

    if not publisher.is_authenticated():
        print("❌ Sessão do YouTube não encontrada!")
        print("Execute primeiro:")
        print("  python scripts/youtube_login.py")
        sys.exit(1)

    try:
        result = publisher.publish_short(
            video_path=video_path,
            title=args.title,
            description="Vídeo publicado através do pipeline automatizado Playwright.",
            tags=["shorts", "cortes", "viral"],
            clip_uid=f"test_{video_path.stem[:8]}"
        )
        print("\n" + "=" * 65)
        print("🎉 UPLOAD CONCLUÍDO COM SUCESSO!")
        print(f"🆔 Video ID: {result.get('youtube_video_id')}")
        print(f"🔗 Link: https://youtube.com/shorts/{result.get('youtube_video_id')}")
        print("=" * 65)
    except Exception as e:
        print(f"\n❌ Erro durante o teste de upload: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
