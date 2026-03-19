import asyncio
from datetime import datetime
from app.services.strava import fetch_all_activities, refresh_token
from app.db.database import init_db, SessionLocal
from app.db.models import Activity
from app.core.config import settings


def format_pace(speed_ms: float) -> str:
    """米/秒 → 配速 X:XX/km"""
    if speed_ms <= 0:
        return "N/A"
    pace_seconds = 1000 / speed_ms
    minutes = int(pace_seconds // 60)
    seconds = int(pace_seconds % 60)
    return f"{minutes}:{seconds:02d}"


def build_description(act: dict) -> str:
    """把一条跑步活动转成自然语言描述"""
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


async def sync():
    init_db()
    print("开始同步 Strava 数据...")

    # 每次运行时自动刷新 token，避免过期问题
    print("刷新 Strava Access Token...")
    token_data = await refresh_token(settings.STRAVA_REFRESH_TOKEN)
    if "access_token" not in token_data:
        print(f"Token 刷新失败: {token_data}")
        return
    access_token = token_data["access_token"]
    print("Token 刷新成功!")

    activities = await fetch_all_activities(access_token)
    print(f"共拉取 {len(activities)} 条活动")

    db = SessionLocal()
    count = 0
    for act in activities:
        if act.get("sport_type") not in ("Run", "TrailRun", "VirtualRun"):
            continue

        existing = db.query(Activity).filter(Activity.id == act["id"]).first()
        if existing:
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
    db.close()
    print(f"新增 {count} 条跑步记录入库！")


if __name__ == "__main__":
    asyncio.run(sync())
