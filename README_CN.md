# iCross Agent — 中文指南

> **AI 驱动的 Ozon 电商运营系统** — 自动完成选品、Listing 生成、定价、广告、财务等全链路运营操作。

---

## 🚀 快速安装

### 安装前准备

你只需要准备：
- **一台电脑**（Windows / macOS / Linux 均可）
- **5 分钟时间**
- **API 密钥**（下文会说明如何获取）

### 方式一：Docker 一键部署（推荐，无需装 Python/Node）

这是最简单的方式，电脑上只需要安装 Docker。

```bash
# 1. 下载项目
git clone https://github.com/Jason-prd/icross-agent.git
cd icross-agent

# 2. 配置 API 密钥
cp .env.example .env
# 用记事本打开 .env，填入你的 API Key（见下方说明）

# 3. 一键启动
docker compose up -d
```

打开浏览器访问 **http://localhost:3000** 即可使用。

> 安装 Docker：https://www.docker.com/products/docker-desktop/

### 方式二：Windows 一键启动

确保已安装 **Python 3.11+** 和 **Node.js 18+**，然后双击：

```batch
start.bat
```

脚本会自动安装所有依赖并启动前后端服务。

> 下载 Python：https://www.python.org/downloads/（安装时勾选 "Add Python to PATH"）
> 下载 Node.js：https://nodejs.org/

### 方式三：macOS / Linux

```bash
./start.sh
```

---

## 🔑 获取 API 密钥

| 服务 | 用途 | 获取方式 | 是否必需 |
|------|------|----------|----------|
| **DeepSeek** | AI 对话主模型 | https://platform.deepseek.com/api_keys → 创建 API Key | ✅ 推荐 |
| **MiniMax** | AI 对话备用模型 | https://platform.minimaxi.com → 创建 API Key + Group ID | ❌ 可选 |
| **Ozon** | 店铺运营（商品/订单/财务） | Ozon 卖家中心 → 设置 → API → 生成密钥对 | ✅ 运营必需 |

### 编辑 .env 文件

用记事本打开 `.env` 文件，填入你的密钥：

```env
# DeepSeek（推荐作为主模型）
DEEPSEEK_API_KEY=sk-你的DeepSeek密钥

# Ozon（运营店铺必需）
OZON_CLIENT_ID=你的Client ID
OZON_API_KEY=你的API Key
```

---

## 🎯 快速上手

### 第一步：配置 LLM 提供商

启动后，打开浏览器进入 **http://localhost:3000** → 点击右上角 **「配置管理」**：

1. 确认 DeepSeek 卡片显示 🟢 **在线**
2. 点击「测试连接」验证 API Key 是否有效
3. 如未自动填入，可手动编辑 Base URL 和模型名

> DeepSeek 默认配置：
> - Base URL: `https://api.deepseek.com/v1`
> - 模型: `deepseek-chat`

### 第二步：添加 Ozon 店铺

在「配置管理」→ 「店铺管理」：

1. 点击「添加店铺」
2. 填入：
   - **店铺 ID**：任意唯一标识，如 `my-shop`
   - **店铺名称**：如「我的 Ozon 店铺」
   - **Ozon Client ID**：从 Ozon 卖家 API 获取
   - **API Key**：对应的 API 密钥
3. 点击「测试连接」验证

### 第三步：开始和 AI Agent 对话

点击顶部导航 **「Agent 对话」**，在聊天框中输入：

```
你好，帮我看看店铺的基本数据
```

Agent 会自动调用 Ozon API 获取数据并回复你。

### 更多示例

```
列出所有待审核草稿
为 XX 产品生成俄语 Listing
查看本月利润分析
检查广告活动效果
从1688搜索蓝牙耳机
帮我处理所有待发货订单
```

---

## 🏠 运营工作台

| 页面 | 功能 | 说明 |
|------|------|------|
| **Agent 对话** | AI 聊天界面 | 和 AI 助手对话，处理所有运营任务 |
| **运营工作台** | 统一管理后台 | 包含看板、选品、商品、订单、财务等 |
| **配置管理** | 系统设置 | 管理 LLM 提供商、店铺、通知等 |

### 运营工作台子页面

| Tab | 功能 |
|-----|------|
| **看板** | 销售趋势图、自动运营状态、关键指标 |
| **选品中心** | 浏览 1688/拼多多 选品结果，导入商品 |
| **商品管理** | 查看和管理 Ozon 商品 |
| **草稿审核** | 审核 AI 生成的 Listing 草稿 |
| **订单管理** | FBO / FBS / rFBS 订单处理 |
| **退货中心** | 退货请求、索赔管理 |
| **财务中心** | 交易流水、销售报表、利润分析 |
| **客服中心** | 买家聊天、问答管理、评价回复 |
| **营销广告** | 广告活动、促销管理 |
| **自动运营** | 自动定价、工作流配置 |
| **报表中心** | 异步报表生成和下载 |

---

## ❓ 常见问题

**Q: 启动时提示端口被占用？**
A: 脚本会自动释放 3000 和 8000 端口。如果其他重要程序在用这些端口，请先关闭它们。

**Q: 不配置 Ozon 密钥能试用吗？**
A: 可以。AI Agent 对话功能可用，但涉及 Ozon 店铺的操作（商品/订单/财务）会提示未配置。

**Q: 启动后页面白屏或无法连接？**
A: 请确保后端（8000）和前端（3000）都已启动。检查终端日志是否有报错。

**Q: 如何更新项目？**
```bash
git pull
# 重新启动即可
```

**Q: 数据存在哪里？**
A: 所有数据存储在 `data/` 目录的 JSON 文件中，无需安装数据库。可以随时备份。

**Q: 如何切换 AI 模型？**
A: 在「配置管理」→「AI 模型配置」中，可以为不同功能指定不同的模型。

---

## 📂 项目结构

```
icross-agent/
├── start.bat              # Windows 一键启动
├── start.sh               # macOS/Linux 一键启动
├── docker-compose.yml     # Docker 部署
├── src/icross/            # Python 后端
│   ├── api/               # FastAPI 接口
│   ├── agents/            # LangGraph AI Agent
│   └── services/          # 业务服务
├── frontend-react/        # React 前端
└── data/                  # 数据文件（自动生成）
```

---

## 📖 技术栈

| 层 | 技术 |
|----|------|
| AI Agent 框架 | LangGraph |
| AI 模型 | DeepSeek / MiniMax / Claude |
| 后端 | FastAPI + WebSocket |
| 前端 | React 18 + Ant Design 5 + Vite |
| 数据存储 | JSON 文件（无需数据库） |

---

## 📝 License

MIT
