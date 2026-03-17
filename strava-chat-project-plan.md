# Chat with Your Strava Data — 项目规划

> 用自然语言跟你的跑步数据对话
> Tech Stack: Python · FastAPI · PostgreSQL + pgvector · OpenAI GPT-4o · React

---

## 项目概述

一个 RAG（Retrieval-Augmented Generation）应用，让用户可以用自然语言查询和分析自己的 Strava 跑步数据。

**用户可以问的问题示例：**

- "我上个月跑了多少公里？"
- "我的半马 PB 是哪次？"
- "帮我分析一下最近三个月的配速趋势"
- "给我制定一个下个月的训练计划"
- "我今年跑量比去年同期多还是少？"

---

## 整体架构

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐     ┌────────────┐
│  React 前端  │ ──> │ FastAPI 后端  │ ──> │ PostgreSQL +    │     │ OpenAI API │
│  对话界面    │ <── │  /chat 接口   │ <── │ pgvector        │     │ GPT-4o     │
└─────────────┘     └──────┬───────┘     └─────────────────┘     └─────┬──────┘
                           │                                           │
                           │  1. 用户提问 → embedding                   │
                           │  2. pgvector 相似度检索                     │
                           │  3. 检索结果作为 context                    │
                           │  4. 发送给 GPT-4o 生成回答 ─────────────────┘
                           │
                    ┌──────┴───────┐
                    │  Strava API  │
                    │  数据同步     │
                    └──────────────┘
