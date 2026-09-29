import sys
sys.path.insert(0, '.')
import json
from src.services.youtube_metrics import extract_video_heatmap_and_chapters
from pathlib import Path

for vid in ['VooMUSClI20', 'soXBCUksUe4']:
    meta = extract_video_heatmap_and_chapters(vid)
    meta_path = Path(f'data/videos_longos/{vid}.meta.json')
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)
    print(f"{vid}: chapters={len(meta.get('chapters', []))} top_peaks={len(meta.get('top_peaks', []))}")
