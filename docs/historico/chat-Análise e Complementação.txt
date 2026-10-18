### USER
Analise e complemente se falta algo sem apagar o que ja esta escrito inclua o que falta ok

### ASSISTANT
Segue uma análise complementar do PRD, **sem apagar nada do que já está escrito**. A proposta abaixo é para ser anexada ao documento original como **“Complemento de PRD”**, adicionando seções, controles, schemas, riscos e critérios operacionais que ainda estão ausentes ou pouco especificados.

---

# Complemento do PRD — Pipeline Autônomo de Cortes

## 1. Parecer geral

O PRD atual já cobre muito bem o núcleo do sistema:

- descoberta de vídeos por hype/VPH;
- ingestão com idempotência por hash;
- processamento via Supoclip;
- publicação em múltiplas plataformas;
- buffer anti-spam;
- limpeza de disco;
- DLQ e heartbeat.

Porém, para uma operação realmente autônoma, segura e auditável, ainda faltam alguns blocos importantes:

1. **Fonte explícita de métricas de views para cálculo de VPH**  
   O RSS mostra vídeos novos, mas não necessariamente estatísticas confiáveis de views. É preciso definir se o VPH virá da YouTube Data API, yt-dlp ou cache de métricas.

2. **Compliance, direitos autorais e LGPD**  
   Falta definir regras claras para uso de conteúdo de terceiros, remoção por copyright, retenção de transcrições e tratamento de dados pessoais.

3. **Segurança de credenciais**  
   O PRD menciona `cookies.txt`, tokens OAuth e tokens TikTok, mas falta especificar permissões de arquivo, rotação, expiração, vault, menor privilégio e proteção contra vazamento em logs.

4. **Máquina de estados mais robusta**  
   Os statuses atuais são bons, mas insuficientes para casos como upload em andamento, reconciliação após crash, bloqueio de política, moderação, expiração de token e falha de quota.

5. **Idempotência de publicação em casos de crash**  
   O sistema precisa garantir que um clip não seja publicado duas vezes se o processo morrer exatamente depois do upload, mas antes de salvar o ID externo.

6. **Modelo de dados para múltiplos canais/contas**  
   O PRD fala em multi-channel no backlog, mas o schema atual ainda não contempla canais de origem, contas de destino, credenciais por perfil, quota por conta e janelas por conta.

7. **Validação de mídia**  
   Falta especificar validação de container, codec, duração, aspect ratio, tamanho, áudio, legenda e integridade via ffprobe/ffmpeg.

8. **Observabilidade mais detalhada**  
   Heartbeat é bom, mas faltam métricas de negócio, logs estruturados, alertas por severidade, rastreamento de falhas, dashboard e SLOs.

9. **Backup, restore e disaster recovery**  
   SQLite é o cérebro do sistema. Falta definir backup, WAL, migrações, retenção, teste de restore e procedimento em caso de perda do servidor.

10. **Testes e critérios de aceite**  
   A Fase 4 traz testes básicos, mas faltam testes de regressão, simulação de quota, token expirado, arquivo corrompido, duplicidade, crash de processo e fallback de LLM.

11. **Runbooks operacionais**  
   Para operação lights-out, é preciso documentar o que fazer quando cookie expirar, quota estourar, disco encher, Supoclip travar, TikTok falhar ou ocorrer alerta crítico.

12. **Proteção contra prompt injection**  
   Como a transcrição será enviada para LLM, é preciso tratar esse texto como entrada não confiável.

13. **Controle de custos**  
   Falta limitar gastos com LLM, YouTube API, downloads, GPU e armazenamento.

14. **Agendamento com timezone, DST e expiração de hype**  
   As janelas de postagem existem, mas é preciso definir fuso horário, horário de reset de quota, expiração de clips antigos e priorização por score.

---

# 2. Novas seções recomendadas para incluir no PRD

Abaixo seguem seções complementares. Elas não substituem o texto existente; devem ser adicionadas como aditivos.

---

## 10. Requisitos Não Funcionais e Operacionais

### 10.1 Disponibilidade

- O sistema deve operar continuamente, com reinicialização automática dos serviços via `systemd`.
- Falhas isoladas de uma plataforma não podem parar toda a esteira.
- Falha no YouTube não deve impedir publicação no TikTok.
- Falha no TikTok não deve impedir publicação no YouTube.
- Falha na LLM não deve interromper a publicação; deve haver fallback determinístico.
- Falha no Supoclip deve gerar retry limitado e, após o limite, envio para DLQ.

### 10.2 Determinismo e idempotência

- Nenhuma ação externa com efeito colateral deve ocorrer sem registro prévio no banco.
- Todo vídeo longo deve ser identificado por:
  - `file_hash`;
  - `youtube_id`, quando conhecido.
- Todo clip deve possuir identificador único e, idealmente, hash próprio.
- Toda publicação deve possuir `idempotency_key` única por combinação:
  - clip;
  - plataforma;
  - conta de publicação.
- Reprocessamentos não podem gerar duplicidade de ingestão, corte ou publicação.

### 10.3 Desempenho e capacidade

- A esteira deve respeitar limites máximos configuráveis:
  - máximo de downloads por ciclo;
  - máximo de downloads por dia;
  - máximo de jobs simultâneos no Supoclip;
  - máximo de uploads por dia por conta;
  - máximo de chamadas LLM por hora/dia.
- O uso de GPU deve ter limite explícito para evitar estouro de memória.
- O uso de disco deve ser monitorado continuamente.

### 10.4 Escalabilidade

- A arquitetura inicial com SQLite é adequada para MVP.
- Caso haja múltiplos workers concorrentes ou volume elevado, deve-se considerar migração para:
  - PostgreSQL;
  - fila dedicada, como Redis Queue, BullMQ, RabbitMQ ou SQS.
- O design atual deve permitir essa evolução sem reescrever os módulos principais.

### 10.5 Segurança

