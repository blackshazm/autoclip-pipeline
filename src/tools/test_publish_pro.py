"""
Ferramenta CLI de Teste Autônomo para o Robô de Postagem PRO (YouTube Shorts).
Permite executar uploads com todos os metadados avançados sem interferir
no banco de dados ou nos workers em produção.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime

# Adiciona o diretório raiz ao sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))  # noqa: E402

from src.services.youtube_browser_publisher_pro import YouTubeBrowserPublisherPro, PublishPayloadPro  # noqa: E402
from src.core.logger import get_logger  # noqa: E402

logger = get_logger("test_publish_pro")


def main():
    parser = argparse.ArgumentParser(description="Testador CLI do Robô de Postagem PRO (YouTube Shorts)")
    parser.add_argument("--video", type=str, required=True, help="Caminho do arquivo de vídeo (.mp4)")
    parser.add_argument("--title", type=str, default="Teste de Corte Avançado #Shorts", help="Título do vídeo")
    parser.add_argument("--desc", type=str, default="Descrição avançada gerada pelo Robô PRO.", help="Descrição")
    parser.add_argument("--tags", type=str, default="cortes,podcast,viral,ia,dicas", help="Tags separadas por vírgula")
    parser.add_argument("--category", type=str, default="Entretenimento", help="Nome da categoria no YouTube")
    parser.add_argument("--language", type=str, default="Português (Brasil)", help="Idioma original")
    parser.add_argument("--ai", action="store_true", help="Marcar como conteúdo sintético / gerado por IA")
    parser.add_argument("--related", type=str, default=None, help="Termo ou ID de vídeo relacionado")
    parser.add_argument(
        "--mode", choices=["PUBLIC", "SCHEDULE", "UNLISTED", "PRIVATE"], default="PUBLIC", help="Visibilidade"
    )
    parser.add_argument(
        "--schedule", type=str, default=None, help="Data/Hora para agendamento (ISO: YYYY-MM-DDTHH:MM:SS)"
    )
    parser.add_argument(
        "--headless",
        type=lambda x: (str(x).lower() == "true"),
        default=False,
        help="Executar em modo headless (padrão: False)",
    )
    parser.add_argument(
        "--niche", choices=["financas", "fitness", "geral"], default=None, help="Nicho do canal (financas ou fitness)"
    )
    parser.add_argument("--profile-dir", type=str, default=None, help="Caminho customizado de perfil do Chrome")
    parser.add_argument("--state-file", type=str, default=None, help="Caminho customizado do state JSON de cookies")
    parser.add_argument("--channel-id", type=str, default=None, help="ID do canal no YouTube Studio")

    args = parser.parse_args()

    video_path = Path(args.video)
    if not video_path.exists():
        logger.error(f"Arquivo de vídeo não encontrado no caminho: {video_path}")
        sys.exit(1)

    tags_list = [t.strip() for t in args.tags.split(",") if t.strip()]

    schedule_dt = None
    if args.schedule:
        try:
            schedule_dt = datetime.fromisoformat(args.schedule)
            args.mode = "SCHEDULE"
        except ValueError:
            logger.error("Formato inválido de data para --schedule. Use formato ISO: YYYY-MM-DDTHH:MM:SS")
            sys.exit(1)

    # Resolução automática de perfil por nicho
    profile_path = None
    state_path = None
    if args.niche == "financas":
        profile_path = BASE_DIR / "data" / "youtube_browser_profile_financas"
        state_path = BASE_DIR / "config" / "youtube_financas_state.json"
    elif args.niche == "fitness":
        profile_path = BASE_DIR / "data" / "youtube_browser_profile_fitness"
        state_path = BASE_DIR / "config" / "youtube_fitness_state.json"

    if args.profile_dir:
        profile_path = Path(args.profile_dir)
    if args.state_file:
        state_path = Path(args.state_file)

    logger.info(f"Iniciando instância de teste PRO (Nicho: {args.niche or 'Padrão'})...")
    publisher = YouTubeBrowserPublisherPro(
        profile_dir=profile_path, state_file=state_path, headless=args.headless, channel_id=args.channel_id
    )

    if not publisher.is_authenticated():
        logger.warning(
            "Aviso: Sessão/Perfil do YouTube não parece autenticado! "
            "Se o navegador for redirecionado para o login do Google, faça login ou use os scripts BAT existentes."
        )

    payload = PublishPayloadPro(
        video_path=video_path,
        title=args.title,
        description=args.desc,
        tags=tags_list,
        category_name=args.category,
        language=args.language,
        is_synthetic_ai=args.ai,
        related_video_query=args.related,
        publish_mode=args.mode,
        schedule_datetime=schedule_dt,
        clip_uid="cli_test_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
    )

    try:
        resultado = publisher.publish_short_pro(payload)
        logger.info(f"Sucesso na publicação PRO! Resultado: {resultado}")
    except Exception as e:
        logger.error(f"Falha na execução do teste PRO: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
