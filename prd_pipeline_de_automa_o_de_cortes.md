# Product Requirements Document (PRD)
## Pipeline Autônomo de Mineração, Edição e Publicação de Cortes de Vídeo

---

### 1. Visão Geral e Objetivos do Produto

#### 1.1 Declaração do Problema
A criação e distribuição de conteúdo em formato vertical (*Shorts, TikTok, Reels*) a partir de vídeos longos (podcasts, streams e entrevistas) exige um esforço manual repetitivo de monitoramento de canais, identificação de trechos relevantes, enquadramento 9:16, transcrição com legendagem estilizada e publicação multiplataforma. Esse ciclo manual limita a escala de produção e atrasa o aproveitamento da janela de relevância temporal (*hype*) do conteúdo.

#### 1.2 Objetivo
Construir uma esteira de software 100% autônoma, modular e determinística, capaz de operar continuamente sem intervenção humana, executando:
1. Descoberta de vídeos longos de alto potencial através de métricas de aceleração de audiência.
2. Extração, enquadramento dinâmico e legendagem automatizada de cortes via **Supoclip**.
3. Seleção estrita de clips qualificados por *Virality Score*.
4. Redação de títulos e metadados contextuais via LLM/Hermes.
5. Publicação sincronizada no **YouTube Shorts** e **TikTok**, garantindo idempotência total (risco zero de duplicatas) e tolerância a falhas isoladas de rede/plataforma.

#### 1.3 KPIs de Sucesso
* **Latência de Esteira:** Tempo total entre a detecção do vídeo longo e a publicação dos primeiros cortes inferior a 45 minutos (dependente da duração do vídeo original e poder de processamento da GPU).
* **Taxa de Idempotência:** 0% de duplicação de vídeos longos ingeridos ou de clips publicados.
* **Resiliência:** Tolerância a indisponibilidade momentânea de APIs terceiras com repescagem automática em ciclo subsequente.
* **Intervenção Manual Requerida:** 0 ações manuais no ciclo operacional padrão.
* **Estabilidade de Armazenamento:** Uso de disco estritamente controlado com ocupação média constante abaixo de 80% da capacidade total da máquina.

---

### 2. Arquitetura do Sistema e Fluxo de Dados

A solução é desenhada sobre uma arquitetura orientada a estados locais, desacoplada por um banco relacional leve (**SQLite**) e dividida em processos independentes executados pelo sistema operacional.

```
                    ┌────────────────────────┐
                    │  Canais Alvo (YouTube) │
                    └───────────┬────────────┘
                                │ (RSS Feed Polling)
                                ▼
                    ┌────────────────────────┐
                    │   MÓDULO 0: RADAR      │ ◄─── [cookies.txt / yt-dlp]
                    │   (radar_youtube.py)   │
                    └───────────┬────────────┘
                                │ (Cálculo VPH / Outlier & Download)
                                ▼
                    ┌────────────────────────┐
                    │  data/videos_longos/   │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │   MÓDULO 1: INGESTOR   │ ◄───► [SQLite DB]
                    │   (robot1_ingest.py)   │       (Controle de Hashes)
                    └───────────┬────────────┘
                                │ (HTTP POST /api/v1/jobs)
                                ▼
                    ┌────────────────────────┐
                    │  SUPOCLIP (Docker)     │
                    │  - Whisper (ASR)       │
                    │  - LLM Moment Chooser  │
                    │  - FFmpeg (9:16 + Sub) │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ data/clips_exportados/ │
                    └───────────┬────────────┘
                                │
                                ▼
                    ┌────────────────────────┐
                    │ MÓDULO 2: PUBLICADOR   │ ◄───► [SQLite DB]
                    │  (robot2_publish.py)   │       (Fila de Agendamento Buffer)
                    └─────┬────────────┬─────┘
                          │            │
             (Meta/Copy)  │            │  (Video Upload com Rate Limit)
                          ▼            ▼
             ┌────────────────┐   ┌───────────────────────────┐
             │ LLM / Hermes   │   │ YouTube Data API / TikTok │
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
                                  │ (Limpeza de Arquivos MP4) │
                                  └───────────────────────────┘
```

