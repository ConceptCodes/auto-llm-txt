from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # LLM — OpenRouter-style, provider-agnostic (mirrors triage-bot)
    openrouter_api_key: str = ""
    llm_model: str = "openai/gpt-4o-mini"
    llm_temperature: float = 0.0

    # Crawler
    max_pages: int = 100
    max_depth: int = 4
    concurrency: int = 8
    request_timeout: int = 15
    crawl_delay: float = 0.2

    # Output
    output_dir: str = "./out"
    include_full: bool = True

    # Optional site title override
    site_title: str = ""


settings = Settings()