- Credenciais não devem aparecer em logs.
- Tokens e cookies devem ter permissão restrita no sistema de arquivos.
- O processo deve preferencialmente rodar com usuário dedicado, não root.
- Entradas externas, incluindo transcrições, devem ser tratadas como não confiáveis.

### 10.6 Privacidade

- Transcrições podem conter dados pessoais.
- O sistema deve minimizar retenção de dados sensíveis.
- Logs não devem conter transcrições completas, salvo modo debug explícito.
- Deve existir política de retenção para:
  - logs;
  - transcrições;
  - respostas de LLM;
  - metadados de publicação.

### 10.7 Observabilidade

- Todos os serviços devem gerar logs estruturados.
- Toda operação relevante deve conter IDs de correlação:
  - `video_id`;
  - `long_video_id`;
  - `clip_id`;
  - `job_id`;
  - `publication_id`.
- O sistema deve expor métricas ou registrar eventos auditáveis para:
  - radar;
  - ingestão;
  - Supoclip;
  - LLM;
  - publicação;
  - limpeza;
  - DLQ.

### 10.8 Custos

- Devem existir limites configuráveis para:
  - consumo de API do YouTube;
  - consumo de LLM;
  - downloads por dia;
  - uploads por dia;
  - uso de disco;
  - uso de GPU.
- O sistema deve alertar antes de atingir limites críticos.

---

## 11. Conformidade, Direitos Autorais e Privacidade

### 11.1 Elegibilidade de conteúdo

Somente devem ser processados vídeos que cumpram ao menos uma das condições:

- pertencem a canal próprio;
- possuem licença explícita de reutilização;
- possuem autorização contratual para cortes;
- estão dentro de uma política aprovada de fair use, se aplicável.

Recomenda-se criar um campo de controle por canal monitorado:

```text
license_mode:
  - owned
  - licensed
  - authorized
  - third_party_review_required
  - blocked
```

Canais com `third_party_review_required` não devem publicar automaticamente sem aprovação.

### 11.2 Direitos autorais e takedown

O sistema deve possuir procedimento para tratamento de remoção:

1. Recebimento de solicitação de remoção.
2. Identificação do vídeo longo original.
3. Identificação dos clips derivados.
4. Identificação das publicações no YouTube/TikTok.
5. Remoção ou despublicação manual/automática quando possível.
6. Registro de auditoria.
7. Bloqueio futuro do mesmo material por hash ou `youtube_id`.

Recomenda-se manter uma tabela de bloqueio:

```text
blocked_assets:
  id
  asset_type: long_video | clip | source_video
  hash
  youtube_id
  reason
  requested_by
  created_at
```

### 11.3 LGPD e dados pessoais

Como as transcrições podem conter dados pessoais:

- reter transcrições apenas pelo tempo necessário;
- evitar logs com transcrição completa;
- mascarar trechos sensíveis quando possível;
- restringir acesso ao banco e aos arquivos;
- permitir exclusão de registros sob solicitação legal, quando aplicável.

### 11.4 Políticas das plataformas

- Respeitar os Termos de Serviço do YouTube.
- Respeitar os Termos da TikTok API.
- Não publicar em comportamento de spam.
- Não manipular métricas.
- Não usar automação para burlar revisões de plataforma.
- Publicações devem seguir as regras de conteúdo de cada rede.

### 11.5 Conteúdo sensível

Recomenda-se adicionar moderação automática antes da publicação:

- discurso de ódio;
- violência gráfica;
- conteúdo sexual;
- desinformação crítica;
- saúde/finanças sensíveis;
- temas proibidos pelas plataformas.

Clips reprovados devem receber status:

```text
MODERATION_BLOCKED
```

e não devem ser publicados.

---

## 12. Segurança e Gestão de Credenciais

### 12.1 Segredos

O arquivo `.env` deve:

- ter permissão restrita, por exemplo `600`;
- não ser commitado;
- não ser exibido em logs;
- não ser enviado em notificações.

Em produção, recomenda-se usar:

- variáveis de ambiente com permissão mínima;
- cofre de segredos, como Vault, AWS Secrets Manager, Doppler, SOPS ou similar;
- rotação periódica de tokens.

### 12.2 Cookies do YouTube

O arquivo `cookies.txt` deve ser tratado como credencial sensível.

Requisitos:

- usar conta secundária dedicada;
- monitorar expiração ou invalidação;
- testar periodicamente se o cookie ainda permite acesso;
- alertar quando houver falha de autenticação;
- nunca logar o conteúdo do arquivo.

Adicionar verificação de saúde:

```text
cookie_status:
  - valid
  - expired
  - invalid
  - unknown
```

### 12.3 OAuth YouTube

- Usar escopo mínimo necessário para upload.
- Armazenar `refresh_token` com proteção.
- Implementar silent refresh.
- Registrar falhas de token como alerta crítico.
- Não expor token em logs ou webhooks.

### 12.4 TikTok

- Preferir Content Posting API oficial.
- Se usar bridge por cookies, marcar explicitamente como modo experimental.
- Exigir aprovação operacional para uso desse modo.
- Monitorar sessões expiradas.
- Registrar falhas de autorização como alerta.

### 12.5 LLM

- Não enviar segredos para a LLM.
- Tratar transcrição como input não confiável.
- Validar saída com schema rígido.
- Limitar tamanho do prompt.
- Aplicar timeout.
- Registrar apenas metadados da resposta, se possível.
- Proteger contra prompt injection presente na transcrição.

### 12.6 Arquivos

- Validar nomes de arquivo para evitar path traversal.
- Usar diretórios dedicados para entrada e saída.
- Não executar arquivos baixados.
- Validar mídia com `ffprobe` antes do processamento.
- Remover arquivos temporários após processamento.

---

## 13. Máquina de Estados e Regras de Transição

O PRD atual possui statuses simples. Recomenda-se adicionar estados mais explícritos, sem remover os existentes.

