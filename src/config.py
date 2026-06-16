from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    fpt_api_key: str = ""
    fpt_base_url: str = "https://mkp-api.fptcloud.com/v1"
    fpt_embedding_model: str = "multilingual-e5-large"
    fpt_embedding_dimensions: int = 1024
    fpt_reranker_model: str = "bge-reranker-v2-m3"

    openai_api_key: str = ""
    openai_chat_model: str = "gpt-4o-mini"
    openai_judge_model: str = "gpt-4o"

    qdrant_url: str = "http://qdrant:6333"
    qdrant_collection: str = "fitness_kb"

    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
