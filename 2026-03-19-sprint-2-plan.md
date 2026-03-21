# 2026-03-19 Plan - Sprint 2 RAG 管道

## 今日目标
完成从“用户问题”到“检索相关跑步记录”的完整链路，覆盖以下能力：

- 调用 OpenAI Embedding API 为活动生成向量
- 将向量写入 PostgreSQL `pgvector`
- 实现自然语言问题的向量检索
- 实现可供 LLM 使用的 context 拼装
- 实现全局统计函数
- 完成两个验收查询的手动验证

## 当前状态
已完成：

- Strava OAuth 授权流程
- Strava 活动同步脚本
- `activities` 表与 `chat_history` 表
- `description_text` 生成逻辑

未完成：

- Embedding 服务
- 向量回填脚本
- RAG 检索服务
- Context 拼装函数
- 汇总统计函数
- 检索测试脚本

已确认风险：

- `.env` 里的 `OPENAI_API_KEY` 目前还是占位值，今天开始前必须替换
- 当前无法确认本机 PostgreSQL 是否已运行，执行前需手动检查

## 手动执行步骤

### 1. 准备环境
1. 激活虚拟环境：
   ```bash
   source venv/bin/activate
   ```
2. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
3. 打开 `.env`，把 `OPENAI_API_KEY=sk-your-key` 替换成真实 key
4. 确认 PostgreSQL 已启动，且 `strava_chat` 数据库可连接

### 2. 检查 Sprint 1 数据是否完整
1. 检查 `activities` 表是否已有数据
2. 检查 `description_text` 是否已生成
3. 如果数据不存在或不完整，重新执行同步：
   ```bash
   python -m scripts.sync_strava
   ```

验收点：

- `activities` 总数大于 0
- 大部分或全部活动都有 `description_text`

### 3. 实现 Embedding 服务
在 `app/services/embedding.py` 中新增：

1. `get_embedding(text: str) -> list[float]`
   - 使用 `text-embedding-3-small`
   - 输入单条文本，输出 1536 维向量

2. `embed_all_activities()`
   - 查询 `embedding IS NULL AND description_text IS NOT NULL` 的活动
   - 按批次生成 embedding
   - 将结果写回 `activities.embedding`
   - 每批 `commit`

实现要求：

- 使用批量请求，不要一条一条调用
- 批大小先用 `20`
- 打印处理进度，方便观察

### 4. 执行向量回填
运行：

```bash
python -c "from app.services.embedding import embed_all_activities; embed_all_activities()"
```

完成后检查：

- `embedding IS NOT NULL` 的数量是否接近有 `description_text` 的活动总数
- 运行过程中是否有单批失败
- 是否存在明显异常值或空向量

### 5. 实现 RAG 检索服务
在 `app/services/rag.py` 中新增以下内容：

1. `_speed_to_pace(speed_ms)`
   - 将 m/s 转为 `X:XX/km`

2. `retrieve_relevant_activities(query, top_k=10, sport_type=None)`
   - 先对用户 query 做 embedding
   - 使用 pgvector 余弦距离检索活动
   - 只检索 `embedding IS NOT NULL` 的记录
   - 按相似度从高到低返回 top N

3. 返回字段至少包括：
   - `id`
   - `name`
   - `sport_type`
   - `start_date`
   - `distance_km`
   - `moving_time_min`
   - `pace`
   - `heartrate`
   - `elevation`
   - `description`
   - `similarity`

### 6. 实现 Context 拼装
在 `app/services/rag.py` 中实现：

- `build_context(activities: list[dict]) -> str`

要求：

- 把检索结果拼成 LLM 可直接消费的文本
- 每条记录至少包含日期、名称、距离、配速、相似度、原始描述
- 没有结果时返回固定文案，不返回空字符串

### 7. 实现全局统计函数
在 `app/services/rag.py` 中实现：

- `get_summary_stats() -> dict`

至少返回：

- `total_runs`
- `total_distance_km`
- `total_hours`
- `longest_run_km`
- `avg_pace`
- `date_range`

要求：

- 平均配速基于 `average_speed` 计算后再转字符串
- 距离统一使用公里
- 时间统一使用小时或分钟，不混乱

### 8. 编写手动测试脚本
新增一个简单脚本，例如 `scripts/test_retrieval.py`，用于：

1. 调用 `retrieve_relevant_activities()`
2. 固定测试以下两个问题：
   - `我最快的5公里`
   - `上个月的长距离拉练`
3. 打印前 5 到 10 条结果，展示：
   - 日期
   - 名称
   - 距离
   - 配速
   - 相似度

目标是让你能直接肉眼判断检索质量。

### 9. 做第一次验收：最快的 5 公里
运行：

```python
retrieve_relevant_activities("我最快的5公里")
```

检查重点：

- 前排结果是否主要是短距离活动
- 配速是否明显快
- 是否混入很多长距离慢跑记录

如果结果不理想，优先检查：

- `description_text` 是否明确写了“距离”和“配速”
- `top_k` 是否过大
- 返回排序是否正确

### 10. 做第二次验收：上个月的长距离拉练
运行：

```python
retrieve_relevant_activities("上个月的长距离拉练")
```

检查重点：

- 前排结果是否集中在上个月
- 距离是否明显偏长
- 是否有很多不相关的普通慢跑混入

如果结果不理想，优先检查：

- 日期是否在 `description_text` 中表达得足够清晰
- 长距离特征是否在文本里体现出来
- 是否需要缩小 `top_k`

### 11. 小范围调优
如果两个查询效果一般，今天只做轻量调优，不扩 scope。

优先顺序：

1. 优化 `description_text` 的表达质量
2. 调整 `top_k`
3. 调整 context 展示格式

今天不做：

- Hybrid retrieval
- SQL 时间过滤
- Chat 接口接入
- Prompt 设计
- 前端联调

## 今日完成标准
今天结束时，应满足以下条件：

- 所有历史活动已成功生成 embedding
- 可以通过自然语言 query 返回相关活动
- `build_context()` 可输出稳定文本
- `get_summary_stats()` 可返回全局摘要
- `retrieve("我最快的5公里")` 结果基本符合预期
- `retrieve("上个月的长距离拉练")` 结果基本符合预期

## 交付物
今天应新增或完成的代码模块：

- `app/services/embedding.py`
- `app/services/rag.py`
- `scripts/test_retrieval.py`

## 备注
今天的目标是先把 Sprint 2 的“纯向量检索版本”跑通，不引入额外复杂度。

已知限制：

- “上个月”这类时间语义仅靠 embedding 可能不够稳定
- 如果该类问题结果不够理想，记录为下一步优化项，在后续引入“向量检索 + 结构化过滤”