### 13.1 Estados sugeridos para candidatos detectados pelo Radar

```text
NEW
MONITORING
QUALIFIED
REJECTED
DOWNLOADED
ERROR
```

Transições:

```text
NEW -> MONITORING
MONITORING -> QUALIFIED
MONITORING -> REJECTED
QUALIFIED -> DOWNLOADED
QUALIFIED -> ERROR
DOWNLOADED -> vinculado a long_videos
```

### 13.2 Estados sugeridos para vídeo longo

Além dos atuais `PENDING`, `PROCESSING`, `COMPLETED` e `FAILED`, recomenda-se controle complementar em tabelas auxiliares:

```text
DISCOVERED
DOWNLOADING
VALIDATING
READY_FOR_INGEST
SUBMITTED_TO_SUPOCLIP
SUPOCLIP_PROCESSING
COMPLETED
FAILED
CLEANED
```

### 13.3 Estados sugeridos para clip

```text
CREATED
SCORED
METADATA_GENERATED
APPROVED
REJECTED_LOW_SCORE
MODERATION_BLOCKED
SCHEDULED
UPLOADING
POSTED
FAILED
SKIPPED
EXPIRED
```

### 13.4 Estados sugeridos para publicação por plataforma

```text
PENDING
SCHEDULED
UPLOADING
POSTED
FAILED
FAILED_QUOTA
POLICY_BLOCKED
RECONCILING
SKIPPED
```

### 13.5 Regras de transição

- Um clip só entra em `UPLOADING` se houver registro de publicação criado.
- Um clip só entra em `POSTED` após confirmação externa com ID da plataforma.
- Se o processo morrer durante upload, a publicação deve entrar em `RECONCILING`.
- Publicações em `RECONCILING` devem ser verificadas antes de novo envio.
- Falha transitória incrementa `retry_count`.
- Falha fatal vai para DLQ.

---

## 14. Detalhamento adicional do Módulo 0 — Radar

O PRD define VPH, mas falta especificar a fonte de métricas.

### 14.1 Fonte de estatísticas

Recomenda-se usar a YouTube Data API para obter:

- `publishedAt`;
- `duration`;
- `viewCount`;
- `likeCount`;
- `commentCount`.

Endpoint sugerido:

```text
GET https://www.googleapis.com/youtube/v3/videos
part=snippet,contentDetails,statistics
id=VIDEO_ID
```

### 14.2 Cache de métricas

Para reduzir quota:

- armazenar métricas em `radar_candidates`;
- atualizar a cada 10–20 minutos;
- evitar consultar repetidamente o mesmo vídeo sem variação relevante.

### 14.3 Regras temporais

Adicionar:

```text
RADAR_MIN_AGE_HOURS=2
RADAR_MAX_AGE_HOURS=48
RADAR_IGNORE_AFTER_DAYS=7
```

Regras:

- vídeos com menos de `RADAR_MIN_AGE_HOURS` são ignorados temporariamente;
- vídeos acima de `RADAR_MAX_AGE_HOURS` só entram se ainda houver aceleração excepcional;
- vídeos muito antigos não devem entrar no pipeline de hype.

### 14.4 Métricas derivadas

Além do VPH simples, recomenda-se calcular:

```text
VPH = view_count / hours_since_publish
median_factor = VPH / channel_median_vph
```

O canal pode ter thresholds próprios:

```text
vph_absolute_threshold
vph_multiplier_threshold
```

### 14.5 Anti-duplicidade no radar

Criar controle por `youtube_id`:

- se o vídeo já foi qualificado, não qualificar novamente;
- se já foi baixado, não baixar novamente;
- se foi rejeitado por duração ou VPH, registrar motivo.

---

## 15. Detalhamento adicional do Supoclip

O Supoclip está bem posicionado no fluxo, mas faltam contratos operacionais.

### 15.1 Contrato de saída esperado

Para cada job concluído, o Supoclip deve retornar ou gravar um manifesto contendo:

```json
{
  "job_id": "...",
  "source_video_id": "...",
  "status": "COMPLETED",
  "clips": [
    {
      "clip_uid": "...",
      "file_path": "...",
      "start_seconds": 123.4,
      "end_seconds": 178.9,
      "duration_seconds": 55.5,
      "virality_score": 82,
      "transcription_path": "...",
      "width": 1080,
      "height": 1920,
      "fps": 30,
      "subtitle_mode": "burned",
      "crop_mode": "face_center"
    }
  ]
}
```

### 15.2 Validação de saída

O publicador deve validar:

- existência do arquivo;
- extensão `.mp4`;
- tamanho maior que zero;
- duração dentro do limite;
- resolução/aspect ratio compatíveis;
- score presente;
- `clip_uid` único.

### 15.3 Timeout e retry

Configurar:

```text
SUPOCLIP_TIMEOUT_SECONDS=300
SUPOCLIP_MAX_RETRIES=3
SUPOCLIP_RETRY_BACKOFF_SECONDS=60
```

Se o job ultrapassar tempo máximo, marcar:

```text
TIMEOUT
```

e enviar para DLQ após retries.

### 15.4 Limite de clips por vídeo

Para evitar excesso de cortes:

```text
MAX_CLIPS_PER_LONG_VIDEO=8
MIN_CLIP_DURATION_SECONDS=20
MAX_CLIP_DURATION_SECONDS=180
```

Esses valores devem ser configuráveis.

### 15.5 Saúde do Supoclip

Adicionar checagem de:

- container ativo;
- API respondendo;
- GPU disponível;
- disco de saída com espaço;
- jobs parados há tempo excessivo.

---

## 16. Detalhamento adicional do Módulo 2 — Publicação

### 16.1 Pré-validação antes de publicar

Antes de enviar um clip, validar:

