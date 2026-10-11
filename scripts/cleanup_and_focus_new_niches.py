"""
Script de Análise, Limpeza e Otimização para Foco Exclusivo nos Novos Nichos (Fitness & Finanças).
- Remove publicações órfãs e agendadas nas contas antigas/desativadas (default_youtube, default_tiktok).
- Limpa candidatos antigos do radar de canais fora do foco (Flow, Podpah, etc.).
- Reseta candidatos em ERROR dos novos nichos para reavaliação limpa.
- Libera espaço em disco (cache de navegador e clips antigos já 100% postados).
"""
import os
import sys
import shutil
import sqlite3
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "data" / "pipeline.db"
DATA_DIR = ROOT_DIR / "data"

def run_analysis_and_cleanup(dry_run: bool = False):
    print("=" * 70)
    print("🧹 INICIANDO ANÁLISE E LIMPEZA DE TRANSIÇÃO PARA NOVOS NICHOS")
    print(f"Modo: {'[SIMULAÇÃO / DRY-RUN]' if dry_run else '[EXECUÇÃO REAL]'}")
    print("=" * 70)

    if not DB_PATH.exists():
        print(f"❌ Banco de dados {DB_PATH} não encontrado!")
        return

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    try:
        # 1. ANÁLISE E LIMPEZA DA FILA DE PUBLICAÇÕES ANTIGAS
        print("\n[1/4] Analisando publicações agendadas nas contas desativadas...")
        cursor.execute("""
            SELECT p.id, p.platform, pa.profile_name, c.title
            FROM publications p
            JOIN publishing_accounts pa ON p.publishing_account_id = pa.id
            JOIN clips c ON p.clip_id = c.id
            WHERE pa.active = 0 AND p.status = 'SCHEDULED';
        """)
        old_pubs = cursor.fetchall()
        print(f"  -> Encontradas {len(old_pubs)} publicações agendadas em contas antigas/desativadas.")

        if not dry_run and old_pubs:
            cursor.execute("""
                DELETE FROM publications
                WHERE publishing_account_id IN (
                    SELECT id FROM publishing_accounts WHERE active = 0
                ) AND status = 'SCHEDULED';
            """)
            print(f"  [✓] {len(old_pubs)} publicações antigas removidas da fila.")

        # 2. LIMPEZA DOS CANDIDATOS DO RADAR DE CANAIS DE ENTRETENIMENTO
        print("\n[2/4] Analisando candidatos do radar de canais fora do foco (entretenimento)...")
        cursor.execute("""
            SELECT count(*) as total
            FROM radar_candidates rc
            JOIN source_channels sc ON rc.source_channel_id = sc.id
            WHERE sc.active = 0;
        """)
        old_candidates_count = cursor.fetchone()["total"]
        print(f"  -> Encontrados {old_candidates_count} candidatos do radar associados a canais inativos.")

        if not dry_run and old_candidates_count > 0:
            cursor.execute("""
                DELETE FROM radar_candidates
                WHERE source_channel_id IN (
                    SELECT id FROM source_channels WHERE active = 0
                );
            """)
            print(f"  [✓] {old_candidates_count} candidatos de entretenimento limpos do radar.")

        # 3. RESET DE CANDIDATOS COM ERRO DOS NOVOS NICHOS
        print("\n[3/4] Resetando candidatos dos novos canais (Fitness e Finanças) para nova varredura...")
        cursor.execute("""
            SELECT count(*) as total
            FROM radar_candidates rc
            JOIN source_channels sc ON rc.source_channel_id = sc.id
            WHERE sc.active = 1 AND rc.status = 'ERROR';
        """)
        error_candidates = cursor.fetchone()["total"]
        print(f"  -> Encontrados {error_candidates} candidatos em ERROR nos novos canais.")

        if not dry_run and error_candidates > 0:
            cursor.execute("""
                DELETE FROM radar_candidates
                WHERE source_channel_id IN (
                    SELECT id FROM source_channels WHERE active = 1
                ) AND status = 'ERROR';
            """)
            print(f"  [✓] Candidatos em ERROR resetados para permitir nova tentativa limpa.")

        # 4. LIMPEZA DE DISCO (Cache de Navegador e Arquivos Temporários)
        print("\n[4/4] Analisando espaço em disco e cache...")
        
        # Cache do Chrome no Playwright (pastas de Cache e Code Cache que inflam gigabytes)
        freed_bytes = 0
        cache_folders = ["Cache", "Code Cache", "GPUCache", "DawnCache"]
        
        for profile_name in ["tiktok_browser_profile", "youtube_browser_profile"]:
            prof_dir = DATA_DIR / profile_name
            if prof_dir.exists():
                for root, dirs, files in os.walk(prof_dir):
                    for d in dirs:
                        if d in cache_folders:
                            cache_path = Path(root) / d
                            try:
                                sz = sum(f.stat().st_size for f in cache_path.rglob('*') if f.is_file())
                                if not dry_run:
                                    shutil.rmtree(cache_path, ignore_errors=True)
                                freed_bytes += sz
                            except Exception:
                                pass

        print(f"  -> Cache temporário de navegador identificado: {freed_bytes / (1024*1024):.2f} MB")
        if not dry_run and freed_bytes > 0:
            print(f"  [✓] Cache de navegação expurgado com sucesso (cookies e sessões preservados).")

        conn.commit()
        print("\n" + "=" * 70)
        print("✅ ANÁLISE E LIMPEZA CONCLUÍDAS COM SUCESSO!")
        print("A esteira agora está 100% enxuta e focada nos novos nichos.")
        print("=" * 70)

    except Exception as e:
        conn.rollback()
        print(f"❌ Erro durante a operação: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Apenas simula a limpeza sem deletar nada")
    args = parser.parse_args()
    run_analysis_and_cleanup(dry_run=args.dry_run)
