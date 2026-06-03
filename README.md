# iCross Agent

AI-powered e-commerce operations system for Ozon (Russian marketplace).

## Quick Start

### Backend

```bash
# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env，填入 API Key

# 启动 API 服务 (热重载)
uv run uvicorn icross.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend-react
npm install
npm run dev
```

### URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| API Server | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |

### Tests

```bash
uv run pytest tests/ -v
```
