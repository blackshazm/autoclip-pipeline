import pytest
from src.services.overlap_filter import calculate_overlap_ratio, filter_overlapping_clips, parse_seconds

def test_parse_seconds():
    assert parse_seconds(45) == 45.0
    assert parse_seconds("30") == 30.0
    assert parse_seconds("01:30") == 90.0
    assert parse_seconds("01:00:10") == 3610.0
    assert parse_seconds(None) == 0.0

def test_calculate_overlap_ratio():
    # Sem sobreposição
    assert calculate_overlap_ratio(0, 30, 40, 70) == 0.0
    # Sobreposição total (idênticos)
    assert calculate_overlap_ratio(10, 40, 10, 40) == 1.0
    # Sobreposição parcial: A (10 a 40 = 30s), B (25 a 55 = 30s) -> inter = 15s -> 15/30 = 0.5
    assert calculate_overlap_ratio(10, 40, 25, 55) == 0.5
    # Caso real encontrado no banco: A (21s a 42s = 21s) e B (12s a 42s = 30s)
    # inter = 42 - 21 = 21s. Menor duração = 21s -> 21 / 21 = 1.0 (100% de A está contido em B)
    assert calculate_overlap_ratio(21, 42, 12, 42) == 1.0

def test_filter_overlapping_clips():
    clips = [
        # Mesmo vídeo longo (ID 1)
        {"id": 1, "long_video_id": 1, "virality_score": 90, "start_seconds": 12, "end_seconds": 42},
        {"id": 2, "long_video_id": 1, "virality_score": 80, "start_seconds": 21, "end_seconds": 42}, # Deve ser descartado por sobreposição com ID 1
        {"id": 3, "long_video_id": 1, "virality_score": 85, "start_seconds": 100, "end_seconds": 140}, # Trecho diferente, deve ser mantido
        # Outro vídeo longo (ID 2)
        {"id": 4, "long_video_id": 2, "virality_score": 75, "start_seconds": 10, "end_seconds": 35}, # Vídeo diferente, deve ser mantido
    ]

    kept, discarded = filter_overlapping_clips(clips, max_overlap_threshold=0.25)

    kept_ids = [c["id"] for c in kept]
    discarded_ids = [c["id"] for c in discarded]

    assert 1 in kept_ids
    assert 2 in discarded_ids
    assert 3 in kept_ids
    assert 4 in kept_ids
    assert len(kept) == 3
    assert len(discarded) == 1

def test_round_robin_interleave():
    from src.services.overlap_filter import round_robin_interleave

    clips = [
        {"id": 10, "long_video_id": 1, "source_channel_id": "podpah", "virality_score": 90},
        {"id": 11, "long_video_id": 1, "source_channel_id": "podpah", "virality_score": 85},
        {"id": 12, "long_video_id": 1, "source_channel_id": "podpah", "virality_score": 80},
        {"id": 20, "long_video_id": 2, "source_channel_id": "flow", "virality_score": 95},
        {"id": 21, "long_video_id": 2, "source_channel_id": "flow", "virality_score": 88},
        {"id": 30, "long_video_id": 3, "source_channel_id": "redcast", "virality_score": 92},
    ]

    interleaved = round_robin_interleave(clips, group_key="long_video_id", secondary_key="source_channel_id")
    ids = [c["id"] for c in interleaved]

    # Não deve ter 2 vídeos do mesmo long_video_id seguidos
    for i in range(len(interleaved) - 1):
        assert interleaved[i]["long_video_id"] != interleaved[i+1]["long_video_id"], f"Dois vídeos seguidos do mesmo long_video_id: {interleaved[i]} e {interleaved[i+1]}"

    assert len(ids) == len(clips)

