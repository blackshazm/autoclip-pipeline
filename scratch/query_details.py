import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import sqlite3
import json

db_path = r"d:\Downloads\haker00\You1\data\pipeline.db"
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

print("=== 1. CANAIS MONITORADOS (source_channels) ===")
for r in cur.execute("SELECT * FROM source_channels").fetchall():
    print(dict(r))

print("\n=== 2. VÍDEOS DETECTADOS PELO RADAR (radar_candidates) ===")
for r in cur.execute("SELECT * FROM radar_candidates").fetchall():
    print(dict(r))

print("\n=== 3. VÍDEOS LONGOS BAIXADOS/PROCESSADOS (long_videos) ===")
for r in cur.execute("SELECT * FROM long_videos").fetchall():
    print(dict(r))

print("\n=== 4. CLIPES GERADOS (clips) ===")
for r in cur.execute("SELECT * FROM clips").fetchall():
    d = dict(r)
    print(f"ID: {d['id']} | LongVideoID: {d['long_video_id']} | Score: {d['virality_score']} | Dur: {d['duration_seconds']}s | Titulo: {d['title']}")
    print(f"   Status YT: {d['youtube_status']} | Status TK: {d['tiktok_status']} | Scheduled: {d['scheduled_for']}")

print("\n=== 5. PUBLICAÇÕES (publications) ===")
for r in cur.execute("SELECT * FROM publications").fetchall():
    print(dict(r))

conn.close()
