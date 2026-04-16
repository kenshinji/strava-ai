from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from sqlalchemy import text

from app.db.database import SessionLocal
from app.db.models import Activity
from app.services.embedding import get_embedding


def _speed_to_pace(speed_ms: float) -> str:
    """Convert m/s to a pace string like 'X:XX/km'."""
    if not speed_ms or speed_ms <= 0:
        return "N/A"
    pace_s = 1000 / speed_ms
    return f"{int(pace_s // 60)}:{int(pace_s % 60):02d}/km"


def _parse_explicit_date(query: str) -> date | None:
    """Parse an explicit date from the user query.

    Supports:
      - YYYY-MM-DD
      - YYYY/MM/DD
      - YYYY年M月D日

    Returns a `date` if found, else None.
    """
    q = query.strip()

    m = re.search(r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", q)
    if m:
        y, mo, d = map(int, m.groups())
        return date(y, mo, d)

    m = re.search(r"(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日", q)
    if m:
        y, mo, d = map(int, m.groups())
        return date(y, mo, d)

    return None


def _rows_to_activity_dicts(rows, *, similarity=None) -> list[dict]:
    out: list[dict] = []
    for row in rows:
        out.append(
            {
                "id": row.id,
                "name": row.name,
                "sport_type": row.sport_type,
                "start_date": row.start_date.isoformat() if row.start_date else None,
                "distance_km": round(row.distance / 1000, 2) if row.distance is not None else None,
                "moving_time_min": round(row.moving_time / 60, 1) if row.moving_time is not None else None,
                "pace": _speed_to_pace(row.average_speed),
                "heartrate": row.average_heartrate,
                "elevation": row.total_elevation_gain,
                "description": row.description_text,
                "similarity": similarity(row) if callable(similarity) else similarity,
            }
        )
    return out


def _fetch_activities_on_date(
    db,
    d: date,
    *,
    sport_type: str | None = None,
) -> list[dict]:
    start_dt = datetime.combine(d, datetime.min.time())
    end_dt = start_dt + timedelta(days=1)

    sql = """
        SELECT id, name, sport_type, start_date,
               distance, moving_time, average_speed,
               average_heartrate, total_elevation_gain,
               description_text
        FROM activities
        WHERE start_date >= :start_dt AND start_date < :end_dt
    """
    params: dict = {"start_dt": start_dt, "end_dt": end_dt}

    if sport_type:
        sql += " AND sport_type = :sport_type"
        params["sport_type"] = sport_type

    sql += " ORDER BY start_date DESC"

    rows = db.execute(text(sql), params).fetchall()
    # similarity=1.0 means "exact hit"; helps the model prioritize these.
    return _rows_to_activity_dicts(rows, similarity=1.0)


def get_recent_activities(limit: int = 5) -> list[dict]:
    """Return the most recent activities by start_date.

    NOTE: Do *not* require embedding here. Users often ask about a specific date;
    if that activity's embedding is missing, it must still be retrievable.
    """
    db = SessionLocal()
    try:
        rows = db.execute(
            text(
                """
                SELECT id, name, sport_type, start_date,
                       distance, moving_time, average_speed,
                       average_heartrate, total_elevation_gain,
                       description_text
                FROM activities
                ORDER BY start_date DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        ).fetchall()
        return _rows_to_activity_dicts(rows, similarity=None)
    finally:
        db.close()


def retrieve_relevant_activities(
    query: str,
    top_k: int = 10,
    sport_type: str | None = None,
) -> list[dict]:
    """Retrieve activities relevant to the query.

    Fixes the bug in your screenshot:
    - Asking "2025年6月29日" may *not* retrieve that exact day via embeddings.
    - If that day's activity has embedding=NULL, prior code would exclude it entirely.

    Strategy:
    1) If the user mentions an explicit date, fetch activities on that date via SQL
       (does NOT require embeddings).
    2) Run semantic pgvector search for general relevance (requires embeddings).
    3) Union with the 5 most recent activities to keep "latest" questions grounded.

    Merge priority: date hits -> semantic hits -> recent.
    """

    explicit = _parse_explicit_date(query)

    db = SessionLocal()
    try:
        date_results: list[dict] = []
        if explicit is not None:
            date_results = _fetch_activities_on_date(db, explicit, sport_type=sport_type)

        # Semantic search (only activities with embeddings)
        query_embedding = get_embedding(query)

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

        params = {"query_embedding": str(query_embedding), "top_k": top_k}
        if sport_type:
            sql += " AND sport_type = :sport_type"
            params["sport_type"] = sport_type

        sql += " ORDER BY cosine_distance ASC LIMIT :top_k"

        rows = db.execute(text(sql), params).fetchall()
        semantic_results = _rows_to_activity_dicts(
            rows,
            similarity=lambda r: round(1 - r.cosine_distance, 4),
        )

    finally:
        db.close()

    recent = get_recent_activities(limit=5)

    merged: list[dict] = []
    seen_ids: set[int] = set()
    for group in (date_results, semantic_results, recent):
        for a in group:
            aid = a.get("id")
            if aid in seen_ids:
                continue
            merged.append(a)
            if aid is not None:
                seen_ids.add(aid)

    return merged


def build_context(activities: list[dict]) -> str:
    """Format retrieved activities into a block the LLM can consume directly.

    Sorted newest-to-oldest; the most recent run is explicitly tagged so the
    model can't substitute a similar-but-older run for "latest run" questions.
    """
    if not activities:
        return "No relevant running activities found."

    sorted_acts = sorted(activities, key=lambda a: a.get("start_date") or "", reverse=True)

    lines = ["Relevant running activities (sorted newest to oldest):\n"]
    for i, act in enumerate(sorted_acts, 1):
        label = "[MOST RECENT]" if i == 1 else f"{i}."
        similarity_str = (
            f" | similarity {act['similarity']}" if act.get("similarity") is not None else ""
        )
        start = (act.get("start_date") or "")
        start_day = start[:10] if start else "unknown-date"
        name = act.get("name") or "(no name)"
        desc = act.get("description") or ""
        distance_km = act.get("distance_km")
        pace = act.get("pace")

        lines.append(
            f"{label} [{start_day}] {name}"
            f" | {distance_km}km | pace {pace}"
            f"{similarity_str}"
            f"\n   {desc}"
        )

    return "\n".join(lines)


def get_summary_stats() -> dict:
    """Compute global running summary stats used as additional context in the system prompt."""
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
                )
                if monthly[m]["speeds"]
                else "N/A",
            }
            for m in recent_months
        }

        return {
            "total_runs": len(activities),
            "total_distance_km": round(total_distance, 1),
            "total_hours": round(total_time, 1),
            "longest_run_km": round(max(distances) / 1000, 2),
            "avg_pace": _speed_to_pace(sum(speeds) / len(speeds)) if speeds else "N/A",
            "date_range": f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}",
            "yearly": yearly_summary,
            "recent_monthly": recent_monthly,
        }
    finally:
        db.close()
