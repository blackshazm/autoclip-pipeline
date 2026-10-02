"""
Módulo de Detecção e Filtragem de Sobreposição Temporal entre Cortes (Anti-Overlap).
Impede a publicação de múltiplos cortes que compartilham essencialmente o mesmo trecho do vídeo longo.
"""
from typing import List, Dict, Any, Tuple, Optional

def parse_seconds(val: Any) -> float:
    """Converte segundos ou formato MM:SS / HH:MM:SS para float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    if not s:
        return 0.0
    parts = s.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        elif len(parts) == 2:
            return float(parts[0]) * 60.0 + float(parts[1])
        elif len(parts) == 3:
            return float(parts[0]) * 3600.0 + float(parts[1]) * 60.0 + float(parts[2])
    except (ValueError, TypeError):
        return 0.0
    return 0.0

def calculate_overlap_ratio(start_a: float, end_a: float, start_b: float, end_b: float) -> float:
    """
    Calcula a taxa de sobreposição relativa entre dois intervalos temporais:
    Overlap = Intersecção / Menor Duração
    """
    inter_start = max(start_a, start_b)
    inter_end = min(end_a, end_b)
    intersection = max(0.0, inter_end - inter_start)

    dur_a = max(0.1, end_a - start_a)
    dur_b = max(0.1, end_b - start_b)
    min_duration = min(dur_a, dur_b)

    return intersection / min_duration

def filter_overlapping_clips(clips: List[Dict[str, Any]], max_overlap_threshold: float = 0.25) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filtra clips do mesmo vídeo longo descartando duplicatas temporais.
    Prioriza o clip com maior virality_score.
    
    Retorna: (kept_clips, discarded_clips)
    """
    # Agrupa por vídeo longo
    by_video: Dict[Any, List[Dict[str, Any]]] = {}
    for clip in clips:
        v_id = clip.get("long_video_id")
        by_video.setdefault(v_id, []).append(clip)

    kept: List[Dict[str, Any]] = []
    discarded: List[Dict[str, Any]] = []

    for v_id, v_clips in by_video.items():
        # Se for None ou sem ID de vídeo, mantém por segurança
        if v_id is None:
            kept.extend(v_clips)
            continue

        # Ordena os clips deste vídeo pelo maior virality_score primeiro
        sorted_clips = sorted(
            v_clips,
            key=lambda x: (float(x.get("virality_score") or 0), parse_seconds(x.get("duration_seconds"))),
            reverse=True
        )

        accepted_in_video: List[Dict[str, Any]] = []

        for candidate in sorted_clips:
            c_start = parse_seconds(candidate.get("start_seconds"))
            c_end = parse_seconds(candidate.get("end_seconds"))

            # Se não há marcação válida de tempo, aceita
            if c_end <= c_start:
                accepted_in_video.append(candidate)
                continue

            has_overlap = False
            for accepted in accepted_in_video:
                a_start = parse_seconds(accepted.get("start_seconds"))
                a_end = parse_seconds(accepted.get("end_seconds"))

                overlap = calculate_overlap_ratio(c_start, c_end, a_start, a_end)
                if overlap > max_overlap_threshold:
                    has_overlap = True
                    candidate["_overlap_reason"] = f"Sobreposição de {int(overlap * 100)}% com corte mais viral ({accepted.get('id') or accepted.get('clip_uid')})"
                    discarded.append(candidate)
                    break

            if not has_overlap:
                accepted_in_video.append(candidate)

        kept.extend(accepted_in_video)

    return kept, discarded

