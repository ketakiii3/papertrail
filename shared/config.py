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
    OLLAMA_URL: str = os.getenv("OLLAMA_URL", "http://ollama:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "tinyllama")
    KAFKA_BOOTSTRAP_SERVERS: str = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "redpanda:9092")
    # Checker agent (LangChain tool calling). Needs a tool-capable model; tinyllama is not one.
    CHECKER_ENABLED: bool = os.getenv("CHECKER_ENABLED", "true").lower() == "true"
    CHECKER_MODEL: str = os.getenv("CHECKER_MODEL", "qwen3:4b")
    CHECKER_OLLAMA_URL: str = os.getenv("CHECKER_OLLAMA_URL", os.getenv("OLLAMA_URL", "http://ollama:11434"))
    CHECKER_MAX_TOOL_CALLS: int = int(os.getenv("CHECKER_MAX_TOOL_CALLS", "3"))
    # Qwen3 "thinking": unset = model default, "true"/"false" to force
    CHECKER_THINK: str = os.getenv("CHECKER_THINK", "")


settings = Settings()
