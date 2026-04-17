from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "learning-agent"
    debug: bool = True

    openai_api_key: str = ""
    openai_model: str = ""
    openai_base_url: str | None = ""
    llm_timeout_seconds: float = 30.0
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 0.5
    session_store_backend: str = "memory"
    session_sqlite_path: str = "data/sessions.db"
    personal_rag_store_path: str = "data/personal_rag.jsonl"
    rag_enabled: bool = True
    rag_store_path: str = "data/knowledge_chunks.jsonl"
    rag_default_chunk_size: int = 500
    rag_default_chunk_overlap: int = 100
    rag_chunk_respect_sentences: bool = True
    rag_chunk_min_size: int = 100
    rag_chunk_overlap_ratio_min: float = 0.10
    rag_chunk_overlap_ratio_max: float = 0.20
    rag_chunk_overlap_ratio_target: float = 0.15
    rag_retrieve_top_k: int = 3
    rag_max_chunks_per_ingest: int = 100
    rag_max_text_length: int = 100000
    rag_ocr_engine: str = "simple"
    rag_embedding_provider: str = "simple"
    rag_embedding_dim: int = 128
    rag_rerank_provider: str = "simple"
    rag_rrf_k: int = 60
    rag_rrf_rank_window_size: int = 100
    rag_rerank_top_n: int = 10
    web_search_provider: str = "stub"
    user_db_path: str = "data/users.db"
    auth_password_salt: str = "learning-agent-local-salt"
    backend_base_url: str = "http://127.0.0.1:1900"
    chainlit_host: str = "0.0.0.0"
    chainlit_port: int = 2554

    # Graph V2开关
    use_graph_v2: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
