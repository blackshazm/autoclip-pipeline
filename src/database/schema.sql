-- ========================================================
-- SCHEMA CONSOLIDADO: PIPELINE AUTÔNOMO DE CORTES
-- Suporte total a WAL Mode, Idempotência e Auditoria
-- ========================================================

-- 1. Controle de Migrações
CREATE TABLE IF NOT EXISTS schema_migrations (
    version TEXT PRIMARY KEY,
    applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Canais Monitorados pelo Radar
CREATE TABLE IF NOT EXISTS source_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    youtube_channel_id TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    rss_url TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    min_duration_minutes INTEGER DEFAULT 20,
    vph_absolute_threshold INTEGER DEFAULT 5000,
    vph_multiplier_threshold REAL DEFAULT 2.0,
    median_vph REAL DEFAULT 1500.0,
    license_mode TEXT DEFAULT 'owned' CHECK(license_mode IN ('owned', 'licensed', 'authorized', 'third_party_review_required', 'blocked')),
    max_videos_per_cycle INTEGER DEFAULT 3,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Candidatos Detectados pelo Radar
CREATE TABLE IF NOT EXISTS radar_candidates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_channel_id INTEGER NOT NULL REFERENCES source_channels(id) ON DELETE CASCADE,
    youtube_id TEXT UNIQUE NOT NULL,
    title TEXT,
    published_at TIMESTAMP,
    duration_seconds INTEGER,
    view_count INTEGER,
    like_count INTEGER,
    comment_count INTEGER,
    vph REAL,
    median_factor REAL,
    status TEXT CHECK(status IN ('NEW', 'MONITORING', 'QUALIFIED', 'REJECTED', 'DOWNLOADED', 'ERROR')) DEFAULT 'NEW',
    reject_reason TEXT,
    first_seen_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_checked_at TIMESTAMP,
    qualified_at TIMESTAMP,
    downloaded_at TIMESTAMP
);

-- 4. Vídeos Longos (Ingestão)
CREATE TABLE IF NOT EXISTS long_videos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_hash TEXT UNIQUE NOT NULL,
    youtube_id TEXT,
    channel_name TEXT,
    source_channel_id INTEGER REFERENCES source_channels(id) ON DELETE SET NULL,
    file_name TEXT NOT NULL,
    file_path TEXT NOT NULL,
    youtube_url TEXT,
    duration_seconds INTEGER,
    file_size_bytes INTEGER,
    media_valid INTEGER DEFAULT 0,
    supoclip_job_id TEXT,
    status TEXT CHECK(status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')) DEFAULT 'PENDING',
    is_deleted_from_disk INTEGER DEFAULT 0,
    error_message TEXT,
    downloaded_at TIMESTAMP,
    completed_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Jobs do Supoclip
CREATE TABLE IF NOT EXISTS supoclip_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    long_video_id INTEGER NOT NULL REFERENCES long_videos(id) ON DELETE CASCADE,
    supoclip_job_id TEXT UNIQUE,
    status TEXT CHECK(status IN ('PENDING', 'SUBMITTED', 'PROCESSING', 'COMPLETED', 'FAILED', 'TIMEOUT', 'CANCELLED')) DEFAULT 'PENDING',
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

-- 6. Tabela de Cortes / Clips
CREATE TABLE IF NOT EXISTS clips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    long_video_id INTEGER NOT NULL REFERENCES long_videos(id) ON DELETE CASCADE,
    clip_uid TEXT UNIQUE NOT NULL,
    file_path TEXT NOT NULL,
    file_hash TEXT UNIQUE,
    virality_score INTEGER NOT NULL,
    start_seconds REAL,
    end_seconds REAL,
    duration_seconds REAL,
    width INTEGER,
    height INTEGER,
    fps REAL,
    title TEXT,
    description TEXT,
    tags TEXT,
    metadata_json TEXT,
    transcription_path TEXT,
    moderation_status TEXT DEFAULT 'PENDING' CHECK(moderation_status IN ('PENDING', 'APPROVED', 'MODERATION_BLOCKED')),
    copyright_status TEXT DEFAULT 'PENDING' CHECK(copyright_status IN ('PENDING', 'APPROVED', 'POLICY_BLOCKED')),
    llm_fallback_used INTEGER DEFAULT 0,
    scheduled_for TIMESTAMP,
    retry_count INTEGER DEFAULT 0,
    youtube_status TEXT CHECK(youtube_status IN ('PENDING', 'SCHEDULED', 'POSTED', 'FAILED', 'SKIPPED', 'FAILED_QUOTA')) DEFAULT 'PENDING',
    youtube_video_id TEXT,
    tiktok_status TEXT CHECK(tiktok_status IN ('PENDING', 'SCHEDULED', 'POSTED', 'FAILED', 'SKIPPED')) DEFAULT 'PENDING',
    tiktok_post_id TEXT,
    is_deleted_from_disk INTEGER DEFAULT 0,
    published_at TIMESTAMP,
    error_log TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 7. Contas de Publicação Multiplataforma
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

-- 8. Fila de Publicações Transacionais com Lease Lock
CREATE TABLE IF NOT EXISTS publications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    publishing_account_id INTEGER NOT NULL REFERENCES publishing_accounts(id) ON DELETE CASCADE,
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
        'RECONCILING',
        'EXPIRED'
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
    quota_units INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(clip_id, publishing_account_id, platform)
);

