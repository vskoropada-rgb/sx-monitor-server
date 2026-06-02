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
            """CREATE TABLE IF NOT EXISTS rdp_log (
                id SERIAL PRIMARY KEY,
                server_id VARCHAR NOT NULL REFERENCES servers(id),
                username VARCHAR NOT NULL,
                ip VARCHAR,
                is_new_ip INTEGER DEFAULT 0,
                event_time TIMESTAMP NOT NULL,
                logged_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (server_id, username, ip, event_time)
            );""",
            """CREATE TABLE IF NOT EXISTS login_logs (
                id SERIAL PRIMARY KEY,
                admin_id INTEGER NOT NULL,
                action VARCHAR NOT NULL,
                ip VARCHAR,
                user_agent TEXT,
                at TIMESTAMP DEFAULT NOW()
            );""",
            """CREATE TABLE IF NOT EXISTS server_heartbeats (
                server_id VARCHAR PRIMARY KEY REFERENCES servers(id),
                online INTEGER DEFAULT 1,
                changed_at TIMESTAMP DEFAULT NOW()
            );""",
            """CREATE TABLE IF NOT EXISTS uptime_events (
                id SERIAL PRIMARY KEY,
                server_id VARCHAR NOT NULL REFERENCES servers(id),
                event VARCHAR NOT NULL,
                at TIMESTAMP DEFAULT NOW() NOT NULL
            );""",
            "CREATE INDEX IF NOT EXISTS idx_uptime_server_at ON uptime_events(server_id, at);",
        ]:
            conn.execute(text(stmt))
        conn.commit()

        # One-time migration: hash any plaintext API keys left from older
        # deployments. A SHA-256 hex digest is exactly 64 lowercase hex chars;
        # anything else is a legacy plaintext key and gets hashed in place.
        # Idempotent — already-hashed keys are skipped, so existing agents keep
        # authenticating (the server hashes the incoming key before lookup).
        import hashlib
        _hexset = set("0123456789abcdef")
        rows = conn.execute(text("SELECT id, api_key FROM servers")).fetchall()
        for sid, key in rows:
            if not key:
                continue
            if len(key) == 64 and set(key) <= _hexset:
                continue  # already hashed
            digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
            conn.execute(
                text("UPDATE servers SET api_key = :k WHERE id = :i"),
                {"k": digest, "i": sid},
            )
        conn.commit()