- arquivo existe;
- hash do clip é conhecido;
- duração aceitável;
- proporção 9:16 ou compatível;
- tamanho dentro do limite da plataforma;
- metadata gerado;
- score mínimo atendido;
- moderação aprovada;
- não existe publicação anterior para a mesma plataforma/conta;
- quota disponível.

### 16.2 Chave de idempotência

Toda publicação deve possuir:

```text
idempotency_key = sha256(clip_uid + platform + publishing_account_id)
```

Ou, se quiser incluir origem:

```text
idempotency_key = sha256(youtube_id + start_seconds + end_seconds + platform + publishing_account_id)
```

Essa chave deve ser única no banco.

### 16.3 Upload com lease/lock

Para evitar concorrência:

1. Worker tenta reservar publicação:

```sql
UPDATE publications
SET status = 'UPLOADING',
    lease_owner = ?,
    lease_expires_at = datetime('now', '+10 minutes')
WHERE id = ?
  AND status = 'SCHEDULED'
  AND (lease_expires_at IS NULL OR lease_expires_at < datetime('now'));
```

2. Se atualizar 1 linha, prossegue.
3. Se não atualizar, outro worker já assumiu.

### 16.4 Reconciliação após crash

Se uma publicação ficar em `UPLOADING` após expiração do lease:

1. marcar `RECONCILING`;
2. tentar descobrir se o vídeo já foi enviado;
3. no YouTube, tentar listar uploads recentes e procurar referência interna;
4. no TikTok, usar endpoint de status se disponível;
5. se confirmado, marcar `POSTED`;
6. se não confirmado, retornar para `PENDING` com limite de retry;
7. se ambíguo, alertar e enviar para DLQ.

### 16.5 Referência interna na publicação

Para ajudar reconciliação, incluir uma referência discreta nos metadados:

```text
ref: {clip_uid}
```

Exemplo no final da descrição:

```text
#Shorts ref:abc123def
```

Isso não deve substituir título/descrição principais.

---

## 17. Publicação no YouTube Shorts — complementos

### 17.1 Requisitos técnicos

Validar:

- container MP4;
- vídeo vertical ou próximo de 9:16;
- duração máxima configurável;
- codec recomendado H.264;
- áudio AAC;
- tamanho máximo suportado pela API;
- tag `#Shorts` presente.

### 17.2 Metadados

Enviar:

- título;
- descrição;
- tags;
- categoria, se aplicável;
- privacidade padrão: `public`;
- `madeForKids` explicitamente definido conforme política.

### 17.3 Quota

Cada upload consome quota elevada. Portanto:

- reservar quota antes do upload;
- registrar consumo em `quota_usage`;
- bloquear novos uploads quando atingir limite diário;
- em `quotaExceeded`, marcar `FAILED_QUOTA`;
- reagendar para o próximo ciclo de quota.

### 17.4 Tratamento de erros

| Erro | Ação |
|---|---|
| 401 token inválido | renovar token e retry |
| 403 quotaExceeded | marcar `FAILED_QUOTA` e reagendar |
| 403 acesso negado | alerta crítico, DLQ |
| 400 metadata inválida | falha fatal ou ajuste automático |
| 5xx API | retry com backoff |
| timeout | retry limitado |

---

## 18. Publicação no TikTok — complementos

### 18.1 Fluxo oficial

Quando usar Content Posting API:

1. inicializar upload;
2. enviar vídeo por upload URL;
3. publicar ou verificar status;
4. consultar status até confirmação final.

### 18.2 Estados TikTok

Além de `POSTED`, considerar:

```text
PROCESSING
PUBLISH_IN_PROGRESS
FAILED_POLICY
RATE_LIMITED
```

### 18.3 Limitações

Validar:

- duração máxima;
- tamanho máximo;
- formato aceito;
- taxa de requisições;
- permissões da conta;
- aprovação de escopo do app.

### 18.4 Modo cookie bridge

Se usado:

- deve ser declarado como não oficial/experimental;
- deve exigir flag explícita:

```text
TIKTOK_MODE=official
# ou
TIKTOK_MODE=cookie_bridge
```

- deve alertar sobre risco;
- deve monitorar sessão expirada;
- deve permitir pausa imediata.

---

## 19. Agendamento, buffer e expiração de hype

### 19.1 Timezone

Toda janela deve usar timezone explícito:

```text
TIMEZONE=America/Sao_Paulo
```

O sistema deve lidar com DST quando aplicável.

### 19.2 Janelas por conta

Cada conta de publicação pode ter janelas próprias:

```json
["11:30", "15:00", "18:30", "21:30"]
```

### 19.3 Priorização

Ao escolher quais clips publicar:

1. priorizar maior `virality_score`;
2. em empate, priorizar clip mais recente;
3. respeitar intervalo mínimo por conta;
4. respeitar máximo diário por plataforma;
5. aplicar jitter opcional de 0 a 10 minutos para evitar pico artificial.

### 19.4 Expiração

Clips muito antigos podem perder valor. Adicionar:

```text
MAX_CLIP_AGE_DAYS=7
```

Regra:

- se o clip não foi publicado dentro do prazo, marcar `EXPIRED`;
- não publicar automaticamente após expiração;
- enviar para limpeza ou revisão.

---

## 20. Limpeza e proteção de disco — complementos

### 20.1 Limpeza normal

Mantém-se a regra atual:

- vídeo longo bruto removido após job `COMPLETED` e clips registrados;
- clips publicados removidos 48 horas após confirmação em todas as plataformas obrigatórias;
- clips reprovados removidos imediatamente.

### 20.2 Limpeza emergencial

Se o disco ultrapassar limite crítico, executar limpeza emergencial:

```text
DISK_ALERT_THRESHOLD=75
DISK_HARD_THRESHOLD=85
```

Ordem sugerida:

1. apagar temporários;
2. apagar clips reprovados;
3. apagar clips já postados com mais tempo;
4. apagar vídeos longos já processados;
5. apagar logs antigos;
6. alertar operador se ainda acima do limite.

