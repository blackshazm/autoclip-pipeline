from pathlib import Path

video_service_path = Path(r"D:\Desktop\ia de cortes\supox\backend\src\services\video_service.py")
if video_service_path.exists():
    code = video_service_path.read_text(encoding="utf-8")

    target = "                segments_json.append(segment_payload)\n\n            if processing_mode == \"fast\":"
    replacement = """                segments_json.append(segment_payload)

            # Validação anti-alucinação de tempo e filtro anti-jabá comercial
            filtered_segments = []
            for seg in segments_json:
                st = seg.get("start_time", 0.0)
                try:
                    if isinstance(st, str) and ":" in st:
                        m, s = st.split(":", 1)
                        st_secs = float(m) * 60 + float(s)
                    else:
                        st_secs = float(st or 0.0)
                except Exception:
                    st_secs = 0.0

                # Rejeita timestamps fora da duração real do arquivo
                if file_duration > 0 and st_secs >= file_duration:
                    logger.warning("Descartando segmento com start_time %.1fs acima da duração do vídeo (%.1fs)", st_secs, file_duration)
                    continue

                # Filtro anti-jabá: descarta anúncios nos primeiros 240s
                text_lower = (seg.get("text") or "").lower()
                commercial_words = ["cupom", "patrocinador", "parceiro", "apoio", "merchan", "link na descrição", "superchat", "manda o pix", "desconto de"]
                if st_secs < 240 and any(w in text_lower for w in commercial_words):
                    logger.info("Descartando segmento aos %.1fs devido a menção comercial/jabá", st_secs)
                    continue

                filtered_segments.append(seg)

            segments_json = filtered_segments

            if processing_mode == "fast":"""

    if target in code:
        code = code.replace(target, replacement)
        video_service_path.write_text(code, encoding="utf-8")
        print("Successfully updated video_service.py with anti-jabá and duration protection!")
    else:
        print("Target block not found in video_service.py")
