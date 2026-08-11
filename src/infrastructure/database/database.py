import os
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, Session
from src.infrastructure.database.models import Base

# Database path configuration
if os.environ.get("VERCEL"):
    default_db_path = "/tmp/recruiting.db"
else:
    default_db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "recruiting.db")

DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")

# Connection Pooling & Engine Initialization
if DATABASE_URL.startswith("sqlite"):
    cleaned_url = DATABASE_URL.replace("\\", "/")
    engine = create_engine(
        cleaned_url,
        connect_args={"check_same_thread": False}
    )
else:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Dependency session generator for FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initializes tables and verifies indexes / column schemas."""
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                inspector = inspect(engine)
                if "candidates" in inspector.get_table_names():
                    existing_cols = [c["name"] for c in inspector.get_columns("candidates")]
                    new_cols = {
                        "email_body": "TEXT",
                        "skills_score": "INTEGER DEFAULT 0",
                        "experience_score": "INTEGER DEFAULT 0",
                        "education_score": "INTEGER DEFAULT 0",
                        "location_score": "INTEGER DEFAULT 0",
                        "recommendation": "VARCHAR DEFAULT 'Pending'",
                        "strengths": "TEXT",
                        "gaps": "TEXT",
                    }
                    for col_name, col_type in new_cols.items():
                        if col_name not in existing_cols:
                            conn.execute(text(f"ALTER TABLE candidates ADD COLUMN {col_name} {col_type}"))
                    conn.commit()
        except Exception as e:
            print(f"[Database] Notice during schema inspection: {e}")
