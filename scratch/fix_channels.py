import sys
from pathlib import Path
sys.path.insert(0, '.')
from src.core.database import get_db

with get_db() as conn:
    c = conn.cursor()
    c.execute("""
        UPDATE source_channels 
        SET youtube_channel_id = 'UCWDmPOsRxlprrygWI-8GekA',
            rss_url = 'https://www.youtube.com/feeds/videos.xml?channel_id=UCWDmPOsRxlprrygWI-8GekA'
        WHERE name = 'Groselha Talk';
    """)
    c.execute("""
        UPDATE source_channels 
        SET youtube_channel_id = 'UC9LH3xFOJCCp2VFRcZjNdRQ',
            rss_url = 'https://www.youtube.com/feeds/videos.xml?channel_id=UC9LH3xFOJCCp2VFRcZjNdRQ'
        WHERE name = 'Ticaracaticast';
    """)
    c.execute("""
        UPDATE source_channels 
        SET youtube_channel_id = 'UCeL1a4rpEA8UG9IQIewPccg',
            rss_url = 'https://www.youtube.com/feeds/videos.xml?channel_id=UCeL1a4rpEA8UG9IQIewPccg'
        WHERE name = 'RedCast';
    """)
    c.execute("DELETE FROM source_channels WHERE name = 'PodDelas';")
    print('Updated channels successfully!')

with get_db() as conn:
    c = conn.cursor()
    for r in c.execute("SELECT id, name, rss_url FROM source_channels").fetchall():
        print(dict(r))
