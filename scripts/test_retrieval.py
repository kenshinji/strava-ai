"""Manual probe for vector-retrieval quality. Print results so a human can eyeball relevance."""

from app.services.rag import retrieve_relevant_activities, get_summary_stats

TEST_QUERIES = [
    "my fastest 5K",
    "long-distance training run last month",
]

TOP_K = 10


def print_results(query: str, results: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"Query: {query}")
    print(f"Returned {len(results)} results")
    print("-" * 60)

    for i, act in enumerate(results, 1):
        print(
            f"  {i:>2}. [{act['start_date'][:10]}] {act['name']}"
            f"  |  {act['distance_km']}km"
            f"  |  pace {act['pace']}"
            f"  |  similarity {act['similarity']}"
        )

    print()


def main():
    print("===== Global stats =====")
    stats = get_summary_stats()
    if stats:
        for k, v in stats.items():
            print(f"  {k}: {v}")
    else:
        print("  (no data)")

    for query in TEST_QUERIES:
        results = retrieve_relevant_activities(query, top_k=TOP_K)
        print_results(query, results)


if __name__ == "__main__":
    main()
