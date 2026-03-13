import os


class Settings:
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://papertrail:papertrail@localhost:5432/papertrail")
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    NEO4J_URI: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER: str = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: str = os.getenv("NEO4J_PASSWORD", "papertrail123")
    EDGAR_USER_AGENT: str = os.getenv("EDGAR_USER_AGENT", "PaperTrail research@papertrail.dev")
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")


settings = Settings()
