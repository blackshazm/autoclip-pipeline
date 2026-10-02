import sqlite3
import json

conn = sqlite3.connect('data/pipeline.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print('=== TOTAL DE TABELAS ===')
cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
print([r[0] for r in cur.fetchall()])

print('\n=== RADAR CANDIDATES ===')
try:
    cur.execute("SELECT count(*), status FROM radar_candidates GROUP BY status;")
    print([dict(r) for r in cur.fetchall()])
except Exception as e:
    print('radar_candidates err:', e)

print('\n=== LONG VIDEOS ===')
try:
    cur.execute("SELECT id, youtube_id, file_name, status, duration_seconds FROM long_videos;")
    print([dict(r) for r in cur.fetchall()])
except Exception as e:
    print('long_videos err:', e)

print('\n=== CLIPS (Amostra e colunas start/end) ===')
try:
    cur.execute("SELECT id, long_video_id, clip_uid, virality_score, start_seconds, end_seconds, duration_seconds, youtube_status, title FROM clips LIMIT 15;")
    for r in cur.fetchall():
        print(dict(r))
except Exception as e:
    print('clips err:', e)

print('\n=== CLIPS TOTAL COUNT & DUPLICATES ===')
try:
    cur.execute("SELECT count(*) as total, count(distinct long_video_id) as total_long_videos FROM clips;")
    print([dict(r) for r in cur.fetchall()])
    cur.execute("SELECT long_video_id, count(*) as count, GROUP_CONCAT(start_seconds) as starts, GROUP_CONCAT(end_seconds) as ends, GROUP_CONCAT(title) as titles FROM clips GROUP BY long_video_id;")
    for r in cur.fetchall():
        print(dict(r))
except Exception as e:
    print('clips dup err:', e)

print('\n=== PUBLICATIONS ===')
try:
    cur.execute("SELECT id, clip_id, platform, status, scheduled_for, external_id FROM publications LIMIT 20;")
    for r in cur.fetchall():
        print(dict(r))
except Exception as e:
    print('publications err:', e)
