# Chat with Your Strava Data — 技术实施手册

> 这份文档包含具体的命令、代码、配置和设置步骤。
> 配合《项目规划》文档使用。

---

## 目录

1. [项目初始化](#1-项目初始化)
2. [环境配置](#2-环境配置)
3. [Strava API 设置与 OAuth](#3-strava-api-设置与-oauth)
4. [数据库 Schema](#4-数据库-schema)
5. [数据同步脚本](#5-数据同步脚本)
6. [Embedding 服务](#6-embedding-服务)
7. [向量检索与 Context 构建](#7-向量检索与-context-构建)
8. [对话服务与 Prompt 设计](#8-对话服务与-prompt-设计)
9. [FastAPI 接口](#9-fastapi-接口)
10. [Docker 部署](#10-docker-部署)
11. [关键文件清单](#11-关键文件清单)

---

## 1. 项目初始化

```bash
mkdir strava-chat && cd strava-chat

# Python 虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install fastapi uvicorn sqlalchemy psycopg2-binary httpx openai pgvector python-dotenv pydantic-settings

# 项目结构
mkdir -p app/{api,core,db,services,models}
touch app/__init__.py app/main.py
touch app/core/__init__.py app/core/config.py
touch app/db/__init__.py app/db/database.py app/db/models.py
touch app/services/__init__.py app/services/strava.py app/services/embedding.py app/services/rag.py app/services/chat.py
touch app/api/__init__.py app/api/chat.py
mkdir scripts
touch scripts/sync_strava.py
touch .env .gitignore requirements.txt
```

---

## 2. 环境配置

```python
# app/core/config.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Strava
    STRAVA_CLIENT_ID: str
    STRAVA_CLIENT_SECRET: str
    STRAVA_ACCESS_TOKEN: str = ""
    STRAVA_REFRESH_TOKEN: str = ""

    # Database
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/strava_chat"

    # OpenAI
    OPENAI_API_KEY: str
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_CHAT_MODEL: str = "gpt-4o"

    class Config:
        env_file = ".env"

settings = Settings()
```

```bash
# .env
STRAVA_CLIENT_ID=your_client_id
STRAVA_CLIENT_SECRET=your_client_secret
STRAVA_ACCESS_TOKEN=
STRAVA_REFRESH_TOKEN=
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/strava_chat
OPENAI_API_KEY=sk-your-key
```

```bash
# .gitignore
.env
venv/
__pycache__/
*.pyc
```

---

## 3. Strava API 设置与 OAuth

### 3.1 创建 Strava App

1. 去 [https://www.strava.com/settings/api](https://www.strava.com/settings/api)
2. 如果没有 app，创建一个：
   - Application Name: `Strava Chat`
   - Authorization Callback Domain: `localhost`
3. 记下 `Client ID` 和 `Client Secret`，填入 `.env`

### 3.2 Strava 服务代码

```python
# app/services/strava.py
import httpx
from app.core.config import settings

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"


def get_auth_url() -> str:
    """生成 Strava 授权链接，浏览器打开后授权"""
    return (
        f"{STRAVA_AUTH_URL}"
        f"?client_id={settings.STRAVA_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri=http://localhost:8000/auth/callback"
        f"&scope=read,activity:read_all"
    )


async def exchange_token(code: str) -> dict:
    """用 authorization code 换取 access token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(STRAVA_TOKEN_URL, data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
        })
        return response.json()


async def refresh_token(refresh_token: str) -> dict:
    """刷新过期的 access token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(STRAVA_TOKEN_URL, data={
            "client_id": settings.STRAVA_CLIENT_ID,
            "client_secret": settings.STRAVA_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        })
        return response.json()


async def fetch_activities(access_token: str, page: int = 1, per_page: int = 50) -> list:
    """拉取活动列表"""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"{STRAVA_API_BASE}/athlete/activities",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"page": page, "per_page": per_page},
        )
        return response.json()


async def fetch_all_activities(access_token: str) -> list:
    """分页拉取所有活动"""
    all_activities = []
    page = 1
    while True:
        activities = await fetch_activities(access_token, page=page, per_page=100)
        if not activities:
            break
        all_activities.extend(activities)
        page += 1
        print(f"  已拉取 {len(all_activities)} 条活动...")
    return all_activities
```

### 3.3 OAuth 流程操作步骤

```bash
# 1. 在浏览器打开以下链接（替换 YOUR_CLIENT_ID）：
# https://www.strava.com/oauth/authorize?client_id=YOUR_CLIENT_ID&response_type=code&redirect_uri=http://localhost:8000/auth/callback&scope=read,activity:read_all

# 2. 授权后浏览器会跳转到 localhost:8000/auth/callback?code=XXXXXX
#    复制 URL 中的 code 参数

# 3. 用 code 换 token（替换实际值）：
curl -X POST https://www.strava.com/oauth/token \
  -d client_id=YOUR_CLIENT_ID \
  -d client_secret=YOUR_CLIENT_SECRET \
  -d code=YOUR_CODE \
  -d grant_type=authorization_code

# 4. 把返回的 access_token 和 refresh_token 填入 .env
```

---

## 4. 数据库 Schema

### 4.1 启动 PostgreSQL（用 Docker）

```bash
docker run -d \
  --name strava-pg \
  -e POSTGRES_DB=strava_chat \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -p 5432:5432 \
  pgvector/pgvector:pg16
```

### 4.2 SQLAlchemy 模型

```python
# app/db/models.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)            # Strava activity ID
    name = Column(String(255))
    sport_type = Column(String(50))                   # Run, TrailRun, etc.
    start_date = Column(DateTime)
    distance = Column(Float)                          # 米
    moving_time = Column(Integer)                     # 秒
    elapsed_time = Column(Integer)                    # 秒
    total_elevation_gain = Column(Float)              # 米
    average_speed = Column(Float)                     # 米/秒
    max_speed = Column(Float)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)
    average_cadence = Column(Float, nullable=True)
    calories = Column(Float, nullable=True)
    suffer_score = Column(Integer, nullable=True)
    description_text = Column(Text, nullable=True)    # 自然语言描述
    embedding = Column(Vector(1536), nullable=True)   # text-embedding-3-small


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50))
    role = Column(String(20))       # user / assistant
    content = Column(Text)
    created_at = Column(DateTime)
```

### 4.3 数据库初始化

```python
# app/db/database.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.db.models import Base

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def init_db():
    """启用 pgvector 扩展 + 建表"""
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()
    Base.metadata.create_all(bind=engine)
    print("数据库初始化完成！")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
```

---

## 5. 数据同步脚本

```python
# scripts/sync_strava.py
import asyncio
from datetime import datetime
from app.services.strava import fetch_all_activities
from app.db.database import init_db, SessionLocal
from app.db.models import Activity
from app.core.config import settings


def format_pace(speed_ms: float) -> str:
    """米/秒 → 配速 X:XX/km"""
    if speed_ms <= 0:
        return "N/A"
    pace_seconds = 1000 / speed_ms
    minutes = int(pace_seconds // 60)
    seconds = int(pace_seconds % 60)
    return f"{minutes}:{seconds:02d}"


def build_description(act: dict) -> str:
    """把一条跑步活动转成自然语言描述"""
    date = datetime.fromisoformat(act["start_date_local"].replace("Z", "+00:00"))
    distance_km = act["distance"] / 1000
    pace = format_pace(act["average_speed"])
    duration_min = act["moving_time"] / 60

    desc = (
        f"{date.strftime('%Y年%m月%d日')} "
        f"{act.get('name', '跑步活动')}，"
        f"类型：{act.get('sport_type', 'Run')}，"
        f"距离：{distance_km:.2f}公里，"
        f"用时：{duration_min:.0f}分钟，"
        f"配速：{pace}/km"
    )

    if act.get("total_elevation_gain"):
        desc += f"，累计爬升：{act['total_elevation_gain']:.0f}米"
    if act.get("average_heartrate"):
        desc += f"，平均心率：{act['average_heartrate']:.0f}bpm"
    if act.get("suffer_score"):
        desc += f"，痛苦指数：{act['suffer_score']}"

    return desc


async def sync():
    init_db()
    print("开始同步 Strava 数据...")

    activities = await fetch_all_activities(settings.STRAVA_ACCESS_TOKEN)
    print(f"共拉取 {len(activities)} 条活动")

    db = SessionLocal()
    count = 0
    for act in activities:
        if act.get("sport_type") not in ("Run", "TrailRun", "VirtualRun"):
            continue

        existing = db.query(Activity).filter(Activity.id == act["id"]).first()
        if existing:
            continue

        activity = Activity(
            id=act["id"],
            name=act.get("name"),
            sport_type=act.get("sport_type"),
            start_date=datetime.fromisoformat(
                act["start_date_local"].replace("Z", "+00:00")
            ),
            distance=act.get("distance"),
            moving_time=act.get("moving_time"),
            elapsed_time=act.get("elapsed_time"),
            total_elevation_gain=act.get("total_elevation_gain"),
            average_speed=act.get("average_speed"),
            max_speed=act.get("max_speed"),
            average_heartrate=act.get("average_heartrate"),
            max_heartrate=act.get("max_heartrate"),
            average_cadence=act.get("average_cadence"),
            calories=act.get("calories"),
            suffer_score=act.get("suffer_score"),
            description_text=build_description(act),
        )
        db.add(activity)
        count += 1

    db.commit()
    db.close()
    print(f"新增 {count} 条跑步记录入库！")


if __name__ == "__main__":
    asyncio.run(sync())
```

```bash
# 运行同步
python -m scripts.sync_strava
```

---

## 6. Embedding 服务

```python
# app/services/embedding.py
from openai import OpenAI
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Activity

client = OpenAI(api_key=settings.OPENAI_API_KEY)


def get_embedding(text: str) -> list[float]:
    """生成单条文本的 embedding 向量"""
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def embed_all_activities():
    """批量为所有活动生成 embedding"""
    db = SessionLocal()
    activities = db.query(Activity).filter(
        Activity.embedding.is_(None),
        Activity.description_text.isnot(None),
    ).all()

    print(f"需要生成 embedding 的活动：{len(activities)} 条")

    batch_size = 20
    for i in range(0, len(activities), batch_size):
        batch = activities[i:i + batch_size]
        texts = [a.description_text for a in batch]

        response = client.embeddings.create(
            model=settings.OPENAI_EMBEDDING_MODEL,
            input=texts,
        )

        for activity, data in zip(batch, response.data):
            activity.embedding = data.embedding

        db.commit()
        print(f"  已处理 {min(i + batch_size, len(activities))}/{len(activities)}")

    db.close()
    print("所有 embedding 生成完毕！")
```

```bash
# 运行 embedding 生成
python -c "from app.services.embedding import embed_all_activities; embed_all_activities()"
```

---

## 7. 向量检索与 Context 构建

```python
# app/services/rag.py
from sqlalchemy import text
from app.db.database import SessionLocal
from app.db.models import Activity
from app.services.embedding import get_embedding


def retrieve_relevant_activities(
    query: str,
    top_k: int = 10,
    sport_type: str = None,
) -> list[dict]:
    """用户问题 → embedding → pgvector 余弦相似度搜索"""
    query_embedding = get_embedding(query)
    db = SessionLocal()

    sql = """
        SELECT
            id, name, sport_type, start_date,
            distance, moving_time, average_speed,
            average_heartrate, total_elevation_gain,
            description_text,
            embedding <=> :query_embedding AS distance
        FROM activities
        WHERE embedding IS NOT NULL
    """

    if sport_type:
        sql += " AND sport_type = :sport_type"

    sql += " ORDER BY distance ASC LIMIT :top_k"

    params = {"query_embedding": str(query_embedding), "top_k": top_k}
    if sport_type:
        params["sport_type"] = sport_type

    result = db.execute(text(sql), params).fetchall()
    db.close()

    return [
        {
            "id": row.id,
            "name": row.name,
            "sport_type": row.sport_type,
            "start_date": row.start_date.isoformat(),
            "distance_km": round(row.distance / 1000, 2),
            "moving_time_min": round(row.moving_time / 60, 1),
            "pace": _speed_to_pace(row.average_speed),
            "heartrate": row.average_heartrate,
            "elevation": row.total_elevation_gain,
            "description": row.description_text,
            "similarity": round(1 - row.distance, 4),
        }
        for row in result
    ]


def build_context(activities: list[dict]) -> str:
    """把检索结果拼成 LLM context"""
    if not activities:
        return "没有找到相关的跑步记录。"

    lines = ["以下是与用户问题最相关的跑步记录：\n"]
    for i, act in enumerate(activities, 1):
        lines.append(f"{i}. {act['description']} (相似度: {act['similarity']})")
    return "\n".join(lines)


def get_summary_stats() -> dict:
    """计算汇总统计，作为 system prompt 的额外 context"""
    db = SessionLocal()
    activities = db.query(Activity).all()
    db.close()

    if not activities:
        return {}

    total_distance = sum(a.distance for a in activities) / 1000
    total_time = sum(a.moving_time for a in activities) / 3600
    distances = [a.distance for a in activities]
    paces = [a.average_speed for a in activities if a.average_speed]

    return {
        "total_runs": len(activities),
        "total_distance_km": round(total_distance, 1),
        "total_hours": round(total_time, 1),
        "longest_run_km": round(max(distances) / 1000, 2),
        "avg_pace": _speed_to_pace(sum(paces) / len(paces)) if paces else "N/A",
        "date_range": (
            f"{min(a.start_date for a in activities).strftime('%Y-%m-%d')}"
            f" 至 "
            f"{max(a.start_date for a in activities).strftime('%Y-%m-%d')}"
        ),
    }


def _speed_to_pace(speed_ms: float) -> str:
    if speed_ms <= 0:
        return "N/A"
    pace_s = 1000 / speed_ms
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"
```

### pgvector 索引（数据量大时添加）

```sql
-- 几百条数据暂时不需要，上千条后加
CREATE INDEX ON activities
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 50);
```

---

## 8. 对话服务与 Prompt 设计

```python
# app/services/chat.py
from openai import OpenAI
from app.core.config import settings
from app.services.rag import retrieve_relevant_activities, build_context, get_summary_stats

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT_TEMPLATE = """你是一个专业的跑步数据分析助手。用户会用自然语言问关于他跑步数据的问题，你需要基于提供的真实数据来回答。

## 用户跑步数据概览
{summary_stats}

## 与当前问题相关的跑步记录
{context}

## 回答规则
1. 只基于提供的数据回答，不要编造数据
2. 涉及具体数字时（距离、配速、心率），请精确引用数据
3. 如果数据不足以回答问题，诚实说明
4. 配速格式用 X:XX/km，距离用公里
5. 日期用中文格式（X年X月X日）
6. 分析趋势时，指出具体的进步或退步
7. 给建议时，基于用户的实际数据水平，不要给超出能力的建议
8. 保持友好、鼓励的语气，像一个懂数据的跑步教练
"""


async def chat(
    user_message: str,
    chat_history: list[dict] = None,
) -> str:
    """完整对话流程：提问 → 检索 → 构建 prompt → 调用 LLM"""

    # 1. 检索相关活动
    relevant_activities = retrieve_relevant_activities(user_message, top_k=10)
    context = build_context(relevant_activities)

    # 2. 汇总统计
    stats = get_summary_stats()
    stats_text = "\n".join(f"- {k}: {v}" for k, v in stats.items()) if stats else "暂无数据"

    # 3. 构建 system prompt
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        summary_stats=stats_text,
        context=context,
    )

    # 4. 消息列表
    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-12:])  # 保留最近 6 轮
    messages.append({"role": "user", "content": user_message})

    # 5. 调用 GPT-4o
    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=1000,
    )

    return response.choices[0].message.content
```

---

## 9. FastAPI 接口

```python
# app/api/chat.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.services.chat import chat

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    history: list[dict] = []


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    try:
        reply = await chat(
            user_message=request.message,
            chat_history=request.history,
        )
        return ChatResponse(reply=reply, session_id=request.session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

```python
# app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.chat import router as chat_router
from app.db.database import init_db

app = FastAPI(title="Strava Chat API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router, prefix="/api")


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok"}
```

```bash
# 启动后端
uvicorn app.main:app --reload --port 8000

# 测试
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "我上个月跑了多少公里？"}'
```

---

## 10. Docker 部署

```yaml
# docker-compose.yml
version: "3.8"
services:
  db:
    image: pgvector/pgvector:pg16
    environment:
      POSTGRES_DB: strava_chat
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data

  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://postgres:postgres@db:5432/strava_chat
    env_file:
      - .env
    depends_on:
      - db

  frontend:
    build: ./strava-chat-ui
    ports:
      - "3000:3000"
    depends_on:
      - api

volumes:
  pgdata:
```

```dockerfile
# Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```bash
# 一键启动
docker-compose up --build
```

---

## 11. 关键文件清单

```
strava-chat/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口
│   ├── core/
│   │   ├── __init__.py
│   │   └── config.py           # 环境变量配置
│   ├── db/
│   │   ├── __init__.py
│   │   ├── database.py         # DB 连接 + 初始化
│   │   └── models.py           # SQLAlchemy 模型
│   ├── services/
│   │   ├── __init__.py
│   │   ├── strava.py           # Strava API 交互
│   │   ├── embedding.py        # OpenAI Embedding
│   │   ├── rag.py              # 检索 + Context 构建
│   │   └── chat.py             # 对话逻辑 + Prompt
│   └── api/
│       ├── __init__.py
│       └── chat.py             # API 路由
├── scripts/
│   └── sync_strava.py          # 数据同步脚本
├── strava-chat-ui/             # React 前端（Sprint 4 再建）
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env
├── .gitignore
└── README.md
```