---

### 3. Especificação Funcional dos Componentes

#### 3.1 Módulo 0: Radar de Hype (`radar_youtube.py`)
* **Mecanismo de Descoberta:** Monitoramento periódico dos feeds RSS de canais pré-definidos (`https://www.youtube.com/feeds/videos.xml?channel_id=CANAL_ID`).
* **Regra de Amostragem Temporal:** Vídeos com menos de 2 horas de vida são ignorados temporariamente para permitir a consolidação das primeiras métricas de audiência.
* **Cálculo de Aceleração ($VPH$):**
  $$VPH = \frac{\text{Total de Visualizações}}{\text{Horas Decorridas desde a Publicação}}$$
* **Gatilho de Decisão:**
  * Condição 1: Duração $\ge 20$ minutos (elimina transmissões curtas ou Shorts do canal original).
  * Condição 2: $VPH \ge \text{Threshold}$ (ex: $5.000\text{ views/h}$ ou fator multiplicador $\ge 2.0\times$ sobre a mediana histórica do canal).
* **Ação:** O `yt-dlp` realiza o download em qualidade otimizada (720p/1080p) salvando em `data/videos_longos/<video_id>.mp4`.
* **Tratamento Anti-Bot:** Injeção obrigatória do arquivo de sessão `cookies.txt` e limitação de taxa de download para evitar banimentos de IP pela infraestrutura do YouTube.

#### 3.2 Módulo 1: Ingestão Determinística (`robot1_ingest.py`)
* **Monitoramento de Diretório:** Varrimento contínuo de `data/videos_longos/`.
* **Trava de Arquivo em Escrita:** Validação de estabilidade do tamanho do arquivo (garante que downloads incompletos ou transferências de rede não sejam processados pela metade).
* **Idempotência Primária:** Geração do hash SHA-256 do arquivo. Se o hash já existir na tabela `long_videos`, o arquivo é descartado ou ignorado.
* **Despacho para Supoclip:**
  * O arquivo é enviado via `multipart/form-data` para o endpoint `POST /api/v1/jobs` do Supoclip.
  * O `job_id` retornado é armazenado no SQLite sob o status `PROCESSING`.

#### 3.3 Motor de Corte: Supoclip (Instância Local / Docker)
* **Transcrição:** Extração de áudio e geração de transcrição com carimbo de data/hora via OpenAI Whisper.
* **Detecção de Segmentos:** Heurística e LLM interno do Supoclip calculam a pontuação de relevância e geram o *Virality Score* (0 a 100) para cada trecho.
* **Renderização:** Corte vertical inteligente (detecção facial/centro de atenção 9:16) e queima de legendas animadas sincronizadas por palavra (*word-level timestamps*).
* **Exportação:** Depósito dos arquivos prontos no volume mapeado `data/clips_exportados/`.

#### 3.4 Módulo 2: Inteligência e Publicação (`robot2_publish.py`)
* **Sincronização de Jobs:** Consulta periódica (`GET /api/v1/jobs/{job_id}`). Ao atingir `status = "COMPLETED"`, os registros dos clips gerados são persistidos na tabela `clips`.
* **Filtro de Qualidade:** Apenas clips com `virality_score >= MIN_VIRALITY_SCORE` (configuração padrão: 70) entram na fila de publicação.
* **Camada de Metadados (Hermes / LLM):**
  * Consumo da transcrição do corte.
  * Geração de título persuasivo (máx. 60 caracteres com emoji frontal).
  * Geração de descrição curta contextualizada.
  * Geração de 3 a 5 tags estratégicas.
* **Publicador YouTube Shorts:**
  * Autenticação via OAuth2 com token de atualização persistido localmente (`youtube_token.json`).
  * Inserção com metadados e tag `#Shorts` forçada.
  * Tolerância a cota: em caso de erro `quotaExceeded` (403), marca o status como `FAILED_QUOTA` e posterga para o dia seguinte sem bloquear a esteira.
