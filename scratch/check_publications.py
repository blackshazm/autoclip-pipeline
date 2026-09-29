import sqlite3

conn = sqlite3.connect(r'D:\Downloads\haker00\You1\data\pipeline.db')
cursor = conn.cursor()

print("=== ALL HISTORICAL PUBLICATIONS ===")
for r in cursor.execute("SELECT id, clip_id, platform, status, published_at, external_id FROM publications").fetchall():
    print(r)

print("\n=== CLIPS WITH EXTERNAL/PUBLISHED STATUS ===")
for r in cursor.execute("SELECT id, clip_uid, youtube_status, youtube_video_id, published_at FROM clips WHERE youtube_video_id IS NOT NULL OR youtube_status = 'PUBLISHED'").fetchall():
    print(r)
