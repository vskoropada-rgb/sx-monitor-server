from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import Base as ModelsBase  # noqa: F401 — registers all models
    ModelsBase.metadata.create_all(bind=engine)
    # Auto-migrate: add columns that may be missing in existing deployments
    with engine.connect() as conn:
        conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE commands ADD COLUMN IF NOT EXISTS tg_topic_id VARCHAR;"
            )
        )
        conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE servers ADD COLUMN IF NOT EXISTS maintenance_until TIMESTAMP;"
            )
        )
        conn.commit()
