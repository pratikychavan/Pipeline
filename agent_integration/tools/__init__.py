"""
Tool Abstraction Layer

Wraps Node execution as Tools for LLM agent consumption.
Does NOT move or duplicate node execution logic.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass
import json
from core.models import Node, PipelineExecution, NodeExecution
from core.execution import get_execution_backend
from django.utils import timezone


@dataclass
class ToolDefinition:
    """
    Tool definition for LLM consumption.
    
    This is a read-only view of a Node as a Tool.
    """
    tool_id: str
    tool_name: str
    description: str
    parameters: Dict[str, Any]
    returns: Dict[str, Any]
    constraints: Dict[str, Any]
    
    def to_dict(self) -> dict:
        """Serialize to JSON-safe dict."""
        return {
            'tool_id': self.tool_id,
            'tool_name': self.tool_name,
            'description': self.description,
            'parameters': self.parameters,
            'returns': self.returns,
            'constraints': self.constraints,
        }


class NodeToolWrapper:
    """
    Wraps a Node as a Tool for agent consumption.
    
    Responsibilities:
    - Expose node as tool definition
    - Trigger existing node execution logic
    - Record execution as ToolExecution
    - Return artifact references only (not raw data)
    """
    
    def __init__(self, node: Node):
        self.node = node
    
    def to_tool_definition(self) -> ToolDefinition:
        """
        Convert Node to ToolDefinition.
        
        This is what the LLM sees.
        """
        # Extract input parameters from input_variable_mappings
        input_params = {}
        if self.node.input_variable_mappings:
            for var_name, mapping in self.node.input_variable_mappings.items():
                input_params[var_name] = {
                    'type': 'artifact_reference',
                    'required': True,
                    'description': f'Input variable {var_name}',
                    'source': mapping.get('source_variable', 'unknown')
                }
        
        # TODO: Parse node.code to detect output types
        # For now, assume generic artifact outputs
        returns = {
            'artifacts': {
                'type': 'list[artifact_reference]',
                'description': 'List of artifacts produced by this node'
            }
        }
        
        # Extract constraints from node position and dependencies
        constraints = {
            'execution_order': self.node.order,
            'dependencies': list(input_params.keys()),
            'node_id': str(self.node.id),
        }
        
        return ToolDefinition(
            tool_id=str(self.node.id),
            tool_name=self.node.name,
            description=self.node.description or f"Execute node: {self.node.name}",
            parameters=input_params,
            returns=returns,
            constraints=constraints
        )
    
    def execute(
        self,
        agent_run: 'AgentRun',
        context: Dict[str, Any],
        agent_decision: Optional['AgentDecision'] = None
    ) -> Dict[str, Any]:
        """
        Execute the node using existing execution logic.
        
        Args:
            agent_run: The agent run controlling this execution
            context: Execution context with input variables
            agent_decision: The agent decision that triggered this execution
            
        Returns:
            Dict containing:
                - tool_execution_id: UUID of ToolExecution record
                - status: execution status
                - artifact_references: list of artifact paths/IDs
                - summary: human-readable summary
        """
        from ..models import ToolExecution
        
        # Get the pipeline execution
        pipeline_execution = agent_run.pipeline_execution
        
        # Create or get NodeExecution
        node_execution, created = NodeExecution.objects.get_or_create(
            pipeline_execution=pipeline_execution,
            node=self.node,
            defaults={
                'status': 'pending',
                'input_data': self._sanitize_context_for_storage(context)
            }
        )
        
        # Create ToolExecution record
        tool_execution = ToolExecution.objects.create(
            agent_run=agent_run,
            node_execution=node_execution,
            agent_decision=agent_decision,
            tool_name=self.node.name,
            tool_parameters=self._sanitize_context_for_storage(context),
            status='queued'
        )
        
        try:
            # Update status
            node_execution.status = 'running'
            node_execution.started_at = timezone.now()
            node_execution.save()
            
            tool_execution.status = 'running'
            tool_execution.started_at = timezone.now()
            tool_execution.save()
            
            # Execute using existing backend
            backend = get_execution_backend()
            outputs = backend.execute_node(self.node, context, pipeline_execution)
            
            # Record outputs
            node_execution.output_data = outputs
            node_execution.output_logs = outputs.get('_output_logs', '')
            node_execution.status = 'completed'
            node_execution.completed_at = timezone.now()
            node_execution.save()
            
            # Extract artifact references (not raw data)
            artifact_refs = self._extract_artifact_references(outputs)
            
            # Create summary for agent
            summary = self._create_execution_summary(outputs, artifact_refs)
            
            # Update tool execution
            tool_execution.status = 'completed'
            tool_execution.completed_at = timezone.now()
            tool_execution.artifact_references = artifact_refs
            tool_execution.result_summary = summary
            tool_execution.save()
            
            return {
                'tool_execution_id': str(tool_execution.id),
                'status': 'completed',
                'artifact_references': artifact_refs,
                'summary': summary,
                'logs': node_execution.output_logs
            }
            
        except Exception as e:
            # Record failure
            node_execution.status = 'failed'
            node_execution.error_message = str(e)
            node_execution.completed_at = timezone.now()
            node_execution.save()
            
            tool_execution.status = 'failed'
            tool_execution.completed_at = timezone.now()
            tool_execution.result_summary = f"Execution failed: {str(e)}"
            tool_execution.save()
            
            return {
                'tool_execution_id': str(tool_execution.id),
                'status': 'failed',
                'error': str(e),
                'summary': f"Node execution failed: {str(e)}"
            }
    
    def _sanitize_context_for_storage(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize context for storage in database.
        
        Removes non-serializable objects and converts artifact references.
        """
        sanitized = {}
        for key, value in context.items():
            if key.startswith('__'):
                # Skip internal variables
                continue
            
            if isinstance(value, dict) and value.get('_artifact'):
                # Keep artifact references
                sanitized[key] = {
                    '_artifact': True,
                    '_type': value.get('_type'),
                    '_file': value.get('_file')
                }
            else:
                try:
                    # Test JSON serializability
                    json.dumps(value)
                    sanitized[key] = value
                except (TypeError, ValueError):
                    # Non-serializable - just store type
                    sanitized[key] = f"<{type(value).__name__}>"
        
        return sanitized
    
    def _extract_artifact_references(self, outputs: Dict[str, Any]) -> List[str]:
        """
        Extract artifact file references from outputs.
        
        Returns list of file paths, not the actual data.
        """
        references = []
        
        for key, value in outputs.items():
            if key.startswith('_'):
                # Skip internal keys like _output_logs
                continue
            
            if isinstance(value, dict) and value.get('_artifact'):
                file_path = value.get('_file')
                if file_path:
                    references.append(file_path)
        
        return references
    
    def _create_execution_summary(
        self,
        outputs: Dict[str, Any],
        artifact_refs: List[str]
    ) -> str:
        """
        Create human-readable summary for agent consumption.
        
        Does NOT include raw data, only metadata.
        """
        lines = [f"Node '{self.node.name}' executed successfully."]
        
        if artifact_refs:
            lines.append(f"Produced {len(artifact_refs)} artifact(s):")
            for ref in artifact_refs:
                lines.append(f"  - {ref}")
        else:
            lines.append("No artifacts produced.")
        
        # Add variable names (but not values)
        output_vars = [k for k in outputs.keys() if not k.startswith('_')]
        if output_vars:
            lines.append(f"Output variables: {', '.join(output_vars)}")
        
        return '\n'.join(lines)


class ToolRegistry:
    """
    Registry of available tools for a pipeline.
    
    Provides tool lookup and validation.
    """
    
    def __init__(self, pipeline: 'Pipeline'):
        self.pipeline = pipeline
        self._tools: Dict[str, NodeToolWrapper] = {}
        self._initialize_tools()
    
    def _initialize_tools(self):
        """Load all nodes as tools."""
        from core.models import Node
        
        nodes = Node.objects.filter(pipeline=self.pipeline).order_by('order')
        for node in nodes:
            wrapper = NodeToolWrapper(node)
            self._tools[str(node.id)] = wrapper
    
    def get_tool(self, tool_id: str) -> Optional[NodeToolWrapper]:
        """Get tool by ID."""
        return self._tools.get(tool_id)
    
    def get_all_tools(self) -> List[NodeToolWrapper]:
        """Get all available tools."""
        return list(self._tools.values())
    
    def get_tool_definitions(self) -> List[ToolDefinition]:
        """Get all tool definitions for LLM consumption."""
        return [tool.to_tool_definition() for tool in self._tools.values()]
    
    def validate_tool_exists(self, tool_id: str) -> bool:
        """Check if tool exists."""
        return tool_id in self._tools
