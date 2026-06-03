# iCross 选品助手 - Browser Extension

一键捕获 1688 / 拼多多 / 淘宝 产品数据，发送到 iCross Agent 后台自动处理。

## 安装（开发模式）

1. 打开 Chrome，进入 `chrome://extensions`
2. 开启"开发者模式"（右上角）
3. 点击"加载已解压的扩展程序"
4. 选择本目录 (`frontend-extension/`)

## 使用方法

### 自动捕获
- 访问 1688 / 拼多多 / 淘宝 产品详情页
- 插件自动提取：标题、价格、图片、规格参数
- 点击插件图标查看提取结果

### 发送到 iCross
1. 点击插件图标
2. 确认产品信息无误
3. 点击"发送到 iCross" — 发送原始数据
4. 或点击"发送并生成 Listing" — 发送后自动触发 AI 生成俄语 Listing

### 查看历史
- 打开插件弹出页查看最近捕获记录
- 点击历史记录可重新查看产品详情

## 项目结构

```
frontend-extension/
├── manifest.json          # Chrome Extension MV3 配置
├── popup.html             # 弹出页面布局
├── popup.js               # 弹出页面逻辑 (ES Module)
├── popup.css              # 弹出页面样式
├── background.js          # Service Worker (ES Module)
├── content-1688.js        # 1688 页面内容抓取
├── content-pinduoduo.js   # 拼多多页面内容抓取
├── content-taobao.js      # 淘宝/天猫页面内容抓取
├── lib/
│   ├── api.js             # iCross 后端 API 通信
│   ├── storage.js         # Chrome Storage 封装
│   └── types.js           # 类型定义 (JSDoc)
├── icons/                 # 插件图标
└── README.md
```

## 配置

点击插件弹出页 ⚙ 图标，配置：

| 设置项 | 说明 | 默认值 |
|--------|------|--------|
| 服务器地址 | iCross Agent 后端地址 | `http://localhost:8000` |
| API Key | 可选，后端鉴权 | 空 |

## 开发

无需构建步骤，直接修改源码后重载扩展即可。

```bash
# 检查扩展代码
npx web-ext lint
```
