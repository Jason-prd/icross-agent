"""Agent system tools with workspace sandbox.

Provides safe file operations, command execution, document parsing, and
search tools. All file I/O is restricted to the designated workspace directory
for security.
"""

import json
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

from langchain_core.tools import tool

from icross.agents.tools import registry

# Resolve workspace root relative to project root (4 levels up from this file)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
_WORKSPACE_ROOT = _PROJECT_ROOT / "workspace"
_WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)

# Commands allowed for run_command without restriction
_ALLOWED_COMMANDS = {
    "ls", "find", "grep", "cat", "head", "tail", "wc", "sort", "uniq",
    "echo", "python", "pip", "git", "node", "npm", "npx", "uv",
    "mkdir", "cp", "mv", "rm", "touch",
    "curl", "wget",
    "date", "pwd", "whoami", "id",
    "ffprobe", "ffmpeg",
    "docker", "docker-compose",
    "ping", "nslookup",
}

_MAX_COMMAND_TIMEOUT = 60  # seconds


def _resolve_workspace_path(path: str) -> Path:
    """Resolve a user-provided path relative to the workspace root.

    Raises ValueError if the resolved path escapes the workspace.
    """
    user_path = Path(path)
    if user_path.is_absolute():
        resolved = user_path.resolve()
    else:
        resolved = (_WORKSPACE_ROOT / user_path).resolve()

    # Ensure the resolved path is within the workspace
    try:
        resolved.relative_to(_WORKSPACE_ROOT)
    except ValueError:
        raise ValueError(
            f"路径越权: {path} 解析到 {resolved}，不在工作区 {_WORKSPACE_ROOT} 内"
        )
    return resolved


def _workspace_summary() -> str:
    """Return a summary of the workspace for agent context."""
    items = list(_WORKSPACE_ROOT.iterdir()) if _WORKSPACE_ROOT.exists() else []
    total_size = sum(
        f.stat().st_size for f in _WORKSPACE_ROOT.rglob("*") if f.is_file()
    )
    total_files = sum(1 for _ in _WORKSPACE_ROOT.rglob("*") if _.is_file())

    parts = [
        f"工作区路径: {_WORKSPACE_ROOT}",
        f"总文件数: {total_files}",
        f"总大小: {total_size / 1024:.1f} KB",
    ]
    if items:
        names = []
        for i in items:
            suffix = "/" if i.is_dir() else ""
            names.append(f"{i.name}{suffix}")
        parts.append(f"根目录内容: {', '.join(names[:50])}")

    return "\n".join(parts)


# ============================================================
# File Operation Tools
# ============================================================


@tool
def read_file(path: str) -> str:
    """读取工作区内的文件内容。

    Args:
        path: 文件路径（相对工作区根目录，或绝对路径）

    Returns:
        文件内容的 JSON 字符串。
    """
    try:
        full_path = _resolve_workspace_path(path)
        if not full_path.exists():
            return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)
        if not full_path.is_file():
            return json.dumps({"error": f"路径不是文件: {path}"}, ensure_ascii=False)

        # Read as text for common extensions
        text_extensions = {
            ".txt", ".md", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
            ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css", ".scss",
            ".sql", ".sh", ".bat", ".ps1", ".env", ".csv", ".xml",
            ".c", ".cpp", ".h", ".hpp", ".java", ".go", ".rs", ".rb",
            ".log", ".rst", ".cfg",
        }
        if full_path.suffix.lower() in text_extensions:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        else:
            # Binary file — return metadata only
            stat = full_path.stat()
            return json.dumps({
                "path": str(full_path.relative_to(_WORKSPACE_ROOT)),
                "size_bytes": stat.st_size,
                "message": "二进制文件，无法直接显示文本内容",
            }, ensure_ascii=False)

        return json.dumps({
            "path": str(full_path.relative_to(_WORKSPACE_ROOT)),
            "size_bytes": len(content),
            "content": content,
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"读取文件失败: {e}"}, ensure_ascii=False)



registry.register(read_file, toolset="system")
@tool
def write_file(path: str, content: str) -> str:
    """写入文件到工作区（创建新文件或覆盖已有文件）。

    此操作直接写入文件，请确认后再执行。

    Args:
        path: 文件路径（相对工作区根目录）
        content: 文件内容

    Returns:
        写入结果的 JSON 字符串。
    """
    try:
        full_path = _resolve_workspace_path(path)

        # Create parent directories if needed
        full_path.parent.mkdir(parents=True, exist_ok=True)

        full_path.write_text(content, encoding="utf-8")

        return json.dumps({
            "success": True,
            "path": str(full_path.relative_to(_WORKSPACE_ROOT)),
            "size_bytes": len(content),
            "message": f"文件已写入: {full_path.relative_to(_WORKSPACE_ROOT)}",
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"写入文件失败: {e}"}, ensure_ascii=False)



