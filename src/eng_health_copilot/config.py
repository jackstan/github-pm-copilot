from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

# Load .env if present
ROOT_DIR = Path(__file__).resolve().parents[2]
env_path = ROOT_DIR / ".env"
if env_path.exists():
    load_dotenv(env_path)


@dataclass
class Settings:
    github_token: str  # can be empty string or None at runtime
    default_days_back: int


def get_settings() -> Settings:
    token = os.getenv("GITHUB_TOKEN")
    return Settings(
        github_token=token if token is not None else "",
        default_days_back=int(os.getenv("DAYS_BACK", "90")),
    )
