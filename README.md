# Strava Chat

用自然语言跟你的跑步数据对话。RAG 应用，基于 Strava API、PostgreSQL + pgvector、OpenAI GPT-4o。

## 快速开始

### 1. 环境准备

```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env，填入 Strava 和 OpenAI 凭证
```

### 2. 启动 PostgreSQL（Docker）

```bash
docker run -d \
  --name strava-pg \
  -e POSTGRES_DB=strava_chat \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 3. Strava OAuth 授权

1. 在 [Strava API 设置页](https://www.strava.com/settings/api) 创建应用（Callback Domain: `localhost`）
2. 将 Client ID 和 Client Secret 填入 `.env`
3. 启动服务后访问 `http://localhost:8000/auth` 获取授权链接
4. 授权后访问回调 URL，将返回的 `access_token` 和 `refresh_token` 填入 `.env`

### 4. 启动服务

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 5. 验证

```bash
curl http://localhost:8000/health
# 应返回 {"status":"ok"}
```

## 项目结构

```
strava-ai/
├── app/
│   ├── main.py           # FastAPI 入口
│   ├── core/config.py    # 环境配置
│   ├── db/               # 数据库模型与连接
│   ├── services/         # Strava、Embedding、RAG、Chat
│   └── api/              # API 路由
├── scripts/
│   └── sync_strava.py    # 数据同步脚本
└── requirements.txt
```

## 开发计划

详见 `strava-chat-project-plan.md` 和 `strava-chat-implementation-guide.md`。