* **Publicador TikTok:**
  * Envio via Content Posting API oficial (ou bridge automatizada por cookies caso a conta não tenha chancela de desenvolvedor comercial).
* **Isolamento de Falha:** Falhas no YouTube não impedem o envio ao TikTok, e vice-versa.
* **Notificação:** Disparo imediato via Webhook (Discord ou Telegram) informando o link de publicação e score do corte.

#### 3.5 Módulo de Cadência e Buffer de Postagem (Anti-Spam)
* **Problema:** Quando um vídeo longo rende de 4 a 8 cortes qualificados, a publicação imediata de todos eles gera saturação de notificações e penalização algorítmica por comportamento de bot.
* **Mecanismo de Fila Espaçada:**
  * Os clips aprovados recebem um carimbo `scheduled_for` baseado em janelas pré-definidas (ex: 11:30, 15:00, 18:30 e 21:30).
  * Intervalo mínimo estrito entre publicações consecutivas no mesmo canal: **180 minutos (3 horas)**.
  * O worker de postagem processa apenas clips cujo `scheduled_for <= CURRENT_TIMESTAMP`.

#### 3.6 Módulo de Retenção e Limpeza de Disco (`services/cleanup.py`)
* **Problema:** O acúmulo contínuo de arquivos brutos de 20 a 180 minutos em resolução Full HD satura o disco rígido em poucos dias de operação autônoma.
* **Regras Determinísticas de Descarte:**
  * **Vídeo Longo Bruto (`data/videos_longos/`):** Excluído do disco assim que o job correspondente no Supoclip atinge o status `COMPLETED` e os clips derivados são registrados no SQLite. O registro na tabela `long_videos` é mantido para garantir idempotência eterna pelo hash SHA-256.
  * **Clips Exportados (`data/clips_exportados/`):** Excluídos do disco 48 horas após a confirmação de postagem em todas as redes configuradas (`youtube_status = 'POSTED'` E `tiktok_status = 'POSTED'`).
  * **Clips Reprovados (`virality_score < MIN_VIRALITY_SCORE`):** Excluídos imediatamente após o parsing do resultado do job.

---

### 4. Modelo de Dados (SQLite Schema)

O banco de dados `pipeline.db` opera como o cérebro de estado de toda a operação.

```sql
-- Tabela de Vídeos Longos (Ingestão)
CREATE TABLE IF NOT EXISTS long_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE NOT NULL,
    youtube_id TEXT,
    channel_name TEXT,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    supoclip_job_id TEXT,
    status TEXT CHECK(status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')) DEFAULT 'PENDING',
    is_deleted_from_disk INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Tabela de Cortes / Clips
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    long_video_id INTEGER NOT NULL,
    clip_uid TEXT UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    virality_score INTEGER NOT NULL,
    title TEXT,
    description TEXT,
    tags TEXT,
    scheduled_for TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    youtube_status TEXT CHECK(youtube_status IN ('PENDING', 'SCHEDULED', 'POSTED', 'FAILED', 'SKIPPED', 'FAILED_QUOTA')) DEFAULT 'PENDING',
    youtube_video_id TEXT,
    tiktok_status TEXT CHECK(tiktok_status IN ('PENDING', 'SCHEDULED', 'POSTED', 'FAILED', 'SKIPPED')) DEFAULT 'PENDING',
    tiktok_post_id TEXT,
    is_deleted_from_disk INTEGER DEFAULT 0,
    published_at TIMESTAMP,
    error_log TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (long_video_id) REFERENCES long_videos (id)
);

-- Tabela de Registro de Saúde / Heartbeat
CREATE TABLE IF NOT EXISTS system_heartbeats (
    service_name TEXT PRIMARY KEY,
    last_ping TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    extra_info TEXT
);

-- Índices de Alta Performance
CREATE INDEX IF NOT EXISTS idx_long_videos_hash ON long_videos(file_hash);
CREATE INDEX IF NOT EXISTS idx_long_videos_status ON long_videos(status);
CREATE INDEX IF NOT EXISTS idx_clips_filter ON clips(virality_score, youtube_status, tiktok_status);
CREATE INDEX IF NOT EXISTS idx_clips_schedule ON clips(scheduled_for, youtube_status, tiktok_status);
```

