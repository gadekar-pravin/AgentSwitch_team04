import datetime as dt
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

INSTANCES = {
    "suryodaya": "https://agentswitch.theschoolofai.in",
    "keystone": "https://class.agentswitch.theschoolofai.in",
}

# Every row this team's harness creates carries this marker in `notes`/`content`,
# so nothing we write can be confused with another team's data.
HARNESS_MARKER = "team04-harness"
FINDING_PREFIX = "TEAM04_FINDING "


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Non-empty values in the project .env win over the process environment."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ[key.strip()] = value


def env(name: str, default: str | None = None) -> str | None:
    load_dotenv()
    return os.environ.get(name) or default


def credentials(instance: str) -> tuple[str, str]:
    email = env("TEAM04_EMAIL", "team04@theschoolofai.in")
    password = env(f"TEAM04_PASSWORD_{instance.upper()}")
    if not password:
        raise RuntimeError(f"Set TEAM04_PASSWORD_{instance.upper()} in .env")
    return email, password


def today() -> dt.date:
    pinned = env("AGENT_TODAY")
    return dt.date.fromisoformat(pinned) if pinned else dt.date.today()
