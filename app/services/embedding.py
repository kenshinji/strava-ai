from openai import OpenAI
from app.core.config import settings
from app.db.database import SessionLocal
from app.db.models import Activity

client = OpenAI(api_key=settings.OPENAI_API_KEY)

BATCH_SIZE = 20


def get_embedding(text: str) -> list[float]:
    """Generate an embedding vector (1536 dims) for a single text."""
    response = client.embeddings.create(
        model=settings.OPENAI_EMBEDDING_MODEL,
        input=text,
    )
    return response.data[0].embedding


def embed_all_activities():
    """Generate embeddings in batches for every activity that doesn't have one yet."""
    db = SessionLocal()
    try:
        activities = db.query(Activity).filter(
            Activity.embedding.is_(None),
            Activity.description_text.isnot(None),
        ).all()

        total = len(activities)
        print(f"Activities needing embeddings: {total}")
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
            print(f"  Processed {done}/{total}")

        print("All embeddings generated.")
    finally:
        db.close()
