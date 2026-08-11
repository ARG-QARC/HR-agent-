import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# Force recruiting.db to be created in the same folder as this script (absolute path)
default_db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "recruiting.db")
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{default_db_path}")

# Create SQLAlchemy Engine
# Note: connect_args={"check_same_thread": False} is only required for SQLite.
if DATABASE_URL.startswith("sqlite"):
    # On Windows, replace backslashes with forward slashes for SQLite compatibility if needed
    cleaned_url = DATABASE_URL.replace("\\", "/")
    engine = create_engine(cleaned_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL)

# Create local session class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Declarative Base for models
Base = declarative_base()

def get_db():
    """Dependency helper to manage database sessions in FastAPI endpoints."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initializes tables in the database and ensures schema columns exist."""
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        try:
            with engine.connect() as conn:
                from sqlalchemy import inspect, text
                inspector = inspect(engine)
                if "candidates" in inspector.get_table_names():
                    existing_cols = [c["name"] for c in inspector.get_columns("candidates")]
                    new_cols = {
                        "email_body": "TEXT",
                        "skills_score": "INTEGER",
                        "experience_score": "INTEGER",
                        "education_score": "INTEGER",
                        "location_score": "INTEGER",
                        "recommendation": "VARCHAR",
                        "strengths": "TEXT",
                        "gaps": "TEXT",
                    }
                    for col_name, col_type in new_cols.items():
                        if col_name not in existing_cols:
                            conn.execute(text(f"ALTER TABLE candidates ADD COLUMN {col_name} {col_type}"))
                            print(f"Database schema auto-update: added column '{col_name}' to candidates table.")
                    conn.commit()
        except Exception as e:
            print(f"Note on DB schema check: {e}")
