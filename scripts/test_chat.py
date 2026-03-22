"""系统化测试对话质量：四种问题类型 + 多轮对话。"""

import asyncio
from app.services.chat import chat

SINGLE_TURN_TESTS = [
    ("事实查询", "我总共跑了多少公里？平均配速是多少？"),
    ("事实查询", "我最长的一次跑步是多少公里？那次跑了多久？"),
    ("对比分析", "我今年的跑量和去年比怎么样？"),
    ("趋势分析", "最近三个月我的配速有没有进步？"),
    ("建议生成", "根据我目前的数据，帮我制定一个下个月的跑步训练计划"),
]

MULTI_TURN_TEST = [
    "我跑过最远的一次是哪次？",
    "那次的配速和心率怎么样？跟我平时的水平比如何？",
]


async def run_single_turn():
    print("=" * 70)
    print("单轮对话测试")
    print("=" * 70)

    for category, question in SINGLE_TURN_TESTS:
        print(f"\n--- [{category}] ---")
        print(f"问：{question}")
        reply = await chat(question)
        print(f"答：{reply}")
        print()


async def run_multi_turn():
    print("=" * 70)
    print("多轮对话测试")
    print("=" * 70)

    history = []
    for i, question in enumerate(MULTI_TURN_TEST, 1):
        print(f"\n--- 第 {i} 轮 ---")
        print(f"问：{question}")
        reply = await chat(question, chat_history=history)
        print(f"答：{reply}")
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        print()


async def main():
    await run_single_turn()
    await run_multi_turn()
    print("=" * 70)
    print("全部测试完成")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
