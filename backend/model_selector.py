import os
from datetime import datetime, timedelta

# In-memory monitoring for rate limits (429 exceptions)
RATE_LIMIT_COOLDOWNS = {}

def get_ordered_models(fallback_default: str) -> list[str]:
    """Returns the prioritized list of valid models, skipping active rate limits."""
    candidates = [
        fallback_default,
        "qwen/qwen3-32b",
        "qwen/qwen3.6-27b",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-20b"
    ]
    
    unique_candidates = []
    seen = set()
    now = datetime.utcnow()
    
    for model in candidates:
        if model in seen:
            continue
        seen.add(model)
        
        # Check if the model is currently down on cooldown
        if model in RATE_LIMIT_COOLDOWNS and now < RATE_LIMIT_COOLDOWNS[model]:
            continue
            
        unique_candidates.append(model)
        
    return unique_candidates if unique_candidates else [fallback_default]

def mark_rate_limited(model_name: str):
    """Flags a model as limited, placing it on a 2-minute cooldown window."""
    RATE_LIMIT_COOLDOWNS[model_name] = datetime.utcnow() + timedelta(minutes=2)
