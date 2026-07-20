"""
Base interface every connector implements.

A connector is a self-contained plugin: it owns a domain (todos, notes, whatever you add next),
declares its own tool schemas, and knows how to execute them. The agent never hardcodes domain
logic — it only ever talks to connectors through this interface, so adding a new capability means
adding a new connector module, not touching the core agent loop.
"""
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class Connector:
    name: str                                    # unique id, e.g. "todos", "notes"
    description: str                             # shown to the router so it can decide relevance
    tools: list                                  # list of Groq/OpenAI-style function tool schemas
    handle: Callable[[str, dict, str], dict]      # (tool_name, args, user_id) -> JSON-able result
    system_prompt: str = field(default="")        # extra instructions merged into the agent's system prompt
