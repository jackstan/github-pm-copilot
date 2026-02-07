from dataclasses import dataclass
from pathlib import Path
import os
from typing import Optional

from dotenv import load_dotenv

# Load .env if present
ROOT_DIR = Path(__file__).resolve().parents[2]
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


@dataclass
class Settings:
    # GitHub settings
    github_token: str
    default_days_back: int

    # OpenAI settings
    openai_api_key: Optional[str]
    openai_model: str

    # Capture settings
    weekly_summary_capture_enabled: bool
    weekly_summary_capture_path: Path


def get_settings() -> Settings:
    token = os.getenv("GITHUB_TOKEN", "")
    capture_enabled = os.getenv("WEEKLY_SUMMARY_CAPTURE", "").lower() in ("1", "true", "yes", "on")
    capture_path = Path(
        os.getenv(
            "WEEKLY_SUMMARY_CAPTURE_PATH",
            str(ROOT_DIR / "data" / "weekly_summary_inputs.jsonl"),
        )
    )

    return Settings(
        # ---- GitHub ----
        github_token=token,
        default_days_back=int(os.getenv("DAYS_BACK", "90")),

        # ---- OpenAI ----
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),

        # ---- Capture ----
        weekly_summary_capture_enabled=capture_enabled,
        weekly_summary_capture_path=capture_path,
    )
