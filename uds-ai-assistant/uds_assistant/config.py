"""Runtime configuration, read from environment variables (prefix ``UDS_``)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(int(default))).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    data_dir: Path = Path("./data")
    # Retrieval backend: "bm25" (zero dependency, default) or "chroma"
    store_backend: str = "bm25"
    embed_model: str = "hash"  # "hash" (offline) or "sentence-transformers:BAAI/bge-small-en-v1.5"
    # LLM: "none" | "ollama" | "openai_compat"
    llm_provider: str = "none"
    llm_model: str = "llama3.1:8b"
    llm_base_url: str = "http://localhost:11434"
    llm_timeout_s: float = 120.0
    llm_api_key: str = ""
    # Auth: "dev" (headers X-User / X-Role, no secrets) or "token" (Bearer tokens from UDS_USERS)
    auth_mode: str = "dev"
    users_json: str = "{}"  # {"token": {"name": "alice", "role": "engineer"}}
    four_eyes: bool = False  # reviewer must differ from test creator
    # Hardware safety
    allow_hardware: bool = False
    allow_state_changing_on_hw: bool = False
    target_environment: str = "simulator"  # must be "bench" for hardware execution
    extra: dict = field(default_factory=dict)

    @property
    def db_path(self) -> Path:
        return self.data_dir / "uds_assistant.sqlite3"

    @property
    def projects_dir(self) -> Path:
        return self.data_dir / "projects"


def get_settings() -> Settings:
    return Settings(
        data_dir=Path(os.getenv("UDS_DATA_DIR", "./data")),
        store_backend=os.getenv("UDS_STORE_BACKEND", "bm25"),
        embed_model=os.getenv("UDS_EMBED_MODEL", "hash"),
        llm_provider=os.getenv("UDS_LLM_PROVIDER", "none"),
        llm_model=os.getenv("UDS_LLM_MODEL", "llama3.1:8b"),
        llm_base_url=os.getenv("UDS_LLM_BASE_URL", "http://localhost:11434"),
        llm_timeout_s=float(os.getenv("UDS_LLM_TIMEOUT_S", "120")),
        llm_api_key=os.getenv("UDS_LLM_API_KEY", ""),
        auth_mode=os.getenv("UDS_AUTH_MODE", "dev"),
        users_json=os.getenv("UDS_USERS", "{}"),
        four_eyes=_bool("UDS_FOUR_EYES", False),
        allow_hardware=_bool("UDS_ALLOW_HARDWARE", False),
        allow_state_changing_on_hw=_bool("UDS_HW_ALLOW_STATE_CHANGING", False),
        target_environment=os.getenv("UDS_TARGET_ENV", "simulator"),
    )
