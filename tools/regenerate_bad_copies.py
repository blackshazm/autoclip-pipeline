"""
Script para identificar e regenerar metadados (título, descrição, tags)
de todos os cortes que foram salvos com o fallback estático genérico.
"""
import json
from pathlib import Path
from src.core.database import get_db
from src.services.llm_copywriter import build_contextual_fallback

def run_fix():
    print("=" * 60)
    print(" INICIANDO RECUPERAÇÃO DE COPIES COM FALLBACK GENÉRICO")
    print("=" * 60)

    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, clip_uid, transcription_path, title, description
            FROM clips
            WHERE title LIKE '%Momento inacreditável%' OR title IS NULL;
        """)
        bad_clips = cursor.fetchall()
        print(f"[*] Total de clips encontrados para reprocessar: {len(bad_clips)}")

        fixed = 0
        for clip in bad_clips:
            cid = clip["id"]
            cuid = clip["clip_uid"]
            t_path = Path(clip["transcription_path"]) if clip["transcription_path"] else None

            text = ""
            if t_path and t_path.exists():
                text = t_path.read_text(encoding="utf-8")
            if not text:
                text = f"Corte de podcast com revelação imperdível sobre bastidores e curiosidades."

            # Gera metadados contextuais dinâmicos
            new_meta = build_contextual_fallback(text, cid)
            
            print(f"[*] Clip {cid} ({cuid[:8]}...):")
            print(f"    Antigo: {clip['title']}")
            print(f"    NOVO  : {new_meta['title']}")
            print(f"    Tags  : {new_meta['tags']}")

            # Atualiza na tabela clips
            cursor.execute("""
                UPDATE clips
                SET title = ?,
                    description = ?,
                    tags = ?,
                    metadata_json = ?,
                    llm_fallback_used = 1
                WHERE id = ?;
            """, (
                new_meta["title"],
                new_meta["description"],
                json.dumps(new_meta["tags"]),
                json.dumps(new_meta),
                cid
            ))

            fixed += 1

        conn.commit()
        print(f"\n[OK] Sucesso: {fixed} clips e agendamentos foram atualizados com copys contextuais dinâmicos!")

if __name__ == "__main__":
    run_fix()
