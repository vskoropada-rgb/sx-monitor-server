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
    from sqlalchemy import text
    with engine.connect() as conn:
        for stmt in [
            "ALTER TABLE commands ADD COLUMN IF NOT EXISTS tg_topic_id VARCHAR;",
            "ALTER TABLE servers  ADD COLUMN IF NOT EXISTS maintenance_until TIMESTAMP;",
            "ALTER TABLE servers  ADD COLUMN IF NOT EXISTS agent_version VARCHAR;",
            "ALTER TABLE alerts   ADD COLUMN IF NOT EXISTS acked_until TIMESTAMP;",
        ]:
            conn.execute(text(stmt))
        conn.commit()
