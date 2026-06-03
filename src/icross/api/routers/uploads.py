"""File upload endpoints for agent document processing."""

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, UploadFile, File

from icross.agents.master.tools_system import _WORKSPACE_ROOT

router = APIRouter()

# Allowed file extensions for document upload
_ALLOWED_EXTENSIONS = {
    ".pdf", ".docx", ".doc", ".xlsx", ".xls",
    ".pptx", ".ppt", ".txt", ".md", ".csv",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp",
    ".html", ".htm", ".json", ".xml", ".yaml", ".yml",
    ".zip", ".tar", ".gz",
}

_MAX_UPLOAD_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to the agent workspace for document processing.

    Supported formats: PDF, DOCX, XLSX, DOC, XLS, PPTX, PPT, TXT, MD, CSV,
    images, HTML, JSON, XML, YAML, ZIP archives.

    The uploaded file can then be read using the read_document or read_file tools.
    """
    # Validate file extension
    ext = Path(file.filename or "").suffix.lower()
    if not ext:
        raise HTTPException(status_code=400, detail="无法识别文件类型")

    if ext not in _ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {ext}。支持的格式: {', '.join(sorted(_ALLOWED_EXTENSIONS))}",
        )

    # Read file content (with size check)
    content = await file.read()
    if len(content) > _MAX_UPLOAD_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大（{len(content) / 1024 / 1024:.1f} MB），最大允许 100 MB",
        )

    # Save to workspace
    safe_filename = Path(file.filename).name  # strip any path components
    dest = _WORKSPACE_ROOT / safe_filename

    # Avoid overwriting existing files
    counter = 1
    while dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        dest = _WORKSPACE_ROOT / f"{stem}_{counter}{suffix}"
        counter += 1

    dest.write_bytes(content)

    return {
        "success": True,
        "filename": dest.name,
        "path": str(dest),
        "size_bytes": len(content),
        "mime_type": file.content_type or "application/octet-medium",
        "message": f"文件已上传: {dest.name}，可使用 read_file 或 read_document 工具读取",
    }
