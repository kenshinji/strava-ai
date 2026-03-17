from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from sqlalchemy.orm import declarative_base
from pgvector.sqlalchemy import Vector

Base = declarative_base()


class Activity(Base):
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True)  # Strava activity ID
    name = Column(String(255))
    sport_type = Column(String(50))  # Run, TrailRun, etc.
    start_date = Column(DateTime)
    distance = Column(Float)  # meters
    moving_time = Column(Integer)  # seconds
    elapsed_time = Column(Integer)  # seconds
    total_elevation_gain = Column(Float)  # meters
    average_speed = Column(Float)  # m/s
    max_speed = Column(Float)
    average_heartrate = Column(Float, nullable=True)
    max_heartrate = Column(Float, nullable=True)
    average_cadence = Column(Float, nullable=True)
    calories = Column(Float, nullable=True)
    suffer_score = Column(Integer, nullable=True)
    description_text = Column(Text, nullable=True)  # natural language description
    embedding = Column(Vector(1536), nullable=True)  # text-embedding-3-small


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(50))
    role = Column(String(20))  # user or assistant
    content = Column(Text)
    created_at = Column(DateTime)
