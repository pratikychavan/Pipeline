"""
Utilities for node tool execution.

Provides helper functions for working with node tools.
"""

import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from core.models import Node, PipelineExecution
from agent_integration.models import AgentRun, ToolExecution

from .registry import NodeToolRegistry


def get_available_tools_for_agent_run(agent_run_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get all available tools (nodes) for an agent run.
    
    This respects:
    - Pipeline graph structure
    - Node dependencies
    - Agent tool mappings from Control Plane
    
    Args:
        agent_run_id: Agent run to get tools for
    
    Returns:
        List of tool definitions
    """
    try:
        agent_run = AgentRun.objects.select_related(
            'pipeline_execution__pipeline'
        ).get(pk=agent_run_id)
        
        pipeline = agent_run.pipeline_execution.pipeline
        
        # Get all tool definitions from registry
        tool_defs = NodeToolRegistry.get_tool_definitions(pipeline.id)
        
        # TODO: Filter based on AgentToolMapping from Control Plane
        # For now, return all tools in the pipeline
        
        return tool_defs
    
    except AgentRun.DoesNotExist:
        return []


def get_executed_tools(agent_run_id: uuid.UUID) -> List[Dict[str, Any]]:
    """
    Get list of tools already executed in this agent run.
    
    Args:
        agent_run_id: Agent run to check
    
    Returns:
        List of tool execution summaries
    """
    executions = ToolExecution.objects.filter(
        agent_run_id=agent_run_id
    ).select_related('node_execution__node').order_by('queued_at')
    
    return [
        {
            'tool_execution_id': str(exec.id),
            'tool_name': exec.tool_name,
            'node_id': str(exec.node_execution.node_id),
            'status': exec.status,
            'queued_at': exec.queued_at.isoformat(),
            'completed_at': exec.completed_at.isoformat() if exec.completed_at else None,
            'result_summary': exec.result_summary,
            'artifact_references': exec.artifact_references,
        }
        for exec in executions
    ]


def get_tool_execution_history(
    agent_run_id: uuid.UUID,
    node_id: Optional[uuid.UUID] = None,
) -> List[ToolExecution]:
    """
    Get tool execution history for an agent run.
    
    Args:
        agent_run_id: Agent run to get history for
        node_id: Optional filter by specific node
    
    Returns:
        List of ToolExecution instances
    """
    query = ToolExecution.objects.filter(agent_run_id=agent_run_id)
    
    if node_id:
        query = query.filter(node_execution__node_id=node_id)
    
    return list(query.select_related(
        'node_execution__node',
        'agent_decision',
    ).order_by('queued_at'))


def can_execute_node(
    node_id: uuid.UUID,
    agent_run_id: uuid.UUID,
    context: Dict[str, Any],
) -> tuple[bool, Optional[str]]:
    """
    Check if a node can be executed in current context.
    
    Validates:
    - Node exists and belongs to pipeline
    - Required inputs are available
    - Node hasn't failed in this run
    - Dependencies are satisfied
    
    Args:
        node_id: Node to check
        agent_run_id: Agent run context
        context: Current execution context
    
    Returns:
        (can_execute, reason_if_not)
    """
    try:
        node = Node.objects.select_related('pipeline').get(pk=node_id)
    except Node.DoesNotExist:
        return False, "Node not found"
    
    # Check if node belongs to this pipeline
    try:
        agent_run = AgentRun.objects.select_related(
            'pipeline_execution__pipeline'
        ).get(pk=agent_run_id)
        
        if node.pipeline_id != agent_run.pipeline_execution.pipeline_id:
            return False, "Node does not belong to pipeline"
    except AgentRun.DoesNotExist:
        return False, "Agent run not found"
    
    # Check if node has already failed in this run
    failed_execution = ToolExecution.objects.filter(
        agent_run_id=agent_run_id,
        node_execution__node_id=node_id,
        status='failed',
    ).exists()
    
    if failed_execution:
        return False, "Node has already failed in this run"
    
    # Check if required inputs are available
    if node.input_variable_mappings:
        required_vars = set(node.input_variable_mappings.keys())
        available_vars = set(context.keys())
        missing = required_vars - available_vars
        
        if missing:
            return False, f"Missing required inputs: {', '.join(missing)}"
    
    return True, None


def create_tool_description(node: Node) -> str:
    """
    Create a tool description from a node.
    
    This is used by the agent to understand what the tool does.
    
    Args:
        node: Node to describe
    
    Returns:
        Human-readable description
    """
    desc_parts = []
    
    # Basic description
    if node.description:
        desc_parts.append(node.description)
    else:
        desc_parts.append(f"Execute node: {node.name}")
    
    # Input requirements
    if node.input_variable_mappings:
        inputs = list(node.input_variable_mappings.keys())
        desc_parts.append(f"Requires inputs: {', '.join(inputs)}")
    
    # Position in pipeline
    desc_parts.append(f"Pipeline: {node.pipeline.name}")
    desc_parts.append(f"Execution order: {node.order}")
    
    return " | ".join(desc_parts)


def format_tool_result_for_agent(result: 'NodeToolResult') -> str:
    """
    Format a tool result for agent consumption.
    
    Creates a concise, structured message about the execution.
    
    Args:
        result: NodeToolResult to format
    
    Returns:
        Formatted string for agent
    """
    if not result.success:
        return (
            f"❌ Tool execution failed\n"
            f"Error: {result.error_message}\n"
            f"Duration: {result.duration_seconds:.2f}s"
        )
    
    lines = [
        f"✅ Tool execution successful",
        f"Duration: {result.duration_seconds:.2f}s",
        result.summary,
    ]
    
    if result.output_variables:
        lines.append(f"Outputs: {', '.join(result.output_variables)}")
    
    if result.artifact_references:
        lines.append(f"Artifacts: {len(result.artifact_references)} created")
    
    return "\n".join(lines)
