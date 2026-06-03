#!/bin/bash
# iCross Agent — One-click setup & start
# Backend=8000  Frontend=3000

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[iCross]${NC} $1"; }
ok()    { echo -e "${GREEN}[  ok]${NC} $1"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $1"; }
fail()  { echo -e "${RED}[fail]${NC} $1"; }

# ──────────────────────────────────────
# Step 1: Environment variables
# ──────────────────────────────────────
if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
    warn ".env 不存在，已从 .env.example 创建"
    warn "请编辑 .env 填入你的 API keys 后重新运行"
  else
    fail ".env.example 也不存在，请手动创建 .env"
  fi
  exit 1
fi

# Check required keys (warn if still placeholders)
source .env 2>/dev/null || true
if echo "${DEEPSEEK_API_KEY:-}" | grep -q "your-deepseek"; then
  warn "DEEPSEEK_API_KEY 尚未配置"
fi
if [ -z "${DEEPSEEK_API_KEY:-}" ] && [ -z "${MINIMAX_API_KEY:-}" ]; then
  warn "至少需要配置 DEEPSEEK_API_KEY 或 MINIMAX_API_KEY"
fi
if [ -z "${OZON_CLIENT_ID:-}" ] || [ -z "${OZON_API_KEY:-}" ]; then
  warn "OZON_CLIENT_ID / OZON_API_KEY 尚未配置（运营功能不可用）"
fi

# ──────────────────────────────────────
# Step 2: Python virtual env + deps
# ──────────────────────────────────────
PYTHON=.venv/Scripts/python
PIP=.venv/Scripts/pip

install_backend_deps() {
  info "正在安装 Python 依赖..."
  if command -v uv &>/dev/null; then
    uv sync
  else
    # Fallback: pip with editable installs
    python -m venv .venv
    $PIP install --upgrade pip
    $PIP install -e vendors/langchain/libs/core
    $PIP install -e vendors/langchain-community/libs/community
    $PIP install -e vendors/langgraph/libs/langgraph
    $PIP install -e vendors/langgraph/libs/checkpoint
    $PIP install -e vendors/langgraph/libs/prebuilt
    $PIP install -e vendors/langchain/libs/partners/anthropic
    $PIP install -e vendors/langchain/libs/partners/openai
    $PIP install -e vendors/rembg
    $PIP install fastapi[standard] uvicorn[standard] pydantic python-dotenv httpx anthropic openai websockets apscheduler Pillow lark-oapi
    $PIP install "langchain-anthropic>=0.3.0" "langchain-openai>=0.3.0"
  fi
}

if [ ! -f "$PYTHON" ]; then
  info "正在创建虚拟环境并安装后端依赖..."
  install_backend_deps
  ok "后端依赖安装完成"
else
  ok "虚拟环境已就绪"
fi

# ──────────────────────────────────────
# Step 3: Frontend deps
# ──────────────────────────────────────
if [ ! -d frontend-react/node_modules ]; then
  info "正在安装前端依赖 (npm install)..."
  cd frontend-react
  npm install
  cd "$SCRIPT_DIR"
  ok "前端依赖安装完成"
else
  ok "前端依赖已就绪"
fi

# ──────────────────────────────────────
# Step 4: Kill processes on our ports
# ──────────────────────────────────────
echo ""
info "检查端口占用..."
for port in 3000 8000; do
  pids=$(netstat -ano 2>/dev/null | grep LISTENING | grep ":$port " | awk '{print $NF}' | sort -u)
  for pid in $pids; do
    [ -n "$pid" ] && [ "$pid" != "0" ] && taskkill //F //PID $pid 2>/dev/null || true
  done
done
sleep 2

# ──────────────────────────────────────
# Step 5: Start servers
# ──────────────────────────────────────
echo ""
info "启动后端 (port 8000)..."
PYTHONPATH="src${PYTHONPATH:+:$PYTHONPATH}" $PYTHON -m uvicorn icross.api.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
sleep 4

# Health check
if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
  ok "后端已就绪 http://localhost:8000"
else
  warn "后端启动较慢，继续等待..."
  sleep 5
fi

info "启动前端 (port 3000)..."
cd frontend-react
npx vite --port 3000 --strictPort &
FRONTEND_PID=$!
cd "$SCRIPT_DIR"

echo ""
echo -e "${GREEN}=================================${NC}"
echo -e "${GREEN}  iCross Agent 已启动${NC}"
echo -e "${GREEN}  后端:  http://localhost:8000${NC}"
echo -e "${GREEN}  前端:  http://localhost:3000${NC}"
echo -e "${GREEN}=================================${NC}"
echo ""
echo "按 Ctrl+C 停止所有服务"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; echo ''; ok '服务已停止'; exit 0" SIGINT SIGTERM
wait
