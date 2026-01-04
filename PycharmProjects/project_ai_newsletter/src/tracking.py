"""
Timing and Cost Tracking Utilities
"""

import time
import logging
import sys
from dataclasses import dataclass, field
from typing import Optional
from contextlib import contextmanager
from pathlib import Path


# =============================================================================
# Debug Logging Setup
# =============================================================================

def setup_debug_logging(log_file: str = "debug.log") -> logging.Logger:
    """
    Set up debug logging to both file and console.

    Args:
        log_file: Path to the log file (default: debug.log in project root)

    Returns:
        Configured logger instance.
    """
    # Create logger
    logger = logging.getLogger("rss_orchestrator")
    logger.setLevel(logging.DEBUG)

    # Clear any existing handlers
    logger.handlers.clear()

    # Create formatters
    detailed_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File handler - captures everything
    log_path = Path(log_file)
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)
    logger.addHandler(file_handler)

    # Console handler - also logs everything
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(detailed_formatter)
    logger.addHandler(console_handler)

    logger.info(f"Debug logging initialized. Log file: {log_path.absolute()}")

    return logger


# Global logger instance (initialized lazily)
_logger: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    """Get or create the global logger instance."""
    global _logger
    if _logger is None:
        _logger = setup_debug_logging()
    return _logger


def debug_log(message: str, level: str = "info"):
    """
    Log a debug message to both file and console.

    Args:
        message: The message to log.
        level: Log level - "debug", "info", "warning", "error".
    """
    logger = get_logger()
    level_map = {
        "debug": logger.debug,
        "info": logger.info,
        "warning": logger.warning,
        "error": logger.error,
    }
    log_func = level_map.get(level, logger.info)
    log_func(message)


# =============================================================================
# Cost Configuration (per 1M tokens)
# =============================================================================

MODEL_COSTS = {
    "claude-sonnet-4-20250514": {
        "input": 3.00,   # $3 per 1M input tokens
        "output": 15.00,  # $15 per 1M output tokens
    },
    "claude-3-5-sonnet-20241022": {
        "input": 3.00,
        "output": 15.00,
    },
    "claude-3-5-haiku-20241022": {
        "input": 0.80,
        "output": 4.00,
    },
    "claude-3-haiku-20240307": {
        "input": 0.25,
        "output": 1.25,
    },
}


# =============================================================================
# Cost Tracker
# =============================================================================

@dataclass
class LLMUsage:
    """Track usage for a single LLM call."""
    model: str
    input_tokens: int
    output_tokens: int

    @property
    def cost(self) -> float:
        """Calculate cost in USD."""
        if self.model not in MODEL_COSTS:
            # Default to Sonnet pricing
            costs = MODEL_COSTS["claude-sonnet-4-20250514"]
        else:
            costs = MODEL_COSTS[self.model]

        input_cost = (self.input_tokens / 1_000_000) * costs["input"]
        output_cost = (self.output_tokens / 1_000_000) * costs["output"]
        return input_cost + output_cost


@dataclass
class CostTracker:
    """Track costs across multiple LLM calls."""
    usages: list[LLMUsage] = field(default_factory=list)

    def add(self, model: str, input_tokens: int, output_tokens: int) -> LLMUsage:
        """Add a new usage record."""
        usage = LLMUsage(model=model, input_tokens=input_tokens, output_tokens=output_tokens)
        self.usages.append(usage)
        return usage

    @property
    def total_input_tokens(self) -> int:
        return sum(u.input_tokens for u in self.usages)

    @property
    def total_output_tokens(self) -> int:
        return sum(u.output_tokens for u in self.usages)

    @property
    def total_cost(self) -> float:
        return sum(u.cost for u in self.usages)

    @property
    def call_count(self) -> int:
        return len(self.usages)

    def print_summary(self):
        """Print cost summary."""
        print(f"\n{'='*60}")
        print("LLM COST SUMMARY")
        print(f"{'='*60}")
        print(f"  Total LLM calls: {self.call_count}")
        print(f"  Input tokens:    {self.total_input_tokens:,}")
        print(f"  Output tokens:   {self.total_output_tokens:,}")
        print(f"  Total cost:      ${self.total_cost:.4f}")
        print(f"{'='*60}\n")


# Global cost tracker
cost_tracker = CostTracker()


def reset_cost_tracker():
    """Reset the global cost tracker."""
    cost_tracker.usages.clear()


def track_llm_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Track an LLM call and return its cost."""
    usage = cost_tracker.add(model, input_tokens, output_tokens)
    cost = usage.cost
    debug_log(f"[COST] ${cost:.4f} ({input_tokens:,} in / {output_tokens:,} out)")
    return cost


# =============================================================================
# Timing
# =============================================================================

@dataclass
class NodeTiming:
    """Track timing for a node."""
    name: str
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def elapsed(self) -> float:
        return self.end_time - self.start_time

    def format_elapsed(self) -> str:
        elapsed = self.elapsed
        if elapsed < 1:
            return f"{elapsed*1000:.0f}ms"
        elif elapsed < 60:
            return f"{elapsed:.2f}s"
        else:
            minutes = int(elapsed // 60)
            seconds = elapsed % 60
            return f"{minutes}m {seconds:.1f}s"


@contextmanager
def track_time(node_name: str):
    """Context manager to track node execution time."""
    timing = NodeTiming(name=node_name, start_time=time.time())
    try:
        yield timing
    finally:
        timing.end_time = time.time()
        debug_log(f"[TIME] {node_name}: {timing.format_elapsed()}")
