"""
Script de Limpeza Atômica de Clips e Publicações de Ontem (< 2026-09-29).
Remove registros no SQLite, apaga arquivos antigos em data/clips_exportados e reseta vídeos longos para reprocessamento.
"""
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

# Garante saída UTF-8 no Windows
sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "pipeline.db"
CLIPS_DIR = BASE_DIR / "data" / "clips_exportados"
VIDEOS_DIR = BASE_DIR / "data" / "videos_longos"

def main():
    print("=" * 60)
    print("🧹 INICIANDO LIMPEZA ATÔMICA DOS CLIPS DE ONTEM (< 2026-09-29)")
    print("=" * 60)

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    with conn:
        # 1. Deletar publicações associadas a clips anteriores a hoje
        del_pubs = conn.execute("""
            DELETE FROM publications 
            WHERE clip_id IN (SELECT id FROM clips WHERE created_at < '2026-09-29')
               OR created_at < '2026-09-29';
        """).rowcount
        print(f"[1] Publicações excluídas do banco: {del_pubs}")

        # 2. Deletar llm_generations associados a clips antigos
        del_llm = conn.execute("""
            DELETE FROM llm_generations
            WHERE clip_id IN (SELECT id FROM clips WHERE created_at < '2026-09-29');
        """).rowcount
        print(f"[2] Registros de LLM excluídos: {del_llm}")

        # 3. Deletar clips antigos
        del_clips = conn.execute("""
            DELETE FROM clips WHERE created_at < '2026-09-29';
        """).rowcount
        print(f"[3] Clips de ontem excluídos do banco: {del_clips}")

        # 4. Deletar supoclip_jobs antigos
        del_jobs = conn.execute("""
            DELETE FROM supoclip_jobs WHERE created_at < '2026-09-29';
        """).rowcount
        print(f"[4] Supoclip Jobs antigos excluídos: {del_jobs}")

        # 5. Resetar long_videos criados ontem para permitir reprocessamento pela pipeline
        del_lv = conn.execute("""
            DELETE FROM long_videos WHERE created_at < '2026-09-29' OR file_name = 'video_real_teste.mp4';
        """).rowcount
        print(f"[5] Registros de long_videos resetados para reingestão: {del_lv}")

    conn.close()

    # 6. Limpeza de arquivos em data/clips_exportados
    print("\n[6] Limpando arquivos físicos em data/clips_exportados...")
    deleted_files = 0
    if CLIPS_DIR.exists():
        for f in CLIPS_DIR.glob("*.*"):
            mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d")
            if mtime < "2026-09-29":
                try:
                    f.unlink()
                    deleted_files += 1
                except Exception as e:
                    print(f"    Erro ao remover {f.name}: {e}")
    print(f"    Total de arquivos antigos removidos do disco: {deleted_files}")

    # 7. Remover arquivo de teste corrompido em data/videos_longos
    corrupt_test = VIDEOS_DIR / "video_real_teste.mp4"
    if corrupt_test.exists():
        try:
            corrupt_test.unlink()
            print("    Arquivo inválido 'video_real_teste.mp4' removido com sucesso de data/videos_longos.")
        except Exception as e:
            print(f"    Erro ao remover video_real_teste.mp4: {e}")

    # 8. Remover jNQXAC9IVRw.mp4 (vídeo de 19s de baixa resolução)
    low_res_test = VIDEOS_DIR / "jNQXAC9IVRw.mp4"
    if low_res_test.exists():
        try:
            low_res_test.unlink()
            print("    Arquivo 'jNQXAC9IVRw.mp4' (19s) removido com sucesso.")
        except Exception as e:
            print(f"    Erro ao remover jNQXAC9IVRw.mp4: {e}")

    print("\n✅ LIMPEZA CONCLUÍDA COM SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    main()
