"""
Script de Reset e Reprocessamento para Clipes Afetados pelo Modal do Studio.
Reseta os 30 clipes que tiveram ID duplicado para status SCHEDULED, permitindo
que o Robot2 / PublishWorker publique cada um com o novo YouTubeBrowserPublisherPro corrigido.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.database import get_db

def main():
    print("=" * 65)
    print("🔄 RESET DE CLIPES AFETADOS PARA REPUBLICAÇÃO PRO")
    print("=" * 65)

    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    with get_db() as conn:
        cursor = conn.cursor()

        # Identifica clipes afetados
        cursor.execute("SELECT id, clip_uid FROM clips WHERE youtube_video_id = 'B9wwuoQn1rA'")
        clips_afetados = cursor.fetchall()
        print(f"[*] Encontrados {len(clips_afetados)} clips com external_id fantasma.")

        if not clips_afetados:
            print("[✓] Nenhum clipe afetado pendente.")
            return

        clip_ids = [c["id"] for c in clips_afetados]
        placeholders = ",".join("?" for _ in clip_ids)

        # Atualiza a tabela publications
        cursor.execute(f"""
            UPDATE publications
            SET status = 'SCHEDULED',
                published_at = NULL,
                external_id = NULL,
                retry_count = 0,
                lease_owner = NULL,
                lease_expires_at = NULL,
                error_message = NULL,
                scheduled_for = ?
            WHERE platform = 'youtube' AND clip_id IN ({placeholders})
        """, [now_iso] + clip_ids)
        pub_updated = cursor.rowcount

        # Atualiza a tabela clips
        cursor.execute(f"""
            UPDATE clips
            SET youtube_status = 'SCHEDULED',
                youtube_video_id = NULL,
                published_at = NULL,
                scheduled_for = ?
            WHERE id IN ({placeholders})
        """, [now_iso] + clip_ids)
        clips_updated = cursor.rowcount

        conn.commit()

    print(f"[+] {clips_updated} clips resetados para SCHEDULED.")
    print(f"[+] {pub_updated} publicações do YouTube resetadas para SCHEDULED.")
    print("[✓] Prontos para publicação autêntica pelo robô PRO corrigido!")

if __name__ == "__main__":
    main()
