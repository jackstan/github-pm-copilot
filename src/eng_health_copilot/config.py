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


def get_settings() -> Settings:
    token = os.getenv("GITHUB_TOKEN", "")

    return Settings(
        # ---- GitHub ----
        github_token=token,
        default_days_back=int(os.getenv("DAYS_BACK", "90")),

        # ---- OpenAI ----
        openai_api_key=os.getenv("OPENAI_API_KEY"),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
    )
