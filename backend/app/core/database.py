import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import settings

Base = declarative_base()

def _normalize_db_url(url: str) -> str:
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


# Engine setup with flexible failure handling if DB is not currently running locally.
# create_engine() is lazy: no connection is attempted until first use.
try:
    engine = create_engine(
        _normalize_db_url(settings.DATABASE_URL),
        pool_pre_ping=True,
        connect_args={"connect_timeout": 4},
        echo=False,
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
except Exception:
    engine = None
    SessionLocal = None


_probe_cache: dict[str, float | bool] = {"ts": 0.0, "ok": False}
_PROBE_TTL_SECONDS = 30.0


def db_available() -> bool:
    """Return True if the configured database is reachable (cached for 30s)."""
    if engine is None:
        return False
    now = time.monotonic()
    if now - float(_probe_cache["ts"]) < _PROBE_TTL_SECONDS:
        return bool(_probe_cache["ok"])
    try:
        with engine.connect():
            ok = True
    except Exception:
        ok = False
    _probe_cache.update(ts=now, ok=ok)
    return ok


def get_db():
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
