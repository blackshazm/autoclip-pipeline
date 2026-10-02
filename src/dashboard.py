"""
Dashboard Web Local em Tempo Real para Acompanhamento do Pipeline de Cortes.
Executa em http://localhost:8085 sem dependências externas (usa http.server nativo).
Design System Dark Neon Glassmorphism com Terminal de Logs, Hero Card e Ações Rápidas.
"""
import http.server
import socketserver
import json
import urllib.parse
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.config import settings
from src.core.database import get_db

PORT = 8085

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Centro de Controle • Pipeline de Cortes</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #07090e;
            --bg-elevated: #0d121f;
            --card-bg: rgba(17, 24, 39, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --card-hover: rgba(255, 255, 255, 0.12);
            --primary: #6366f1;
            --primary-light: #818cf8;
            --primary-glow: rgba(99, 102, 241, 0.25);
            --accent: #ec4899;
            --cyan: #06b6d4;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --text-dim: #64748b;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Plus Jakarta Sans', sans-serif;
        }

        body {
            background-color: var(--bg);
            background-image: 
                radial-gradient(at 0% 0%, rgba(99, 102, 241, 0.12) 0px, transparent 50%),
                radial-gradient(at 100% 0%, rgba(236, 72, 153, 0.10) 0px, transparent 50%),
                radial-gradient(at 50% 100%, rgba(6, 182, 212, 0.08) 0px, transparent 50%);
            background-attachment: fixed;
            color: var(--text-main);
            padding: 32px 36px;
            min-height: 100vh;
        }

        /* HEADER */
        .header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 28px;
            padding-bottom: 20px;
            border-bottom: 1px solid var(--card-border);
            flex-wrap: wrap;
            gap: 16px;
        }

        .header-title h1 {
            font-size: 26px;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(135deg, #ffffff 30%, #a5b4fc 70%, #ec4899 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .header-title p {
            color: var(--text-muted);
            font-size: 13.5px;
            margin-top: 4px;
        }

        .header-controls {
            display: flex;
            gap: 12px;
            align-items: center;
        }

        .refresh-pill {
            font-size: 12.5px;
            color: var(--text-muted);
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 255, 255, 0.04);
            padding: 8px 14px;
            border-radius: 9999px;
            border: 1px solid var(--card-border);
            backdrop-filter: blur(8px);
        }

        .badge-live {
            background: rgba(16, 185, 129, 0.12);
            color: var(--success);
            border: 1px solid rgba(16, 185, 129, 0.3);
            padding: 7px 16px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: 0.5px;
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

        .btn-action {
            background: linear-gradient(135deg, var(--primary), #4f46e5);
            color: #fff;
            border: none;
            padding: 9px 18px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 13px;
            cursor: pointer;
            transition: all 0.2s ease;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 0 4px 14px var(--primary-glow);
        }

        .btn-action:hover {
            transform: translateY(-1px);
            box-shadow: 0 6px 20px rgba(99, 102, 241, 0.4);
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.06);
            color: var(--text-main);
            border: 1px solid var(--card-border);
            padding: 7px 14px;
            border-radius: 8px;
            font-weight: 600;
            font-size: 12px;
            cursor: pointer;
            transition: all 0.15s ease;
            text-decoration: none;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.12);
            border-color: rgba(255, 255, 255, 0.2);
        }

        .btn-danger {
            background: rgba(239, 68, 68, 0.15);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        .btn-danger:hover {
            background: rgba(239, 68, 68, 0.25);
        }

        .btn-success {
            background: rgba(16, 185, 129, 0.15);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        .btn-success:hover {
            background: rgba(16, 185, 129, 0.25);
        }

        /* HERO CARD DO PROXIMO DISPARO */
        .hero-banner {
            background: linear-gradient(135deg, rgba(30, 27, 75, 0.85) 0%, rgba(17, 24, 39, 0.85) 100%);
            border: 1px solid rgba(99, 102, 241, 0.35);
            border-radius: 20px;
            padding: 24px 28px;
            margin-bottom: 28px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255, 255, 255, 0.1);
            backdrop-filter: blur(12px);
        }

        .hero-banner::after {
            content: '';
            position: absolute;
            top: -50px;
            right: -50px;
            width: 250px;
            height: 250px;
            background: radial-gradient(circle, rgba(236, 72, 153, 0.2) 0%, transparent 70%);
            pointer-events: none;
        }

        .hero-content {
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 20px;
            position: relative;
            z-index: 1;
        }

        .hero-info {
            flex: 1;
            min-width: 280px;
        }

        .hero-badge-tag {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(99, 102, 241, 0.2);
            color: #a5b4fc;
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 11px;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.8px;
            margin-bottom: 10px;
            border: 1px solid rgba(99, 102, 241, 0.3);
        }

        .hero-title {
            font-size: 20px;
            font-weight: 800;
            color: #ffffff;
            line-height: 1.35;
            margin-bottom: 8px;
        }

        .hero-meta {
            display: flex;
            gap: 16px;
            align-items: center;
            color: var(--text-muted);
            font-size: 13px;
            flex-wrap: wrap;
        }

        .hero-actions {
            display: flex;
            align-items: center;
            gap: 14px;
        }

        .countdown-box {
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid var(--card-border);
            border-radius: 14px;
            padding: 12px 18px;
            text-align: center;
            min-width: 140px;
        }

        .countdown-label {
            font-size: 10.5px;
            color: var(--text-muted);
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.5px;
        }

        .countdown-time {
            font-family: 'JetBrains Mono', monospace;
            font-size: 22px;
            font-weight: 700;
            color: #38bdf8;
            margin-top: 2px;
        }

        /* METRICS GRID */
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
            gap: 18px;
            margin-bottom: 28px;
        }

        .metric-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 18px;
            padding: 22px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, border-color 0.2s ease;
        }

        .metric-card:hover {
            transform: translateY(-2px);
            border-color: var(--card-hover);
        }

        .metric-card h3 {
            font-size: 12px;
            font-weight: 700;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 0.8px;
        }

        .metric-card .value {
            font-size: 30px;
            font-weight: 800;
            margin-top: 8px;
            color: #fff;
            letter-spacing: -0.5px;
        }

        .progress-bar-container {
            margin-top: 14px;
            background: rgba(255, 255, 255, 0.06);
            height: 6px;
            border-radius: 9999px;
            overflow: hidden;
        }

        .progress-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--primary), var(--cyan));
            border-radius: 9999px;
            transition: width 0.4s ease;
        }

        /* LAYOUT PRINCIPAL */
        .main-grid {
            display: grid;
            grid-template-columns: 1.6fr 1fr;
            gap: 24px;
            margin-bottom: 28px;
        }

        @media (max-width: 1200px) {
            .main-grid {
                grid-template-columns: 1fr;
            }
        }

        .section-box {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.25);
            backdrop-filter: blur(10px);
        }

        .section-box-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 18px;
            flex-wrap: wrap;
            gap: 12px;
        }

        .section-box-header h2 {
            font-size: 17px;
            font-weight: 700;
            color: #ffffff;
            display: flex;
            align-items: center;
            gap: 10px;
        }

        /* FILTROS DE TABELA */
        .table-filters {
            display: flex;
            gap: 6px;
            background: rgba(0, 0, 0, 0.3);
            padding: 4px;
            border-radius: 10px;
            border: 1px solid var(--card-border);
        }

        .filter-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            padding: 5px 12px;
            border-radius: 7px;
            font-size: 11.5px;
            font-weight: 700;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .filter-btn.active, .filter-btn:hover {
            background: rgba(255, 255, 255, 0.1);
            color: #fff;
        }

        /* TABELAS */
        .table-custom {
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
        }

        .table-custom th {
            text-align: left;
            padding: 12px 14px;
            color: var(--text-muted);
            border-bottom: 1px solid var(--card-border);
            font-weight: 700;
            font-size: 11.5px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .table-custom td {
            padding: 14px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            color: #e2e8f0;
            vertical-align: middle;
        }

        .table-custom tr:hover td {
            background: rgba(255, 255, 255, 0.02);
        }

        .tag-pill {
            display: inline-block;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 11.5px;
            font-weight: 700;
            letter-spacing: 0.3px;
        }

        .heartbeat-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            display: inline-block;
            margin-right: 8px;
        }

        /* TERMINAL DE LOGS AO VIVO */
        .terminal-box {
            background: #05070c;
            border: 1px solid #1a2234;
            border-radius: 16px;
            overflow: hidden;
            box-shadow: inset 0 2px 8px rgba(0,0,0,0.8);
        }

        .terminal-header {
            background: #0a0f1d;
            padding: 10px 18px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #1a2234;
            flex-wrap: wrap;
            gap: 10px;
        }

        .terminal-tabs {
            display: flex;
            gap: 8px;
        }

        .tab-btn {
            background: transparent;
            border: 1px solid transparent;
            color: var(--text-muted);
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.15s ease;
        }

        .tab-btn.active {
            background: rgba(99, 102, 241, 0.15);
            color: #a5b4fc;
            border-color: rgba(99, 102, 241, 0.3);
        }

        .terminal-body {
            font-family: 'JetBrains Mono', monospace;
            font-size: 12px;
            line-height: 1.6;
            padding: 16px 20px;
            height: 320px;
            overflow-y: auto;
            color: #cbd5e1;
            white-space: pre-wrap;
            word-break: break-all;
        }

        .log-info { color: #94a3b8; }
        .log-success { color: #34d399; font-weight: 600; }
        .log-warn { color: #fbbf24; font-weight: 600; }
        .log-error { color: #f87171; font-weight: 700; background: rgba(239, 68, 68, 0.1); padding: 1px 4px; border-radius: 4px; }

        /* CARDS DE CORTES */
        .clips-container {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 16px;
        }

        .clip-card {
            background: #0b0f19;
            border: 1px solid var(--card-border);
            border-radius: 14px;
            overflow: hidden;
            display: flex;
            flex-direction: column;
            transition: all 0.2s ease;
        }

        .clip-card:hover {
            border-color: rgba(99, 102, 241, 0.4);
            transform: translateY(-2px);
        }

        .clip-video-box {
            position: relative;
            background: #000;
            aspect-ratio: 9/16;
            max-height: 280px;
            overflow: hidden;
        }

        .clip-video-box video {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .clip-card-info {
            padding: 14px;
            flex: 1;
            display: flex;
            flex-direction: column;
        }

        .clip-card-title {
            font-size: 13.5px;
            font-weight: 700;
            line-height: 1.4;
            color: #fff;
            margin-bottom: 8px;
        }
        /* PAINEL DE SINAIS EM TEMPO REAL */
        .signals-panel-box {
            background: linear-gradient(135deg, rgba(17, 24, 39, 0.85) 0%, rgba(10, 14, 26, 0.95) 100%);
            border: 1px solid rgba(99, 102, 241, 0.25);
            border-radius: 16px;
            padding: 20px 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35);
        }

        .signals-panel-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 1px solid rgba(255, 255, 255, 0.06);
            flex-wrap: wrap;
            gap: 12px;
        }

        .signals-panel-header h2 {
            font-size: 16.5px;
            font-weight: 700;
            display: flex;
            align-items: center;
            gap: 10px;
            color: #fff;
        }

        .signals-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 14px;
        }

        .signal-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid rgba(255, 255, 255, 0.07);
            border-radius: 12px;
            padding: 14px;
            display: flex;
            flex-direction: column;
            gap: 8px;
            transition: all 0.2s ease;
        }

        .signal-card:hover {
            border-color: rgba(99, 102, 241, 0.35);
            background: rgba(255, 255, 255, 0.05);
        }

        .signal-card-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .signal-card-title {
            font-size: 13.5px;
            font-weight: 700;
            color: #f8fafc;
            display: flex;
            align-items: center;
            gap: 6px;
        }

        .signal-badge {
            font-size: 11px;
            font-weight: 700;
            padding: 2px 8px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .signal-badge.running {
            background: rgba(6, 182, 212, 0.18);
            color: #38bdf8;
            border: 1px solid rgba(6, 182, 212, 0.35);
            animation: pulse-border 1.8s infinite;
        }

        .signal-badge.completed {
            background: rgba(16, 185, 129, 0.18);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.35);
        }

        .signal-badge.failed {
            background: rgba(239, 68, 68, 0.18);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.35);
        }

        .signal-badge.idle {
            background: rgba(148, 163, 184, 0.12);
            color: #94a3b8;
            border: 1px solid rgba(148, 163, 184, 0.2);
        }

        .signal-msg {
            font-size: 12px;
            color: #cbd5e1;
            line-height: 1.4;
            min-height: 34px;
        }

        .signal-bar-track {
            height: 4px;
            background: rgba(255, 255, 255, 0.08);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 4px;
        }

        .signal-bar-fill {
            height: 100%;
            background: linear-gradient(90deg, #6366f1, #06b6d4);
            border-radius: 4px;
            transition: width 0.3s ease;
        }

        .signal-time {
            font-size: 11px;
            color: var(--text-dim);
            font-family: 'JetBrains Mono', monospace;
            display: flex;
            justify-content: space-between;
        }

        @keyframes pulse-border {
            0% { box-shadow: 0 0 0 0 rgba(6, 182, 212, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(6, 182, 212, 0); }
            100% { box-shadow: 0 0 0 0 rgba(6, 182, 212, 0); }
        }
    </style>
</head>
<body>

    <!-- HEADER -->
    <div class="header">
        <div class="header-title">
            <h1>⚡ AutoClip • Centro de Controle</h1>
            <p>Esteira Autônoma de Mineração, Edição 9:16 e Publicação Multiplataforma</p>
        </div>
        <div class="header-controls">
            <div class="refresh-pill">
                <span>Atualização:</span> <strong id="autoRefreshTimer" style="color: var(--cyan); font-family: 'JetBrains Mono', monospace;">05:00</strong>
            </div>
            <button class="btn-action" onclick="location.reload()">🔄 Atualizar</button>
            <div class="badge-live">MODO TURBO ATIVO</div>
        </div>
    </div>

    <!-- BANNER DE STATUS OPERACIONAL -->
    {{STATUS_ALERT_BANNER}}

    <!-- HERO CARD: PRÓXIMO DISPARO DO YOUTUBE -->
    {{NEXT_PUBLICATION_HERO}}

    <!-- CONTROLE DE FREQUÊNCIA DE POSTAGEM -->
    {{POST_INTERVAL_CONTROL}}

    <!-- ESTEIRA DE PROCESSOS EM TEMPO REAL (SINAIS DE CICLO E ETAPAS) -->
    {{PROCESS_SIGNALS_PANEL}}

    <!-- GRID DE MÉTRICAS -->
    <div class="metrics-grid">
        <div class="metric-card">
            <h3>Vídeos Postados Hoje</h3>
            <div class="value" style="color: #38bdf8; font-size: 22px;">
                🔴 YT: {{TOTAL_POSTED_YOUTUBE}}<span style="font-size: 14px; color: var(--text-dim); font-weight: 500;">/{{MAX_DAILY_UPLOADS}}</span> 
                <span style="color: #64748b; font-size: 16px; margin: 0 4px;">•</span> 
                🎵 TT: {{TOTAL_POSTED_TIKTOK}}<span style="font-size: 14px; color: var(--text-dim); font-weight: 500;">/{{MAX_DAILY_TIKTOK}}</span>
            </div>
            <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: {{DAILY_PROGRESS_PCT}}%;"></div>
            </div>
        </div>
        <div class="metric-card">
            <h3>Cortes na Fila de Agendamento</h3>
            <div class="value" style="color: #a5b4fc;">{{TOTAL_SCHEDULED}}</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">Espaçados a cada {{ACTIVE_POST_INTERVAL}} min</div>
        </div>
        <div class="metric-card">
            <h3>Vídeos Longos Analisados</h3>
            <div class="value">{{TOTAL_LONG_VIDEOS}}</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">Varredura periódica via RSS</div>
        </div>
        <div class="metric-card">
            <h3>Armazenamento em Disco</h3>
            <div class="value" style="color: {{DISK_COLOR}};">{{DISK_USAGE}}%</div>
            <div style="font-size: 12px; color: var(--text-muted); margin-top: 8px;">Purga automática acima de 75%</div>
        </div>
    </div>

    <!-- MAIN GRID -->
    <div class="main-grid">
        <!-- COLUNA ESQUERDA -->
        <div>
            <!-- FILA DE PUBLICAÇÕES -->
            <div class="section-box">
                <div class="section-box-header">
                    <h2>📅 Fila de Publicações (YouTube Shorts & TikTok)</h2>
                    <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                        <div class="table-filters">
                            <button class="filter-btn active" onclick="filterPublications('all', this)">Todos</button>
                            <button class="filter-btn" onclick="filterPublications('scheduled', this)">Agendados</button>
                            <button class="filter-btn" onclick="filterPublications('posted', this)">Publicados</button>
                            <button class="filter-btn" onclick="filterPublications('failed', this)">Falhas</button>
                        </div>
                        <button class="btn-secondary btn-danger" onclick="retryAllFailed()" title="Reenfileirar todas as postagens com erro">
                            🔄 Re-tentar Falhas
                        </button>
                    </div>
                </div>

                <div style="overflow-x: auto;">
                    <table class="table-custom" id="publicationsTable">
                        <thead>
                            <tr>
                                <th>Plataforma</th>
                                <th>Título / Corte</th>
                                <th>Status</th>
                                <th>Horário</th>
                                <th style="text-align: right;">Ação</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{PUBLICATIONS_ROWS}}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- TERMINAL DE LOGS AO VIVO -->
            <div class="section-box">
                <div class="section-box-header">
                    <h2>💻 Console / Logs da Esteira em Tempo Real</h2>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span id="logStatusText" style="font-size: 11.5px; color: var(--text-muted);">🟢 Polling ativo (4s)</span>
                        <button class="btn-secondary" onclick="fetchActiveLogs()" style="padding: 4px 10px;">Atualizar</button>
                    </div>
                </div>
                <div class="terminal-box">
                    <div class="terminal-header">
                        <div class="terminal-tabs">
                            <button class="tab-btn active" onclick="switchLogTab('robot2_publish', this)">Publicador (YouTube)</button>
                            <button class="tab-btn" onclick="switchLogTab('robot1_ingest', this)">Ingestor & Supoclip</button>
                            <button class="tab-btn" onclick="switchLogTab('radar_youtube', this)">Radar de Hype</button>
                            <button class="tab-btn" onclick="switchLogTab('llm_copywriter', this)">Copywriter (Qwen)</button>
                        </div>
                    </div>
                    <div class="terminal-body" id="terminalOutput">Carregando logs do serviço...</div>
                </div>
            </div>
        </div>

        <!-- COLUNA DIREITA -->
        <div>
            <!-- STATUS DOS ROBÔS (HEARTBEATS) -->
            <div class="section-box">
                <div class="section-box-header">
                    <h2>🤖 Saúde dos Robôs & Workers</h2>
                </div>
                <div style="overflow-x: auto;">
                    <table class="table-custom">
                        <thead>
                            <tr>
                                <th>Robô</th>
                                <th>Saúde</th>
                                <th>Última Atividade</th>
                                <th>Ping</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{HEARTBEATS_ROWS}}
                        </tbody>
                    </table>
                </div>
            </div>

            <!-- CANAIS MONITORADOS PELO RADAR -->
            <div class="section-box">
                <div class="section-box-header">
                    <h2>📡 Canais no Radar (YouTube)</h2>
                    <button class="btn-action" onclick="openChannelModal()" style="padding: 6px 14px; font-size: 12px;">+ Canal</button>
                </div>
                <div style="overflow-x: auto;">
                    <table class="table-custom">
                        <thead>
                            <tr>
                                <th>Status</th>
                                <th>Nome</th>
                                <th>VPH</th>
                                <th>Ações</th>
                            </tr>
                        </thead>
                        <tbody>
                            {{CHANNELS_ROWS}}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <!-- SEÇÃO DE VÍDEOS EM 9:16 -->
    <div class="section-box">
        <div class="section-box-header">
            <h2>🎬 Amostra de Cortes Renderizados em 9:16 (Com Legenda & Áudio)</h2>
        </div>
        <div class="clips-container">
            {{CLIPS_CARDS}}
        </div>
    </div>

    <!-- MODAL ADICIONAR CANAL -->
    <div id="channelModal" style="display: none; position: fixed; inset: 0; background: rgba(0,0,0,0.8); backdrop-filter: blur(6px); z-index: 9999; align-items: center; justify-content: center;">
        <div style="background: var(--bg-elevated); border: 1px solid var(--card-border); border-radius: 18px; padding: 28px; width: 100%; max-width: 480px; box-shadow: 0 20px 40px rgba(0,0,0,0.6);">
            <h3 style="margin-bottom: 6px; font-size: 18px; font-weight: 700;">📡 Monitorar Novo Canal</h3>
            <p style="color: var(--text-muted); font-size: 13px; margin-bottom: 20px;">Insira a URL, @handle ou ID do canal no YouTube.</p>
            <form id="addChannelForm" onsubmit="submitChannel(event)">
                <div style="margin-bottom: 14px;">
                    <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">URL / Handle / Channel ID *</label>
                    <input type="text" id="channelIdentifier" required placeholder="Ex: @flowpodcast ou https://youtube.com/@cortes" style="width: 100%; background: #07090e; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px; outline: none;">
                </div>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 18px;">
                    <div>
                        <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">VPH Mínimo</label>
                        <input type="number" id="channelVph" value="2000" style="width: 100%; background: #07090e; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px;">
                    </div>
                    <div>
                        <label style="display: block; font-size: 12px; font-weight: 600; color: var(--text-muted); margin-bottom: 6px;">Duração Mín. (min)</label>
                        <input type="number" id="channelDuration" value="15" style="width: 100%; background: #07090e; border: 1px solid var(--card-border); border-radius: 8px; padding: 10px 14px; color: white; font-size: 14px;">
                    </div>
                </div>
                <div style="display: flex; gap: 10px; justify-content: flex-end;">
                    <button type="button" onclick="closeChannelModal()" class="btn-secondary">Cancelar</button>
                    <button type="submit" class="btn-action">Salvar Canal</button>
                </div>
            </form>
        </div>
    </div>

    <!-- JAVASCRIPT DINÂMICO -->
    <script>
        // 1. Contador Regressivo de Auto-Refresh (5 min)
        let countdown = 300;
        const timerEl = document.getElementById('autoRefreshTimer');
        function formatTime(s) {
            const m = Math.floor(s / 60);
            const sec = s % 60;
            return String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0');
        }
        setInterval(() => {
            countdown--;
            if (timerEl) timerEl.innerText = formatTime(countdown);
            if (countdown <= 0) {
                window.location.reload();
            }
        }, 1000);

        // 2. Filtros na Tabela de Publicações
        function filterPublications(status, btn) {
            document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            const rows = document.querySelectorAll('#publicationsTable tbody tr');
            rows.forEach(r => {
                const rowStatus = r.getAttribute('data-status') || '';
                if (status === 'all' || rowStatus === status) {
                    r.style.display = '';
                } else {
                    r.style.display = 'none';
                }
            });
        }

        // 3. Ações Rápidas: Publicar Agora
        async function publishNow(pubId) {
            if (!confirm('Deseja forçar o disparo imediato desta publicação no YouTube?')) return;
            try {
                const res = await fetch('/api/publications/publish_now?id=' + pubId, { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    alert('⚡ Publicação antecipada para agora! O Robô 2 assumirá o envio no próximo ciclo.');
                    window.location.reload();
                } else {
                    alert('❌ Erro: ' + data.error);
                }
            } catch(e) {
                alert('Erro de conexão: ' + e);
            }
        }

        // 4. Ações Rápidas: Re-tentar todas as falhas
        async function retryAllFailed() {
            if (!confirm('Deseja recolocar todas as postagens com falha na fila de agendamento?')) return;
            try {
                const res = await fetch('/api/publications/retry_failed', { method: 'POST' });
                const data = await res.json();
                if (data.ok) {
                    alert('🔄 ' + data.count + ' publicações recuperadas e re-agendadas com sucesso!');
                    window.location.reload();
                } else {
                    alert('❌ ' + data.error);
                }
            } catch(e) {
                alert('Erro de conexão: ' + e);
            }
        }

        // 5. Console de Logs em Tempo Real
        let currentLogService = 'robot2_publish';
        function switchLogTab(service, btn) {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            currentLogService = service;
            fetchActiveLogs();
        }

        async function fetchActiveLogs() {
            const out = document.getElementById('terminalOutput');
            try {
                const res = await fetch('/api/logs?service=' + currentLogService + '&lines=35');
                const data = await res.json();
                if (data.lines && data.lines.length) {
                    out.innerHTML = data.lines.map(line => {
                        let cls = 'log-info';
                        if (line.includes('ERROR') || line.includes('falhou') || line.includes('Exception')) cls = 'log-error';
                        else if (line.includes('WARNING') || line.includes('AVISO')) cls = 'log-warn';
                        else if (line.includes('sucesso') || line.includes('POSTED') || line.includes('COMPLETED')) cls = 'log-success';
                        return '<div class="' + cls + '">' + escapeHtml(line) + '</div>';
                    }).join('');
                    out.scrollTop = out.scrollHeight;
                } else {
                    out.innerHTML = '<span style="color: var(--text-muted);">Nenhum registro de log recente para este serviço.</span>';
                }
            } catch(e) {
                // Silencioso em caso de polling
            }
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }

        // Inicia polling de logs a cada 4 segundos
        fetchActiveLogs();
        setInterval(fetchActiveLogs, 4000);

        // Modal de Canais
        function openChannelModal() { document.getElementById('channelModal').style.display = 'flex'; }
        function closeChannelModal() { document.getElementById('channelModal').style.display = 'none'; }
        async function submitChannel(e) {
            e.preventDefault();
            const ident = document.getElementById('channelIdentifier').value;
            const vph = document.getElementById('channelVph').value;
            const dur = document.getElementById('channelDuration').value;
            try {
                const res = await fetch('/api/channels/add', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({identifier: ident, vph: vph, min_duration: dur})
                });
                const d = await res.json();
                if (d.ok) {
                    alert('✅ Canal adicionado: ' + d.name);
                    window.location.reload();
                } else {
                    alert('❌ ' + d.error);
                }
            } catch(err) {
                alert('Erro: ' + err);
            }
        }
        async function deleteChannel(id, name) {
            if (!confirm('Remover ' + name + ' do radar?')) return;
            await fetch('/api/channels/delete?id=' + id, { method: 'POST' });
            window.location.reload();
        }
        async function toggleChannel(id) {
            await fetch('/api/channels/toggle?id=' + id, { method: 'POST' });
            window.location.reload();
        }

        async function changePostInterval(mins) {
            try {
                const res = await fetch('/api/settings/post_interval', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({minutes: mins})
                });
                const d = await res.json();
                if (d.ok) {
                    window.location.reload();
                } else {
                    alert('Erro ao alterar intervalo: ' + d.error);
                }
            } catch(e) {
                alert('Erro de conexão: ' + e);
            }
        }

        async function applyCustomInterval() {
            const el = document.getElementById('customIntervalInput');
            const val = parseInt(el ? el.value : 0);
            if (!val || val < 1) {
                alert('Informe um valor válido em minutos.');
                return;
            }
            await changePostInterval(val);
        }

        async function rescheduleQueueNow(showAlert = true) {
            try {
                const res = await fetch('/api/settings/reschedule_immediate', { method: 'POST' });
                const d = await res.json();
                if (d.ok) {
                    if (showAlert) alert(`🚀 Fila reagendada com sucesso!\n${d.count} publicações reorganizadas a cada ${d.interval_minutes} min a partir de AGORA.`);
                    window.location.reload();
                } else {
                    alert('❌ Erro: ' + d.error);
                }
            } catch(e) {
                alert('Erro de conexão: ' + e);
            }
        }

        async function fetchLiveSignals() {
            try {
                const res = await fetch('/api/signals');
                const data = await res.json();
                if (data.ok && data.signals && data.signals.length > 0) {
                    const grid = document.getElementById('liveSignalsGrid');
                    if (!grid) return;
                    grid.innerHTML = data.signals.map(s => {
                        const pct = s.total_steps > 0 ? Math.min(100, Math.round((s.current_step / s.total_steps) * 100)) : (s.status === 'COMPLETED' ? 100 : 0);
                        const badgeClass = (s.status || 'idle').toLowerCase();
                        let badgeLabel = 'OCIOSO';
                        if (s.status === 'RUNNING') badgeLabel = `EM EXECUÇÃO (${pct}%)`;
                        else if (s.status === 'COMPLETED') badgeLabel = 'CONCLUÍDO';
                        else if (s.status === 'FAILED') badgeLabel = 'FALHOU';

                        const timeFormatted = s.last_updated ? s.last_updated.replace('T', ' ').substring(11, 19) : '--:--:--';
                        const extraLink = s.extra && s.extra.video_id ? `<a href="https://youtube.com/shorts/${s.extra.video_id}" target="_blank" style="color: #38bdf8; font-size: 11px; text-decoration: underline; margin-left: 6px;">▶️ Link Real</a>` : '';

                        return `
                        <div class="signal-card" id="card-${s.process_name}">
                            <div class="signal-card-top">
                                <span class="signal-card-title">${s.display_name}</span>
                                <span class="signal-badge ${badgeClass}">${badgeLabel}</span>
                            </div>
                            <div class="signal-msg">${s.message || 'Aguardando próximo ciclo...'}</div>
                            <div class="signal-bar-track">
                                <div class="signal-bar-fill" style="width: ${pct}%;"></div>
                            </div>
                            <div class="signal-time">
                                <span>Passo ${s.current_step}/${s.total_steps}</span>
                                <span>${timeFormatted} ${extraLink}</span>
                            </div>
                        </div>
                        `;
                    }).join('');
                }
            } catch (e) {
                console.error("Erro ao sincronizar sinais:", e);
            }
        }
        setInterval(fetchLiveSignals, 3500);
        setTimeout(fetchLiveSignals, 600);
    </script>
