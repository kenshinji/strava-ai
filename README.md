# Strava AI Chat

用自然语言跟你的跑步数据对话。一个完整的 RAG 应用，基于 Strava API、PostgreSQL + pgvector、OpenAI GPT-4o 和 React。

## 技术栈

- **后端**：Python · FastAPI · SQLAlchemy · OpenAI API
- **数据库**：PostgreSQL + pgvector（向量检索）
- **前端**：React · Vite
- **部署**：Docker Compose

## 快速启动（Docker Compose）

```bash
# 1. 克隆项目
git clone <repo-url> && cd strava-ai

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入 Strava 和 OpenAI 凭证

# 3. 一键启动
docker-compose up --build

# 4. 打开浏览器
# 前端：http://localhost:3000
# API：http://localhost:8000
# Health check：http://localhost:8000/health
```

## 本地开发

### 后端

```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd strava-chat-ui
npm install
npm run dev
```

### 数据同步

```bash
# Strava OAuth 授权
# 1. 在 https://www.strava.com/settings/api 创建应用（Callback Domain: localhost）
# 2. 将 Client ID / Client Secret 填入 .env
# 3. 访问 http://localhost:8000/auth 完成授权
# 4. 将返回的 token 填入 .env

# 同步跑步数据
python -m scripts.sync_strava

# 生成 embedding
python -c "from app.services.embedding import embed_all_activities; embed_all_activities()"
```

## 项目结构

```
strava-ai/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── core/config.py       # 环境配置
│   ├── db/
│   │   ├── database.py      # DB 连接 + 初始化
│   │   └── models.py        # SQLAlchemy 模型
│   ├── services/
│   │   ├── strava.py        # Strava API 交互
│   │   ├── embedding.py     # OpenAI Embedding
│   │   ├── rag.py           # 向量检索 + Context 构建
│   │   └── chat.py          # 对话逻辑 + Prompt
│   └── api/
│       └── chat.py          # Chat API 路由
├── strava-chat-ui/          # React 前端
├── scripts/
│   ├── sync_strava.py       # 数据同步脚本
│   ├── test_retrieval.py    # 检索质量测试
│   └── test_chat.py         # 对话质量测试
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```
