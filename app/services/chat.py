from openai import OpenAI
from app.core.config import settings
from app.services.rag import retrieve_relevant_activities, build_context, get_summary_stats

client = OpenAI(api_key=settings.OPENAI_API_KEY)

SYSTEM_PROMPT_TEMPLATE = """You are a professional running data analyst. The user will ask natural-language questions about their running data, and you must answer using the real data provided below.

## Running Data Overview
{summary_stats}

## Activities Relevant to the Current Question
{context}

## Answering Rules
1. Answer using the data provided. Lean on the global, yearly, and monthly stats in the overview whenever they help.
2. When citing specific numbers (distance, pace, heart rate), quote the data precisely.
3. **For any "most recent run" question, you MUST use the activity tagged [MOST RECENT] in the activity list. Do not substitute another activity.**
4. The activity list is sorted newest to oldest, so the first entry is always the latest run.
5. If retrieved activities don't perfectly match the question, still analyze what they do show — don't just say "no data".
6. Only fall back to "not enough data" when the data truly cannot answer the question, and suggest a rephrasing.
7. Format pace as X:XX/km and distances in kilometers.
8. Use ISO-style dates (YYYY-MM-DD) or natural English dates (e.g. "Oct 12, 2025").
9. When analyzing trends, compare monthly data and call out the magnitude of improvement or regression.
10. For year-over-year comparisons, use the yearly stats and give concrete numbers.
11. When giving advice, ground it in the user's actual data — don't suggest something beyond their current level.
12. Stay friendly and encouraging, like a data-aware running coach.
"""


async def chat(
    user_message: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Full chat flow: question -> retrieval -> prompt assembly -> LLM call."""

    relevant_activities = retrieve_relevant_activities(user_message, top_k=10)
    context = build_context(relevant_activities)

    stats = get_summary_stats()
    stats_text = "\n".join(f"- {k}: {v}" for k, v in stats.items()) if stats else "No data available"

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
