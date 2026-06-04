@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

:: iCross Agent — Windows One-click Setup & Start
:: Backend=8000  Frontend=3000

title iCross Agent

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

color 0B

echo =====================================
echo          iCross Agent 启动中...
echo =====================================
echo.

:: ── Step 1: Check prerequisites ──
echo [iCross] 检查运行环境...

:: Check Python
set "PYTHON_CMD="
for %%p in (python py) do (
    where %%p >nul 2>&1 && (
        for /f "tokens=2 delims=." %%v in ('%%p --version 2^>^&1 ^| findstr /r "^Python 3\."') do (
            if %%v geq 11 (
                set "PYTHON_CMD=%%p"
                goto :python_found
            )
        )
    )
)
:python_found
if not defined PYTHON_CMD (
    echo [fail] 未找到 Python 3.11+，请先安装: https://www.python.org/downloads/
    echo        安装时请勾选 "Add Python to PATH"
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('%PYTHON_CMD% --version') do echo [  ok] %%v

:: Check Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [fail] 未找到 Node.js 18+，请先安装: https://nodejs.org/
    pause
    exit /b 1
)
for /f "tokens=*" %%v in ('node --version') do echo [  ok] Node.js %%v

:: ── Step 2: Environment variables ──
echo.
echo [iCross] 检查环境配置...

if not exist ".env" (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo [warn] .env 不存在，已从 .env.example 创建
        echo [warn] 请编辑 .env 填入你的 API keys，然后重新运行本脚本
        echo [warn]
        echo [warn] 至少需要 DEEPSEEK_API_KEY 或 MINIMAX_API_KEY
        echo [warn] Ozon 运营需要 OZON_CLIENT_ID + OZON_API_KEY
        start "" notepad.exe ".env"
        pause
        exit /b 1
    ) else (
        echo [fail] .env.example 也不存在，请手动创建 .env
        pause
        exit /b 1
    )
)

:: Check if keys are placeholders (basic check)
findstr /C:"your-deepseek" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo [warn] DEEPSEEK_API_KEY 尚未配置（当前为占位符）
)
findstr /C:"your-ozon" .env >nul 2>&1
if %errorlevel% equ 0 (
    echo [warn] Ozon API Key 尚未配置
)

:: ── Step 3: Python virtual env + deps ──
echo.
echo [iCross] 安装后端依赖...

if not exist ".venv\Scripts\python.exe" (
    echo [iCross] 创建虚拟环境...
    %PYTHON_CMD% -m venv .venv
    if !errorlevel! neq 0 (
        echo [fail] 创建虚拟环境失败
        pause
        exit /b 1
    )
)

:: Check if uv is available
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo [iCross] 使用 uv 安装依赖...
    uv sync
) else (
    echo [iCross] 使用 pip 安装依赖（推荐安装 uv 加速: pip install uv）...
    call .venv\Scripts\pip install --upgrade pip >nul 2>&1
    call .venv\Scripts\pip install -e vendors\langchain\libs\core -q
    call .venv\Scripts\pip install -e vendors\langchain-community\libs\community -q
    call .venv\Scripts\pip install -e vendors\langgraph\libs\langgraph -q
    call .venv\Scripts\pip install -e vendors\langgraph\libs\checkpoint -q
    call .venv\Scripts\pip install -e vendors\langgraph\libs\prebuilt -q
    call .venv\Scripts\pip install -e vendors\langchain\libs\partners\anthropic -q
    call .venv\Scripts\pip install -e vendors\langchain\libs\partners\openai -q
    call .venv\Scripts\pip install -e vendors\rembg -q
    call .venv\Scripts\pip install fastapi[standard] uvicorn[standard] pydantic python-dotenv httpx anthropic openai websockets apscheduler Pillow lark-oapi -q
    call .venv\Scripts\pip install "langchain-anthropic>=0.3.0" "langchain-openai>=0.3.0" -q
)
echo [  ok] 后端依赖安装完成

:: ── Step 4: Frontend deps ──
echo.
echo [iCross] 安装前端依赖...
if not exist "frontend-react\node_modules" (
    cd frontend-react
    call npm install
    cd "%SCRIPT_DIR%"
    if !errorlevel! neq 0 (
        echo [warn] npm install 失败，尝试使用 cnpm...
        cd frontend-react
        call npx cnpm install 2>nul || call npm install --legacy-peer-deps
        cd "%SCRIPT_DIR%"
    )
    echo [  ok] 前端依赖安装完成
) else (
    echo [  ok] 前端依赖已就绪
)

:: ── Step 5: Kill processes on our ports ──
echo.
echo [iCross] 释放端口...
for %%p in (3000 8000) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 2 /nobreak >nul

:: ── Step 6: Start servers ──
echo.
echo [iCross] 启动后端 (port 8000)...

:: Temporarily set PYTHONPATH for this process
set "PYTHONPATH=src"
start "iCross-Backend" /B /MIN "" ".venv\Scripts\python" -m uvicorn icross.api.main:app --host 0.0.0.0 --port 8000

:: Wait for backend
echo [iCross] 等待后端就绪...
:wait_backend
timeout /t 2 /nobreak >nul
curl -sf http://localhost:8000/health >nul 2>&1
if errorlevel 1 goto wait_backend
echo [  ok] 后端已就绪 http://localhost:8000

echo [iCross] 启动前端 (port 3000)...
cd frontend-react
start "iCross-Frontend" /B /MIN "" "npx" vite --port 3000 --strictPort
cd "%SCRIPT_DIR%"

echo.
echo =====================================
echo    iCross Agent 已启动！
echo    后端: http://localhost:8000
echo    前端: http://localhost:3000
echo =====================================
echo.
echo 关闭此窗口将停止所有服务
echo.

:: Keep the window open
:keep_alive
timeout /t 10 /nobreak >nul
:: Check if backend is still running
curl -sf http://localhost:8000/health >nul 2>&1
if errorlevel 1 (
    echo [fail] 后端似乎已停止运行，请检查日志
    pause
    exit /b 1
)
goto keep_alive
