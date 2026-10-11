import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.core.database import get_db

def main():
    print("=" * 65)
    print("🔧 RECUPERAÇÃO FORENSE E ACELERAÇÃO IMEDIATA DA FILA")
    print("=" * 65)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Recuperar publicações que falharam pelo bug de sqlite3.Row
        cursor.execute("""
            UPDATE publications
            SET status = 'SCHEDULED',
                retry_count = 0,
                error_message = NULL,
                lease_owner = NULL,
                lease_expires_at = NULL
            WHERE status = 'FAILED' 
              AND (error_message LIKE "%sqlite3.Row%" OR error_message LIKE "%attribute 'get'%");
        """)
        recovered_count = cursor.rowcount
        print(f"[+] Publicações recuperadas do erro 'sqlite3.Row': {recovered_count}")

        # Sincroniza status dos clips correspondentes
        cursor.execute("""
            UPDATE clips
            SET youtube_status = 'SCHEDULED', moderation_status = 'APPROVED', error_log = NULL
            WHERE id IN (
                SELECT clip_id FROM publications 
                WHERE platform = 'youtube' AND status = 'SCHEDULED'
            );
        """)
        cursor.execute("""
            UPDATE clips
            SET tiktok_status = 'SCHEDULED', moderation_status = 'APPROVED', error_log = NULL
            WHERE id IN (
                SELECT clip_id FROM publications 
                WHERE platform = 'tiktok' AND status = 'SCHEDULED'
            );
        """)

        # 2. Re-enfileirar publicações SCHEDULED para início IMEDIATO (a cada 2 min)
        # Separado por conta para respeitar o intervalo por plataforma/nicho
        now_dt = datetime.now(timezone.utc)
        
        cursor.execute("SELECT id, platform, niche, display_name FROM publishing_accounts WHERE active = 1;")
        active_accounts = cursor.fetchall()

        total_requeued = 0
        for acc in active_accounts:
            acc_id = acc["id"]
            acc_name = acc["display_name"]
            
            cursor.execute("""
                SELECT id, clip_id, scheduled_for
                FROM publications
                WHERE publishing_account_id = ? AND status = 'SCHEDULED'
                ORDER BY id ASC;
            """, (acc_id,))
            pubs = cursor.fetchall()

            if not pubs:
                continue

            print(f"\n[*] Re-agendando {len(pubs)} publicações para: {acc_name} (Conta {acc_id})")
            for idx, p in enumerate(pubs):
                slot = now_dt + timedelta(minutes=idx * 2)
                cursor.execute("""
                    UPDATE publications
                    SET scheduled_for = ?
                    WHERE id = ?;
                """, (slot.isoformat(), p["id"]))
                total_requeued += 1

        conn.commit()

        print("\n" + "=" * 65)
        print(f"✔ SUCESSO! Total de publicações ativadas na fila imediata: {total_requeued}")
        print("=" * 65)

        # Exibe as 10 próximas de Finanças (Raiz do Éden)
        print("\nPróximas publicações para YouTube Shorts - Raiz do Éden:")
        cursor.execute("""
            SELECT p.id, p.scheduled_for, c.title
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.publishing_account_id = 5 AND p.status = 'SCHEDULED'
            ORDER BY p.scheduled_for ASC
            LIMIT 5;
        """)
        for row in cursor.fetchall():
            print(f"  [{row[1]}] ID {row[0]}: {row[2][:50] if row[2] else 'Sem título'}")

if __name__ == "__main__":
    main()
