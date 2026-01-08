"""
Configuration management for multi-config pipeline support.

Each config (e.g., business_news, academic_papers) has its own:
- prompts/ directory with config-specific prompts
- input_urls.json
- twitter_accounts.json
- Output data directory under data/{config_name}/

Usage:
    from src.config import set_config, get_data_dir, get_prompts_dir

    set_config("business_news")  # Set active config
    data_dir = get_data_dir()    # Returns data/business_news/
    prompts_dir = get_prompts_dir()  # Returns configs/business_news/prompts/
"""

from pathlib import Path
import json

# Base directories
_PROJECT_ROOT = Path(__file__).parent.parent
CONFIGS_DIR = _PROJECT_ROOT / "configs"
DATA_DIR = _PROJECT_ROOT / "data"

# Default configuration
DEFAULT_CONFIG = "business_news"

# Current active configuration (module-level state)
_current_config: str = DEFAULT_CONFIG


def set_config(config_name: str) -> None:
    """
    Set the active configuration.

    Args:
        config_name: Name of the configuration (e.g., 'business_news', 'academic_papers')

    Raises:
        ValueError: If the config directory doesn't exist
    """
    global _current_config
    config_path = CONFIGS_DIR / config_name
    if not config_path.exists():
        raise ValueError(f"Config not found: {config_name} (expected at {config_path})")
    _current_config = config_name


def get_config() -> str:
    """Get the current configuration name."""
    return _current_config


def get_config_path() -> Path:
    """Get path to current config directory."""
    return CONFIGS_DIR / _current_config


def get_prompts_dir() -> Path:
    """Get prompts directory for current config."""
    return get_config_path() / "prompts"


def get_input_urls_path() -> Path:
    """Get input_urls.json path for current config."""
    return get_config_path() / "input_urls.json"


def get_twitter_accounts_path() -> Path:
    """Get twitter_accounts.json path for current config."""
    return get_config_path() / "twitter_accounts.json"


def get_data_dir() -> Path:
    """
    Get output data directory for current config.

    Creates the directory if it doesn't exist.

    Returns:
        Path to data/{config_name}/ directory
    """
    data_dir = DATA_DIR / _current_config
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


def load_config_settings() -> dict:
    """
    Load config.json settings (optional overrides).

    Returns:
        Dict with config settings, or empty dict if no config.json exists
    """
    config_file = get_config_path() / "config.json"
    if config_file.exists():
        return json.loads(config_file.read_text(encoding="utf-8"))
    return {}
