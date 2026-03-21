from openai import OpenAI
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Activity

client = OpenAI(api_key=settings.OPENAI_API_KEY)

BATCH_SIZE = 20


def get_embedding(text: str) -> list[float]:
    """生成单条文本的 embedding 向量（1536 维）"""
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def embed_all_activities():
    """批量为所有缺少 embedding 的活动生成向量并写回数据库"""
    db = SessionLocal()
    try:
        activities = db.query(Activity).filter(
            Activity.embedding.is_(None),
            Activity.description_text.isnot(None),
        ).all()

        total = len(activities)
        print(f"需要生成 embedding 的活动：{total} 条")
        if total == 0:
            return

        for i in range(0, total, BATCH_SIZE):
            batch = activities[i : i + BATCH_SIZE]
            texts = [a.description_text for a in batch]

            response = client.embeddings.create(
                model=settings.OPENAI_EMBEDDING_MODEL,
                input=texts,
            )

            for activity, data in zip(batch, response.data):
                activity.embedding = data.embedding

            db.commit()
            done = min(i + BATCH_SIZE, total)
            print(f"  已处理 {done}/{total}")

        print("所有 embedding 生成完毕！")
    finally:
        db.close()
