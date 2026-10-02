"""
Script de Auditoria e Reconciliação de Publicações (reconcile_publications.py).
Identifica e corrige registros marcados como POSTED com IDs fictícios (yt_... e tk_...).
"""
import argparse
import json
import sqlite3
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.config import settings
from src.core.database import get_db

def reconcile(apply_changes: bool = False, reschedule: bool = False):
    print("=" * 65)
    print("🔍 AUDITORIA E RECONCILIAÇÃO DE PUBLICAÇÕES (YOUTUBE & TIKTOK)")
    print("=" * 65)

    with get_db() as conn:
        cursor = conn.cursor()

        # Busca todas as publicações marcadas como POSTED
        cursor.execute("""
            SELECT p.id, p.clip_id, p.platform, p.status, p.external_id, p.published_at,
                   c.clip_uid, c.file_path, c.title
            FROM publications p
            JOIN clips c ON p.clip_id = c.id
            WHERE p.status = 'POSTED';
        """)
        all_posted = cursor.fetchall()

        fake_yt = []
        fake_tk = []
        real_yt = []
        real_tk = []

        for row in all_posted:
            ext_id = row["external_id"] or ""
            platform = row["platform"]

            if platform == "youtube":
                # Um ID real do YouTube tem exatamente 11 caracteres e não começa com 'yt_'
                if ext_id.startswith("yt_") or len(ext_id) != 11:
                    fake_yt.append(row)
                else:
                    real_yt.append(row)
            elif platform == "tiktok":
                # IDs falsos do TikTok começam com 'tk_'
                if ext_id.startswith("tk_") or len(ext_id) < 14:
                    fake_tk.append(row)
                else:
                    real_tk.append(row)

        print(f"\n📊 Diagnóstico do Banco de Dados:")
        print(f"   🔴 YouTube Realmente Confirmados: {len(real_yt)}")
        print(f"   🔴 YouTube FALSOS (ID fictício 'yt_...'): {len(fake_yt)}")
        print(f"   🎵 TikTok Realmente Confirmados:  {len(real_tk)}")
        print(f"   🎵 TikTok FALSOS (ID fictício 'tk_...'):  {len(fake_tk)}")
        print(f"   Total de Inconsistências Detectadas: {len(fake_yt) + len(fake_tk)}")

        all_fakes = fake_yt + fake_tk

        # Verifica disponibilidade dos arquivos em disco para possível reagendamento
        can_reschedule = []
        missing_files = []

        for f in all_fakes:
            fpath = Path(f["file_path"]) if f["file_path"] else None
            if fpath and fpath.exists():
                can_reschedule.append(f)
            else:
                missing_files.append(f)

        print(f"\n📁 Arquivos de Vídeo no Disco (data/clips_exportados):")
        print(f"   ✅ Arquivos íntegros disponíveis para novo upload real: {len(can_reschedule)}")
        print(f"   ❌ Arquivos ausentes ou já deletados: {len(missing_files)}")

        if not apply_changes:
            print("\n⚠️  Modo de Simulação (--dry-run). Nenhuma alteração foi gravada.")
            print("👉 Para aplicar as correções no banco de dados, execute:")
            print("   python scripts/reconcile_publications.py --apply")
            print("👉 Para aplicar E reagendar os cortes existentes na fila de postagem real:")
            print("   python scripts/reconcile_publications.py --apply --reschedule")
            return

        print("\n⚙️  Aplicando correções no banco de dados...")

        now_iso = datetime.now(timezone.utc).isoformat()
        fixed_count = 0
        rescheduled_count = 0

        for row in all_fakes:
            pub_id = row["id"]
            clip_id = row["clip_id"]
            platform = row["platform"]
            fpath = Path(row["file_path"]) if row["file_path"] else None
            file_exists = fpath and fpath.exists()

            if reschedule and file_exists:
                # Reagenda como SCHEDULED para publicação real
                cursor.execute("""
                    UPDATE publications
                    SET status = 'SCHEDULED',
                        external_id = NULL,
                        scheduled_for = datetime('now', '+5 minutes'),
                        error_message = 'Reagendado para postagem real após auditoria'
                    WHERE id = ?;
                """, (pub_id,))

                if platform == "youtube":
                    cursor.execute("UPDATE clips SET youtube_status = 'SCHEDULED', youtube_video_id = NULL WHERE id = ?;", (clip_id,))
                elif platform == "tiktok":
                    cursor.execute("UPDATE clips SET tiktok_status = 'SCHEDULED', tiktok_post_id = NULL WHERE id = ?;", (clip_id,))

                rescheduled_count += 1
            else:
                # Marca como FAILED_UNVERIFIED
                err_msg = "Publicação não confirmada na plataforma (ID fictício detectado pela auditoria)"
                cursor.execute("""
                    UPDATE publications
                    SET status = 'FAILED',
                        error_message = ?
                    WHERE id = ?;
                """, (err_msg, pub_id))

                if platform == "youtube":
                    cursor.execute("UPDATE clips SET youtube_status = 'FAILED', error_log = ? WHERE id = ?;", (err_msg, clip_id))
                elif platform == "tiktok":
                    cursor.execute("UPDATE clips SET tiktok_status = 'FAILED', error_log = ? WHERE id = ?;", (err_msg, clip_id))

                fixed_count += 1

        conn.commit()

        print(f"\n✅ RECONCILIAÇÃO CONCLUÍDA COM SUCESSO!")
        print(f"   Corrigidos para FAILED: {fixed_count}")
        print(f"   Reagendados para POSTAGEM REAL: {rescheduled_count}")
        print("=" * 65)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Auditoria e Reconciliação de Publicações")
    parser.add_argument("--apply", action="store_true", help="Aplica as correções no banco de dados")
    parser.add_argument("--reschedule", action="store_true", help="Reagenda clips com arquivo existente para publicação real")
    args = parser.parse_args()

    reconcile(apply_changes=args.apply, reschedule=args.reschedule)
