import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.database import get_db

with get_db() as conn:
    c = conn.cursor()
    existing = [r["name"] for r in c.execute("SELECT name FROM source_channels").fetchall()]
    print("EXISTING:", existing)

    new_channels = [
        ('Groselha Talk', 'UC4L-J5b8wVbT2qYjZ-99bLg', 'https://www.youtube.com/feeds/videos.xml?channel_id=UC4L-J5b8wVbT2qYjZ-99bLg', 1500, 1.8, 20, 1),
        ('Ticaracaticast', 'UCmU2W4f6R_s0e78_e4o9jsw', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCmU2W4f6R_s0e78_e4o9jsw', 2000, 1.8, 20, 1),
        ('PodDelas', 'UCg4Vw7U_pE_5e0T8j8aQ3_A', 'https://www.youtube.com/feeds/videos.xml?channel_id=UCg4Vw7U_pE_5e0T8j8aQ3_A', 2000, 1.8, 20, 1),
        ('RedCast', 'UClz5X8dG5d9n7j4E9m0Z5YQ', 'https://www.youtube.com/feeds/videos.xml?channel_id=UClz5X8dG5d9n7j4E9m0Z5YQ', 1500, 1.8, 20, 1)
    ]

    for name, ch_id, rss, vph, mult, dur, act in new_channels:
        if name not in existing:
            c.execute("""
                INSERT INTO source_channels (name, youtube_channel_id, rss_url, vph_absolute_threshold, vph_multiplier_threshold, min_duration_minutes, active)
                VALUES (?, ?, ?, ?, ?, ?, ?);
            """, (name, ch_id, rss, vph, mult, dur, act))
            print(f"Added {name}")
        else:
            print(f"Already exists: {name}")

with get_db() as conn:
    c = conn.cursor()
    print("\nALL CHANNELS:")
    for r in c.execute("SELECT id, name, youtube_channel_id, vph_absolute_threshold, min_duration_minutes, active FROM source_channels").fetchall():
        print(dict(r))
