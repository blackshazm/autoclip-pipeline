import sys
from src.services.channel_manager import add_source_channel

canais = [
    ('@FlowPodcast', 'Flow Podcast', 2500, 20),
    ('@Podpah', 'Podpah', 2500, 20),
    ('@inteligencialimitada', 'Inteligência Ltda.', 2000, 20),
    ('@ossociospodcast', 'Os Sócios Podcast', 1500, 20),
    ('@IronbergPodcast', 'Ironberg Podcast', 1500, 15)
]

print("Iniciando cadastro dos 5 maiores canais de videocasts/podcasts do Brasil...")
for handle, name, vph, duration in canais:
    try:
        res = add_source_channel(
            handle,
            name=name,
            vph_threshold=vph,
            min_duration_minutes=duration,
            license_mode='authorized'
        )
        print(f"✅ Adicionado: {res['name']} | ID: {res['youtube_channel_id']} | Feed: {res['rss_url']}")
    except Exception as e:
        print(f"❌ Erro em {handle}: {e}")
