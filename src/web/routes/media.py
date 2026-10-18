"""
Endpoint de Streaming de Vídeo com suporte a HTTP 206 Partial Content (Range Requests)
e proteção estrita contra Path Traversal.
"""

import urllib.parse
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger("web_media")

router = APIRouter(prefix="/media", tags=["Media"])


@router.get("/{filename:path}")
async def stream_media(filename: str, request: Request):
    """
    Transmite arquivos de vídeo da pasta de output com suporte a scrubbing e Range Requests.
    """
    decoded_filename = urllib.parse.unquote(filename)
    output_dir = Path(settings.OUTPUT_DIR).resolve()
    target_path = (output_dir / decoded_filename).resolve()

    # Prevenção rigorosa contra Path Traversal
    try:
        if not target_path.is_relative_to(output_dir):
            logger.warning(f"Tentativa de path traversal bloqueada: {filename}")
            raise HTTPException(status_code=403, detail="Acesso proibido")
    except ValueError:
        raise HTTPException(status_code=403, detail="Acesso proibido")

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=404, detail="Vídeo não encontrado")

    file_size = target_path.stat().st_size
    range_header = request.headers.get("Range") or request.headers.get("range")

    if not range_header:

        def full_iter():
            with open(target_path, "rb") as f:
                while chunk := f.read(1024 * 512):
                    yield chunk

        return StreamingResponse(
            full_iter(),
            status_code=200,
            media_type="video/mp4",
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
                "Content-Disposition": f'inline; filename="{target_path.name}"',
            },
        )

    # Tratamento de Range (HTTP 206 Partial Content)
    try:
        bytes_prefix, range_str = range_header.strip().split("=")
        if bytes_prefix.strip().lower() != "bytes":
            raise ValueError()

        parts = range_str.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if len(parts) > 1 and parts[1] else file_size - 1

        if start >= file_size or start < 0 or end >= file_size or start > end:
            raise HTTPException(
                status_code=416, detail="Range Not Satisfiable", headers={"Content-Range": f"bytes */{file_size}"}
            )

        content_length = end - start + 1

        def ranged_iter():
            with open(target_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                chunk_size = 1024 * 512  # 512 KB
                while remaining > 0:
                    read_bytes = min(chunk_size, remaining)
                    data = f.read(read_bytes)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f'inline; filename="{target_path.name}"',
        }
        return StreamingResponse(ranged_iter(), status_code=206, headers=headers, media_type="video/mp4")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar Range header '{range_header}': {e}")
        return FileResponse(target_path, media_type="video/mp4")
