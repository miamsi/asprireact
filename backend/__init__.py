"""
Connector registry.

To add a new connector: write a new module in this package exposing a module-level `connector`
(a connectors.base.Connector instance), then register it in ALL_CONNECTORS below. Nothing else
in the app needs to change — agent.py discovers tools and routes to handlers purely through
this registry.
"""
from .base import Connector
from .todos import connector as todos_connector
from .notes import connector as notes_connector

ALL_CONNECTORS: dict[str, Connector] = {
    todos_connector.name: todos_connector,
    notes_connector.name: notes_connector,
}


def get_connector_for_tool(tool_name: str) -> Connector | None:
    """Find which connector owns a given tool/function name."""
    for connector in ALL_CONNECTORS.values():
        if any(t["function"]["name"] == tool_name for t in connector.tools):
            return connector
    return None


def tools_for(connector_names: list[str]) -> list[dict]:
    """Flatten the tool schemas for a chosen subset of connectors."""
    tools = []
    for name in connector_names:
        conn = ALL_CONNECTORS.get(name)
        if conn:
            tools.extend(conn.tools)
    return tools


def prompts_for(connector_names: list[str]) -> str:
    """Concatenate the extra system-prompt instructions for a chosen subset of connectors."""
    parts = []
    for name in connector_names:
        conn = ALL_CONNECTORS.get(name)
        if conn and conn.system_prompt:
            parts.append(conn.system_prompt.strip())
    return "\n\n".join(parts)