def round_robin_interleave(
    items: List[Dict[str, Any]], 
    group_key: str = "long_video_id",
    secondary_key: Optional[str] = "source_channel_id"
) -> List[Dict[str, Any]]:
    """
    Reorganiza a lista de cortes utilizando intercalação Round-Robin.
    Garante que itens do mesmo vídeo longo e canal fiquem o mais distante possível uns dos outros.
    """
    if not items:
        return []

    # Agrupa por chave principal (long_video_id)
    groups: Dict[Any, List[Dict[str, Any]]] = {}
    for item in items:
        k = item.get(group_key)
        groups.setdefault(k, []).append(item)

    # Ordena cada grupo internamente por virality_score decrescente
    for k in groups:
        groups[k] = sorted(
            groups[k],
            key=lambda x: (
                0 if x.get("series_id") else 1, # Séries primeiro se houver
                x.get("part_number") or 1,
                float(x.get("virality_score") or 0)
            ),
            reverse=False # Séries em ordem crescente de partes
        )
        # Se não for série, ordena por virality_score DESC
        non_series = [x for x in groups[k] if not x.get("series_id")]
        series = [x for x in groups[k] if x.get("series_id")]
        non_series.sort(key=lambda x: float(x.get("virality_score") or 0), reverse=True)
        groups[k] = series + non_series

    # Ordena os grupos de forma balanceada pelo tamanho ou canal
    group_keys = sorted(groups.keys(), key=lambda k: len(groups[k]), reverse=True)

    result: List[Dict[str, Any]] = []
    while any(groups[k] for k in group_keys):
        for k in group_keys:
            if groups[k]:
                # Evita se possível colocar o mesmo canal consecutivamente se secondary_key existir
                cand = groups[k][0]
                if result and secondary_key and cand.get(secondary_key):
                    last_sec = result[-1].get(secondary_key)
                    # Se for o mesmo canal do anterior e tivermos outro grupo com canal diferente disponível, busca o outro
                    if last_sec and cand.get(secondary_key) == last_sec and len(group_keys) > 1:
                        # Tenta encontrar outro grupo com canal diferente
                        alt_found = False
                        for alt_k in group_keys:
                            if alt_k != k and groups[alt_k]:
                                alt_cand = groups[alt_k][0]
                                if alt_cand.get(secondary_key) != last_sec:
                                    result.append(groups[alt_k].pop(0))
                                    alt_found = True
                                    break
                        if alt_found:
                            continue

                result.append(groups[k].pop(0))

    return result

def filter_against_database(
    clips: List[Dict[str, Any]], 
    conn: Optional[Any] = None, 
    max_overlap_threshold: float = 0.25
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Filtra clips candidatos comparando contra cortes JÁ EXISTENTES no banco de dados
    para o mesmo long_video_id que foram aprovados ou agendados/postados.
    Evita duplicação temporal histórica entre lotes diferentes.
    """
    from src.core.database import get_db

    kept: List[Dict[str, Any]] = []
    discarded: List[Dict[str, Any]] = []

    def check_with_connection(c):
        cursor = c.cursor()
        for cand in clips:
            v_id = cand.get("long_video_id")
            c_id = cand.get("id")
            c_start = parse_seconds(cand.get("start_seconds"))
            c_end = parse_seconds(cand.get("end_seconds"))

            if not v_id or c_end <= c_start:
                kept.append(cand)
                continue

            query = """
                SELECT id, clip_uid, start_seconds, end_seconds, virality_score, title
                FROM clips
                WHERE long_video_id = ? 
                  AND moderation_status = 'APPROVED'
                  AND (youtube_status IN ('PENDING', 'SCHEDULED', 'POSTED') OR tiktok_status IN ('PENDING', 'SCHEDULED', 'POSTED'))
            """
            params = [v_id]
            if c_id:
                query += " AND id != ?"
                params.append(c_id)

            cursor.execute(query, tuple(params))
            existing_clips = cursor.fetchall()

            has_overlap = False
            for ex in existing_clips:
                ex_start = parse_seconds(ex["start_seconds"])
                ex_end = parse_seconds(ex["end_seconds"])
                if ex_end <= ex_start:
                    continue

                overlap = calculate_overlap_ratio(c_start, c_end, ex_start, ex_end)
                if overlap > max_overlap_threshold:
                    has_overlap = True
                    ex_dict = dict(ex)
                    ex_ref = ex_dict.get('title') or ex_dict.get('clip_uid')
                    cand["_overlap_reason"] = f"Sobreposição de {int(overlap * 100)}% com corte histórico existente ID {ex_dict.get('id')} ({ex_ref})"
                    discarded.append(cand)
                    break

            if not has_overlap:
                kept.append(cand)

    if conn is not None:
        check_with_connection(conn)
    else:
        with get_db() as local_conn:
            check_with_connection(local_conn)

    return kept, discarded

