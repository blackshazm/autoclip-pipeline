import sys
sys.path.insert(0, '.')
from src.core.database import get_db

with get_db() as conn:
    c = conn.cursor()
    print('=== SUPOCLIP JOBS RECENTES ===')
    for r in c.execute('SELECT id, long_video_id, supoclip_job_id, status, submitted_at, completed_at FROM supoclip_jobs ORDER BY id DESC LIMIT 5').fetchall():
        print(dict(r))

    print('\n=== ULTIMOS CLIPS GERADOS ===')
    for r in c.execute('SELECT id, long_video_id, clip_uid, virality_score, start_seconds, end_seconds, title, youtube_status, created_at FROM clips ORDER BY id DESC LIMIT 10').fetchall():
        print(dict(r))

    print('\n=== ULTIMAS PUBLICACOES (YOUTUBE) ===')
    for r in c.execute("SELECT p.id, c.title, p.platform, p.status, p.scheduled_for, p.published_at, p.external_id FROM publications p JOIN clips c ON p.clip_id = c.id WHERE p.platform = 'youtube' ORDER BY p.id DESC LIMIT 6").fetchall():
        print(dict(r))