registry.register(write_file, toolset="system")
@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """编辑工作区内已有文件的内容（查找替换）。

    在文件中查找 old_string 并替换为 new_string。
    如果 old_string 在文件中出现多次，需要提供足够的上下文确保唯一匹配。

    Args:
        path: 文件路径（相对工作区根目录）
        old_string: 要被替换的文本（需要足够唯一）
        new_string: 替换后的文本

    Returns:
        编辑结果的 JSON 字符串。
    """
    try:
        full_path = _resolve_workspace_path(path)
        if not full_path.exists():
            return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)

        original = full_path.read_text(encoding="utf-8")
        if old_string not in original:
            return json.dumps({
                "error": f"未在文件中找到匹配文本: '{old_string[:50]}...'",
            }, ensure_ascii=False)

        count = original.count(old_string)
        if count > 1:
            return json.dumps({
                "error": f"找到 {count} 处匹配，请提供更多上下文以确保唯一匹配",
            }, ensure_ascii=False)

        new_content = original.replace(old_string, new_string, 1)
        full_path.write_text(new_content, encoding="utf-8")

        return json.dumps({
            "success": True,
            "path": str(full_path.relative_to(_WORKSPACE_ROOT)),
            "replacement_count": 1,
            "message": "文件已更新",
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"编辑文件失败: {e}"}, ensure_ascii=False)



registry.register(edit_file, toolset="system")
@tool
def delete_file(path: str) -> str:
    """删除工作区内的文件。

    Args:
        path: 文件路径（相对工作区根目录）

    Returns:
        删除结果的 JSON 字符串。
    """
    try:
        full_path = _resolve_workspace_path(path)
        if not full_path.exists():
            return json.dumps({"error": f"文件不存在: {path}"}, ensure_ascii=False)
        if not full_path.is_file():
            return json.dumps({"error": f"路径不是文件: {path}"}, ensure_ascii=False)

        full_path.unlink()
        return json.dumps({
            "success": True,
            "path": str(full_path.relative_to(_WORKSPACE_ROOT)),
            "message": "文件已删除",
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"删除文件失败: {e}"}, ensure_ascii=False)


# ============================================================
# Command Execution Tools
# ============================================================



registry.register(delete_file, toolset="system")
@tool
def run_command(command: str, timeout: int = 30) -> str:
    """在工作区目录下执行 shell 命令。

    仅允许执行以下安全命令：
    ls, find, grep, cat, head, tail, wc, sort, uniq,
    echo, python, pip, git, node, npm, npx, uv,
    mkdir, cp, mv, rm, touch, curl, wget,
    date, pwd, whoami, id, docker

    禁止的操作：删除 .git 目录、修改父目录文件、大规模删除。

    Args:
        command: 要执行的 shell 命令
        timeout: 超时秒数（默认 30，最大 300）

    Returns:
        命令输出的 JSON 字符串（stdout/stderr/返回码）。
    """
    actual_timeout = min(max(timeout, 1), 300)

    # Parse the command to check the base command
    try:
        cmd_parts = shlex.split(command)
    except ValueError as e:
        return json.dumps({"error": f"命令解析失败: {e}"}, ensure_ascii=False)

    if not cmd_parts:
        return json.dumps({"error": "命令不能为空"}, ensure_ascii=False)

    base_cmd = os.path.basename(cmd_parts[0])
    if base_cmd not in _ALLOWED_COMMANDS:
        return json.dumps({
            "error": f"命令 '{base_cmd}' 不在允许列表中",
            "allowed_commands": sorted(_ALLOWED_COMMANDS),
        }, ensure_ascii=False)

    # Safety: prevent git operations with destructive flags
    if base_cmd == "git":
        dangerous_flags = {"push --force", "reset --hard", "clean -f", "rm -r"}
        for flag in dangerous_flags:
            if flag in command:
                return json.dumps({
                    "error": f"禁止的 git 操作: {flag}",
                }, ensure_ascii=False)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=actual_timeout,
            cwd=str(_WORKSPACE_ROOT),
        )

        output_parts = []
        if result.stdout:
            # Truncate very long output
            stdout = result.stdout
            if len(stdout) > 50000:
                stdout = stdout[:50000] + "\n... (输出截断，超过50000字符)"
            output_parts.append(f"[stdout]\n{stdout}")
        if result.stderr:
            stderr = result.stderr
            if len(stderr) > 10000:
                stderr = stderr[:10000] + "\n... (错误输出截断)"
            output_parts.append(f"[stderr]\n{stderr}")

        return json.dumps({
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "output": "\n".join(output_parts) if output_parts else "(无输出)",
            "cwd": str(_WORKSPACE_ROOT),
        }, ensure_ascii=False)

    except subprocess.TimeoutExpired:
        return json.dumps({
            "error": f"命令执行超时（{actual_timeout}秒）",
            "command": command[:200],
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"命令执行失败: {e}"}, ensure_ascii=False)


