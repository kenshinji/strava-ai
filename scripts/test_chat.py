"""Systematic chat-quality probe: four question categories + a multi-turn conversation."""

import asyncio
from app.services.chat import chat

SINGLE_TURN_TESTS = [
    ("factual", "How many kilometers have I run in total? What's my average pace?"),
    ("factual", "What was my longest run, and how long did it take?"),
    ("comparison", "How does my mileage this year compare to last year?"),
    ("trend", "Has my pace improved over the last three months?"),
    ("advice", "Based on my data, draft a training plan for next month."),
]

MULTI_TURN_TEST = [
    "What was the longest run I've ever done?",
    "How were the pace and heart rate on that run compared to my usual level?",
]


async def run_single_turn():
    print("=" * 70)
    print("Single-turn tests")
    print("=" * 70)

    for category, question in SINGLE_TURN_TESTS:
        print(f"\n--- [{category}] ---")
        print(f"Q: {question}")
        reply = await chat(question)
        print(f"A: {reply}")
        print()


async def run_multi_turn():
    print("=" * 70)
    print("Multi-turn test")
    print("=" * 70)

    history = []
    for i, question in enumerate(MULTI_TURN_TEST, 1):
        print(f"\n--- Turn {i} ---")
        print(f"Q: {question}")
        reply = await chat(question, chat_history=history)
        print(f"A: {reply}")
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": reply})
        print()


async def main():
    await run_single_turn()
    await run_multi_turn()
    print("=" * 70)
    print("All tests done")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