-- 9. Controle de Quota Diária de API
CREATE TABLE IF NOT EXISTS quota_usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    publishing_account_id INTEGER NOT NULL REFERENCES publishing_accounts(id) ON DELETE CASCADE,
    platform TEXT NOT NULL,
    quota_date TEXT NOT NULL,
    units_used INTEGER DEFAULT 0,
    uploads_used INTEGER DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(publishing_account_id, platform, quota_date)
);

-- 10. Auditoria Estruturada de Eventos
CREATE TABLE IF NOT EXISTS audit_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT DEFAULT 'system',
    payload_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 11. Central de Alertas e Incidentes
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

-- 12. Execuções de Limpeza de Disco
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

-- 13. Gerações de LLM (Copywriting & Auditoria de Fallback)
CREATE TABLE IF NOT EXISTS llm_generations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clip_id INTEGER NOT NULL REFERENCES clips(id) ON DELETE CASCADE,
    model TEXT,
    prompt_version TEXT,
    status TEXT CHECK(status IN ('SUCCESS', 'FALLBACK', 'FAILED')) DEFAULT 'SUCCESS',
    latency_ms INTEGER,
    raw_response TEXT,
    parsed_json TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. Bloqueio de Conteúdo e Direitos Autorais (Takedown)
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

-- 15. Heartbeats do Sistema (Watchdog)
CREATE TABLE IF NOT EXISTS system_heartbeats (
    service_name TEXT PRIMARY KEY,
    last_ping TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    status TEXT,
    extra_info TEXT
);

-- ========================================================
-- ÍNDICES DE ALTA PERFORMANCE
-- ========================================================
CREATE INDEX IF NOT EXISTS idx_long_videos_hash ON long_videos(file_hash);
CREATE INDEX IF NOT EXISTS idx_long_videos_status ON long_videos(status);
CREATE INDEX IF NOT EXISTS idx_long_videos_youtube_id ON long_videos(youtube_id);

CREATE INDEX IF NOT EXISTS idx_clips_uid ON clips(clip_uid);
CREATE INDEX IF NOT EXISTS idx_clips_filter ON clips(virality_score, moderation_status, copyright_status);
CREATE INDEX IF NOT EXISTS idx_clips_schedule ON clips(scheduled_for, youtube_status, tiktok_status);

CREATE INDEX IF NOT EXISTS idx_publications_schedule ON publications(status, scheduled_for);
CREATE INDEX IF NOT EXISTS idx_publications_lease ON publications(status, lease_expires_at);

CREATE INDEX IF NOT EXISTS idx_radar_candidates_status ON radar_candidates(status, last_checked_at);
