import asyncio
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Activity
from app.services.strava import fetch_all_activities, refresh_token
from app.services.embedding import embed_all_activities


def format_pace(speed_ms: float) -> str:
    if speed_ms <= 0:
        return "N/A"
    pace_seconds = 1000 / speed_ms
    minutes = int(pace_seconds // 60)
    seconds = int(pace_seconds % 60)
    return f"{minutes}:{seconds:02d}"


def build_description(act: dict) -> str:
    date = datetime.fromisoformat(act["start_date_local"].replace("Z", "+00:00"))
    distance_km = act["distance"] / 1000
    pace = format_pace(act["average_speed"])
    duration_min = act["moving_time"] / 60

    desc = (
        f"{date.strftime('%Y年%m月%d日')} "
        f"{act.get('name', '跑步活动')}，"
        f"类型：{act.get('sport_type', 'Run')}，"
        f"距离：{distance_km:.2f}公里，"
        f"用时：{duration_min:.0f}分钟，"
        f"配速：{pace}/km"
    )

    if act.get("total_elevation_gain"):
        desc += f"，累计爬升：{act['total_elevation_gain']:.0f}米"
    if act.get("average_heartrate"):
        desc += f"，平均心率：{act['average_heartrate']:.0f}bpm"
    if act.get("suffer_score"):
        desc += f"，痛苦指数：{act['suffer_score']}"

    return desc


def _get_latest_activity_timestamp() -> int | None:
    """Return the Unix timestamp of the most recent activity in the DB, or None if empty."""
    db = SessionLocal()
    try:
        latest = db.query(Activity).order_by(Activity.start_date.desc()).first()
        if latest and latest.start_date:
            dt = latest.start_date
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        return None
    finally:
        db.close()


async def run_sync(full: bool = False) -> dict:
    """
    Sync Strava activities to the local database.

    - If `full=True`, fetches all activities from Strava (initial load).
    - Otherwise, only fetches activities newer than the latest one already in the DB.

    Returns a summary dict with counts.
    """
    print("开始同步 Strava 数据...")

    print("刷新 Strava Access Token...")
    token_data = await refresh_token(settings.STRAVA_REFRESH_TOKEN)
    if "access_token" not in token_data:
        msg = f"Token 刷新失败: {token_data}"
        print(msg)
        return {"status": "error", "message": msg}
    access_token = token_data["access_token"]
    print("Token 刷新成功!")

    after_ts: int | None = None
    if not full:
        after_ts = _get_latest_activity_timestamp()
        if after_ts:
            print(f"增量同步：仅拉取 {datetime.fromtimestamp(after_ts)} 之后的活动")
        else:
            print("数据库为空，执行全量同步")

    activities = await fetch_all_activities(access_token, after=after_ts)
    print(f"共拉取 {len(activities)} 条活动")

    db = SessionLocal()
    count = 0
    try:
        for act in activities:
            if act.get("sport_type") not in ("Run", "TrailRun", "VirtualRun"):
                continue

            if db.query(Activity).filter(Activity.id == act["id"]).first():
                continue

            activity = Activity(
                id=act["id"],
                name=act.get("name"),
                sport_type=act.get("sport_type"),
                start_date=datetime.fromisoformat(
                    act["start_date_local"].replace("Z", "+00:00")
                ),
                distance=act.get("distance"),
                moving_time=act.get("moving_time"),
                elapsed_time=act.get("elapsed_time"),
                total_elevation_gain=act.get("total_elevation_gain"),
                average_speed=act.get("average_speed"),
                max_speed=act.get("max_speed"),
                average_heartrate=act.get("average_heartrate"),
                max_heartrate=act.get("max_heartrate"),
                average_cadence=act.get("average_cadence"),
                calories=act.get("calories"),
                suffer_score=act.get("suffer_score"),
                description_text=build_description(act),
            )
            db.add(activity)
            count += 1

        db.commit()
    finally:
        db.close()

    print(f"新增 {count} 条跑步记录入库！")

    if count > 0:
        print("为新活动生成 embedding 向量...")
        embed_all_activities()

    return {"status": "ok", "new_activities": count}


def run_sync_job():
    """Synchronous wrapper for APScheduler to call the async sync function."""
    asyncio.run(run_sync())