### 20.3 Registro de limpeza

Toda limpeza deve registrar:

- data;
- arquivos removidos;
- bytes liberados;
- uso de disco antes/depois;
- erros.

### 20.4 Preservação de idempotência

Mesmo removendo arquivos, manter no banco:

- hash do vídeo longo;
- `youtube_id`;
- registros de clips;
- IDs externos publicados;
- histórico de falhas.

---

## 21. Modelo de dados complementar

As tabelas abaixo podem ser adicionadas sem remover as existentes.

### 21.1 Tabela de migração

```sql
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.2 Canais monitorados

```sql
CREATE TABLE IF NOT EXISTS source_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_channel_id TEXT UNIQUE NOT NULL,
    name TEXT,
    rss_url TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    min_duration_minutes INTEGER DEFAULT 20,
    vph_absolute_threshold INTEGER DEFAULT 5000,
    vph_multiplier_threshold REAL DEFAULT 2.0,
    median_vph REAL,
    license_mode TEXT DEFAULT 'owned',
    max_videos_per_cycle INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.3 Candidatos detectados pelo radar

```sql
CREATE TABLE IF NOT EXISTS radar_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel_id INTEGER NOT NULL REFERENCES source_channels(id),
    youtube_id TEXT UNIQUE NOT NULL,
    title TEXT,
    published_at TIMESTAMP,
    duration_seconds INTEGER,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    vph REAL,
    median_factor REAL,
    status TEXT CHECK(status IN (
        'NEW',
        'MONITORING',
        'QUALIFIED',
        'REJECTED',
        'DOWNLOADED',
        'ERROR'
    )) DEFAULT 'NEW',
    reject_reason TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP,
    qualified_at TIMESTAMP,
    downloaded_at TIMESTAMP
);
```

### 21.4 Contas de publicação

```sql
CREATE TABLE IF NOT EXISTS publishing_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT CHECK(platform IN ('youtube', 'tiktok')) NOT NULL,
    profile_name TEXT UNIQUE NOT NULL,
    external_channel_id TEXT,
    display_name TEXT,
    credentials_ref TEXT NOT NULL,
    timezone TEXT DEFAULT 'America/Sao_Paulo',
    posting_windows TEXT DEFAULT '["11:30","15:00","18:30","21:30"]',
    min_interval_minutes INTEGER DEFAULT 180,
    max_daily_posts INTEGER DEFAULT 6,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.5 Jobs do Supoclip

```sql
CREATE TABLE IF NOT EXISTS supoclip_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    long_video_id INTEGER NOT NULL REFERENCES long_videos(id),
    supoclip_job_id TEXT UNIQUE,
    status TEXT CHECK(status IN (
        'PENDING',
        'SUBMITTED',
        'PROCESSING',
        'COMPLETED',
        'FAILED',
        'TIMEOUT',
        'CANCELLED'
    )) DEFAULT 'PENDING',
    attempt INTEGER DEFAULT 1,
    request_hash TEXT,
    submitted_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    failed_at TIMESTAMP,
    error_code TEXT,
    error_message TEXT,
    response_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.6 Publicações por plataforma

```sql
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    publishing_account_id INTEGER NOT NULL REFERENCES publishing_accounts(id),
    platform TEXT CHECK(platform IN ('youtube', 'tiktok')) NOT NULL,
    status TEXT CHECK(status IN (
        'PENDING',
        'SCHEDULED',
        'UPLOADING',
        'POSTED',
        'FAILED',
        'FAILED_QUOTA',
        'SKIPPED',
        'POLICY_BLOCKED',
        'RECONCILING'
    )) DEFAULT 'PENDING',
    scheduled_for TIMESTAMP,
    published_at TIMESTAMP,
    external_id TEXT,
    idempotency_key TEXT UNIQUE NOT NULL,
    retry_count INTEGER DEFAULT 0,
    lease_owner TEXT,
    lease_expires_at TIMESTAMP,
    error_code TEXT,
    error_message TEXT,
    response_json TEXT,
    quota_date TEXT,
    quota_units INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_publications_clip_account_platform
ON publications(clip_id, publishing_account_id, platform);

CREATE INDEX IF NOT EXISTS idx_publications_schedule
ON publications(status, scheduled_for);
```

### 21.7 Controle de quota diária

```sql
CREATE TABLE IF NOT EXISTS quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publishing_account_id INTEGER NOT NULL REFERENCES publishing_accounts(id),
    platform TEXT NOT NULL,
    quota_date TEXT NOT NULL,
    units_used INTEGER DEFAULT 0,
    uploads_used INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(publishing_account_id, platform, quota_date)
);
```

### 21.8 Auditoria

```sql
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT DEFAULT 'system',
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.9 Alertas

```sql
CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    severity TEXT CHECK(severity IN ('INFO', 'WARNING', 'CRITICAL')) NOT NULL,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    status TEXT CHECK(status IN ('OPEN', 'ACK', 'RESOLVED')) DEFAULT 'OPEN',
    fingerprint TEXT UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    resolved_at TIMESTAMP
);
```

### 21.10 Execuções de limpeza

```sql
CREATE TABLE IF NOT EXISTS cleanup_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status TEXT CHECK(status IN ('RUNNING', 'COMPLETED', 'FAILED')) DEFAULT 'RUNNING',
    deleted_long_videos INTEGER DEFAULT 0,
    deleted_clips INTEGER DEFAULT 0,
    freed_bytes INTEGER DEFAULT 0,
    disk_usage_percent REAL,
    error_message TEXT
);
```

### 21.11 Gerações de LLM

```sql
CREATE TABLE IF NOT EXISTS llm_generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id),
    model TEXT,
    prompt_version TEXT,
    status TEXT CHECK(status IN ('SUCCESS', 'FALLBACK', 'FAILED')) DEFAULT 'SUCCESS',
    latency_ms INTEGER,
    raw_response TEXT,
    parsed_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 21.12 Bloqueio de conteúdo