---

### 5. Guia de Implementação Passo a Passo

#### Fase 1: Preparação do Ambiente e Infraestrutura
1. **Estrutura de Pastas:**
   ```bash
   mkdir -p clip-automation/{data/videos_longos,data/clips_exportados,services,config}
   cd clip-automation
   python3 -m venv venv
   source venv/bin/activate
   ```
2. **Dependências do Sistema Operacional:**
   ```bash
   sudo apt-get update && sudo apt-get install -y ffmpeg jq sqlite3 curl
   ```
3. **Instalação do Supoclip via Docker:**
   Clone e inicialize o Supoclip conforme a documentação oficial, garantindo que o volume de saída do container aponte para `data/clips_exportados`:
   ```bash
   docker run -d --gpus all -p 8000:8000 \
     -v $(pwd)/data/clips_exportados:/app/output \
     --name supoclip fujiwarachoki/supoclip:latest
   ```

#### Fase 2: Configuração de Credenciais e Variáveis de Ambiente
1. Crie o arquivo `.env` na raiz do projeto:
   ```ini
   WATCH_DIR=./data/videos_longos
   OUTPUT_DIR=./data/clips_exportados
   DB_PATH=./data/pipeline.db
   SUPOCLIP_API_URL=http://localhost:8000

   MIN_VIRALITY_SCORE=70
   VPH_MINIMUM_THRESHOLD=5000
   POST_INTERVAL_MINUTES=180

   # Configurações do yt-dlp
   YTDLP_COOKIES_PATH=./config/cookies.txt

   OPENAI_API_KEY=sk-proj-...
   OPENAI_MODEL=gpt-4o-mini

   YOUTUBE_CLIENT_SECRETS=config/client_secrets.json
   YOUTUBE_TOKEN_PATH=config/youtube_token.json

   TIKTOK_ACCESS_TOKEN=act....
   TIKTOK_OPEN_ID=...

   DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
   ```
2. **Setup do OAuth2 do YouTube:**
   Execute o script one-off `services/setup_youtube_token.py` para autenticar seu canal no navegador e gerar o token offline resiliente (`config/youtube_token.json`).

#### Fase 3: Scripts de Automação
* Crie os scripts correspondentes às camadas descritas na arquitetura:
  * `radar_youtube.py`: Varredura, checagem de VPH e download seletivo com cookies.
  * `robot1_ingest.py`: Leitura de pasta, hash SHA-256 e postagem no Supoclip.
  * `robot2_publish.py`: Monitoramento do Supoclip, copywriting com LLM, buffer temporal e despacho social.
  * `services/cleanup.py`: Expurgo agendado de arquivos processados para proteção do volume de armazenamento.

#### Fase 4: Bateria de Testes Unitários e Integrados
Execute os testes sequenciais no terminal:
1. **Teste do Radar:** Execute uma checagem pontual em um canal de teste:
   ```bash
   python -c "from radar_youtube import run_radar_check; run_radar_check(dry_run=True)"
   ```
2. **Teste de Ingestão:** Mova um vídeo de teste curto (ex: 30 segundos) para `data/videos_longos/` e execute:
   ```bash
   python -c "from robot1_ingest import run_ingestor; run_ingestor()"
   ```
   Valide se o job foi criado via `sqlite3 data/pipeline.db "SELECT * FROM long_videos;"`.
3. **Teste do Publicador:** Quando o job finalizar no Supoclip:
   ```bash
   python -c "from robot2_publish import run_publisher; run_publisher()"
   ```
   Verifique o log de saída e a notificação no Discord/Telegram.
4. **Teste de Purge de Disco:**
   ```bash
   python -c "from services.cleanup import run_disk_cleanup; run_disk_cleanup()"
   ```

