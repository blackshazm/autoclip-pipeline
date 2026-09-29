"""
Exceções customizadas para o Pipeline Autônomo de Cortes.
"""

class PipelineError(Exception):
    """Exceção base do pipeline."""
    pass

class MediaValidationError(PipelineError):
    """Erro de validação ou corrupção de mídia (ffprobe/ffmpeg)."""
    pass

class IdempotencyError(PipelineError):
    """Violação de idempotência ou tentativa de reprocessamento duplicado."""
    pass

class SupoclipError(PipelineError):
    """Erro de comunicação, processamento ou timeout no Supoclip."""
    pass

class LLMGenerationError(PipelineError):
    """Falha irrecuperável na geração de metadados via LLM."""
    pass

class YouTubePublishError(PipelineError):
    """Erro durante o envio para a API do YouTube Shorts."""
    pass

class TikTokPublishError(PipelineError):
    """Erro durante o envio para a API do TikTok."""
    pass

class QuotaExceededError(PipelineError):
    """Cota diária de requisições ou uploads da plataforma excedida."""
    pass

class LeaseLockError(PipelineError):
    """Falha ao adquirir trava exclusiva de execução/upload."""
    pass