```sql
CREATE TABLE IF NOT EXISTS blocked_assets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_type TEXT CHECK(asset_type IN ('long_video', 'clip', 'source_video')) NOT NULL,
    file_hash TEXT,
    youtube_id TEXT,
    clip_uid TEXT,
    reason TEXT,
    requested_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 22. Alterações aditivas sugeridas nas tabelas existentes

Estas alterações não apagam campos existentes.

### 22.1 Em `long_videos`

```sql
ALTER TABLE long_videos ADD COLUMN source_channel_id INTEGER REFERENCES source_channels(id);
ALTER TABLE long_videos ADD COLUMN youtube_url TEXT;
ALTER TABLE long_videos ADD COLUMN duration_seconds INTEGER;
ALTER TABLE long_videos ADD COLUMN file_size_bytes INTEGER;
ALTER TABLE long_videos ADD COLUMN media_valid INTEGER DEFAULT 0;
ALTER TABLE long_videos ADD COLUMN downloaded_at TIMESTAMP;
ALTER TABLE long_videos ADD COLUMN completed_at TIMESTAMP;
```

### 22.2 Em `clips`

```sql
ALTER TABLE clips ADD COLUMN start_seconds REAL;
ALTER TABLE clips ADD COLUMN end_seconds REAL;
ALTER TABLE clips ADD COLUMN duration_seconds REAL;
ALTER TABLE clips ADD COLUMN file_hash TEXT;
ALTER TABLE clips ADD COLUMN width INTEGER;
ALTER TABLE clips ADD COLUMN height INTEGER;
ALTER TABLE clips ADD COLUMN fps REAL;
ALTER TABLE clips ADD COLUMN transcription_path TEXT;
ALTER TABLE clips ADD COLUMN metadata_json TEXT;
ALTER TABLE clips ADD COLUMN moderation_status TEXT DEFAULT 'PENDING';
ALTER TABLE clips ADD COLUMN copyright_status TEXT DEFAULT 'PENDING';
ALTER TABLE clips ADD COLUMN llm_fallback_used INTEGER DEFAULT 0;
```

### 22.3 Índices úteis

```sql
CREATE UNIQUE INDEX IF NOT EXISTS idx_clips_file_hash
ON clips(file_hash);

CREATE INDEX IF NOT EXISTS idx_clips_moderation
ON clips(moderation_status, copyright_status);

CREATE UNIQUE INDEX IF NOT EXISTS idx_long_videos_youtube_id
ON long_videos(youtube_id)
WHERE youtube_id IS NOT NULL;
```

Observação: os campos `youtube_status` e `tiktok_status` da tabela `clips` podem continuar existindo por compatibilidade, mas a tabela `publications` deve ser a fonte de verdade para publicações por conta/plataforma.

---

## 23. Variáveis de ambiente adicionais

Adicionar ao `.env`, sem remover as existentes:

```text
# Radar
RADAR_INTERVAL_MINUTES=15
RADAR_MIN_AGE_HOURS=2
RADAR_MAX_AGE_HOURS=48
RADAR_IGNORE_AFTER_DAYS=7
MAX_DOWNLOADS_PER_CYCLE=3
MAX_DAILY_DOWNLOADS=12

# Métricas
YOUTUBE_DATA_API_MAX_QUOTA_UNITS_PER_DAY=9000

# Mídia
MEDIA_MIN_HEIGHT=1080
MEDIA_ASPECT=9:16
MAX_CLIP_DURATION_SECONDS=180
MIN_CLIP_DURATION_SECONDS=20
MAX_CLIPS_PER_LONG_VIDEO=8

# Disco
DISK_ALERT_THRESHOLD=75
DISK_HARD_THRESHOLD=85
EMERGENCY_CLEANUP_ENABLED=true

# Logs
LOG_LEVEL=INFO
LOG_DIR=./logs
LOG_RETENTION_DAYS=30

# Timezone
TIMEZONE=America/Sao_Paulo

# TikTok
TIKTOK_MODE=official

# Moderação
MODERATION_ENABLED=true

