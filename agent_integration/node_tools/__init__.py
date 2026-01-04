"""
Node Tool Wrappers

This package provides tool wrappers for existing Pipeline Nodes,
allowing LLM agents to execute nodes as tools while maintaining
full auditability and observability.

IMPORTANT:
- Does NOT duplicate node execution logic
- Does NOT modify core.models or core execution
- Wraps existing node execution with ToolExecution tracking
- Maintains pipeline graph constraints
"""

from .base import NodeToolWrapper, NodeToolResult
from .executor import NodeToolExecutor
from .registry import NodeToolRegistry, get_node_tool
from .utils import (
    get_available_tools_for_agent_run,
    get_executed_tools,
    get_tool_execution_history,
    can_execute_node,
    create_tool_description,
    format_tool_result_for_agent,
)

__all__ = [
    'NodeToolWrapper',
    'NodeToolResult',
    'NodeToolExecutor',
    'NodeToolRegistry',
    'get_node_tool',
    'get_available_tools_for_agent_run',
    'get_executed_tools',
    'get_tool_execution_history',
    'can_execute_node',
    'create_tool_description',
    'format_tool_result_for_agent',
]
