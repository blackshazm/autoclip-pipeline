"""
Dashboard Web Local em Tempo Real para Acompanhamento do Pipeline de Cortes.
Executa em http://localhost:5000 sem dependências extras (usa http.server nativo).
"""
import http.server
import socketserver
import json
import urllib.parse
from pathlib import Path
from typing import Dict, Any

from src.core.config import settings
from src.core.database import get_db

PORT = 8085

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Pipeline de Cortes • Centro de Controle</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #090d16;
            --card-bg: #111827;
            --card-border: #1f293d;
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.25);
            --accent: #ec4899;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }

        body {
            background-color: var(--bg);
            color: var(--text-main);
            padding: 28px;
            min-height: 100vh;
        }

        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--card-border);
        }

        .header-title h1 {
            font-size: 26px;
            font-weight: 800;
            background: linear-gradient(135deg, #a5b4fc, #ec4899);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .header-title p {
            color: var(--text-muted);
            font-size: 14px;
            margin-top: 4px;
        }

        .badge-live {
            background: rgba(16, 185, 129, 0.15);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .badge-live::before {
            content: '';
            width: 8px;
            height: 8px;
            background: var(--success);
            border-radius: 50%;
            box-shadow: 0 0 10px var(--success);
            animation: pulse 1.5s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; transform: scale(1); }
            50% { opacity: 0.4; transform: scale(0.8); }
        }

        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 18px;
            margin-bottom: 28px;
        }

        .metric-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 20px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        }

        .metric-card h3 {
            font-size: 13px;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .metric-card .value {
            font-size: 28px;
            font-weight: 800;
            margin-top: 8px;
            color: #fff;
        }

        .main-grid {
            display: grid;
            grid-template-columns: 2fr 1fr;
            gap: 24px;
        }

        .section-box {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 24px;
            margin-bottom: 24px;
        }

        .section-box h2 {
            font-size: 18px;
            font-weight: 700;
            margin-bottom: 18px;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .clips-container {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
        }

        .clip-card {
            background: #0d1322;
            border: 1px solid var(--card-border);
            border-radius: 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: transform 0.2s, border-color 0.2s;
        }

        .clip-card:hover {
            transform: translateY(-3px);
            border-color: var(--primary);
        }

        .video-preview {
            width: 100%;
            height: 380px;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .video-preview video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .clip-info {
            padding: 16px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .score-badge {
            align-self: flex-start;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 700;
            margin-bottom: 10px;
        }

        .score-high {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }

        .score-medium {
            background: rgba(245, 158, 11, 0.15);
            color: #fbbf24;
            border: 1px solid rgba(245, 158, 11, 0.3);
        }

        .score-low {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }

        .clip-title {
            font-size: 14px;
            font-weight: 700;
            line-height: 1.4;
            margin-bottom: 8px;
            color: #fff;
        }

        .clip-meta {
            font-size: 12px;
            color: var(--text-muted);
            margin-top: auto;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }

        .table-custom {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        .table-custom th {
            text-align: left;
            padding: 10px 14px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--card-border);
            font-weight: 600;
        }

        .table-custom td {
            padding: 12px 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
            color: #e2e8f0;
        }

        .tag-pill {
            display: inline-block;
            background: rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            margin-right: 4px;
            margin-top: 4px;
        }

        .heartbeat-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 6px;
            background: var(--success);
        }

        .btn-action {
            background: var(--primary);
            color: #fff;
            border: none;
            padding: 10px 18px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 13px;
            cursor: pointer;
            transition: opacity 0.2s;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }

        .btn-action:hover {
            opacity: 0.9;
        }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-title">
            <h1>⚡ Pipeline de Cortes Autônomo</h1>
            <p>Monitor de Inteligência, Ingestão, Edição 9:16 e Publicação Multiplataforma</p>
        </div>
        <div style="display: flex; gap: 12px; align-items: center;">
            <button class="btn-action" onclick="location.reload()">🔄 Atualizar</button>
            <div class="badge-live">LIGHTS-OUT OPERATIONAL</div>
        </div>
    </div>

    <div class="metrics-grid">
        <div class="metric-card">
            <h3>Vídeos Longos Processados</h3>
            <div class="value">{{TOTAL_LONG_VIDEOS}}</div>
        </div>
        <div class="metric-card">
            <h3>Cortes Gerados (Supoclip)</h3>
            <div class="value">{{TOTAL_CLIPS}}</div>
        </div>
        <div class="metric-card">
            <h3>Publicações Agendadas</h3>
            <div class="value">{{TOTAL_PUBLICATIONS}}</div>
        </div>
        <div class="metric-card">
            <h3>Espaço em Disco Utilizado</h3>
            <div class="value">{{DISK_USAGE}}%</div>
        </div>
    </div>

    <div class="main-grid">
        <div>
            <div class="section-box">
                <h2>🎬 Cortes Renderizados em 9:16 (Com Legenda e Áudio)</h2>
                <div class="clips-container">
                    {{CLIPS_CARDS}}
                </div>
            </div>

            <div class="section-box">
                <h2>📅 Fila de Publicações (YouTube Shorts & TikTok)</h2>
                <table class="table-custom">
                    <thead>
                        <tr>
                            <th>Plataforma</th>
                            <th>Clip UID</th>
                            <th>Status</th>
                            <th>Horário Agendado</th>
                            <th>Chave Idempotência</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{PUBLICATIONS_ROWS}}
                    </tbody>
                </table>
            </div>
        </div>

        <div>
            <div class="section-box">
                <h2>🤖 Status dos Workers (Heartbeats)</h2>
                <table class="table-custom">
                    <thead>
                        <tr>
                            <th>Serviço</th>
                            <th>Status</th>
                            <th>Último Ping</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{HEARTBEATS_ROWS}}
                    </tbody>
                </table>
            </div>

            <div class="section-box">
                <h2>🧹 Retenção e Purga de Disco</h2>
                <table class="table-custom">
                    <thead>
                        <tr>
                            <th>Status</th>
                            <th>Vídeos Purgados</th>
                            <th>Espaço Liberado</th>
                        </tr>
                    </thead>
                    <tbody>
                        {{CLEANUP_ROWS}}
                    </tbody>
                </table>
            </div>
        </div>

        <!-- SEÇÃO DE CANAIS MONITORADOS PELO RADAR -->
        <div class="section-box" style="margin-top: 24px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                <div>
                    <h2>📡 Canais Monitorados pelo Radar (YouTube)</h2>
                    <p style="color: var(--text-muted); font-size: 13px; margin-top: 4px;">Varredura periódica via RSS, qualificação por VPH e fatiamento automático.</p>
                </div>
                <button onclick="openChannelModal()" style="background: linear-gradient(135deg, var(--primary), var(--accent)); color: white; border: none; padding: 10px 18px; border-radius: 8px; font-weight: 700; cursor: pointer; display: flex; align-items: center; gap: 8px; font-size: 13px; box-shadow: 0 4px 14px var(--primary-glow);">
                    + Adicionar Canal
                </button>
            </div>
            <table class="table-custom">
                <thead>
                    <tr>
                        <th>Status</th>
                        <th>Nome do Canal</th>
                        <th>Channel ID / Handle</th>
                        <th>VPH Mínimo</th>
                        <th>Duração Mínima</th>
                        <th>Licença</th>
                        <th>Ações</th>
                    </tr>
                </thead>
                <tbody>
                    {{CHANNELS_ROWS}}
                </tbody>
            </table>
        </div>

        <!-- MODAL ADICIONAR CANAL -->
        <div id="channelModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.75); backdrop-filter: blur(4px); z-index: 9999; align-items: center; justify-content: center;">
            <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 16px; padding: 28px; width: 100%; max-width: 480px; box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
                <h3 style="margin-bottom: 8px; font-size: 18px; font-weight: 700;">📡 Monitorar Novo Canal</h3>
                <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 20px;">Insira a URL, @handle ou ID do canal no YouTube.</p>
                <form id="addChannelForm" onsubmit="submitChannel(event)">
                    <div style="margin-bottom: 14px;">
                        <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">URL / Handle / Channel ID *</label>
                        <input type="text" id="channelIdentifier" required placeholder="Ex: @flowpodcast ou https://youtube.com/@cortes" style="width: 100%; background: #0b0f19; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px; outline: none;">
                    </div>
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 14px;">
                        <div>
                            <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">VPH Mínimo</label>
                            <input type="number" id="channelVph" value="2000" style="width: 100%; background: #0b0f19; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px;">
                        </div>
                        <div>
                            <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">Duração Mín. (min)</label>
                            <input type="number" id="channelDuration" value="15" style="width: 100%; background: #0b0f19; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px;">
                        </div>
                    </div>
                    <div style="margin-bottom: 20px;">
                        <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">Modo de Licença</label>
                        <select id="channelLicense" style="width: 100%; background: #0b0f19; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px;">
                            <option value="owned">Próprio (Owned)</option>
                            <option value="authorized">Autorizado / Parceria</option>
                            <option value="licensed">Licenciado</option>
                            <option value="third_party_review_required">Exige Revisão</option>
                        </select>
                    </div>
                    <div style="display: flex; justify-content: flex-end; gap: 10px;">
                        <button type="button" onclick="closeChannelModal()" style="background: transparent; border: 1px solid var(--card-border); color: var(--text-muted); padding: 8px 16px; border-radius: 8px; cursor: pointer;">Cancelar</button>
                        <button type="submit" id="btnSubmitChannel" style="background: var(--primary); border: none; color: white; padding: 8px 20px; border-radius: 8px; font-weight: 600; cursor: pointer;">Salvar Canal</button>
                    </div>
                </form>
            </div>
        </div>

        <script>
            function openChannelModal() {
                document.getElementById('channelModal').style.display = 'flex';
            }
            function closeChannelModal() {
                document.getElementById('channelModal').style.display = 'none';
            }
            async function submitChannel(e) {
                e.preventDefault();
                const btn = document.getElementById('btnSubmitChannel');
                btn.disabled = true;
                btn.innerText = 'Resolvendo...';
                const payload = {
                    identifier: document.getElementById('channelIdentifier').value,
                    vph: parseInt(document.getElementById('channelVph').value) || 2000,
                    min_duration: parseInt(document.getElementById('channelDuration').value) || 15,
                    license: document.getElementById('channelLicense').value
                };
                try {
                    const res = await fetch('/api/channels/add', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify(payload)
                    });
                    const data = await res.json();
                    if (data.ok) {
                        alert('✅ Canal cadastrado: ' + data.name);
                        window.location.reload();
                    } else {
                        alert('❌ ' + (data.error || 'Erro ao cadastrar canal.'));
                    }
                } catch(err) {
                    alert('❌ Erro na requisição: ' + err);
                } finally {
                    btn.disabled = false;
                    btn.innerText = 'Salvar Canal';
                }
            }
            async function deleteChannel(id, name) {
                if (!confirm('Deseja realmente remover o canal ' + name + ' do radar?')) return;
                try {
                    const res = await fetch('/api/channels/delete?id=' + id, { method: 'POST' });
                    const data = await res.json();
                    if (data.ok) {
                        window.location.reload();
                    } else {
                        alert('❌ ' + data.error);
                    }
                } catch(err) {
                    alert('❌ Erro: ' + err);
                }
            }
            async function toggleChannel(id) {
                try {
                    const res = await fetch('/api/channels/toggle?id=' + id, { method: 'POST' });
                    const data = await res.json();
                    if (data.ok) {
                        window.location.reload();
                    }
                } catch(err) {
                    alert('❌ Erro: ' + err);
                }
            }
        </script>
    </div>
