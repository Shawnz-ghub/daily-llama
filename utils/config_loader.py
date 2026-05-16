"""
Config loader for The Daily Llama.
Loads configuration from ~/site-data/config.yaml.
"""

import os
import yaml

from utils.paths import CONFIG_PATH


def load_config():
    """Load configuration from ~/site-data/config.yaml.

    Returns the parsed YAML dict. Raises FileNotFoundError if the config
    file does not exist, and yaml.YAMLError on parse failures.
    """
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def get_default_config():
    """Return a minimal default config for bootstrapping.

    Used when config.yaml does not yet exist so collect/render steps
    that need a config can still run with sensible defaults.
    """
    return {
        "categories": {
            "AI/LLM": {
                "weight": 10,
                "keywords": [
                    "LLM", "large language model", "transformer", "GPT",
                    "Claude", "DeepSeek", "agent", "reasoning", "RLHF",
                    "fine-tuning", "LoRA", "RAG", "open source model",
                    "open weights",
                ],
            },
            "Hermes Agent": {
                "weight": 15,
                "keywords": [
                    "Hermes Agent", "hermes-agent", "Nous Research",
                    "nousresearch", "subagent", "kanban worker", "multi-agent",
                ],
            },
        },
        "source_multipliers": {},
        "youtube_source_multipliers": {},
        "thresholds": {
            "featured_video_min_score": 0.80,
            "runner_up_min_score": 0.65,
            "news_card_min_score": 0.30,
            "novel_finding_min_score": 0.55,
            "novel_finding_source_multiplier_max": 0.0,
        },
        "recency": {
            "half_life_hours": 48,
            "max_age_hours": 168,
        },
        "display": {
            "featured_video_count": 1,
            "runner_up_count_min": 2,
            "runner_up_count_max": 4,
            "news_card_soft_cap": 50,
        },
        "prospecting": {
            "enabled": True,
            "max_sources_to_scout": 5,
        },
    }
