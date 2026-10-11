"""
Script de Limpeza Cirúrgica de Nichos:
Cancela clipes de entretenimento (Flow, Podpah, Groselha) da fila de agendamento,
libera espaço em disco e reorganiza o agendamento dos clipes dos nichos oficiais (Finanças e Fitness).
"""
import sys
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import zoneinfo

sys.stdout.reconfigure(encoding='utf-8')

db_path = Path("data/pipeline.db")
conn = sqlite3.connect(db_path)
c = conn.cursor()

print("=== INICIANDO LIMPEZA DE NICHOS FORA DO PADRÃO ===")

# 1. Identifica os clipes de entretenimento agendados
query_identify = """
SELECT cl.id, cl.clip_uid, cl.title, cl.file_path, sc.name, sc.niche
FROM clips cl
JOIN long_videos lv ON cl.long_video_id = lv.id
JOIN source_channels sc ON lv.source_channel_id = sc.id
WHERE cl.youtube_status = 'SCHEDULED' AND sc.niche = 'entretenimento'
"""

clips_to_clean = c.execute(query_identify).fetchall()
print(f"Total de clipes de entretenimento agendados a limpar: {len(clips_to_clean)}")

cleaned_ids = []
freed_bytes = 0

for row in clips_to_clean:
    clip_id, clip_uid, title, file_path_str, ch_name, niche = row
    p = Path(file_path_str) if file_path_str else None

    # Apaga arquivo do disco se existir
    if p and p.exists():
        try:
            freed_bytes += p.stat().st_size
            p.unlink()
            print(f"  [DISCO] Apagado vídeo do clipe {clip_id} ({ch_name}): {p.name}")
        except Exception as e:
            print(f"  [AVISO] Não foi possível apagar {p}: {e}")

    # Atualiza status no banco
    c.execute("""
        UPDATE clips
        SET youtube_status = 'SKIPPED',
            error_log = 'CLEANUP_NICHE_FILTER: Ignorado para manter canal focado apenas em Finanças e Fitness',
            is_deleted_from_disk = 1
        WHERE id = ?
    """, (clip_id,))
    cleaned_ids.append(clip_id)

conn.commit()

freed_mb = round(freed_bytes / (1024 * 1024), 2)
print(f"\nLimpeza de arquivos concluída: {len(cleaned_ids)} clipes cancelados. Espaço liberado: {freed_mb} MB.")

# 2. Reorganiza a fila de agendamento dos clipes de Finanças e Fitness
# Garante que os clipes restantes comecem a ser postados nas próximas janelas oficiais
print("\n=== REORGANIZANDO AGENDA DOS CLIPES DE FINANÇAS E FITNESS ===")

query_remaining = """
SELECT cl.id, cl.title, sc.name, sc.niche
FROM clips cl
JOIN long_videos lv ON cl.long_video_id = lv.id
JOIN source_channels sc ON lv.source_channel_id = sc.id
WHERE cl.youtube_status = 'SCHEDULED' AND sc.niche IN ('financas', 'fitness')
ORDER BY cl.id ASC
"""

remaining_clips = c.execute(query_remaining).fetchall()
print(f"Total de clipes de nicho na fila: {len(remaining_clips)}")

tz_sp = zoneinfo.ZoneInfo("America/Sao_Paulo")
now = datetime.now(tz_sp)

# Janelas padrão de postagem diária
POSTING_WINDOWS = [(9, 0), (11, 30), (13, 30), (15, 30), (17, 30), (19, 30), (21, 30)]

# Encontra a próxima janela disponível
schedule_time = None
curr_date = now.date()

slots = []
for day_offset in range(15): # planeja próximos dias
    target_date = curr_date + timedelta(days=day_offset)
    for h, m in POSTING_WINDOWS:
        slot_dt = datetime(target_date.year, target_date.month, target_date.day, h, m, tzinfo=tz_sp)
        # Só considera se for pelo menos 15 minutos no futuro
        if slot_dt > now + timedelta(minutes=15):
            slots.append(slot_dt)
        if len(slots) >= len(remaining_clips):
            break
    if len(slots) >= len(remaining_clips):
        break

for i, clip_row in enumerate(remaining_clips):
    target_slot = slots[i]
    target_utc_iso = target_slot.astimezone(zoneinfo.ZoneInfo("UTC")).isoformat()
    c.execute("""
        UPDATE clips
        SET scheduled_for = ?
        WHERE id = ?
    """, (target_utc_iso, clip_row[0]))
    print(f"  Clip ID {clip_row[0]} [{clip_row[3]} - {clip_row[2]}] reagendado para: {target_slot.strftime('%d/%m/%Y %H:%M')}")

conn.commit()

# 3. Status final consolidado
print("\n=== NOVO STATUS CONSOLIDADO DA FILA ===")
status_query = """
SELECT sc.niche, sc.name, cl.youtube_status, count(cl.id)
FROM clips cl
LEFT JOIN long_videos lv ON cl.long_video_id = lv.id
LEFT JOIN source_channels sc ON lv.source_channel_id = sc.id
WHERE cl.youtube_status = 'SCHEDULED'
GROUP BY sc.niche, sc.name, cl.youtube_status
"""
for r in c.execute(status_query).fetchall():
    print(f" Nicho: {r[0]} | Canal: {r[1]} | Status: {r[2]} | Quantidade: {r[3]}")

conn.close()
print("\n=== LIMPEZA E REAGENDAMENTO FINALIZADOS COM SUCESSO! ===")
