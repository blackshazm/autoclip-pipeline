"""
Ferramenta de Teste Comparativo de Enquadramento Facial para Shorts e TikTok.
Gera 3 formatos lado a lado a partir de um vídeo horizontal de podcast:
1. Crop Atual Sufocado (Crop 9:16 padrão y=0 - testa e topo cortados)
2. Smart Headroom Reframe (Crop com headroom de 20% e respiro vertical)
3. Blurred Background Fit (Cinema Fit: 100% do vídeo visível no centro + fundo desfocado)
"""

import subprocess
from pathlib import Path

out_dir = Path("data/testes_enquadramento")
out_dir.mkdir(parents=True, exist_ok=True)

video_id = "tnNUPyU8JFc"  # Lucas Garcia - Monster Cast / 16:9 horizontal
raw_sample = out_dir / "raw_podcast_16_9.mp4.webm"
if not raw_sample.exists():
    raw_sample = out_dir / "raw_podcast_16_9.mp4"

print(f"Vídeo base pronto: {raw_sample} ({raw_sample.stat().st_size} bytes)")

# 2. Formato 1: Crop Padrão Atual Sufocado (608x1080 at y=0, esticado para 1080x1920)
# Simula exatamente o que o reframing atual do Supox faz (y=0)
f1_path = out_dir / "1_crop_atual_sufocado.mp4"
filter_f1 = (
    "crop=608:1080:(in_w-608)/2:0,"
    "scale=1080:1920:flags=lanczos,setsar=1,"
    "drawtext=text='1. CROP ATUAL (TESTA CORTADA / y=0)':fontcolor=red:fontsize=40:x=(w-text_w)/2:y=120:box=1:boxcolor=black@0.8:boxborderw=10"
)
cmd_f1 = [
    "ffmpeg",
    "-y",
    "-i",
    str(raw_sample),
    "-vf",
    filter_f1,
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "22",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    str(f1_path),
]
print("Renderizando Formato 1: Crop Atual Sufocado...")
subprocess.run(cmd_f1, check=True, capture_output=True)

# 3. Formato 2: Smart Headroom & Respiro (Scale com Headroom de 20% no topo e fundo blur suave)
f2_path = out_dir / "2_smart_headroom.mp4"
# O vídeo é escalado para preencher a largura com folga superior, preservando testa e mãos
filter_f2 = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[bg_blur];"
    "[fg]crop=900:1080:(in_w-900)/2:0,scale=960:1152[fg_scaled];"
    "[bg_blur][fg_scaled]overlay=(W-w)/2:220,"
    "drawtext=text='2. SMART HEADROOM (COM RESPIRO NO TOPO)':fontcolor=yellow:fontsize=36:x=(w-text_w)/2:y=120:box=1:boxcolor=black@0.8:boxborderw=10[v]"
)
cmd_f2 = [
    "ffmpeg",
    "-y",
    "-i",
    str(raw_sample),
    "-filter_complex",
    filter_f2,
    "-map",
    "[v]",
    "-map",
    "0:a?",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "22",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    str(f2_path),
]
print("Renderizando Formato 2: Smart Headroom...")
subprocess.run(cmd_f2, check=True, capture_output=True)

# 4. Formato 3: Blurred Background Fit (Cinema Fit: 100% do vídeo visível no centro + fundo blur + área para legenda)
f3_path = out_dir / "3_blurred_background_fit.mp4"
filter_f3 = (
    "[0:v]split=2[bg][fg];"
    "[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=30:5[bg_blur];"
    "[fg]scale=1080:608:flags=lanczos[fg_fit];"
    "[bg_blur][fg_fit]overlay=0:(H-h)/2-100,"
    "drawtext=text='3. BLURRED FIT (100% CABECA E GESTOS VISIVEIS)':fontcolor=green:fontsize=34:x=(w-text_w)/2:y=120:box=1:boxcolor=black@0.8:boxborderw=10,"
    "drawtext=text='ESPACO LIVRE PARA LEGENDAS GRANDES':fontcolor=white:fontsize=32:x=(w-text_w)/2:y=1500:box=1:boxcolor=black@0.6:boxborderw=8[v]"
)
cmd_f3 = [
    "ffmpeg",
    "-y",
    "-i",
    str(raw_sample),
    "-filter_complex",
    filter_f3,
    "-map",
    "[v]",
    "-map",
    "0:a?",
    "-c:v",
    "libx264",
    "-preset",
    "veryfast",
    "-crf",
    "22",
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    str(f3_path),
]
print("Renderizando Formato 3: Blurred Background Fit...")
subprocess.run(cmd_f3, check=True, capture_output=True)

# 5. Gera Snapshot Comparativo Lado a Lado (Grid 3x1 em uma imagem única)
grid_image = out_dir / "comparativo_3_formatos.jpg"
filter_grid = "[0:v]scale=360:640[v0];[1:v]scale=360:640[v1];[2:v]scale=360:640[v2];" "[v0][v1][v2]hstack=inputs=3[v]"
cmd_grid = [
    "ffmpeg",
    "-y",
    "-ss",
    "00:00:03",
    "-i",
    str(f1_path),
    "-ss",
    "00:00:03",
    "-i",
    str(f2_path),
    "-ss",
    "00:00:03",
    "-i",
    str(f3_path),
    "-filter_complex",
    filter_grid,
    "-map",
    "[v]",
    "-vframes",
    "1",
    str(grid_image),
]
print("Gerando Snapshot Comparativo Lado a Lado...")
subprocess.run(cmd_grid, check=True, capture_output=True)

print("\nTeste concluído com sucesso!")
print(f"Snapshot comparativo gerado em: {grid_image.resolve()}")
