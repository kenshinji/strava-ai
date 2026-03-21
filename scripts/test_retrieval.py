"""手动测试向量检索质量，肉眼判断结果是否合理。"""

from app.services.rag import retrieve_relevant_activities, get_summary_stats

TEST_QUERIES = [
    "我最快的5公里",
    "上个月的长距离拉练",
]

TOP_K = 10


def print_results(query: str, results: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"查询：{query}")
    print(f"返回 {len(results)} 条结果")
    print("-" * 60)

    for i, act in enumerate(results, 1):
        print(
            f"  {i:>2}. [{act['start_date'][:10]}] {act['name']}"
            f"  |  {act['distance_km']}km"
            f"  |  配速 {act['pace']}"
            f"  |  相似度 {act['similarity']}"
        )

    print()


def main():
    print("===== 全局统计 =====")
    stats = get_summary_stats()
    if stats:
        for k, v in stats.items():
            print(f"  {k}: {v}")
    else:
        print("  （无数据）")

    for query in TEST_QUERIES:
        results = retrieve_relevant_activities(query, top_k=TOP_K)
        print_results(query, results)


if __name__ == "__main__":
    main()
