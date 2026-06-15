"""
Configuration loading module.
Reads configuration from ~/.mcp-sec/config.yaml and provides default fallback values.
Automatically creates the default config file and data directories on first run.
"""

from pathlib import Path
import os
from dataclasses import dataclass, field

import yaml


# ── Configuration directory constants ────────────────────────────────────────────
CONFIG_DIR = Path.home() / ".mcp-sec"
CONFIG_FILE = CONFIG_DIR / "config.yaml"
DATA_DIR = CONFIG_DIR / "data"


def _ensure_default_config() -> None:
    """Ensure the config file exists; create default config if missing."""
    if CONFIG_FILE.exists():
        return

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    default_content = """\
sec:
  email: ""

paths:
  data_dir: "~/.mcp-sec/data"
  html_dir: "~/.mcp-sec/data/html"
  json_dir: "~/.mcp-sec/data/json"

download:
  delay_between_requests: 0.2
  min_file_size: 5000
"""
    CONFIG_FILE.write_text(default_content, encoding="utf-8")


@dataclass
class SecConfig:
    email: str = ""

    @property
    def user_agent(self) -> str:
        """Build SEC-compliant User-Agent from email, or fall back to default."""
        if self.email:
            return f"AgentLadleMcpSec {self.email}"
        return "AgentLadleMcpSec admin@example.com"


@dataclass
class PathsConfig:
    data_dir: str = "~/.mcp-sec/data"
    html_dir: str = "~/.mcp-sec/data/html"
    json_dir: str = "~/.mcp-sec/data/json"


@dataclass
class DownloadConfig:
    delay_between_requests: float = 0.2
    min_file_size: int = 5000


@dataclass
class AppConfig:
    sec: SecConfig = field(default_factory=SecConfig)
    paths: PathsConfig = field(default_factory=PathsConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)

    def resolve_path(self, raw: str) -> Path:
        """Resolve a raw path string to an absolute Path (supports ~ and relative paths).
        Security: resolved path must be within CONFIG_DIR to prevent path traversal."""
        p = Path(raw).expanduser()
        if p.is_absolute():
            resolved = p.resolve()
        else:
            resolved = (DATA_DIR / p).resolve()
        # Security check: path must be within CONFIG_DIR
        config_dir_resolved = CONFIG_DIR.resolve()
        if not str(resolved).startswith(str(config_dir_resolved)):
            raise ValueError(
                f"Path '{raw}' resolves to '{resolved}' which is outside "
                f"the allowed directory '{config_dir_resolved}'"
            )
        return resolved

    @property
    def html_dir_path(self) -> Path:
        return self.resolve_path(self.paths.html_dir)

    @property
    def json_dir_path(self) -> Path:
        return self.resolve_path(self.paths.json_dir)

    @property
    def data_dir_path(self) -> Path:
        return self.resolve_path(self.paths.data_dir)

    @property
    def company_tickers_path(self) -> Path:
        return self.data_dir_path / "company_tickers.json"

    def ensure_dirs(self):
        """Ensure all data directories exist."""
        self.html_dir_path.mkdir(parents=True, exist_ok=True)
        self.json_dir_path.mkdir(parents=True, exist_ok=True)


_cached_config: AppConfig | None = None


def load_config() -> AppConfig:
    """Load the config file, falling back to defaults if missing. Singleton: cached after first load."""
    global _cached_config
    if _cached_config is not None:
        return _cached_config

    # Ensure config file exists
    _ensure_default_config()

    # Read email from environment variable (highest priority)
    env_email = os.environ.get("SEC_EMAIL", "")

    config = AppConfig()

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}

        if "sec" in raw:
            sec_raw = raw["sec"].copy()
            # Remove user_agent from old configs to avoid passing it to SecConfig
            sec_raw.pop("user_agent", None)
            config.sec = SecConfig(**sec_raw)
        if "paths" in raw:
            config.paths = PathsConfig(**raw["paths"])
        if "download" in raw:
            config.download = DownloadConfig(**raw["download"])

    # Environment variable overrides config file
    if env_email:
        config.sec.email = env_email

    config.ensure_dirs()
    _cached_config = config
    return config


def reset_config() -> None:
    """Reset the config cache (used for testing)."""
    global _cached_config
    _cached_config = None