# LLM
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RETRIES=1
LLM_TEMPERATURE=0
LLM_MAX_TOKENS=512
LLM_DAILY_LIMIT=200
```

---

## 24. Observabilidade, logs e alertas

### 24.1 Logs estruturados

Todos os logs devem ser, preferencialmente, JSON:

```json
{
  "timestamp": "2026-06-11T12:00:00Z",
  "level": "INFO",
  "service": "robot2_publish",
  "event": "clip_published",
  "clip_id": 123,
  "platform": "youtube",
  "publication_id": 456,
  "external_id": "abcd1234",
  "trace_id": "uuid"
}
```

### 24.2 Campos obrigatórios

Sempre que possível, logar:

- `service`;
- `event`;
- `entity_type`;
- `entity_id`;
- `status`;
- `error_code`;
- `duration_ms`;
- `trace_id`.

### 24.3 Métricas mínimas

#### Radar

- feeds verificados;
- novos candidatos;
- candidatos qualificados;
- candidatos rejeitados;
- downloads iniciados;
- downloads concluídos;
- falhas de download.

#### Ingestão

- arquivos detectados;
- arquivos ignorados por hash duplicado;
- arquivos inválidos;
- jobs enviados ao Supoclip;
- falhas de envio.

#### Supoclip

- jobs submetidos;
- jobs em processamento;
- jobs concluídos;
- jobs com timeout;
- duração média de processamento;
- score médio dos clips.

#### Publicação

- clips aprovados;
- clips reprovados por score;
- clips bloqueados por moderação;
- uploads iniciados;
- uploads concluídos;
- falhas por plataforma;
- quota consumida;
- fallback de LLM.

#### Cleanup

- bytes liberados;
- uso de disco;
- arquivos removidos;
- falhas de remoção.

### 24.4 Alertas recomendados

| Alerta | Severidade | Ação |
|---|---:|---|
| Heartbeat ausente > 15 min | CRITICAL | reiniciar/investigar worker |
| Disco > 75% | WARNING | cleanup normal |
| Disco > 85% | CRITICAL | cleanup emergencial |
| Cookie inválido | CRITICAL | pausar radar/download |
| Token OAuth expirado | CRITICAL | renovar token |
| Quota YouTube próxima do limite | WARNING | reduzir uploads |
| Quota YouTube estourada | CRITICAL | reagendar para próximo dia |
| Supoclip sem resposta | CRITICAL | retry/DLQ |
| Falha de LLM acima de 20% | WARNING | verificar provedor |
| Clip parado em UPLOADING | CRITICAL | reconciliação |
| Publicação com retry > 3 | CRITICAL | DLQ |
| Falha de moderação | WARNING/CRITICAL | bloquear publicação |

### 24.5 SLOs sugeridos

- Pipeline latency p95 < 45 minutos quando GPU disponível.
- Taxa de duplicidade: 0%.
- Taxa de sucesso de publicação > 95%, descontando falhas externas temporárias.
- Uso de disco médio < 80%.
- Nenhum worker sem heartbeat por mais de 15 minutos.

---

## 25. Testes adicionais recomendados

Além dos testes já previstos, incluir:

### 25.1 Testes unitários

- cálculo de VPH;
- cálculo de fator sobre mediana;
- geração de chave de idempotência;
- parser de resposta LLM;
- fallback de LLM;
- seleção de janela de postagem;
- cálculo de intervalo mínimo;
- validação de duração de clip;
- validação de aspect ratio;
- cálculo de quota diária.

### 25.2 Testes de integração

- ingestão duas vezes do mesmo arquivo não cria duplicata;
- radar não baixa o mesmo vídeo duas vezes;
- job Supoclip completado gera clips uma única vez;
- publicação não duplica após retry;
- falha de YouTube não impede TikTok;
- falha de TikTok não impede YouTube;
- cleanup remove apenas arquivos elegíveis;
- cleanup emergencial respeita prioridades;
- watchdog detecta heartbeat atrasado.

### 25.3 Testes de falha

- token YouTube expirado;
- cookie YouTube inválido;
- TikTok token expirado;
- quota YouTube excedida;
- arquivo corrompido;
- vídeo sem áudio;
- Supoclip timeout;
- LLM timeout;
- LLM retorna JSON inválido;
- disco cheio;
- rede indisponível;
- processo morto durante upload.

### 25.4 Critérios de aceite

- Nenhuma publicação duplicada após retry.
- Nenhum vídeo longo duplicado após reingestão.
- Nenhum arquivo é processado enquanto ainda está sendo baixado.
- Nenhum clip abaixo do score mínimo é publicado.
- Nenhum clip sem metadata válido é publicado.
- O sistema continua operando após falha isolada de plataforma.
- O operador recebe alerta crítico em caso de falha fatal.
- O disco permanece abaixo do limite configurado em operação contínua.

---

## 26. Backup, migração e recuperação de desastres

### 26.1 SQLite

Recomenda-se ativar WAL:

```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
PRAGMA synchronous=NORMAL;
```

### 26.2 Backup diário

Exemplo:

```bash
sqlite3 ./data/pipeline.db ".backup ./backups/pipeline_$(date +%F_%H%M).db"
```

### 26.3 Retenção

Sugestão:

- backups diários por 14 dias;
- backups semanais por 60 dias;
- backup mensal por 1 ano, se necessário.

### 26.4 Restore

Procedimento:

1. parar serviços;
2. restaurar backup do SQLite;
3. restaurar configurações/credenciais;
4. validar integridade com consultas básicas;
5. iniciar serviços em modo observação;
6. confirmar heartbeat e fila.

### 26.5 Migrações

Toda alteração de schema deve:

- ser versionada;
- ser aplicada idempotentemente;
- registrar versão em `schema_migrations`;
- fazer backup antes;
- suportar rollback manual.

---

## 27. Serviços adicionais no systemd

O PRD já traz `clip-ingest` e `clip-publish`. Recomenda-se adicionar também serviços/timers para radar, limpeza e watchdog.

### 27.1 Radar

`/etc/systemd/system/clip-radar.service`

```ini
[Unit]
Description=Automacao de Cortes - Radar YouTube
After=network.target

[Service]
Type=oneshot
User=clipbot
WorkingDirectory=/opt/clip-automation
ExecStart=/opt/clip-automation/venv/bin/python radar_youtube.py
```

`/etc/systemd/system/clip-radar.timer`

```ini
[Unit]
Description=Executa Radar YouTube periodicamente

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
RandomizedDelaySec=60

[Install]
WantedBy=timers.target
```

### 27.2 Cleanup

`/etc/systemd/system/clip-cleanup.service`

```ini
[Unit]
Description=Automacao de Cortes - Cleanup
After=network.target

[Service]
Type=oneshot
User=clipbot
WorkingDirectory=/opt/clip-automation
ExecStart=/opt/clip-automation/venv/bin/python services/cleanup.py
```

`/etc/systemd/system/clip-cleanup.timer`

```ini
[Unit]
Description=Executa cleanup periodicamente

[Timer]
OnBootSec=5min
OnUnitActiveSec=30min
RandomizedDelaySec=120

[Install]
WantedBy=timers.target
```

### 27.3 Watchdog

`/etc/systemd/system/clip-watchdog.service`

```ini
[Unit]
Description=Automacao de Cortes - Watchdog
After=network.target

[Service]
Type=simple
User=clipbot
WorkingDirectory=/opt/clip-automation
ExecStart=/opt/clip-automation/venv/bin/python services/watchdog.py
Restart=always
RestartSec=30

