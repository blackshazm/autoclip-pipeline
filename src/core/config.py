"""
Módulo de Configuração Tipada via Pydantic Settings.
"""
from pathlib import Path
from typing import List
import json
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Diretórios
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    WATCH_DIR: Path = Field(default=Path("./data/videos_longos"))
    OUTPUT_DIR: Path = Field(default=Path("./data/clips_exportados"))
    BACKUP_DIR: Path = Field(default=Path("./data/backups"))
    DB_PATH: Path = Field(default=Path("./data/pipeline.db"))
    LOG_DIR: Path = Field(default=Path("./logs"))
    LOG_LEVEL: str = Field(default="INFO")

    # Supoclip
    SUPOCLIP_API_URL: str = Field(default="http://localhost:8000")
    SUPOCLIP_TIMEOUT_SECONDS: int = Field(default=600)
    SUPOCLIP_MAX_RETRIES: int = Field(default=3)
    SUPOCLIP_USER_ID: str = Field(default="qJHay5ukwhNUBiYTSb3FJcIdrPFNg8RG")
    SUPOCLIP_AUTH_SECRET: str = Field(default="change_me_backend_auth_secret")
    SUPOCLIP_API_KEY: str = Field(default="")
    MOCK_SUPOCLIP: bool = Field(default=False)

    # Motor de Corte e Duração Alvo
    CLIP_MIN_DURATION_SECONDS: int = Field(default=50)
    CLIP_MAX_DURATION_SECONDS: int = Field(default=75)

    # Limiares de Qualidade e Radar
    MIN_VIRALITY_SCORE: int = Field(default=60)
    VPH_MINIMUM_THRESHOLD: int = Field(default=5000)
    RADAR_INTERVAL_MINUTES: int = Field(default=15)
    RADAR_MIN_AGE_HOURS: int = Field(default=2)
    RADAR_MAX_AGE_HOURS: int = Field(default=48)
    RADAR_IGNORE_AFTER_DAYS: int = Field(default=7)
    MAX_DOWNLOADS_PER_CYCLE: int = Field(default=4)
    MAX_DAILY_DOWNLOADS: int = Field(default=16)

    # Agendamento e Buffer Anti-Spam
    TIMEZONE: str = Field(default="America/Sao_Paulo")
    POST_INTERVAL_MINUTES: int = Field(default=90)
    DEFAULT_POSTING_WINDOWS: List[str] = Field(
        default=["09:00", "11:30", "13:30", "15:30", "17:30", "19:30", "21:30"]
    )
    MAX_CLIP_AGE_DAYS: int = Field(default=7)

    # Limpeza e Proteção de Disco
    DISK_ALERT_THRESHOLD: int = Field(default=75)
    DISK_HARD_THRESHOLD: int = Field(default=85)
    EMERGENCY_CLEANUP_ENABLED: bool = Field(default=True)
    KEEP_POSTED_CLIPS_HOURS: int = Field(default=48)

    # Credenciais YouTube
    YTDLP_COOKIES_PATH: Path = Field(default=Path("./config/cookies.txt"))
    YOUTUBE_API_KEY: str = Field(default="")
    YOUTUBE_CLIENT_SECRETS: Path = Field(default=Path("./config/client_secrets.json"))
    YOUTUBE_TOKEN_PATH: Path = Field(default=Path("./config/youtube_token.json"))
    YOUTUBE_DATA_API_MAX_QUOTA_UNITS_PER_DAY: int = Field(default=9000)
    YOUTUBE_DAILY_UPLOAD_LIMIT: int = Field(default=10)

    # Credenciais TikTok
    TIKTOK_MODE: str = Field(default="official")
    TIKTOK_ACCESS_TOKEN: str = Field(default="")
    TIKTOK_OPEN_ID: str = Field(default="")

    # LLM / Copywriting (Hermes / OpenAI)
    OPENAI_API_KEY: str = Field(default="local-hermes")
    OPENAI_BASE_URL: str = Field(default="http://localhost:11434/v1")
    OPENAI_MODEL: str = Field(default="hermes-3-llama-3.1-8b")
    LLM_TIMEOUT_SECONDS: int = Field(default=30)
    LLM_TEMPERATURE: float = Field(default=0.3)
    LLM_MAX_RETRIES: int = Field(default=1)

    # Notificações e Webhooks
    DISCORD_WEBHOOK_URL: str = Field(default="")
    TELEGRAM_BOT_TOKEN: str = Field(default="")
    TELEGRAM_CHAT_ID: str = Field(default="")

    @field_validator("DEFAULT_POSTING_WINDOWS", mode="before")
    @classmethod
    def parse_posting_windows(cls, v):
        if isinstance(v, str):
            try:
                return json.loads(v)
            except Exception:
                return [w.strip() for w in v.split(",") if w.strip()]
        return v

    def resolve_paths(self):
        """Converte caminhos relativos em caminhos absolutos baseados no BASE_DIR."""
        self.WATCH_DIR = (self.BASE_DIR / self.WATCH_DIR).resolve()
        self.OUTPUT_DIR = (self.BASE_DIR / self.OUTPUT_DIR).resolve()
        self.BACKUP_DIR = (self.BASE_DIR / self.BACKUP_DIR).resolve()
        self.DB_PATH = (self.BASE_DIR / self.DB_PATH).resolve()
        self.LOG_DIR = (self.BASE_DIR / self.LOG_DIR).resolve()
        self.YTDLP_COOKIES_PATH = (self.BASE_DIR / self.YTDLP_COOKIES_PATH).resolve()
        self.YOUTUBE_CLIENT_SECRETS = (self.BASE_DIR / self.YOUTUBE_CLIENT_SECRETS).resolve()
        self.YOUTUBE_TOKEN_PATH = (self.BASE_DIR / self.YOUTUBE_TOKEN_PATH).resolve()

        # Cria diretórios necessários
        self.WATCH_DIR.mkdir(parents=True, exist_ok=True)
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        self.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

# Singleton global de configurações
settings = Settings()
settings.resolve_paths()