#### Fase 5: Execução Contínua via Systemd
Para garantir que a esteira continue funcionando mesmo após reinicializações do servidor ou falhas inesperadas, crie os serviços do sistema:

1. **Serviço do Robô 1 (Ingestão e Radar):** `/etc/systemd/system/clip-ingest.service`
   ```ini
   [Unit]
   Description=Automacao de Cortes - Radar e Ingestao
   After=network.target docker.service

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/clip-automation
   ExecStart=/root/clip-automation/venv/bin/python robot1_ingest.py
   Restart=always
   RestartSec=15

   [Install]
   WantedBy=multi-user.target
   ```
2. **Serviço do Robô 2 (Publicador e Buffer):** `/etc/systemd/system/clip-publish.service`
   ```ini
   [Unit]
   Description=Automacao de Cortes - Publicador e Social
   After=network.target

   [Service]
   Type=simple
   User=root
   WorkingDirectory=/root/clip-automation
   ExecStart=/root/clip-automation/venv/bin/python robot2_publish.py
   Restart=always
   RestartSec=30

   [Install]
   WantedBy=multi-user.target
   ```
3. Ative os serviços:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now clip-ingest clip-publish
   ```

#### Fase 6: Gestão de Sessão e Cookies do YouTube para `yt-dlp`
Para contornar telas de consentimento e bloqueios anti-bot do YouTube em servidores dedicados:
1. Instale no navegador do seu computador pessoal a extensão *Get cookies.txt LOCALLY*.
2. Acesse o YouTube logado em uma conta secundária dedicada.
3. Exporte os cookies para o arquivo `cookies.txt` e copie para o servidor em `clip-automation/config/cookies.txt`.
4. Configure o `yt-dlp` para carregar o arquivo com a flag `--cookies config/cookies.txt`.

---

### 6. Matriz de Riscos e Planos de Mitigação

| Risco Identificado | Impacto | Estratégia de Mitigação |
| :--- | :--- | :--- |
| **Esgotamento da cota diária do YouTube API** (10.000 unidades/dia; cada upload consome ~1.600). | Alto | O `robot2_publish.py` limita os uploads diários a no máximo 5 ou 6 vídeos por canal. Se a cota for atingida, marca como `FAILED_QUOTA` e reagenda automaticamente para o ciclo das 00:00 UTC. |
| **Download corrompido ou arquivo incompleto.** | Médio | Verificação de integridade via FFmpeg (`ffmpeg -v error -i video.mp4 -f null -`) antes de disparar o envio para o Supoclip. |
| **Bloqueio de IP por scraping no YouTube.** | Médio | Utilização exclusiva de feeds RSS abertos para monitoramento de canais (sem scraping em HTML). O `yt-dlp` é acionado unicamente para vídeos já confirmados como virais, utilizando `cookies.txt`. |
| **Travamento ou timeout do Supoclip em vídeos muito longos.** | Alto | Configuração de timeouts explicitados nos clients HTTP (timeout de requisição de 300s) e flag de retry automático até 3 tentativas no banco de dados. |
| **Expiração de Tokens OAuth (YouTube/TikTok).** | Médio | Implementação de renovação automática silenciosa (*silent refresh*) utilizando `refresh_token` gerenciado pela biblioteca oficial do Google. |
| **Esgotamento de espaço em disco (Crash de Servidor).** | Crítico | Módulo `services/cleanup.py` executa o expurgo imediato do vídeo bruto original após o processamento completo do Supoclip e purga clips após 48h de postados. |
| **Penalização algorítmica por spam de uploads.** | Alto | Motor de agendamento em buffer (Seção 3.5) obriga um espaçamento mínimo de 180 minutos entre postagens públicas. |
| **Alucinação ou falha de formatação na LLM.** | Médio | Validação estrita de schema JSON na saída da LLM com mecanismo de fallback determinístico (título padrão gerado via template) caso o parse falhe. |

---

### 7. Extensões Futuras (Backlog Técnico)
* **Postagem com Agendamento Inteligente (Buffer Mode):** Em vez de publicar imediatamente no instante do corte, enfileirar os clips distribuindo-os nos horários de maior audiência do canal (ex: 12h, 18h e 21h).
* **Módulo Enriquecedor de Contexto (Hermes + Agent-Reach):** Ingestão dos comentários mais curtidos do vídeo original para gerar títulos baseados nas reações orgânicas da audiência.
* **Multi-Channel & Multi-Account:** Suporte a múltiplos canais de nichos diferentes alimentando o mesmo banco de dados com chaveamento de credenciais sociais.
* **Ajuste Dinâmico de Legendas por Plataforma:** Modificação de fontes e cores nas legendas para atender à identidade visual específica de cada canal parceiro.

---

### 8. Especificação de Prompt Engineering para o Hermes / LLM

Para assegurar que o gerador de cópias funcione de modo determinístico e sem erros de sintaxe JSON, a chamada do Módulo 2 para o Hermes/LLM deve seguir rigorosamente a especificação abaixo:

#### 8.1 System Prompt
```text
Você é um estrategista de crescimento e especialista em retenção para YouTube Shorts e TikTok.
Sua missão é extrair o núcleo dramático, cômico ou informativo de uma transcrição e produzir metadados de altíssima conversão (CTR e retenção).

