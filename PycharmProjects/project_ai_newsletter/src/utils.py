"""
Utility functions for the project.
"""

from pathlib import Path


# =============================================================================
# Prompt Loading
# =============================================================================

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"


def load_prompt(filename: str) -> str:
    """
    Load a prompt from the prompts/ directory.

    Args:
        filename: Name of the prompt file (e.g., "summarize_system_prompt.md")

    Returns:
        Prompt content as string.

    Raises:
        FileNotFoundError: If the prompt file doesn't exist.
    """
    prompt_path = PROMPTS_DIR / filename
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


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