</body>
</html>
"""

class PipelineDashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        # Rota de streaming de vídeos
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

        # Rota de API: Leitura de Logs ao Vivo
        if path == "/api/logs":
            query = urllib.parse.parse_qs(parsed.query)
            service = query.get("service", ["robot2_publish"])[0]
            lines_count = int(query.get("lines", [35])[0])

            # Sanitização do nome do arquivo
            safe_services = ["robot2_publish", "robot1_ingest", "radar_youtube", "llm_copywriter", "dashboard"]
            if service not in safe_services:
                service = "robot2_publish"

            log_file = Path(settings.LOG_DIR) / f"{service}.log"
            lines: List[str] = []
            if log_file.exists():
                try:
                    with open(log_file, "r", encoding="utf-8", errors="replace") as f:
                        all_lines = f.readlines()
                        lines = [l.strip() for l in all_lines[-lines_count:] if l.strip()]
                except Exception as e:
                    lines = [f"Erro ao ler log: {e}"]

            self._send_json({"service": service, "lines": lines})
            return

        # Rota de API: Controle de Intervalo (Suporta GET e POST)
        if path == "/api/settings/post_interval":
            query = urllib.parse.parse_qs(parsed.query)
            if "minutes" in query:
                mins = int(query["minutes"][0])
                self._handle_post_interval(mins)
            else:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT min_interval_minutes FROM publishing_accounts WHERE active = 1 LIMIT 1")
                    row = cur.fetchone()
                    cur_mins = row["min_interval_minutes"] if row and row["min_interval_minutes"] else 15
                self._send_json({"ok": True, "interval_minutes": cur_mins, "message": f"Intervalo atual: {cur_mins} min"})
            return

        # Rota de API: Reagendamento Imediato (Suporta GET e POST)
        if path == "/api/settings/reschedule_immediate":
            self._handle_reschedule_immediate()
            return

        # Rota de API: Sinais em Tempo Real dos Processos
        if path == "/api/signals":
            from src.core.process_signals import SignalTracker
            signals = SignalTracker.get_all_signals()
            self._send_json({"ok": True, "signals": signals})
            return

        # Rota principal: Dashboard HTML
        if path in ("/", "/index.html"):
            html_content = self.render_dashboard()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content.encode("utf-8"))))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
            return

        self.send_error(404, "Página não encontrada")

    def _handle_post_interval(self, minutes: int):
        try:
            if minutes < 1:
                minutes = 15

            windows = [f"{h:02d}:{m:02d}" for h in range(24) for m in range(0, 60, max(5, minutes))]
            windows_json = json.dumps(windows)

            total_rescheduled = 0
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("""
                    UPDATE publishing_accounts
                    SET min_interval_minutes = ?, posting_windows = ?
                    WHERE active = 1;
                """, (minutes, windows_json))

                # Reagenda automaticamente toda a fila SCHEDULED com o novo intervalo
                now_utc = datetime.now(timezone.utc)
                for platform in ["youtube", "tiktok"]:
                    cur.execute("""
                        SELECT id, clip_id FROM publications
                        WHERE platform = ? AND status = 'SCHEDULED'
                        ORDER BY id ASC;
                    """, (platform,))
                    rows = cur.fetchall()

                    # Se o YouTube estiver com limite diário excedido, reagenda a partir de 24h
                    base_time = now_utc
                    if platform == "youtube":
                        cur.execute("SELECT count(*) as c FROM publications WHERE platform = 'youtube' AND (status = 'FAILED_QUOTA' OR error_message LIKE '%limite diário%');")
                        if cur.fetchone()["c"] > 0:
                            base_time = now_utc + timedelta(hours=24)

                    for idx, row in enumerate(rows):
                        if idx == 0 and base_time == now_utc:
                            slot_iso = (now_utc - timedelta(minutes=1)).isoformat()
                        else:
                            slot_iso = (base_time + timedelta(minutes=idx * minutes)).isoformat()

                        cur.execute("""
                            UPDATE publications
                            SET scheduled_for = ?, lease_owner = NULL, lease_expires_at = NULL
                            WHERE id = ?;
                        """, (slot_iso, row["id"]))

                        cur.execute("""
                            UPDATE clips
                            SET scheduled_for = ?
                            WHERE id = ?;
                        """, (slot_iso, row["clip_id"]))
                        total_rescheduled += 1

                conn.commit()

            settings.POST_INTERVAL_MINUTES = minutes

            try:
                env_path = settings.BASE_DIR / ".env"
                if env_path.exists():
                    content_env = env_path.read_text(encoding="utf-8")
                    import re
                    if "POST_INTERVAL_MINUTES=" in content_env:
                        content_env = re.sub(r"POST_INTERVAL_MINUTES=\d+", f"POST_INTERVAL_MINUTES={minutes}", content_env)
                    else:
                        content_env += f"\nPOST_INTERVAL_MINUTES={minutes}\n"
                    env_path.write_text(content_env, encoding="utf-8")
            except Exception as env_err:
                print(f"Aviso ao salvar .env: {env_err}")

            self._send_json({
                "ok": True,
                "interval_minutes": minutes,
                "rescheduled": total_rescheduled,
                "message": f"Intervalo configurado para {minutes} min e {total_rescheduled} vídeos reorganizados na fila!"
            })
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=400)

    def _handle_reschedule_immediate(self):
        try:
            with get_db() as conn:
                cur = conn.cursor()
                cur.execute("SELECT MIN(min_interval_minutes) as m FROM publishing_accounts WHERE active = 1;")
                r_int = cur.fetchone()
                interval_min = r_int["m"] if r_int and r_int["m"] else getattr(settings, "POST_INTERVAL_MINUTES", 15)

                now_utc = datetime.now(timezone.utc)
                total_rescheduled = 0

                for platform in ["youtube", "tiktok"]:
                    cur.execute("""
                        SELECT id, clip_id FROM publications
                        WHERE platform = ? AND status = 'SCHEDULED'
                        ORDER BY id ASC;
                    """, (platform,))
                    rows = cur.fetchall()

                    base_time = now_utc

                    for idx, row in enumerate(rows):
                        if idx == 0 and base_time == now_utc:
                            slot_iso = (now_utc - timedelta(minutes=1)).isoformat()
                        else:
                            slot_iso = (base_time + timedelta(minutes=idx * interval_min)).isoformat()

                        cur.execute("""
                            UPDATE publications
                            SET scheduled_for = ?, lease_owner = NULL, lease_expires_at = NULL
                            WHERE id = ?;
                        """, (slot_iso, row["id"]))

                        cur.execute("""
                            UPDATE clips
                            SET scheduled_for = ?
                            WHERE id = ?;
                        """, (slot_iso, row["clip_id"]))
                        total_rescheduled += 1

                conn.commit()

            self._send_json({"ok": True, "count": total_rescheduled, "interval_minutes": interval_min})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)}, status=500)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        from src.services.channel_manager import add_source_channel, delete_source_channel, toggle_channel_status

        # 1. Antecipar publicação para disparo agora
        if path == "/api/publications/publish_now":
            query = urllib.parse.parse_qs(parsed.query)
            pub_id = query.get("id", [None])[0]
            if not pub_id:
                self._send_json({"ok": False, "error": "ID ausente"}, status=400)
                return

            now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE publications
                        SET scheduled_for = ?, status = 'SCHEDULED', lease_owner = NULL, lease_expires_at = NULL
                        WHERE id = ?;
                    """, (now_iso, int(pub_id)))
                    conn.commit()
                self._send_json({"ok": True, "id": pub_id})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        # 2. Re-tentar todas as falhas
        if path == "/api/publications/retry_failed":
            now_iso = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
            try:
                with get_db() as conn:
                    cur = conn.cursor()
                    cur.execute("""
                        UPDATE publications
                        SET status = 'SCHEDULED', error_message = NULL, scheduled_for = ?,
                            lease_owner = NULL, lease_expires_at = NULL
                        WHERE status = 'FAILED';
                    """, (now_iso,))
                    count = cur.rowcount
                    conn.commit()
                self._send_json({"ok": True, "count": count})
            except Exception as e:
                self._send_json({"ok": False, "error": str(e)}, status=500)
            return

        # 3. Configurar Intervalo de Postagem
        if path == "/api/settings/post_interval":
            query = urllib.parse.parse_qs(parsed.query)
            mins = 15
            if "minutes" in query:
                mins = int(query["minutes"][0])
            else:
                try:
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length > 0:
                        body = self.rfile.read(content_length).decode("utf-8")
                        data = json.loads(body)
                        mins = int(data.get("minutes", 15))
                except Exception:
                    pass
            self._handle_post_interval(mins)
            return

        # 4. Reagendar Toda a Fila com Início Imediato a partir de Agora
        if path == "/api/settings/reschedule_immediate":
            self._handle_reschedule_immediate()
            return

        # 3. Gerenciamento de Canais
        if path == "/api/channels/add":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
                ident = data.get("identifier", "").strip()
                vph = int(data.get("vph", 2000))
                min_dur = int(data.get("min_duration", 15))
                if not ident:
                    raise ValueError("Identificador obrigatório.")
                channel = add_source_channel(ident, min_duration_minutes=min_dur, vph_threshold=vph)
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
                        new_st = 0 if row["active"] == 1 else 1
                        cur.execute("UPDATE source_channels SET active = ? WHERE id = ?;", (new_st, int(ch_id)))
                        conn.commit()
                self._send_json({"ok": True})
            else:
                self._send_json({"ok": False, "error": "ID ausente"}, status=400)
            return

        self.send_error(404, "Endpoint não encontrado")

    def _send_json(self, data: Dict[str, Any], status: int = 200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def render_dashboard(self) -> str:
        with get_db() as conn:
            cursor = conn.cursor()
            tz_local = ZoneInfo(settings.TIMEZONE)
            now_utc = datetime.now(timezone.utc)
            now_local = datetime.now(tz_local)

            # 1. Métricas Gerais
            cursor.execute("SELECT COUNT(*) as cnt FROM long_videos;")
            total_long = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM publications WHERE platform='youtube' AND status='POSTED';")
            total_posted_youtube = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM publications WHERE platform='tiktok' AND status='POSTED';")
            total_posted_tiktok = cursor.fetchone()["cnt"]

            cursor.execute("SELECT COUNT(*) as cnt FROM publications WHERE status='SCHEDULED';")
            total_scheduled = cursor.fetchone()["cnt"]

            # Limite diário configurado
            max_daily = getattr(settings, "YOUTUBE_DAILY_UPLOAD_LIMIT", 100)
            cursor.execute("SELECT max_daily_posts FROM publishing_accounts WHERE platform='tiktok' AND active=1 LIMIT 1;")
            r_tt = cursor.fetchone()
            max_daily_tiktok = r_tt["max_daily_posts"] if r_tt and r_tt["max_daily_posts"] else 50

            progress_pct = min(100, int(((total_posted_youtube + total_posted_tiktok) / (max_daily + max_daily_tiktok)) * 100)) if (max_daily + max_daily_tiktok) > 0 else 0

            # Disco
            from src.services.cleanup import get_disk_usage_percent
            disk_pct = get_disk_usage_percent(settings.BASE_DIR)
            disk_color = "#34d399" if disk_pct < 70 else ("#fbbf24" if disk_pct < 85 else "#f87171")

            # 2. Hero Card: Próximo Disparo do YouTube
            cursor.execute("""
                SELECT p.id, p.platform, c.clip_uid, c.title, c.virality_score, c.tags, p.scheduled_for
                FROM publications p
                JOIN clips c ON p.clip_id = c.id
                WHERE p.platform = 'youtube' AND p.status = 'SCHEDULED'
                ORDER BY p.scheduled_for ASC LIMIT 1;
            """)
            next_pub = cursor.fetchone()

            if next_pub:
                sched_dt = datetime.fromisoformat(next_pub["scheduled_for"].replace("Z", "+00:00"))
                if sched_dt.tzinfo is None:
                    sched_dt = sched_dt.replace(tzinfo=timezone.utc)
                sched_local = sched_dt.astimezone(tz_local)
                diff_min = int((sched_dt - now_utc).total_seconds() / 60)
                
                countdown_str = f"Em {diff_min} min" if diff_min > 0 else "Na agulha (Agora)"
                time_str = sched_local.strftime("%H:%M")

                tags_list = json.loads(next_pub["tags"]) if next_pub["tags"] else ["#shorts"]
                tags_html = " ".join([f"<span style='color: var(--cyan); margin-right: 6px;'>{t}</span>" for t in tags_list[:4]])

                next_hero_html = f"""
                <div class="hero-banner">
                    <div class="hero-content">
                        <div class="hero-info">
                            <div class="hero-badge-tag">🎯 Próximo Disparo YouTube Shorts</div>
                            <h2 class="hero-title">{next_pub['title']}</h2>
                            <div class="hero-meta">
                                <span>🔥 <strong>{next_pub['virality_score']}</strong> Viral Score</span>
                                <span>🕒 Previsto para: <strong style="color: #fff;">{time_str}</strong></span>
                                <span>{tags_html}</span>
                            </div>
                        </div>
                        <div class="hero-actions">
                            <div class="countdown-box">
                                <div class="countdown-label">Tempo Restante</div>
                                <div class="countdown-time">{countdown_str}</div>
                            </div>
                            <button class="btn-action" onclick="publishNow({next_pub['id']})">
                                ⚡ Publicar Agora
                            </button>
                        </div>
                    </div>
                </div>
                """
            else:
                next_hero_html = """
                <div class="hero-banner" style="padding: 20px 28px;">
                    <div class="hero-content">
                        <div class="hero-info">
                            <h2 class="hero-title" style="font-size: 16px;">Nenhum vídeo aguardando agendamento no momento</h2>
                            <p style="color: var(--text-muted); font-size: 13px;">O Radar de Hype e o Ingestor estão minerando novos episódios.</p>
                        </div>
                    </div>
                </div>
                """

            # 3. Tabela de Publicações com Links Diretos e Filtros
            cursor.execute("""
                SELECT p.id, p.platform, c.clip_uid, c.title, p.status, p.scheduled_for, p.external_id, p.error_message
                FROM publications p
                JOIN clips c ON p.clip_id = c.id
                ORDER BY p.scheduled_for ASC;
            """)
            pubs = cursor.fetchall()

            pubs_html = ""
            failed_count = 0
            for p in pubs:
                st = p["status"]
                err = p["error_message"] or ""
                ext_id = p["external_id"] or ""

                # Filtro class
                f_class = "scheduled"
                if st == "POSTED": f_class = "posted"
                elif st == "FAILED": f_class = "failed"

                # Horário formatado
                sched_str = p["scheduled_for"] or "Imediato"
                try:
                    dt_s = datetime.fromisoformat(sched_str.replace("Z", "+00:00"))
                    if dt_s.tzinfo is None:
                        dt_s = dt_s.replace(tzinfo=timezone.utc)
                    sched_str = dt_s.astimezone(tz_local).strftime("%d/%m %H:%M")
                except Exception:
                    pass

                title_disp = p["title"] or p["clip_uid"]
                if len(title_disp) > 42:
                    title_disp = title_disp[:42] + "..."

                pub_id = p["id"]
                action_html = ""
                if st == "POSTED":
                    pill = '<span class="tag-pill" style="background: rgba(160, 185, 129, 0.15); color: #34d399;">✅ PUBLICADO</span>'
                    if p["platform"] == "youtube" and ext_id:
                        yt_link = f"https://youtube.com/shorts/{ext_id}"
                        action_html = f'<a href="{yt_link}" target="_blank" class="btn-secondary btn-success">▶️ Abrir Short</a>'
                    else:
                        action_html = '<span style="font-size: 12px; color: var(--text-dim);">-</span>'
                elif st == "UPLOADING":
                    pill = '<span class="tag-pill" style="background: rgba(168, 85, 247, 0.2); color: #c084fc; font-weight:700;">🚀 ENVIANDO...</span>'
                    action_html = '<span style="font-size: 12px; color: #a855f7;">Em andamento</span>'
                elif st == "FAILED":
                    failed_count += 1
                    err_clean = err.replace('"', '&quot;')
                    pill = f'<span class="tag-pill" style="background: rgba(239, 68, 68, 0.2); color: #f87171; cursor:pointer;" title="{err_clean}">❌ FALHOU</span>'
                    action_html = f'<button onclick="publishNow({pub_id})" class="btn-secondary btn-danger">🔄 Re-tentar</button>'
                else:
                    pill = '<span class="tag-pill" style="background: rgba(59, 130, 246, 0.15); color: #93c5fd;">⏳ AGENDADO</span>'
                    action_html = f'<button onclick="publishNow({pub_id})" class="btn-secondary" title="Disparar no próximo ciclo">⚡ Postar Já</button>'

                platform_icon = "🔴 YT" if p["platform"] == "youtube" else "🎵 TT"

                pubs_html += f"""
                <tr data-status="{f_class}">
                    <td><strong>{platform_icon}</strong></td>
                    <td title="{p['title'] or p['clip_uid']}">{title_disp}</td>
                    <td>{pill}</td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #f8fafc;">{sched_str}</td>
                    <td style="text-align: right;">{action_html}</td>
                </tr>
                """

            # 4. Status de Saúde dos Robôs (Heartbeats)
            cursor.execute("SELECT service_name, last_ping, status, extra_info FROM system_heartbeats ORDER BY last_ping DESC;")
            beats = cursor.fetchall()
            beats_html = ""
            has_bugged_worker = False

            name_map = {
                "radar_youtube": "Radar de Hype",
                "robot1_ingest": "Robô 1: Ingestor",
                "robot2_publish": "Robô 2: Publicador",
                "watchdog": "Watchdog Guardião"
            }

            for b in beats:
                s_name = b["service_name"]
                l_ping = b["last_ping"]
                info = b["extra_info"] or "Operando normalmente"

                diff_sec = 9999
                ping_local_str = "-"
                if l_ping:
                    try:
                        clean_ping = l_ping.replace("Z", "+00:00")
                        dt_ping = datetime.fromisoformat(clean_ping)
                        if dt_ping.tzinfo is None:
                            dt_ping = dt_ping.replace(tzinfo=timezone.utc)
                        diff_sec = (now_utc - dt_ping).total_seconds()
                        ping_local_str = dt_ping.astimezone(tz_local).strftime("%H:%M:%S")
                    except Exception:
                        pass

                friendly_name = name_map.get(s_name, s_name)

                if diff_sec < 300: # < 5 min
                    dot_color = "#10b981"
                    status_pill = f'<span class="tag-pill" style="background: rgba(16, 185, 129, 0.15); color: #10b981;">🟢 ATIVO ({int(diff_sec)}s)</span>'
                elif diff_sec < 900: # 5 a 15 min
                    dot_color = "#f59e0b"
                    status_pill = f'<span class="tag-pill" style="background: rgba(245, 158, 11, 0.15); color: #f59e0b;">🟡 ESPERA ({int(diff_sec//60)}m)</span>'
                else: # > 15 min
                    dot_color = "#ef4444"
                    has_bugged_worker = True
                    status_pill = '<span class="tag-pill" style="background: rgba(239, 68, 68, 0.2); color: #ef4444; font-weight:700;">🔴 INATIVO</span>'

                beats_html += f"""
                <tr>
                    <td><span class="heartbeat-dot" style="background:{dot_color}; box-shadow: 0 0 8px {dot_color};"></span><strong>{friendly_name}</strong></td>
                    <td>{status_pill}</td>
                    <td style="font-size: 12px; color: #cbd5e1; max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="{info}">{info}</td>
                    <td style="font-family: 'JetBrains Mono', monospace; font-size: 11px; color: #94a3b8;">{ping_local_str}</td>
                </tr>
                """

            # 5. Banner Geral de Diagnóstico
            if has_bugged_worker or failed_count > 0:
                alert_banner_html = f"""
                <div style="background: rgba(239, 68, 68, 0.12); border: 1px solid rgba(239, 68, 68, 0.35); border-radius: 14px; padding: 16px 22px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 12px;">
                    <div style="display: flex; align-items: center; gap: 12px;">
                        <span style="font-size: 22px;">⚠️</span>
                        <div>
                            <strong style="color: #f87171; font-size: 14px;">Diagnóstico: Atenção Requerida</strong>
                            <p style="color: #cbd5e1; font-size: 13px; margin-top: 2px;">
                                {'Existem ' + str(failed_count) + ' publicações com falha na fila (clique em "Re-tentar Falhas" para reenfileirar). ' if failed_count else ''}
                                {'Atenção: Um dos robôs está há mais de 15 minutos sem ping.' if has_bugged_worker else 'Os demais serviços estão operando normalmente.'}
                            </p>
                        </div>
                    </div>
                    <button class="btn-secondary btn-danger" onclick="retryAllFailed()">Recuperar Postagens</button>
                </div>
                """
            else:
                alert_banner_html = """
                <div style="background: rgba(16, 185, 129, 0.1); border: 1px solid rgba(16, 185, 129, 0.25); border-radius: 14px; padding: 14px 22px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 18px;">✅</span>
                        <span style="color: #34d399; font-size: 13.5px; font-weight: 600;">Todos os robôs (Radar, Ingestor, Publicador) estão 100% operacionais e sem erros ativos.</span>
                    </div>
                    <span style="color: var(--text-muted); font-size: 12px; font-family: 'JetBrains Mono', monospace;">ESTEIRA DETERMINÍSTICA</span>
                </div>
                """

            # 6. Canais Monitorados pelo Radar
            cursor.execute("SELECT id, name, youtube_channel_id, active, vph_absolute_threshold FROM source_channels ORDER BY active DESC, id ASC;")
            channels = cursor.fetchall()
            channels_html = ""
            for ch in channels:
                is_act = ch["active"] == 1
                status_badge = f"""<span class="tag-pill" style="cursor: pointer; background: {'rgba(16, 185, 129, 0.15)' if is_act else 'rgba(239, 68, 68, 0.15)'}; color: {'#10b981' if is_act else '#ef4444'};" onclick="toggleChannel({ch['id']})">{'🟢 Ativo' if is_act else '⏸ Pausado'}</span>"""
                channels_html += f"""
                <tr>
                    <td>{status_badge}</td>
                    <td><strong>{ch["name"]}</strong></td>
                    <td>{ch["vph_absolute_threshold"]}</td>
                    <td>
                        <button onclick="deleteChannel({ch['id']}, '{ch['name']}')" style="background: transparent; border: none; color: #ef4444; font-size: 12px; cursor: pointer;">Remover</button>
                    </td>
                </tr>
                """

            # 7. Amostra de Vídeos em 9:16
            cursor.execute("""
                SELECT id, clip_uid, file_path, virality_score, title
                FROM clips
                WHERE file_path IS NOT NULL
                ORDER BY id DESC LIMIT 4;
            """)
            clips_sample = cursor.fetchall()
            cards_html = ""
            for c in clips_sample:
                fpath = Path(c["file_path"])
                score_color = "#34d399" if c["virality_score"] >= 75 else "#fbbf24"
                cards_html += f"""
                <div class="clip-card">
                    <div class="clip-video-box">
                        <video controls preload="metadata">
                            <source src="/media/{fpath.name}" type="video/mp4">
                        </video>
                    </div>
                    <div class="clip-card-info">
                        <span class="tag-pill" style="background: rgba(255,255,255,0.06); color: {score_color}; align-self: flex-start; margin-bottom: 8px;">
                            Score {c['virality_score']}
                        </span>
                        <div class="clip-card-title">{c['title'] or c['clip_uid']}</div>
                    </div>
                </div>
                """

            # 8. Frequência de Postagem Ativa
            cursor.execute("SELECT MIN(min_interval_minutes) as m FROM publishing_accounts WHERE active = 1;")
            row_int = cursor.fetchone()
            current_interval = row_int["m"] if row_int and row_int["m"] else getattr(settings, "POST_INTERVAL_MINUTES", 15)

            btn_15 = "btn-secondary btn-success" if current_interval == 15 else "btn-secondary"
            btn_30 = "btn-secondary btn-success" if current_interval == 30 else "btn-secondary"
            btn_45 = "btn-secondary btn-success" if current_interval == 45 else "btn-secondary"
            btn_60 = "btn-secondary btn-success" if current_interval == 60 else "btn-secondary"

            interval_control_html = f"""
            <div style="background: linear-gradient(135deg, rgba(20, 25, 45, 0.85) 0%, rgba(13, 18, 31, 0.95) 100%); border: 1px solid rgba(99, 102, 241, 0.3); border-radius: 16px; padding: 20px 24px; margin-bottom: 24px; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; box-shadow: 0 8px 24px rgba(0,0,0,0.3);">
                <div style="display: flex; align-items: center; gap: 14px;">
                    <div style="width: 44px; height: 44px; border-radius: 12px; background: rgba(99, 102, 241, 0.15); border: 1px solid rgba(99, 102, 241, 0.4); display: flex; align-items: center; justify-content: center; font-size: 22px;">⏱️</div>
                    <div>
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <h3 style="font-size: 16px; font-weight: 700; color: #fff; letter-spacing: -0.3px;">Frequência de Postagem (YouTube & TikTok)</h3>
                            <span class="tag-pill" style="background: rgba(16, 185, 129, 0.15); color: #10b981; font-weight: 700;">Ativo: {current_interval} min</span>
                        </div>
                        <p style="font-size: 13px; color: var(--text-muted); margin-top: 3px;">Defina o intervalo entre cada publicação e reordene a fila para início imediato.</p>
                    </div>
                </div>
                <div style="display: flex; align-items: center; gap: 10px; flex-wrap: wrap;">
                    <button class="{btn_15}" style="font-weight: 700;" onclick="changePostInterval(15)">⚡ 15 min</button>
                    <button class="{btn_30}" style="font-weight: 700;" onclick="changePostInterval(30)">⏱️ 30 min</button>
                    <button class="{btn_45}" style="font-weight: 700;" onclick="changePostInterval(45)">⏳ 45 min</button>
                    <button class="{btn_60}" style="font-weight: 700;" onclick="changePostInterval(60)">🕒 60 min</button>
                    <div style="display: flex; align-items: center; gap: 6px; background: rgba(255,255,255,0.05); padding: 4px 8px; border-radius: 8px; border: 1px solid var(--card-border);">
                        <input id="customIntervalInput" type="number" min="5" max="360" placeholder="{current_interval}" style="width: 55px; background: transparent; border: none; color: #fff; font-weight: 700; text-align: center; font-family: 'JetBrains Mono', monospace;">
                        <span style="font-size: 12px; color: var(--text-muted);">min</span>
                        <button class="btn-secondary" style="padding: 4px 8px; font-size: 11px;" onclick="applyCustomInterval()">OK</button>
                    </div>
                    <button class="btn-action" style="background: linear-gradient(135deg, #06b6d4, #3b82f6); box-shadow: 0 4px 14px rgba(6, 182, 212, 0.35);" onclick="rescheduleQueueNow()">🚀 Reagendar Fila Imediata</button>
                </div>
            </div>
            """

            # 9. Sinais e Telemetria em Tempo Real dos Processos
            from src.core.process_signals import SignalTracker
            active_signals = SignalTracker.get_all_signals()
            signals_cards_html = ""
            for s in active_signals:
                pct = min(100, int((s["current_step"] / max(1, s["total_steps"])) * 100)) if s["total_steps"] > 0 else (100 if s["status"] == "COMPLETED" else 0)
                badge_class = s["status"].lower()
                badge_label = "OCIOSO"
                if s["status"] == "RUNNING": badge_label = f"EM EXECUÇÃO ({pct}%)"
                elif s["status"] == "COMPLETED": badge_label = "CONCLUÍDO"
                elif s["status"] == "FAILED": badge_label = "FALHOU"

                time_str = s["last_updated"].replace("T", " ")[11:19] if s["last_updated"] else "--:--:--"
                extra_link = ""
                if s.get("extra") and s["extra"].get("video_id"):
                    extra_link = f'<a href="https://youtube.com/shorts/{s["extra"]["video_id"]}" target="_blank" style="color: #38bdf8; font-size: 11px; text-decoration: underline; margin-left: 6px;">▶️ Link Real</a>'

                signals_cards_html += f"""
                <div class="signal-card" id="card-{s['process_name']}">
                    <div class="signal-card-top">
                        <span class="signal-card-title">{s['display_name']}</span>
                        <span class="signal-badge {badge_class}">{badge_label}</span>
                    </div>
                    <div class="signal-msg">{s['message'] or 'Aguardando próximo ciclo...'}</div>
                    <div class="signal-bar-track">
                        <div class="signal-bar-fill" style="width: {pct}%;"></div>
                    </div>
                    <div class="signal-time">
                        <span>Passo {s['current_step']}/{s['total_steps']}</span>
                        <span>{time_str} {extra_link}</span>
                    </div>
                </div>
                """

            signals_panel_html = f"""
            <div class="signals-panel-box">
                <div class="signals-panel-header">
                    <h2>📡 Esteira de Processos & Sinais em Tempo Real</h2>
                    <div style="font-size: 12px; color: var(--text-muted); display: flex; align-items: center; gap: 8px;">
                        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #38bdf8; box-shadow: 0 0 8px #38bdf8;"></span>
                        Atualização contínua (3.5s)
                    </div>
                </div>
                <div class="signals-grid" id="liveSignalsGrid">
                    {signals_cards_html or '<p style="color:var(--text-muted); font-size:13px;">Nenhum sinal emitido ainda. Os processos reportarão ao iniciar.</p>'}
                </div>
            </div>
            """

            # Substituições no Template HTML
            content = HTML_TEMPLATE
            content = content.replace("{{STATUS_ALERT_BANNER}}", alert_banner_html)
            content = content.replace("{{NEXT_PUBLICATION_HERO}}", next_hero_html)
            content = content.replace("{{POST_INTERVAL_CONTROL}}", interval_control_html)
            content = content.replace("{{PROCESS_SIGNALS_PANEL}}", signals_panel_html)
            content = content.replace("{{ACTIVE_POST_INTERVAL}}", str(current_interval))
            content = content.replace("{{TOTAL_POSTED_YOUTUBE}}", str(total_posted_youtube))
            content = content.replace("{{TOTAL_POSTED_TIKTOK}}", str(total_posted_tiktok))
            content = content.replace("{{TOTAL_POSTED_TODAY}}", str(total_posted_youtube))
            content = content.replace("{{MAX_DAILY_UPLOADS}}", str(max_daily))
            content = content.replace("{{MAX_DAILY_TIKTOK}}", str(max_daily_tiktok))
            content = content.replace("{{DAILY_PROGRESS_PCT}}", str(progress_pct))
            content = content.replace("{{TOTAL_SCHEDULED}}", str(total_scheduled))
            content = content.replace("{{TOTAL_LONG_VIDEOS}}", str(total_long))
            content = content.replace("{{DISK_USAGE}}", str(disk_pct))
            content = content.replace("{{DISK_COLOR}}", disk_color)
            content = content.replace("{{PUBLICATIONS_ROWS}}", pubs_html or "<tr><td colspan='5' style='text-align:center;'>Nenhuma publicação registrada.</td></tr>")
            content = content.replace("{{HEARTBEATS_ROWS}}", beats_html or "<tr><td colspan='4' style='text-align:center;'>Sem heartbeats.</td></tr>")
            content = content.replace("{{CHANNELS_ROWS}}", channels_html or "<tr><td colspan='4' style='text-align:center;'>Nenhum canal monitorado.</td></tr>")
            content = content.replace("{{CLIPS_CARDS}}", cards_html or "<p style='color:var(--text-muted);'>Nenhum corte renderizado ainda.</p>")

            return content

def run_dashboard():
    handler = PipelineDashboardHandler
    with http.server.ThreadingHTTPServer(("", PORT), handler) as httpd:
        print(f"[*] Dashboard Web ativo em http://localhost:{PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_dashboard()
