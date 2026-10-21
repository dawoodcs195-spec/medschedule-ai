import os
from pathlib import Path
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
load_dotenv(BACKEND_DIR / ".env")


class Settings(BaseSettings):
    PROJECT_NAME: str = "MedSchedule AI — Modular Curriculum & Timetable Engine"
    API_V1_STR: str = "/api"
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    GEMINI_EMBEDDING_MODEL: str = os.getenv("GEMINI_EMBEDDING_MODEL", "text-embedding-004")
    EMBEDDING_DIMENSION: int = 1536

    # Supabase / PostgreSQL Database Connection (Optional local fallback)
    SUPABASE_URL: str = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY: str = os.getenv("SUPABASE_KEY", "")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        os.getenv("SUPABASE_URL", "postgresql://postgres:postgres@localhost:5432/postgres"),
    )
    CORS_ORIGINS_RAW: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000,https://medschedule-ai.vercel.app",
    )

    @property
    def CORS_ORIGINS(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS_RAW.split(",") if o.strip()]

    class Config:
        env_file = str(BACKEND_DIR / ".env")
        extra = "allow"


settings = Settings()
