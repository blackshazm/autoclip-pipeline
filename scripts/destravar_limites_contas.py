"""
Script de Migração e Desbloqueio de Contas de Publicação.
Eleva os limites de postagens diárias para 100 posts/dia e intervalo para 2 minutos,
alinhando o banco de dados à alta capacidade dos Recursos Avançados do YouTube e TikTok.
"""
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.core.database import get_db

def main():
    print("=" * 65)
    print("🚀 DESBLOQUEIO DE LIMITES DE POSTAGENS NAS CONTAS")
    print("=" * 65)

    with get_db() as conn:
        cursor = conn.cursor()

        # 1. Atualizar limites de postagem nas contas ativas
        cursor.execute("""
            UPDATE publishing_accounts
            SET max_daily_posts = 100,
                min_interval_minutes = 2,
                updated_at = CURRENT_TIMESTAMP
            WHERE active = 1;
        """)
        updated_accounts = cursor.rowcount
        print(f"[+] Contas atualizadas para 100 posts/dia (intervalo 2 min): {updated_accounts}")

        # 2. Reseta publicações marcadas como FAILED_QUOTA para SCHEDULED
        cursor.execute("""
            UPDATE publications
            SET status = 'SCHEDULED',
                error_message = NULL,
                retry_count = 0,
                lease_owner = NULL,
                lease_expires_at = NULL,
                scheduled_for = CURRENT_TIMESTAMP
            WHERE status = 'FAILED_QUOTA';
        """)
        quota_unlocked = cursor.rowcount
        print(f"[+] Publicações desbloqueadas do status FAILED_QUOTA: {quota_unlocked}")

        # 3. Resincroniza clips associados a essas publicações se necessário
        cursor.execute("""
            UPDATE clips
            SET youtube_status = 'SCHEDULED'
            WHERE youtube_status = 'FAILED_QUOTA';
        """)
        clips_unlocked = cursor.rowcount
        print(f"[+] Clips com status FAILED_QUOTA resetados para SCHEDULED: {clips_unlocked}")

        conn.commit()

        # Exibe o status atual das contas
        print("\n--- CONTAS DE PUBLICAÇÃO ATIVAS ---")
        cursor.execute("SELECT id, platform, profile_name, niche, max_daily_posts, min_interval_minutes FROM publishing_accounts WHERE active = 1;")
        for r in cursor.fetchall():
            print(f"ID: {r['id']} | Plataforma: {r['platform']:7s} | Nicho: {r['niche']:8s} | Limite Diário: {r['max_daily_posts']} | Intervalo: {r['min_interval_minutes']}m")

    print("\n[✓] Contas 100% desbloqueadas para fluxo de postagem contínuo!")

if __name__ == "__main__":
    main()
