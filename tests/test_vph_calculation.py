"""
Testes unitários para cálculo de VPH, median factor e parsing de duração.
"""
from datetime import datetime, timezone, timedelta
from src.services.youtube_metrics import calculate_vph, calculate_median_factor, parse_iso8601_duration

def test_parse_iso8601_duration():
    assert parse_iso8601_duration("PT1H23M45S") == 3600 + 23 * 60 + 45
    assert parse_iso8601_duration("PT30M") == 1800
    assert parse_iso8601_duration("PT45S") == 45
    assert parse_iso8601_duration("PT2H") == 7200
    assert parse_iso8601_duration("INVALID") == 0

def test_calculate_vph():
    now = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    published_2h_ago = now - timedelta(hours=2)
    published_10h_ago = now - timedelta(hours=10)

    # 10.000 views em 2 horas = 5.000 VPH
    assert calculate_vph(10000, published_2h_ago, reference_time=now) == 5000.0

    # 50.000 views em 10 horas = 5.000 VPH
    assert calculate_vph(50000, published_10h_ago, reference_time=now) == 5000.0

    # 1.000 views em 2 horas = 500 VPH
    assert calculate_vph(1000, published_2h_ago, reference_time=now) == 500.0

def test_calculate_median_factor():
    channel_median = 2000.0

    # VPH 5000 com mediana 2000 = 2.5x
    assert calculate_median_factor(5000.0, channel_median) == 2.5

    # VPH 2000 com mediana 2000 = 1.0x
    assert calculate_median_factor(2000.0, channel_median) == 1.0

    # VPH 1000 com mediana 2000 = 0.5x
    assert calculate_median_factor(1000.0, channel_median) == 0.5

    # Mediana nula ou zero retorna 1.0 seguro
    assert calculate_median_factor(5000.0, 0.0) == 1.0
    assert calculate_median_factor(5000.0, None) == 1.0
    assert calculate_median_factor(None, channel_median) == 0.0

def test_calculate_vph_edge_cases():
    now = datetime(2026, 6, 1, 15, 0, 0, tzinfo=timezone.utc)
    future_date = now + timedelta(hours=5)

    # Views nulas ou None
    assert calculate_vph(None, now - timedelta(hours=1), reference_time=now) == 0.0
    assert calculate_vph(0, now - timedelta(hours=1), reference_time=now) == 0.0

    # Data de publicação nula (assume data atual)
    assert calculate_vph(100, None, reference_time=now) >= 0.0

    # Data no futuro (usa piso de 60 segundos)
    assert calculate_vph(120, future_date, reference_time=now) == round(120 / (60 / 3600), 2)

def test_calculate_engagement_ratio():
    from src.services.youtube_metrics import calculate_engagement_ratio
    # 100 views, 5 likes, 2 comments -> (5*2 + 2*5)/100 * 100 = 20%
    assert calculate_engagement_ratio(100, 5, 2) == 20.0

    # Views zero ou None retorna 0.0 com segurança
    assert calculate_engagement_ratio(0, 5, 2) == 0.0
    assert calculate_engagement_ratio(None, 5, 2) == 0.0

    # Likes ou comentários None tratados como zero
    assert calculate_engagement_ratio(100, None, 2) == 10.0
    assert calculate_engagement_ratio(100, 5, None) == 10.0

