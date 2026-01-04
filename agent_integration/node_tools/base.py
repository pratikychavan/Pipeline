"""
Base classes for Node Tool Wrappers.

These classes provide the interface for wrapping Pipeline Nodes
as tools without modifying the underlying execution logic.
"""

import time
import uuid
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field
from datetime import datetime, timezone
from abc import ABC, abstractmethod


@dataclass
class NodeToolResult:
    """
    Result of a node tool execution.
    
    This is what gets returned to the agent - no raw data,
    only references and summaries.
    """
    success: bool
    tool_execution_id: uuid.UUID
    node_execution_id: uuid.UUID
    duration_seconds: float
    
    # For agent consumption
    summary: str
    artifact_references: List[str] = field(default_factory=list)
    output_variables: List[str] = field(default_factory=list)
    
    # Error handling
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    
    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'success': self.success,
            'tool_execution_id': str(self.tool_execution_id),
            'node_execution_id': str(self.node_execution_id),
            'duration_seconds': self.duration_seconds,
            'summary': self.summary,
            'artifact_references': self.artifact_references,
            'output_variables': self.output_variables,
            'error_message': self.error_message,
            'error_type': self.error_type,
            'metadata': self.metadata,
        }


class NodeToolWrapper(ABC):
    """
    Base class for wrapping Pipeline Nodes as tools.
    
    This wrapper:
    - Accepts node_id and execution context
    - Triggers existing node execution logic
    - Creates ToolExecution record
    - Reports results without exposing raw data
    """
    
    def __init__(self, node_id: uuid.UUID, node_name: str):
        """
        Initialize tool wrapper.
        
        Args:
            node_id: UUID of the node to wrap
            node_name: Name of the node (for display)
        """
        self.node_id = node_id
        self.node_name = node_name
    
    @abstractmethod
    async def execute(
        self,
        agent_run_id: uuid.UUID,
        agent_decision_id: Optional[uuid.UUID],
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> NodeToolResult:
        """
        Execute the node as a tool.
        
        Args:
            agent_run_id: ID of the agent run triggering this
            agent_decision_id: ID of the decision that led to this execution
            parameters: Tool-specific parameters from agent
            context: Execution context (variables, state)
        
        Returns:
            NodeToolResult with execution summary
        """
        pass
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate tool parameters before execution.
        
        Args:
            parameters: Parameters to validate
        
        Returns:
            (is_valid, error_message)
        """
        # Default implementation - override in subclasses for specific validation
        return True, None
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get tool definition for agent context.
        
        Returns:
            Dictionary describing the tool's interface
        """
        return {
            'tool_id': str(self.node_id),
            'tool_name': self.node_name,
            'tool_type': 'pipeline_node',
            'description': f'Execute pipeline node: {self.node_name}',
        }
    
    def _create_result_summary(
        self,
        success: bool,
        output_data: Dict[str, Any],
        error_message: Optional[str] = None,
    ) -> str:
        """
        Create human-readable summary for agent.
        
        This should NEVER include raw data, only descriptions
        of what was produced.
        
        Args:
            success: Whether execution succeeded
            output_data: Output variables from node
            error_message: Error message if failed
        
        Returns:
            Summary string for agent consumption
        """
        if not success:
            return f"Node '{self.node_name}' failed: {error_message}"
        
        # Describe outputs without revealing data
        output_vars = [k for k in output_data.keys() if not k.startswith('_')]
        
        if not output_vars:
            return f"Node '{self.node_name}' completed successfully (no outputs)"
        
        return (
            f"Node '{self.node_name}' completed successfully. "
            f"Produced {len(output_vars)} output variable(s): {', '.join(output_vars)}"
        )
    
    def _extract_artifact_references(self, output_data: Dict[str, Any]) -> List[str]:
        """
        Extract artifact references from output data.
        
        Looks for artifact metadata markers and returns references.
        
        Args:
            output_data: Output variables from node execution
        
        Returns:
            List of artifact reference strings
        """
        artifacts = []
        
        for key, value in output_data.items():
            # Check for artifact metadata (as set by WarpDrive)
            if isinstance(value, dict) and value.get('_artifact'):
                artifact_ref = value.get('_artifact_path') or value.get('_artifact_id')
                if artifact_ref:
                    artifacts.append(f"{key}:{artifact_ref}")
        
        return artifacts
