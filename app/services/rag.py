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


def get_recent_activities(limit: int = 5) -> list[dict]:
    """Return the most recent activities by start_date so the latest data is always in context."""
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


_DISTANCE_KEYWORDS: list[tuple[list[str], float, float]] = [
    # (keywords, min_km, max_km)
    (["half marathon", "半程马拉松", "半马", "halbmarathon", "semi-marathon", "medio maratón"], 18.0, 23.0),
    (["marathon", "全程马拉松", "全马", "マラソン"], 38.0, 45.0),
    (["10k", "10km", "10公里", "10-k", "10 km", "10 k"], 9.0, 11.5),
    (["5k", "5km", "5公里", "5-k", "5 km", "5 k"], 4.0, 6.5),
]


def _extract_distance_range(query: str) -> tuple[float, float] | None:
    """Return (min_km, max_km) if the query mentions a known race distance, else None."""
    q = query.lower()
    for keywords, min_km, max_km in _DISTANCE_KEYWORDS:
        if any(kw in q for kw in keywords):
            # "marathon" would also match "half marathon" — exclude full if half matched first
            return (min_km, max_km)
    return None


def get_activities_by_distance(min_km: float, max_km: float) -> list[dict]:
    """Fetch all activities whose distance falls within [min_km, max_km]."""
    db = SessionLocal()
    try:
        rows = db.execute(
            text("""
                SELECT id, name, sport_type, start_date,
                       distance, moving_time, average_speed,
                       average_heartrate, total_elevation_gain,
                       description_text
                FROM activities
                WHERE distance BETWEEN :min_m AND :max_m
                ORDER BY average_speed DESC
            """),
            {"min_m": min_km * 1000, "max_m": max_km * 1000},
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


_YEAR_OFFSET_PATTERNS: list[tuple[str, int]] = [
    # Chinese / Japanese
    (r"前年", -2),
    (r"去年|昨年", -1),
    (r"今年|本年", 0),
    # English
    (r"the\s+year\s+before\s+last", -2),
    (r"last\s+year", -1),
    (r"this\s+year", 0),
    # French
    (r"l['\u2019]ann[ée]e\s+derni[eè]re|l['\u2019]an\s+dernier", -1),
    # German
    (r"letztes\s+Jahr", -1),
    (r"dieses\s+Jahr", 0),
    # Spanish / Portuguese
    (r"el\s+a[ñn]o\s+pasado|ano\s+passado", -1),
    (r"este\s+a[ñn]o|este\s+ano", 0),
]

# Regex for CJK month-day formats: MM月DD日 (with optional YYYY年 prefix)
_CJK_DATE_RE = re.compile(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日")


def _extract_date_hints(query: str) -> list[date]:
    """Extract candidate dates from a query string.

    Strategy:
    1. Detect a relative-year modifier ("last year", "去年", etc.) and compute a year offset.
    2. Use regex for CJK month/day formats (月/日), resolving the year with the offset.
    3. Use dateparser for everything else (English, French, German, Spanish, …),
       then apply the year offset to the parsed result.

    Returns a deduplicated list of dates.
    """
    import dateparser

    today = date.today()
    seen: set[date] = set()
    results: list[date] = []

    def _add(d: date) -> None:
        if d not in seen:
            seen.add(d)
            results.append(d)

    # --- Step 1: detect year offset modifier ---
    year_offset = 0
    cleaned_query = query
    for pattern, offset in _YEAR_OFFSET_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            year_offset = offset
            cleaned_query = re.sub(pattern, "", query, flags=re.IGNORECASE).strip()
            break

    # --- Step 2: CJK date regex (handles 2025年6月29日 and 6月29日) ---
    for m in _CJK_DATE_RE.finditer(query):
        explicit_year = int(m.group(1)) if m.group(1) else None
        month, day = int(m.group(2)), int(m.group(3))
        year = explicit_year if explicit_year else today.year + year_offset
        try:
            _add(date(year, month, day))
        except ValueError:
            pass

    # --- Step 3: dateparser for non-CJK text ---
    dp_settings = {
        "PREFER_DAY_OF_MONTH": "first",
        "RELATIVE_BASE": datetime(today.year + year_offset, today.month, today.day),
        "RETURN_AS_TIMEZONE_AWARE": False,
    }
    # Try the cleaned query (relative word removed) so dateparser sees bare date text
    for text in {query, cleaned_query}:
        # Skip if already fully covered by CJK regex
        if _CJK_DATE_RE.search(text):
            continue
        parsed = dateparser.parse(text, settings=dp_settings)
        if parsed:
            d = parsed.date()
            # Apply explicit year offset when the relative word was present
            if year_offset and d.year == today.year:
                try:
                    d = d.replace(year=today.year + year_offset)
                except ValueError:
                    pass
            _add(d)

    return results


def get_activities_by_dates(target_dates: list[date], window_days: int = 1) -> list[dict]:
    """Fetch activities that fall within ±window_days of any target date."""
    if not target_dates:
        return []
    db = SessionLocal()
    try:
        all_rows = []
        seen_ids: set = set()
        for d in target_dates:
            start = d - timedelta(days=window_days)
            end = d + timedelta(days=window_days)
            rows = db.execute(
                text("""
                    SELECT id, name, sport_type, start_date,
                           distance, moving_time, average_speed,
                           average_heartrate, total_elevation_gain,
                           description_text
                    FROM activities
                    WHERE DATE(start_date) BETWEEN :start AND :end
                    ORDER BY start_date DESC
                """),
                {"start": start.isoformat(), "end": end.isoformat()},
            ).fetchall()
            for row in rows:
                if row.id not in seen_ids:
                    seen_ids.add(row.id)
                    all_rows.append({
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
                    })
        return all_rows
    finally:
        db.close()


def retrieve_relevant_activities(
    query: str,
    top_k: int = 10,
    sport_type: str | None = None,
) -> list[dict]:
    """Embed the user query, run a pgvector cosine search, and merge with recent activities.

    The merge with the 5 most-recent runs guarantees that time-anchored questions
    (e.g. "my latest run") still see the newest data even when it isn't the most
    semantically similar to the query.
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

    # Union with recent activities so time-based questions don't miss the newest data.
    recent = get_recent_activities(limit=5)
    seen_ids = {a["id"] for a in semantic_results}
    merged = semantic_results + [a for a in recent if a["id"] not in seen_ids]

    # Union with exact-date matches so specific-date questions always find their data.
    date_hints = _extract_date_hints(query)
    if date_hints:
        date_matches = get_activities_by_dates(date_hints)
        seen_ids = {a["id"] for a in merged}
        merged = merged + [a for a in date_matches if a["id"] not in seen_ids]

    # Union with distance-range matches so "best half marathon" etc. see all candidates.
    dist_range = _extract_distance_range(query)
    if dist_range:
        dist_matches = get_activities_by_distance(*dist_range)
        seen_ids = {a["id"] for a in merged}
        merged = merged + [a for a in dist_matches if a["id"] not in seen_ids]

    return merged


def build_context(activities: list[dict]) -> str:
    """Format retrieved activities into a block the LLM can consume directly.

    Sorted newest-to-oldest; the most recent run is explicitly tagged so the
    model can't substitute a similar-but-older run for "latest run" questions.
    """
    if not activities:
        return "No relevant running activities found."

    sorted_acts = sorted(activities, key=lambda a: a["start_date"], reverse=True)

    lines = ["Relevant running activities (sorted newest to oldest):\n"]
    for i, act in enumerate(sorted_acts, 1):
        label = "[MOST RECENT]" if i == 1 else f"{i}."
        similarity_str = f" | similarity {act['similarity']}" if act["similarity"] is not None else ""
        lines.append(
            f"{label} [{act['start_date'][:10]}] {act['name']}"
            f" | {act['distance_km']}km | pace {act['pace']}"
            f"{similarity_str}"
            f"\n   {act['description']}"
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
            "date_range": f"{min(dates).strftime('%Y-%m-%d')} to {max(dates).strftime('%Y-%m-%d')}",
            "yearly": yearly_summary,
            "recent_monthly": recent_monthly,
        }
    finally:
        db.close()