Diretrizes estritas:
1. O título DEVE ter entre 35 e 60 caracteres.
2. Inicie o título com exatamente 1 emoji contextual.
3. Não use clickbaits mentirosos; foque em quebra de expectativa ou curiosidade genuína.
4. A descrição deve ter no máximo 2 frases concisas e diretas.
5. Gere entre 3 e 5 hashtags relevantes no formato minúsculo e sem acentuação.
6. A saída DEVE ser estritamente um objeto JSON válido, sem texto explicativo antes ou depois.
```

#### 8.2 JSON Schema de Resposta
```json
{
  "type": "object",
  "properties": {
    "title": {
      "type": "string",
      "maxLength": 60
    },
    "description": {
      "type": "string",
      "maxLength": 200
    },
    "tags": {
      "type": "array",
      "items": { "type": "string" },
      "minItems": 3,
      "maxItems": 5
    }
  },
  "required": ["title", "description", "tags"],
  "additionalProperties": false
}
```

#### 8.3 Algoritmo de Fallback (Sem Falha de Esteira)
Se a chamada à LLM falhar por timeout, resposta corrompida ou limite de requisições:
1. O sistema faz 1 tentativa adicional após 5 segundos.
2. Se persistir a falha, aplica o template local determinístico:
   * **Título:** `🔥 Momento inacreditável do episódio #Shorts`
   * **Descrição:** `Confira este trecho imperdível. Inscreva-se no canal para acompanhar os melhores momentos diários!`
   * **Tags:** `["#shorts", "#cortes", "#viral", "#podcast"]`
3. A esteira prossegue normalmente sem interrupção.

---

### 9. Procedimento Operacional de Observabilidade e Dead Letter Queue (DLQ)

Para garantir operação 100% autônoma (*lights-out operation*), a esteira adota um padrão de Dead Letter Queue para itens defeituosos:

1. **Classificação de Falhas:**
   * **Falhas Transientes (Rede, Timeout de API, Supoclip ocupado):** Incrementa o contador `retry_count`. O item volta para status `PENDING` para reprocessamento em 10 minutos (máximo de 3 tentativas).
   * **Falhas Fatais (Arquivo ilegível, formato corrompido, Violação de Direitos):** Marca status como `FAILED`, registra o stacktrace em `error_log` e notifica imediatamente o operador via Webhook do Discord/Telegram com a tag `[ERRO CRÍTICO]`.
2. **Monitor de Integridade (Watchdog):**
   * A cada 5 minutos, cada worker grava um registro de timestamp na tabela `system_heartbeats`.
   * Caso o `last_ping` de qualquer módulo tenha mais de 15 minutos de atraso, o script de watchdog dispara alerta de processo travado ou silenciosamente morto.