</body>
</html>
"""

class PipelineDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Rota para streaming dos vídeos cortados de data/clips_exportados/
        if path.startswith("/media/"):
            clip_name = path.replace("/media/", "")
            clip_file = settings.OUTPUT_DIR / clip_name
            if clip_file.exists() and clip_file.is_file():
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(clip_file.stat().st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(clip_file, "rb") as f:
                    self.copyfile(f, self.wfile)
                return
            else:
                self.send_error(404, "Vídeo não encontrado")
                return

        # Rota principal: Dashboard HTML
        if path in ("/", "/index.html"):
            html_content = self.render_dashboard()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        self.send_error(404, "Página não encontrada")

    def render_dashboard(self) -> str:
        with get_db() as conn:
            cursor = conn.cursor()

            # Métricas Gerais
            cursor.execute("SELECT COUNT(*) as cnt FROM long_videos;")
            total_long = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM clips;")
            total_clips = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM publications WHERE status = 'SCHEDULED';")
            total_pubs = cursor.fetchone()["cnt"]

            import shutil
            total, used, free = shutil.disk_usage(str(settings.BASE_DIR))
            disk_pct = round((used / total) * 100, 1)

            # Clips
            cursor.execute("""
                SELECT id, clip_uid, file_path, virality_score, title, tags, moderation_status
                FROM clips
                ORDER BY virality_score DESC;
            """)
            clips = cursor.fetchall()

            cards_html = ""
            for c in clips:
                score = c["virality_score"]
                score_class = "score-high" if score >= 80 else ("score-medium" if score >= 70 else "score-low")
                p = Path(c["file_path"])
                video_url = f"/media/{p.name}"

                tags_list = json.loads(c["tags"]) if c["tags"] else ["#shorts"]
                tags_badges = "".join([f'<span class="tag-pill">{t}</span>' for t in tags_list])

                cards_html += f"""
                <div class="clip-card">
                    <div class="video-preview">
                        <video controls preload="metadata">
                            <source src="{video_url}" type="video/mp4">
                            Seu navegador não suporta a tag video.
                        </video>
                    </div>
                    <div class="clip-info">
                        <div class="score-badge {score_class}">Virality Score: {score}/100</div>
                        <div class="clip-title">{c["title"] or "Trecho Analisado"}</div>
                        <div style="margin-bottom: 12px;">{tags_badges}</div>
                        <div class="clip-meta">
                            <span><strong>UID:</strong> {c["clip_uid"]}</span>
                            <span><strong>Moderação:</strong> {c["moderation_status"]}</span>
                        </div>
                    </div>
                </div>
                """

            # Publicações
            cursor.execute("""
                SELECT p.platform, c.clip_uid, p.status, p.scheduled_for, p.idempotency_key
                FROM publications p
                JOIN clips c ON p.clip_id = c.id
                ORDER BY p.scheduled_for ASC;
            """)
            pubs = cursor.fetchall()

            pubs_html = ""
            for p in pubs:
                pubs_html += f"""
                <tr>
                    <td><strong>{p["platform"].upper()}</strong></td>
                    <td>{p["clip_uid"]}</td>
                    <td><span class="tag-pill" style="background: rgba(16, 185, 129, 0.2); color: #34d399;">{p["status"]}</span></td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 12px;">{p["scheduled_for"] or "Imediato"}</td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94a3b8;">{p["idempotency_key"][:16]}...</td>
                </tr>
                """

            # Heartbeats
            cursor.execute("SELECT service_name, last_ping, status FROM system_heartbeats ORDER BY last_ping DESC;")
            beats = cursor.fetchall()
            beats_html = ""
            for b in beats:
                beats_html += f"""
                <tr>
                    <td><span class="heartbeat-dot"></span><strong>{b["service_name"]}</strong></td>
                    <td><span class="tag-pill" style="background: rgba(59, 130, 246, 0.15); color: #93c5fd;">{b["status"]}</span></td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 11px;">{b["last_ping"]}</td>
                </tr>
                """

            # Cleanup
            cursor.execute("SELECT status, deleted_long_videos, freed_bytes FROM cleanup_runs ORDER BY id DESC LIMIT 5;")
            runs = cursor.fetchall()
            clean_html = ""
            for r in runs:
                freed_kb = round(r["freed_bytes"] / 1024, 1)
                clean_html += f"""
                <tr>
                    <td><span class="tag-pill">{r["status"]}</span></td>
                    <td>{r["deleted_long_videos"]} vídeo(s)</td>
                    <td>{freed_kb} KB</td>
                </tr>
                """

            # Canais Monitorados pelo Radar
            cursor.execute("SELECT id, name, youtube_channel_id, rss_url, active, min_duration_minutes, vph_absolute_threshold, license_mode FROM source_channels ORDER BY active DESC, id ASC;")
            channels = cursor.fetchall()
            channels_html = ""
            for ch in channels:
                is_act = ch["active"] == 1
                status_badge = f"""<span class="tag-pill" style="cursor: pointer; background: {'rgba(16, 185, 129, 0.15)' if is_act else 'rgba(239, 68, 68, 0.15)'}; color: {'#10b981' if is_act else '#ef4444'};" onclick="toggleChannel({ch['id']})">{'🟢 Ativo' if is_act else '⏸ Pausado'}</span>"""
                channels_html += f"""
                <tr>
                    <td>{status_badge}</td>
                    <td><strong>{ch["name"]}</strong></td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: var(--text-muted);">{ch["youtube_channel_id"]}</td>
                    <td>{ch["vph_absolute_threshold"]} VPH</td>
                    <td>{ch["min_duration_minutes"]} min</td>
                    <td><span class="tag-pill">{ch["license_mode"]}</span></td>
                    <td>
                        <button onclick="deleteChannel({ch['id']}, '{ch['name']}')" style="background: transparent; border: 1px solid rgba(239,68,68,0.3); color: #ef4444; padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;">Remover</button>
                    </td>
                </tr>
                """

            content = HTML_TEMPLATE
            content = content.replace("{{TOTAL_LONG_VIDEOS}}", str(total_long))
            content = content.replace("{{TOTAL_CLIPS}}", str(total_clips))
            content = content.replace("{{TOTAL_PUBLICATIONS}}", str(total_pubs))
            content = content.replace("{{DISK_USAGE}}", str(disk_pct))
            content = content.replace("{{CLIPS_CARDS}}", cards_html or "<p style='color:#94a3b8; padding: 20px;'>Nenhum clip registrado ainda.</p>")
            content = content.replace("{{PUBLICATIONS_ROWS}}", pubs_html or "<tr><td colspan='5' style='text-align:center;'>Nenhuma publicação agendada.</td></tr>")
            content = content.replace("{{HEARTBEATS_ROWS}}", beats_html or "<tr><td colspan='3' style='text-align:center;'>Sem heartbeats registrados.</td></tr>")
            content = content.replace("{{CLEANUP_ROWS}}", clean_html or "<tr><td colspan='3' style='text-align:center;'>Sem execuções de limpeza.</td></tr>")
            content = content.replace("{{CHANNELS_ROWS}}", channels_html or "<tr><td colspan='7' style='text-align:center;'>Nenhum canal monitorado. Clique em '+ Adicionar Canal'.</td></tr>")

            return content

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        from src.services.channel_manager import add_source_channel, delete_source_channel, toggle_channel_status

        if path == "/api/channels/add":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                ident = data.get("identifier", "").strip()
                vph = int(data.get("vph", 2000))
                min_dur = int(data.get("min_duration", 15))
                lic = data.get("license", "owned")

                if not ident:
                    raise ValueError("Identificador do canal é obrigatório.")

                channel = add_source_channel(ident, min_duration_minutes=min_dur, vph_threshold=vph, license_mode=lic)
                self._send_json({"ok": True, "name": channel["name"], "id": channel["id"]})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=400)
            return

        if path == "/api/channels/delete":
            query = urllib.parse.parse_qs(parsed.query)
            ch_id = query.get("id", [None])[0]
            if ch_id:
                ok = delete_source_channel(int(ch_id))
                self._send_json({"ok": ok})
            else:
                self._send_json({"ok": False, "error": "ID ausente"}, status=400)
            return

        if path == "/api/channels/toggle":
            query = urllib.parse.parse_qs(parsed.query)
            ch_id = query.get("id", [None])[0]
            if ch_id:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT active FROM source_channels WHERE id = ?;", (int(ch_id),))
                    row = cur.fetchone()
                    if row:
                        new_state = not bool(row["active"])
                        toggle_channel_status(int(ch_id), new_state)
                        self._send_json({"ok": True, "active": new_state})
                        return
            self._send_json({"ok": False, "error": "Canal não encontrado"}, status=404)
            return

        self.send_error(404, "Endpoint não encontrado")

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

def start_dashboard():
    with socketserver.TCPServer(("", PORT), PipelineDashboardHandler) as httpd:
        print(f"\n========================================================")
        print(f"🚀 DASHBOARD WEB ATIVO EM: http://localhost:{PORT}")
        print(f"Pressione Ctrl+C para encerrar o servidor.")
        print(f"========================================================\n")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard encerrado.")

if __name__ == "__main__":
    start_dashboard()
