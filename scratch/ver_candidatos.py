from src.core.database import get_db

with get_db() as conn:
    rows = conn.execute("""
        SELECT c.youtube_id, c.title, c.vph, c.status, sc.name 
        FROM radar_candidates c 
        JOIN source_channels sc ON c.source_channel_id = sc.id
        ORDER BY c.vph DESC;
    """).fetchall()
    print(f"Total de candidatos analisados: {len(rows)}")
    for r in rows:
        print(f"[{r['name']}] {r['title']} | VPH: {r['vph']} | Status: {r['status']}")