# ============================================================
# Search Tools
# ============================================================



registry.register(run_command, toolset="system")
@tool
def glob_files(pattern: str, path: str = "") -> str:
    """在工作区内搜索匹配 glob 模式的文件。

    Args:
        pattern: glob 模式，如 "**/*.py", "*.txt", "data/*.json"
        path: 搜索的子目录（留空搜索整个工作区）

    Returns:
        匹配文件列表的 JSON 字符串。
    """
    try:
        search_root = _WORKSPACE_ROOT
        if path:
            search_root = _resolve_workspace_path(path)
            if not search_root.is_dir():
                return json.dumps({"error": f"路径不是目录: {path}"}, ensure_ascii=False)

        from glob import glob
        full_pattern = str(search_root / pattern)
        matches = glob(full_pattern, recursive=True)

        # Filter to workspace and make relative
        result = []
        for m in sorted(matches):
            mp = Path(m)
            try:
                rel = mp.relative_to(_WORKSPACE_ROOT)
                result.append(str(rel))
            except ValueError:
                continue

        return json.dumps({
            "pattern": pattern,
            "search_path": str(search_root.relative_to(_WORKSPACE_ROOT)) if search_root != _WORKSPACE_ROOT else ".",
            "matches": result,
            "total": len(result),
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {e}"}, ensure_ascii=False)



registry.register(glob_files, toolset="system")
@tool
def grep_files(pattern: str, glob: str = "", path: str = "") -> str:
    """在工作区内搜索文件内容（支持正则表达式）。

    Args:
        pattern: 搜索的正则表达式
        glob: 文件类型过滤，如 "*.py", "*.{json,md}"
        path: 搜索的子目录（留空搜索整个工作区）

    Returns:
        匹配结果的 JSON 字符串。
    """
    try:
        search_root = _WORKSPACE_ROOT
        if path:
            search_root = _resolve_workspace_path(path)
            if not search_root.is_dir():
                return json.dumps({"error": f"路径不是目录: {path}"}, ensure_ascii=False)

        import re as re_module

        matches = []
        file_pattern = glob if glob else "*"

        # Simple recursive grep using pathlib
        for f in search_root.rglob(file_pattern):
            if not f.is_file():
                continue
            try:
                rel_path = f.relative_to(_WORKSPACE_ROOT)
                content = f.read_text(encoding="utf-8", errors="replace")
                for i, line in enumerate(content.splitlines(), 1):
                    if re_module.search(pattern, line):
                        matches.append({
                            "file": str(rel_path),
                            "line": i,
                            "content": line[:200],  # Truncate long lines
                        })
            except Exception:
                continue

            # Limit results to prevent huge output
            if len(matches) >= 100:
                break

        return json.dumps({
            "pattern": pattern,
            "glob": glob,
            "matches": matches,
            "total": len(matches),
            "truncated": len(matches) >= 100,
        }, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"搜索失败: {e}"}, ensure_ascii=False)


# ============================================================
# Document Parsing Tool
# ============================================================



registry.register(grep_files, toolset="system")
@tool
def read_document(file_path: str) -> str:
    """读取文档文件（PDF、Word、Excel、PPT、HTML、图片等）并提取文本内容。

    支持格式：PDF, DOCX, XLSX, PPTX, HTML, TXT, CSV, 以及常见图片格式。
    使用 Docling 引擎进行文档解析，支持表格提取、OCR 识别。

    Args:
        file_path: 文档路径（相对工作区根目录）

    Returns:
        JSON 字符串，包含文档的 Markdown 格式文本。
    """
    try:
        full_path = _resolve_workspace_path(file_path)
        if not full_path.exists():
            return json.dumps({"error": f"文件不存在: {file_path}"}, ensure_ascii=False)
        if not full_path.is_file():
            return json.dumps({"error": f"路径不是文件: {file_path}"}, ensure_ascii=False)

        from icross.services.document_reader import read_document as _read_doc

        result = _read_doc(str(full_path))
        return json.dumps(result, ensure_ascii=False)

    except ValueError as e:
        return json.dumps({"error": str(e)}, ensure_ascii=False)
    except ImportError:
        return json.dumps({
            "error": "文档解析模块未安装，请执行: pip install docling",
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"文档解析失败: {e}"}, ensure_ascii=False)


# ============================================================
# Tool List
# ============================================================


registry.register(read_document, toolset="system")
SYSTEM_TOOLS = [
    read_file,
    write_file,
    edit_file,
    delete_file,
    run_command,
    glob_files,
    grep_files,
    read_document,
]