[Install]
WantedBy=multi-user.target
```

Observação: manter os serviços existentes. Estes são complementares.

---

## 28. Runbooks operacionais recomendados

### 28.1 Cookie do YouTube inválido

Sintomas:

- falha no download;
- erro de autenticação no yt-dlp;
- alerta `cookie_invalid`.

Ação:

1. pausar radar;
2. exportar novo `cookies.txt`;
3. copiar para `config/cookies.txt`;
4. aplicar permissão restrita;
5. executar teste de download curto;
6. reativar radar.

### 28.2 Quota YouTube estourada

Sintomas:

- erro `quotaExceeded`;
- publicações `FAILED_QUOTA`.

Ação:

1. verificar `quota_usage`;
2. bloquear novos uploads no dia;
3. confirmar reagendamento automático;
4. validar reset de quota no horário esperado;
5. retomar publicações.

### 28.3 Disco cheio

Sintomas:

- uso acima de 85%;
- falha de download ou gravação.

Ação:

1. executar cleanup emergencial;
2. remover temporários;
3. remover clips já postados;
4. verificar logs antigos;
5. alertar se não liberar espaço;
6. considerar aumento de disco.

### 28.4 Supoclip travado

Sintomas:

- job em `PROCESSING` por tempo excessivo;
- timeout;
- container sem resposta.

Ação:

1. checar saúde do container;
2. verificar GPU;
3. verificar disco de saída;
4. reiniciar container se necessário;
5. reprocessar job com retry limitado;
6. enviar para DLQ se falhar novamente.

### 28.5 Publicação duplicada potencial

Sintomas:

- publicação ficou em `UPLOADING` após crash;
- reconciliação inconclusiva.

Ação:

1. não reenviar imediatamente;
2. buscar na plataforma por referência interna;
3. conferir horário/título;
4. se encontrado, marcar `POSTED`;
5. se não encontrado, liberar retry controlado;
6. registrar auditoria.

---

## 29. Riscos adicionais a incluir na matriz

| Risco adicional | Impacto | Mitigação |
|---|---|---|
| Fonte de views indisponível | Radar para de qualificar | Cache de métricas, fallback e dry-run |
| Cookie expirado | Downloads param | Monitorar cookie e alerta crítico |
| Token TikTok expirado | Publicação TikTok para | Refresh automático e alerta |
| Prompt injection via transcrição | Metadados maliciosos | Sanitização, validação JSON e limits |
| Crash durante upload | Duplicação potencial | Lease, reconciliation e idempotency_key |
| SQLite corrompido | Estado perdido | WAL, backups e teste de restore |
| Falta de índice/trava | Condição de corrida | Unique constraints, locks e transações |
| Crescimento de logs | Disco cheio | Rotação, retenção e limpeza |
| GPU indisponível | Pipeline atrasado | Healthcheck, retry e alerta |
| Alteração de API externa | Quebra de integração | Versão de API, testes e feature flags |
| Conteúdo com copyright | Strike/bloqueio | Controle de licença, bloqueio e takedown |
| LLM acima do custo esperado | Custo elevado | Limites diários e fallback |
| Multi-worker sem lock | Duplicidade | Lease/lock em publicações |
| Timezone/DST errado | Posts fora da janela | Timezone explícito e testes |

---

## 30. Checklist final de go-live

Antes de colocar em produção, validar:

### Infraestrutura

- [ ] Docker ativo.
- [ ] Supoclip respondendo.
- [ ] GPU disponível, se aplicável.
- [ ] Diretórios de dados criados.
- [ ] Permissões de arquivo corretas.
- [ ] NTP sincronizado.
- [ ] Espaço em disco suficiente.

### Credenciais

- [ ] `.env` protegido.
- [ ] `cookies.txt` válido.
- [ ] Token YouTube gerado.
- [ ] Token TikTok válido.
- [ ] Webhook Discord/Telegram válido.
- [ ] Nenhum segredo em logs.

### Banco

- [ ] Migrações aplicadas.
- [ ] Índices criados.
- [ ] WAL ativo.
- [ ] Backup inicial realizado.
- [ ] Teste de restore realizado.

### Pipeline

- [ ] Radar dry-run OK.
- [ ] Ingestão de vídeo de teste OK.
- [ ] Supoclip processou job de teste.
- [ ] Publicador gerou metadata.
- [ ] Publicação em sandbox ou teste OK.
- [ ] Cleanup executado sem remover itens ativos.
- [ ] Heartbeat registrado.
- [ ] DLQ notifica falhas.

### Segurança e compliance

- [ ] Canais autorizados configurados.
- [ ] Política de direitos autorais definida.
- [ ] Moderação habilitada ou risco aceito.
- [ ] Retenção de logs definida.
- [ ] Acesso ao servidor restrito.

---

# 31. Resumo do que falta e deve ser adicionado

De forma objetiva, os principais complementos são:

1. Definir fonte de views para VPH.
2. Criar tabela de canais monitorados.
3. Criar tabela de candidatos do radar.
4. Criar tabela de contas de publicação.
5. Criar tabela de publicações por plataforma.
6. Criar chave de idempotência para publicação.
7. Criar mecanismo de lease/reconciliação para uploads.
8. Criar controle de quota por conta e por dia.
9. Criar validação de mídia com ffprobe.
10. Criar regras de moderação e compliance.
11. Criar política de direitos autorais e bloqueio.
12. Criar política de LGPD para transcrições.
13. Criar logs estruturados.
14. Criar métricas e alertas detalhados.
15. Criar backup e restore do SQLite.
16. Criar testes de falha e critérios de aceite.
17. Criar runbooks operacionais.
18. Criar limpeza emergencial por uso de disco.
19. Criar timezone e expiração de hype.
20. Criar controles de custo de LLM/API/GPU.

Esses complementos tornam o PRD mais completo para uma operação realmente autônoma, auditável, resiliente e segura, mantendo intacto o escopo original já definido.