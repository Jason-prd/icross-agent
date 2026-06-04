# =============================================================================
# iCross Agent — PyInstaller Build Script
# =============================================================================
# Builds the backend API server into a standalone Windows executable.
#
# Usage:
#   cd icross-agent
#   pip install pyinstaller
#   python scripts/build_exe.py
#
# Output: dist/icross-agent-backend.exe
#
# Note: The frontend React app is NOT bundled. Run it separately with
# `npm run dev` in the frontend-react directory, or use Docker.
# =============================================================================

import os
import sys
import shutil
from pathlib import Path

# Ensure we're in the project root
SCRIPT_DIR = Path(__file__).parent.parent.absolute()
os.chdir(SCRIPT_DIR)

# ── Configuration ──
APP_NAME = "iCross Agent Backend"
MAIN_SCRIPT = "src/icross/api/main.py"
OUTPUT_DIR = "dist"
DATA_DIRS = [
    ("data", "data"),           # Runtime data files
    ("src/icross", "src/icross"),  # Source package
]

# ── Clean previous build ──
for d in ["build", OUTPUT_DIR]:
    shutil.rmtree(d, ignore_errors=True)

# ═══════════════════════════════════════════════════════════════════════
# Build with PyInstaller
# ═══════════════════════════════════════════════════════════════════════
# We use a .spec file approach for maximum control. The key challenges are:
# 1. Vendor packages installed as editable (-e) packages
# 2. Dynamic imports from langchain/langgraph
# 3. Multiple data directories
#
# The .spec file handles these via hidden-imports and datas collections.
# ═══════════════════════════════════════════════════════════════════════

SPEC_CONTENT = f'''# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Collect all vendor packages from .venv
_venv = Path(".venv")
_site_pkgs = list(_venv.glob("Lib/site-packages")) + list(_venv.glob("lib/python*/site-packages"))

block_cipher = None

a = Analysis(
    ['{MAIN_SCRIPT}'],
    pathex=[
        str(SCRIPT_DIR / "src"),
        str(SCRIPT_DIR),
    ],
    binaries=[],
    datas=[
        ("data", "data"),
    ],
    hiddenimports=[
        # ── LangChain / LangGraph ──
        "langchain",
        "langchain_core",
        "langchain_community",
        "langchain_anthropic",
        "langchain_openai",
        "langgraph",
        "langgraph.prebuilt",
        "langgraph.checkpoint",
        "langgraph.pregel",
        # ── LLM providers ──
        "anthropic",
        "openai",
        "httpx",
        # ── Web framework ──
        "uvicorn",
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "fastapi",
        "websockets",
        "pydantic",
        "pydantic.dataclasses",
        # ── Utilities ──
        "dotenv",
        "apscheduler",
        "apscheduler.triggers",
        "apscheduler.triggers.interval",
        "apscheduler.triggers.cron",
        "apscheduler.executors",
        "apscheduler.executors.pool",
        "PIL",
        "PIL._tkinter_finder",
        "lark_oapi",
        # ── Ozon API ──
        "ozonapi",
        # ── All API routers (dynamic imports in main.py) ──
        "icross.api.routers.chat",
        "icross.api.routers.sessions",
        "icross.api.routers.shops",
        "icross.api.routers.products",
        "icross.api.routers.drafts",
        "icross.api.routers.ozon",
        "icross.api.routers.templates",
        "icross.api.routers.categories",
        "icross.api.routers.images",
        "icross.api.routers.pricing",
        "icross.api.routers.rules",
        "icross.api.routers.listings",
        "icross.api.routers.tasks",
        "icross.api.routers.workflows",
        "icross.api.routers.uploads",
        "icross.api.routers.reports",
        "icross.api.routers.dashboard",
        "icross.api.routers.notifications",
        "icross.api.routers.providers",
        "icross.api.routers.scheduler",
        "icross.api.routers.parser",
        "icross.api.routers.auto_pilot",
        "icross.api.routers.auto_pilot_prompt",
        "icross.api.routers.sourcing",
        "icross.api.routers.ai_product",
        "icross.api.routers.ai_config",
        "icross.api.routers.ai_orders",
        "icross.api.routers.ai_returns",
        "icross.api.routers.ai_finance",
        "icross.api.routers.ai_reports",
        "icross.api.routers.ai_marketing",
        "icross.api.routers.ai_service",
        "icross.api.routers.ai_operations",
        "icross.api.routers.ai_autopilot",
        "icross.api.routers.ai_pricing",
        "icross.api.routers.ai_drafts",
        "icross.api.routers.compound_tasks",
        "icross.api.routers.extension",
        # ── Services ──
        "icross.services.report_service",
        "icross.services.scheduler",
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,       # Show console window for server logs
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
'''

# Write spec file
spec_path = SCRIPT_DIR / "build.spec"
spec_path.write_text(SPEC_CONTENT, encoding="utf-8")
print(f"[build] Spec file created: {spec_path}")

# ── Install PyInstaller if needed ──
import subprocess
try:
    import PyInstaller  # noqa: F401
except ImportError:
    print("[build] Installing PyInstaller...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

# ── Run PyInstaller ──
print(f"[build] Running PyInstaller...")
result = subprocess.run(
    [sys.executable, "-m", "PyInstaller", str(spec_path)],
    cwd=SCRIPT_DIR,
)
if result.returncode != 0:
    print(f"[build] PyInstaller failed with code {result.returncode}")
    sys.exit(1)

# ── Post-build cleanup ──
exe_name = f"{APP_NAME}.exe"
exe_path = Path(OUTPUT_DIR) / exe_name
if exe_path.exists():
    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print(f"[build] ✅ Build complete: {exe_path} ({size_mb:.1f} MB)")
else:
    print(f"[build] ⚠️  Build finished but {exe_name} not found in {OUTPUT_DIR}/")
    print(f"    Check the build/ directory for intermediate files.")

print(f"\n[build] Next steps:")
print(f"  1. Copy the entire {OUTPUT_DIR}/ directory to the target machine")
print(f"  2. Create a .env file with your API keys")
print(f"  3. Run: {APP_NAME}.exe")
print(f"  4. Frontend (separate): cd frontend-react && npm run dev")
