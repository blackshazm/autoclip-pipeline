"""
Acelerador de Fila da Pipeline: Ativa o Modo Contínuo Imediato ("Sem Espera").
1. Configura intervalo de 2 minutos e janelas livres 24h em publishing_accounts.
2. Re-enfileira todas as publicações SCHEDULED para começarem imediatamente (now + 30s) a cada 2 minutos.
"""
import sys
import io
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.core.database import get_db

def accelerate_queue():
    print("=" * 65)
    print("🚀 ATIVANDO MODO CONTÍNUO IMEDIATO NA FILA DE PUBLICAÇÃO")
    print("=" * 65)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Atualiza publishing_accounts para modo sem janelas e intervalo de 2 minutos
        cursor.execute("""
            UPDATE publishing_accounts
            SET min_interval_minutes = 2,
                posting_windows = NULL
            WHERE id IN (3, 4, 5, 6);
        """)
        cursor.execute("""
            UPDATE publishing_accounts
            SET display_name = 'YouTube Shorts - Raiz do Éden'
            WHERE id = 5;
        """)
        conn.commit()
        print("✔ Contas de publicação configuradas: min_interval = 2 min | Janelas: 24h livres.")

        # 2. Busca todas as publicações agendadas
        cursor.execute("""
            SELECT p.id, p.clip_id, p.platform, p.publishing_account_id, pa.niche, p.scheduled_for
            FROM publications p
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            WHERE p.status = 'SCHEDULED'
            ORDER BY pa.niche ASC, p.clip_id ASC, p.platform DESC;
        """)
        scheduled_pubs = cursor.fetchall()
        total = len(scheduled_pubs)

        if total == 0:
            print("[*] Nenhuma publicação SCHEDULED encontrada na fila.")
            return

        print(f"[*] Re-enfileirando {total} publicações agendadas para modo contínuo imediato...")

        # 3. Distribui os horários a partir de agora com espaçamento de 2 minutos por canal/nicho
        now = datetime.now(timezone.utc)
        # Inicia a primeira postagem para 30 segundos no futuro
        current_slots = {
            ("youtube", "financas"): now + timedelta(seconds=30),
            ("tiktok", "financas"): now + timedelta(seconds=90),
            ("youtube", "fitness"): now + timedelta(seconds=60),
            ("tiktok", "fitness"): now + timedelta(seconds=120),
        }

        step = timedelta(minutes=2)

        for pub in scheduled_pubs:
            pub_id = pub["id"]
            platform = pub["platform"]
            niche = pub["niche"]
            key = (platform, niche)

            slot = current_slots.get(key, now + timedelta(seconds=30))
            new_sched_iso = slot.isoformat()

            cursor.execute("""
                UPDATE publications
                SET scheduled_for = ?
                WHERE id = ?;
            """, (new_sched_iso, pub_id))

            # Avança o slot desta plataforma/nicho em 2 minutos
            current_slots[key] = slot + step

        conn.commit()

        print(f"✔ Sucesso! {total} publicações reprogramadas em esteira rápida contínua.")
        print("\nPróximas postagens programadas para disparo imediato:")
        cursor.execute("""
            SELECT p.id, pa.niche, p.platform, p.scheduled_for, c.title
            FROM publications p
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            JOIN clips c ON p.clip_id = c.id
            WHERE p.status = 'SCHEDULED'
            ORDER BY p.scheduled_for ASC
            LIMIT 6;
        """)
        for r in cursor.fetchall():
            print(f"  [{r['scheduled_for'][:19]}] Nicho: {r['niche']:<9} | {r['platform']:<7} -> {r['title'][:45]}")

    print("=" * 65)

if __name__ == "__main__":
    accelerate_queue()