```

---

## 一周时间表（周二 → 周日）

| 日期 | Sprint | 核心目标 | 预计时间 |
|------|--------|---------|---------|
| 周二 | Sprint 1 | 项目初始化 + Strava OAuth 授权流程跑通 | 2-3h |
| 周三 | Sprint 1 | 拉取全部跑步数据，清洗后入库 PostgreSQL | 2-3h |
| 周四 | Sprint 2 | 为每条跑步记录生成 embedding，实现向量检索 | 2-3h |
| 周五 | Sprint 3 | 搭 FastAPI 后端，设计 system prompt，对话接口跑通 | 2-3h |
| 周六 | Sprint 3 | 完善对话逻辑，测试各类问题，调优 prompt | 2-3h |
| 周日 | Sprint 4 | 简易 React 对话界面 + Docker Compose 打包 | 2-3h |

---

## Sprint 详情

### Sprint 1: 数据层（周二 - 周三）

**核心目标：** 把你的 Strava 跑步数据全部拉下来，存入 PostgreSQL。

**Features：**
- Strava OAuth 2.0 授权流程（获取 access_token）
- Token 自动刷新机制
- 分页拉取全部跑步活动（Run / TrailRun / VirtualRun）
- PostgreSQL 数据库 schema 设计（activities 表 + chat_history 表）
- 启用 pgvector 扩展，activities 表预留 embedding 列
- 数据清洗：原始 API 数据 → 结构化字段入库
- 为每条活动生成自然语言描述文本（`description_text`），后续用于 embedding

**验收标准：**
- `SELECT count(*) FROM activities` 能看到你所有的跑步记录
- 每条记录都有完整的 `description_text`

---

### Sprint 2: RAG 管道（周四）

**核心目标：** 实现"用户问题 → embedding → 向量检索 → 返回相关跑步记录"的完整链路。

**Features：**
- 调用 OpenAI Embedding API（text-embedding-3-small）为所有活动生成向量
- 向量存入 pgvector
- 实现余弦相似度检索函数：输入自然语言问题，返回最相关的 N 条跑步记录
- 构建 context 拼装函数：把检索结果组织成 LLM 可消费的文本格式
- 汇总统计函数：总跑量、总次数、最长距离、平均配速等全局数据

**验收标准：**
- `retrieve("我最快的5公里")` 返回的结果中，排在前面的确实是短距离高速度的活动
- `retrieve("上个月的长距离拉练")` 返回的结果符合时间和距离的预期

---

### Sprint 3: 对话层（周五 - 周六）

**核心目标：** 搭建 FastAPI 后端，实现完整的 Chat 对话能力。

**Features：**
- FastAPI `/api/chat` 接口，接收用户消息，返回 AI 回复
- System prompt 设计：包含用户数据概览 + 检索到的相关记录 + 回答规则
- 对话历史管理：支持多轮对话，保持上下文连贯
- CORS 配置，允许前端跨域访问
- 能处理多种问题类型：
  - 事实查询（"我上个月跑了多少"）
  - 对比分析（"这个月 vs 上个月"）
  - 趋势分析（"最近配速有没有进步"）
  - 建议生成（"帮我制定训练计划"）

**验收标准：**
- 用 curl 发一条消息能收到基于真实数据的回复
- 连续问两个相关问题，第二个回答能理解上下文

---

### Sprint 4: 前端 + 部署（周日）

**核心目标：** 一个可演示的完整产品。

**Features：**
- React 对话界面：消息输入框 + 消息气泡列表 + 加载状态
- 区分用户消息和 AI 回复的样式
- Docker Compose 一键启动（PostgreSQL + API + 前端）
- 项目 README

**验收标准：**
- `docker-compose up` 后在浏览器里能完成一次完整对话
- 向一个不了解项目的人演示，他能理解这是什么

---

## 通过这个项目要学习和掌握的内容

### 核心线 1：RAG 的完整思维模型

这是目前 AI Engineer 最高频的工作内容。要理解的不只是 "embedding → 检索 → 拼 context → 调 LLM" 这个流程，而是背后的设计决策：

- **数据表示的选择**：为什么要把跑步数据转成自然语言描述再做 embedding，而不是直接用结构化字段？什么时候该用向量检索，什么时候用 SQL 过滤更合适（比如 "上个月" 这种时间限定）？
- **检索参数的 trade-off**：top_k 取多大？取多了 context 太长浪费 token 且引入噪音，取少了可能漏掉关键数据。相似度阈值要不要设？
- **Context 的组织方式**：检索到的记录以什么格式喂给 LLM 效果最好？是 JSON、表格、还是自然语言描述？排序方式影不影响回答质量？
- **端到端的数据流**：从原始 API 数据 → 清洗 → 存储 → embedding → 检索 → context → LLM 回答，每一步的设计选择如何影响最终效果。

### 核心线 2：真实数据场景下的 Prompt Engineering

跟网上 "写一首诗" 的 prompt 教程完全不同，这是面向生产的 prompt 设计：

- **System prompt 架构**：怎么把结构化的数据库记录组织成 LLM 能理解、能准确引用的 context。
- **约束规则设计**：哪些规则是必须的（"不要编造数据"、"数字要精确引用"），哪些是优化体验的（"用中文日期格式"、"像教练一样鼓励"）。
- **Temperature 的选择**：为什么数据分析场景要用低 temperature（0.2-0.3），而建议生成可以稍高。
- **对话历史管理**：保留多少轮历史？保留太多 token 开销大，太少丢失上下文。

### 核心线 3：Structured Data 与 Unstructured Query 的桥接

这是 AI 工程中最常见也最有价值的问题模式：

- **语义鸿沟**：用户说 "我最快的那次半马"，数据库里存的是 `distance=21100, moving_time=5400`。怎么让两个世界对话？
- **两种检索的互补**：向量语义检索擅长理解意图（"轻松跑" → 低心率低配速的活动），SQL 查询擅长精确过滤（"3月份"、"超过10公里"）。理解各自的优势和局限。
- **数据建模的思考**：同一份数据，既要能做结构化查询（聚合、排序、过滤），又要能做语义检索（相似度匹配）。表结构怎么同时满足两种需求。

### 附带学到的实用技能

- **OpenAI API 实战**：Embedding API（text-embedding-3-small）和 Chat Completion API（GPT-4o）两种接口的调用方式、参数调优、错误处理、费用控制。
- **pgvector 向量数据库**：作为 PostgreSQL 扩展使用，比从零学 Pinecone/Weaviate 实用得多。向量存储、余弦相似度检索、索引优化。
- **FastAPI 后端开发**：异步接口、Pydantic 数据校验、CORS 配置、依赖注入。
- **OAuth 2.0 实战**：通过 Strava API 完整走一遍 authorization code flow。
- **Docker 容器化**：Docker Compose 编排多服务应用。

### 深入方向（做完基础版后探索）

- **Hybrid Search**：向量检索 + 关键词/日期过滤的结合，面试高频考点。
- **Evaluation**：怎么量化衡量 RAG 系统的检索质量和回答准确度，这是从 demo 到生产的关键一步。
- **Streaming Response**：SSE 流式输出，提升用户体验。

---

## 简历亮点提炼

完成后，这个项目可以展示的 AI Engineer 技能点：

- **RAG Pipeline**：端到端的检索增强生成系统
- **Embedding + Vector Search**：pgvector 向量数据库实战
- **Prompt Engineering**：结构化数据 → 自然语言 context 的设计
- **LLM API Integration**：OpenAI GPT-4o 集成
- **Full-Stack**：FastAPI + React + PostgreSQL
- **Data Pipeline**：第三方 API 数据清洗入库
