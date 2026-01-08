"""
Utility functions for the project.
"""

from pathlib import Path

from src.config import get_prompts_dir


# =============================================================================
# Prompt Loading
# =============================================================================

# Legacy prompts directory (for non-config-specific prompts like Layer 1/3)
LEGACY_PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    """
    Load a prompt from the current config's prompts directory.

    Falls back to legacy prompts/ directory for non-config-specific prompts
    (e.g., Layer 1 discovery prompts, Layer 3 dedup prompts).

    Args:
        filename: Name of the prompt file (e.g., "filter_system_prompt.md")

    Returns:
        Prompt content as string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist in either location.
    """
    # First, try config-specific prompts directory
    config_prompt_path = get_prompts_dir() / filename
    if config_prompt_path.exists():
        return config_prompt_path.read_text(encoding="utf-8")

    # Fall back to legacy prompts/ directory
    legacy_prompt_path = LEGACY_PROMPTS_DIR / filename
    if legacy_prompt_path.exists():
        return legacy_prompt_path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Prompt file not found: {filename}\n"
        f"  Checked: {config_prompt_path}\n"
        f"  Checked: {legacy_prompt_path}"
    )


def load_prompt_with_vars(filename: str, **variables) -> str:
    """
    Load a prompt and substitute variables.

    Args:
        filename: Name of the prompt file.
        **variables: Variables to substitute in the prompt.
                    Use {variable_name} placeholders in the prompt.

    Returns:
        Prompt content with variables substituted.

    Example:
        prompt = load_prompt_with_vars(
            "summarize_user_prompt.md",
            article_text="...",
            max_words=100
        )
    """
    prompt = load_prompt(filename)
    return prompt.format(**variables)
