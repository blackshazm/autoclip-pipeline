# Pipeline Autônomo de Mineração, Edição e Publicação de Cortes de Vídeo

Este repositório contém a implementação completa, modular e determinística da esteira de produção autônoma (*lights-out*) de cortes verticais (YouTube Shorts e TikTok) a partir de vídeos longos, consolidando todos os requisitos do **PRD original** e de seu **Complemento Técnico de Engenharia**.

---

## 🏗️ Arquitetura do Sistema

```
                    ┌────────────────────────┐
                    │  Canais Alvo (YouTube) │
                    └───────────┬────────────┘
                                │ (RSS Feed Polling)
                                ▼
                    ┌────────────────────────┐
                    │   MÓDULO 0: RADAR      │ ◄─── [cookies.txt / yt-dlp]
                    │   (src/radar_youtube)  │
                    └───────────┬────────────┘
                                │ (Cálculo VPH / Outlier & Download)
                                ▼
                    ┌────────────────────────┐
                    │  data/videos_longos/   │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   MÓDULO 1: INGESTOR   │ ◄───► [SQLite DB: WAL Mode]
                    │   (src/robot1_ingest)  │       (Hashes SHA-256)
                    └───────────┬────────────┘
                                │ (HTTP POST /api/v1/jobs)
                                ▼
                    ┌────────────────────────┐
                    │   SUPOCLIP (Docker)    │
                    │   - Whisper (ASR)      │
                    │   - LLM Moment Chooser │
                    │   - FFmpeg (9:16 + Sub)│
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ data/clips_exportados/ │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │  MÓDULO 2: PUBLICADOR  │ ◄───► [Fila Transacional Lease-Lock]
                    │  (src/robot2_publish)  │
                    └─────┬────────────┬─────┘
                          │            │
            (Copywriting) │            │ (Upload com Controle de Cota)
                          ▼            ▼
             ┌────────────────┐   ┌───────────────────────────┐
             │ Hermes / LLM   │   │ YouTube Data API / TikTok │
             └────────────────┘   └─────────────┬─────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ Notificador (Discord/TG)  │
                                  └───────────────────────────┘
                                                │
                                                ▼
                                  ┌───────────────────────────┐
                                  │ MÓDULO 3: PURGE & CLEANUP │
                                  │ (src/services/cleanup)    │
                                  └───────────────────────────┘
```

---

## 🚀 Como Executar Localmente

### 1. Pré-requisitos
- Python 3.10+ (testado e validado em Python 3.13)
- `ffmpeg` e `ffprobe` instalados e presentes no PATH
- Docker (caso utilize a instância do Supoclip local; em desenvolvimento, use `MOCK_SUPOCLIP=true`)

### 2. Instalação de Dependências
```bash
python -m pip install -r requirements.txt
```

### 3. Configuração do `.env`
Copie o arquivo de exemplo ou edite o `.env`:
```bash
cp .env.example .env
```
Principais parâmetros:
- `MOCK_SUPOCLIP`: `true` para simulação sintética de cortes durante testes locais; `false` para conectar ao container Docker real.
- `OPENAI_BASE_URL`: Endpoint da LLM local (ex: Hermes em `http://localhost:11434/v1` ou OpenAI).
- `TIMEZONE`: `America/Sao_Paulo`.

### 4. Inicialização do Banco de Dados
Aplica o schema relacional em modo WAL e semeia canais e contas de publicação padrão:
```bash
python -m src.database.migrations
```

### 5. Execução dos Módulos

#### Módulo 0: Radar de Hype YouTube
```bash
# Execução pontual em modo dry-run (apenas consulta métricas e feeds sem baixar):
python -m src.radar_youtube --dry-run --once

# Execução contínua:
python -m src.radar_youtube
```

#### Módulo 1: Ingestão e Despacho
```bash
# Executa uma varredura na pasta data/videos_longos/ e despacha para Supoclip:
python -m src.robot1_ingest --once

# Execução contínua em segundo plano:
python -m src.robot1_ingest
```

#### Módulo 2: Inteligência, Agendamento e Publicação
```bash
# Sincroniza Supoclip, gera cópias com LLM, agenda no buffer e publica clips vencidos:
python -m src.robot2_publish --once

# Execução contínua:
python -m src.robot2_publish
```

#### Limpeza de Disco e Retenção
```bash
# Executa purga normal de vídeos longos pós-corte e clips pós-48h de postados:
python -m src.services.cleanup
```

#### Watchdog e Monitoramento de Heartbeats
```bash
# Checa se algum worker está sem ping há mais de 15 min e reporta falhas:
python -m src.services.watchdog
```

---

## 🧪 Bateria de Testes Automatizados

A suíte cobre:
- Idempotência primária e rejeição de duplicatas por hash SHA-256.
- Validação e detecção de arquivos corrompidos via `ffprobe`/`ffmpeg`.
- Concorrência de publicação com lease-lock no SQLite e reconciliação pós-crash (`RECONCILING`).
- Sanitização contra prompt injection na transcrição e fallback determinístico da LLM.
- Algoritmo de agendamento em buffer anti-spam, janelas horárias e espaçamento de 180 min.
- Expurgo físico de mídias pós-processamento preservando auditoria no banco.

Executar os testes:
```bash
python -m pytest tests/ -v
```

---

## 🐧 Deploy em Produção (Linux / Systemd)

Na pasta `deploy/`, disponibilizamos os unit e timer files prontos para serem copiados para `/etc/systemd/system/`:
- `clip-ingest.service`: Worker contínuo de monitoramento de pasta e despacho.
- `clip-publish.service`: Worker contínuo de sincronização, copywriting e postagem com lease lock.
- `clip-radar.timer` / `clip-radar.service`: Varredura periódica RSS a cada 15 minutos.
- `clip-cleanup.timer` / `clip-cleanup.service`: Expurgo e retenção de disco a cada 30 minutos.
- `clip-watchdog.service`: Monitor contínuo de heartbeat e DLQ.

Ativação no servidor:
```bash
sudo cp deploy/* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now clip-ingest clip-publish clip-radar.timer clip-cleanup.timer clip-watchdog
```
