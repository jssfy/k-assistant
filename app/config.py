from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/k_assistant"
    LITELLM_BASE_URL: str = "http://localhost:4000/v1"
    LITELLM_API_KEY: str = "sk-1234"
    DEFAULT_MODEL: str = "claude-sonnet"
    APP_ENV: str = "development"

    # Phase 1: hardcoded default user
    DEFAULT_USER_ID: str = "00000000-0000-0000-0000-000000000001"

    # Phase 2: Memory (Mem0)
    MEM0_ENABLED: bool = True
    MEM0_COLLECTION_NAME: str = "k_assistant"

    # Phase 2: MCP Tools
    MCP_SERVERS_CONFIG: str = "mcp_servers.json"


settings = Settings()
