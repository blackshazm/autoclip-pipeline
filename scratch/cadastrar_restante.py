from src.services.channel_manager import add_source_channel

outros_canais = [
    ('@inteligencialtda', 'Inteligência Ltda.', 2000, 20),
    ('@PrimoCast', 'PrimoCast', 1500, 20),
    ('@IronbergCT', 'Ironberg Podcast', 1500, 15)
]

for handle, name, vph, duration in outros_canais:
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
