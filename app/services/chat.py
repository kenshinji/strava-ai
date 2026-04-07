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
1. 尽力基于提供的数据回答，充分利用"数据概览"中的全局统计、年度统计和月度统计
2. 涉及具体数字时（距离、配速、心率），请精确引用数据
3. **"最近一次跑步"必须使用记录列表中标注【最近一次】的那条记录，不得使用其他记录代替**
4. 跑步记录列表已按时间从新到旧排列，第一条即为最新活动
5. 当检索到的相关记录不完全匹配用户问题时，仍应分析已有记录，指出它们能说明什么，而不是简单说"没有数据"
6. 只有在数据确实完全无法回答时，才诚实说明数据不足，并建议用户换一种问法
7. 配速格式用 X:XX/km，距离用公里
8. 日期用中文格式（X年X月X日）
9. 分析趋势时，用月度数据对比，指出具体的进步或退步幅度
10. 做年度对比时，使用年度统计数据给出具体数字
11. 给建议时，基于用户的实际数据水平，不要给超出能力的建议
12. 保持友好、鼓励的语气，像一个懂数据的跑步教练
"""


async def chat(
    user_message: str,
    chat_history: list[dict] | None = None,
) -> str:
    """完整对话流程：提问 → 检索 → 构建 prompt → 调用 LLM"""

    relevant_activities = retrieve_relevant_activities(user_message, top_k=10)
    context = build_context(relevant_activities)

    stats = get_summary_stats()
    stats_text = "\n".join(f"- {k}: {v}" for k, v in stats.items()) if stats else "暂无数据"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        summary_stats=stats_text,
        context=context,
    )

    messages = [{"role": "system", "content": system_prompt}]
    if chat_history:
        messages.extend(chat_history[-12:])
    messages.append({"role": "user", "content": user_message})

    response = client.chat.completions.create(
        model=settings.OPENAI_CHAT_MODEL,
        messages=messages,
        temperature=0.3,
        max_tokens=1000,
    )

    return response.choices[0].message.content
