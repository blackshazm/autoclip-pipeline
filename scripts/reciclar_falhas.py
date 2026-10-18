"""
Script Inteligente de Reciclagem de Publicações que Falharam.
1. Identifica vídeos do TikTok que já foram ao ar (possuem post_id real) e os atualiza para POSTED.
2. Reenfileira para SCHEDULED as 40 publicações do YouTube cujos arquivos físicos estão íntegros no disco.
3. Descarta publicações cujos arquivos físicos não existem mais.
"""
import sys
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from src.core.database import get_db

def main():
    print("=" * 65)
    print("♻️  RECICLAGEM INTELIGENTE DE PUBLICAÇÕES (FAILED)")
    print("=" * 65)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Recuperar publicações do TikTok que já tinham sido enviadas com sucesso
        cursor.execute("""
            SELECT p.id, p.clip_id, p.external_id
            FROM publications p
            WHERE p.status = 'FAILED' AND p.platform = 'tiktok'
              AND p.external_id IS NOT NULL AND p.external_id != '';
        """)
        tk_already_done = cursor.fetchall()

        if tk_already_done:
            print(f"[*] Sincronizando {len(tk_already_done)} publicações do TikTok já confirmadas ao vivo...")
            for r in tk_already_done:
                cursor.execute("""
                    UPDATE publications
                    SET status = 'POSTED', error_message = NULL, published_at = COALESCE(published_at, ?)
                    WHERE id = ?;
                """, (now_iso, r["id"]))
                cursor.execute("""
                    UPDATE clips
                    SET tiktok_status = 'POSTED', tiktok_post_id = ?
                    WHERE id = ?;
                """, (r["external_id"], r["clip_id"]))
            print(f"[✓] {len(tk_already_done)} publicações do TikTok marcadas como POSTED com sucesso!")

        # 2. Selecionar publicações restantes em FAILED
        cursor.execute("""
            SELECT p.id, p.clip_id, p.platform, c.file_path
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.status = 'FAILED';
        """)
        remaining_failed = cursor.fetchall()

        requeued_count = 0
        skipped_count = 0

        for r in remaining_failed:
            fpath = r["file_path"]
            if fpath and os.path.exists(fpath):
                # Arquivo íntegro -> Reenfileira para SCHEDULED
                cursor.execute("""
                    UPDATE publications
                    SET status = 'SCHEDULED',
                        external_id = NULL,
                        published_at = NULL,
                        error_message = NULL,
                        retry_count = 0,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        scheduled_for = ?
                    WHERE id = ?;
                """, (now_iso, r["id"]))

                if r["platform"] == "youtube":
                    cursor.execute("""
                        UPDATE clips
                        SET youtube_status = 'SCHEDULED', youtube_video_id = NULL, scheduled_for = ?
                        WHERE id = ?;
                    """, (now_iso, r["clip_id"]))
                elif r["platform"] == "tiktok":
                    cursor.execute("""
                        UPDATE clips
                        SET tiktok_status = 'SCHEDULED', tiktok_post_id = NULL
                        WHERE id = ?;
                    """, (r["clip_id"],))

                requeued_count += 1
            else:
                # Arquivo ausente -> Marca como SKIPPED
                cursor.execute("""
                    UPDATE publications
                    SET status = 'SKIPPED', error_message = 'Arquivo físico de vídeo não encontrado no disco'
                    WHERE id = ?;
                """, (r["id"],))
                skipped_count += 1

        conn.commit()

        print(f"[+] {requeued_count} publicações reenfileiradas com sucesso para SCHEDULED!")
        if skipped_count > 0:
            print(f"[!] {skipped_count} publicações descartadas por arquivo ausente no disco.")

        # Exibe status atualizado
        print("\n--- NOVO STATUS DA FILA (PUBLICATIONS) ---")
        cursor.execute("SELECT platform, status, COUNT(*) as cnt FROM publications GROUP BY platform, status ORDER BY platform, status;")
        for row in cursor.fetchall():
            print(f"  [{row['platform'].upper():7s}] {row['status']:12s} : {row['cnt']:4d}")

    print("\n[✓] Reciclagem concluída! As publicações estão prontas para os workers.")

if __name__ == "__main__":
    main()
