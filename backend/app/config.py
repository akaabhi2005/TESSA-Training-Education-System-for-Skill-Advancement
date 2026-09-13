import os
import tempfile
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
# Vercel functions can write only to /tmp, and that directory is intentionally
# short-lived. Local development retains the on-disk cache used for repeatable
# demos. A durable production deployment should set LPR_CACHE_DIR to external
# storage instead of relying on either location.
if configured_cache := os.getenv("LPR_CACHE_DIR"):
    CACHE_DIR = Path(configured_cache)
elif os.getenv("VERCEL"):
    CACHE_DIR = Path(tempfile.gettempdir()) / "learning-path-recommendor"
else:
    CACHE_DIR = DATA_DIR / "cache"


class Settings(BaseSettings):
    # Use an absolute env-file path so starting Uvicorn from the repository
    # root and starting it from backend/ behave identically.
    model_config = SettingsConfigDict(env_file=BASE_DIR / ".env", env_prefix="LPR_", extra="ignore")

    # Credentials use the conventional provider names while the app's tuning
    # flags retain their LPR_ prefix. There is deliberately no default: a key
    # committed to source is a leaked key, and the app already fails honestly
    # without one rather than inventing a catalogue to fill the gap.
    gemini_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GEMINI_API_KEY", "LPR_GEMINI_API_KEY"),
    )
    tavily_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("TAVILY_API_KEY", "LPR_TAVILY_API_KEY"),
    )
    adzuna_app_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADZUNA_APP_ID", "LPR_ADZUNA_APP_ID"),
    )
    adzuna_app_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ADZUNA_APP_KEY", "LPR_ADZUNA_APP_KEY"),
    )
    # Optional. Any pool entry written as "vendor/model" is routed through the
    # OpenAI-compatible gateway below instead of the Gemini SDK; without this
    # key those entries are dropped from the pool and Gemini serves every lane.
    airouter_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("AIROUTER_API_KEY", "LPR_AIROUTER_API_KEY"),
    )
    airouter_base_url: str = "https://api.airouter.in/v1"
    # A gateway call has to fail fast enough that the Gemini fallback still
    # fits inside the 60s serverless function limit. The graph model answers
    # this prompt in about 6s, so this is roughly 2.5x its measured latency.
    airouter_timeout: float = 15.0

    # A single Gemini model is a needless single point of failure.  These
    # pools contain the models available to this demo account and are kept as
    # plain configuration so a production deployment can override them with
    # LPR_GRAPH_MODELS / LPR_FAST_MODELS without changing the adapter.
    #
    # The graph lane leads with a routed model: it returns a deeper skill DAG
    # (multiple independent roots and multi-parent edges) where Gemini tends to
    # hang most skills off one foundation, and the planner's phases are only as
    # good as that graph. The fast lane stays on Gemini, which labels resources
    # roughly 2.5x quicker under the concurrency discovery actually uses.
    model: str = "gemini-3.6-flash"
    graph_models: str = (
        "openai/gpt-5.6-luna-fast,"
        "gemini-3.6-flash,gemini-3.5-flash,gemini-2.5-flash,"
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite"
    )
    fast_models: str = (
        "gemini-3.5-flash-lite,gemini-3.1-flash-lite,gemini-2.5-flash,"
        "gemini-3.5-flash,gemini-3.6-flash"
    )
    # Everything except the two chat-facing calls is mechanical extraction, so
    # it runs at low effort. Chat and explanations run at the default.
    offline: bool = False
    use_embeddings: bool = True

    # Scoring weights. Exposed here rather than buried in retrieval.py because
    # we tune these in the eval notebook and the API surfaces them for the
    # "why this course" panel.
    w_gap: float = 0.42
    w_semantic: float = 0.22
    w_level: float = 0.14
    w_quality: float = 0.08     # source specificity, not an invented rating
    w_preference: float = 0.14
    w_redundancy: float = 0.15

    # Below this the planner stops adding courses - chasing the last few
    # percent of a gap is how you end up with a 40-course roadmap.
    gap_tolerance: float = 0.12
    max_path_courses: int = 14


settings = Settings()
CACHE_DIR.mkdir(parents=True, exist_ok=True)
