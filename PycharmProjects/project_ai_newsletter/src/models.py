"""
LLM Model Definitions and Helpers

All LLM models should be imported from this module.
This centralizes model management for easy updates when models become obsolete.
"""

from typing import Optional
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic


# =============================================================================
# Model Configurations
# =============================================================================

MODELS = {
    # OpenAI Models
    "gpt-4o": {
        "provider": "openai",
        "model_name": "gpt-4o",
        "temperature": 0.7,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "temperature": 0.7,
    },
    # Anthropic Models
    "claude-sonnet": {
        "provider": "anthropic",
        "model_name": "claude-sonnet-4-20250514",
        "temperature": 0.7,
    },
    "claude-haiku": {
        "provider": "anthropic",
        "model_name": "claude-haiku-4-5-20251001",
        "temperature": 0.7,
    },
    "gpt-5-mini": {
        "provider": "openai",
        "model_name": "gpt-5-mini",
        "temperature": 0.7,
    },
}

# Default model to use when none specified
DEFAULT_MODEL = "gpt-4o"


# =============================================================================
# Helper Functions
# =============================================================================

def get_model(
    model_name: Optional[str] = None,
    temperature: Optional[float] = None,
    **kwargs
):
    """
    Get an LLM instance by model name.

    Args:
        model_name: Name of the model (must be in MODELS dict).
                   Defaults to DEFAULT_MODEL if not specified.
        temperature: Override the default temperature for this model.
        **kwargs: Additional arguments passed to the model constructor.

    Returns:
        LLM instance (ChatOpenAI or ChatAnthropic)

    Raises:
        ValueError: If model_name is not found in MODELS.
    """
    if model_name is None:
        model_name = DEFAULT_MODEL

    if model_name not in MODELS:
        available = ", ".join(MODELS.keys())
        raise ValueError(f"Model '{model_name}' not found. Available: {available}")

    config = MODELS[model_name].copy()
    provider = config.pop("provider")

    # Override temperature if provided
    if temperature is not None:
        config["temperature"] = temperature

    # Merge additional kwargs
    config.update(kwargs)

    # Instantiate the appropriate model class
    if provider == "openai":
        return ChatOpenAI(**config)
    elif provider == "anthropic":
        return ChatAnthropic(**config)
    else:
        raise ValueError(f"Unknown provider: {provider}")


def get_default_model(**kwargs):
    """
    Get the default LLM instance.

    Args:
        **kwargs: Additional arguments passed to the model constructor.

    Returns:
        LLM instance using DEFAULT_MODEL.
    """
    return get_model(DEFAULT_MODEL, **kwargs)


def list_available_models() -> list[str]:
    """
    List all available model names.

    Returns:
        List of model name strings.
    """
    return list(MODELS.keys())
