from sqlalchemy import text
from app.db.database import SessionLocal
from app.db.models import Activity
from app.services.embedding import get_embedding


def _speed_to_pace(speed_ms: float) -> str:
    """将 m/s 转为配速字符串 X:XX/km"""
    if not speed_ms or speed_ms <= 0:
        return "N/A"
    pace_s = 1000 / speed_ms
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"


def get_recent_activities(limit: int = 5) -> list[dict]:
    """按时间倒序获取最近的活动，用于确保最新数据始终在 context 中"""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id, name, sport_type, start_date,
                       distance, moving_time, average_speed,
                       average_heartrate, total_elevation_gain,
                       description_text
                FROM activities
                WHERE embedding IS NOT NULL
                ORDER BY start_date DESC
                LIMIT :limit
            """),
            {"limit": limit},
        ).fetchall()

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
                "similarity": None,
            }
            for row in rows
        ]
    finally:
        db.close()


def retrieve_relevant_activities(
    query: str,
    top_k: int = 10,
    sport_type: str | None = None,
) -> list[dict]:
    """用户问题 → embedding → pgvector 余弦距离检索最相关活动。
    结果会与最近 5 条活动合并（去重），确保时间相关问题能找到最新数据。
    """
    query_embedding = get_embedding(query)
    db = SessionLocal()

    try:
        sql = """
            SELECT
                id, name, sport_type, start_date,
                distance, moving_time, average_speed,
                average_heartrate, total_elevation_gain,
                description_text,
                embedding <=> :query_embedding AS cosine_distance
            FROM activities
            WHERE embedding IS NOT NULL
        """

        if sport_type:
            sql += " AND sport_type = :sport_type"

        sql += " ORDER BY cosine_distance ASC LIMIT :top_k"

        params = {"query_embedding": str(query_embedding), "top_k": top_k}
        if sport_type:
            params["sport_type"] = sport_type

        rows = db.execute(text(sql), params).fetchall()

        semantic_results = [
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
                "similarity": round(1 - row.cosine_distance, 4),
            }
            for row in rows
        ]
    finally:
        db.close()

    # 合并最近活动，确保时间相关问题不会遗漏最新数据
    recent = get_recent_activities(limit=5)
    seen_ids = {a["id"] for a in semantic_results}
    merged = semantic_results + [a for a in recent if a["id"] not in seen_ids]
    return merged


def build_context(activities: list[dict]) -> str:
    """把检索结果拼成 LLM 可直接消费的文本。
    按 start_date 倒序展示，最新活动排在最前面并明确标注。
    """
    if not activities:
        return "没有找到相关的跑步记录。"

    sorted_acts = sorted(activities, key=lambda a: a["start_date"], reverse=True)

    lines = ["以下是相关跑步记录（按时间从新到旧排列）：\n"]
    for i, act in enumerate(sorted_acts, 1):
        label = "【最近一次】" if i == 1 else f"{i}."
        similarity_str = f" | 相似度 {act['similarity']}" if act["similarity"] is not None else ""
        lines.append(
            f"{label} [{act['start_date'][:10]}] {act['name']}"
            f" | {act['distance_km']}km | 配速 {act['pace']}"
            f"{similarity_str}"
            f"\n   {act['description']}"
        )

    return "\n".join(lines)


def get_summary_stats() -> dict:
    """计算全局跑步汇总统计，用于 system prompt 的额外 context"""
    db = SessionLocal()
    try:
        activities = db.query(Activity).all()

        if not activities:
            return {}

        total_distance = sum(a.distance for a in activities) / 1000
        total_time = sum(a.moving_time for a in activities) / 3600
        distances = [a.distance for a in activities]
        speeds = [a.average_speed for a in activities if a.average_speed]
        dates = [a.start_date for a in activities]

        yearly = {}
        for a in activities:
            year = a.start_date.strftime("%Y")
            yearly.setdefault(year, {"runs": 0, "distance": 0.0, "time": 0})
            yearly[year]["runs"] += 1
            yearly[year]["distance"] += a.distance
            yearly[year]["time"] += a.moving_time

        yearly_summary = {
            y: {
                "runs": d["runs"],
                "distance_km": round(d["distance"] / 1000, 1),
                "hours": round(d["time"] / 3600, 1),
            }
            for y, d in sorted(yearly.items())
        }

        from collections import defaultdict
        monthly = defaultdict(lambda: {"runs": 0, "distance": 0.0, "speeds": []})
        for a in activities:
            key = a.start_date.strftime("%Y-%m")
            monthly[key]["runs"] += 1
            monthly[key]["distance"] += a.distance
            if a.average_speed:
                monthly[key]["speeds"].append(a.average_speed)

        recent_months = sorted(monthly.keys())[-6:]
        recent_monthly = {
            m: {
                "runs": monthly[m]["runs"],
                "distance_km": round(monthly[m]["distance"] / 1000, 1),
                "avg_pace": _speed_to_pace(
                    sum(monthly[m]["speeds"]) / len(monthly[m]["speeds"])
                ) if monthly[m]["speeds"] else "N/A",
            }
            for m in recent_months
        }

        return {
            "total_runs": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_hours": round(total_time, 1),
            "longest_run_km": round(max(distances) / 1000, 2),
            "avg_pace": _speed_to_pace(sum(speeds) / len(speeds)) if speeds else "N/A",
            "date_range": f"{min(dates).strftime('%Y-%m-%d')} 至 {max(dates).strftime('%Y-%m-%d')}",
            "yearly": yearly_summary,
            "recent_monthly": recent_monthly,
        }
    finally:
        db.close()
