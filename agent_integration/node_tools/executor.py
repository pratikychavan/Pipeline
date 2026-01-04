"""
Node Tool Executor - Wraps existing node execution logic.

This module provides the concrete implementation that:
1. Creates ToolExecution records
2. Invokes existing backend.execute_node()
3. Tracks timing and results
4. Does NOT duplicate node execution code
"""

import uuid
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from asgiref.sync import sync_to_async

from django.db import transaction
from core.models import Node, NodeExecution, PipelineExecution
from core.execution import get_execution_backend
from agent_integration.models import AgentRun, AgentDecision, ToolExecution

from .base import NodeToolWrapper, NodeToolResult


class NodeToolExecutor(NodeToolWrapper):
    """
    Concrete implementation of NodeToolWrapper.
    
    This class wraps existing node execution logic without
    duplicating it. It uses the same backend.execute_node()
    that the pipeline already uses.
    """
    
    def __init__(self, node_id: uuid.UUID, node_name: str, node: Optional[Node] = None):
        """
        Initialize executor.
        
        Args:
            node_id: UUID of the node
            node_name: Name of the node
            node: Optional Node instance (avoids DB query)
        """
        super().__init__(node_id, node_name)
        self._node = node
    
    @property
    def node(self) -> Node:
        """Lazy-load node from database."""
        if self._node is None:
            self._node = Node.objects.select_related('pipeline').get(pk=self.node_id)
        return self._node
    
    async def execute(
        self,
        agent_run_id: uuid.UUID,
        agent_decision_id: Optional[uuid.UUID],
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> NodeToolResult:
        """
        Execute node using existing execution logic.
        
        This method:
        1. Validates parameters and context
        2. Creates ToolExecution record
        3. Calls existing backend.execute_node() (the same one used by pipeline execution)
        4. Records results in ToolExecution
        5. Returns NodeToolResult for agent
        
        Args:
            agent_run_id: Agent run triggering this
            agent_decision_id: Decision that led here
            parameters: Tool parameters from agent
            context: Execution context
        
        Returns:
            NodeToolResult with execution summary
        """
        start_time = time.time()
        
        # Validate parameters
        is_valid, error_msg = self.validate_parameters(parameters)
        if not is_valid:
            return NodeToolResult(
                success=False,
                tool_execution_id=uuid.uuid4(),
                node_execution_id=uuid.uuid4(),
                duration_seconds=time.time() - start_time,
                summary=f"Parameter validation failed: {error_msg}",
                error_message=error_msg,
                error_type='validation_error',
            )
        
        # Execute in sync context (database operations)
        return await sync_to_async(self._execute_sync)(
            agent_run_id,
            agent_decision_id,
            parameters,
            context,
            start_time,
        )
    
    def _execute_sync(
        self,
        agent_run_id: uuid.UUID,
        agent_decision_id: Optional[uuid.UUID],
        parameters: Dict[str, Any],
        context: Dict[str, Any],
        start_time: float,
    ) -> NodeToolResult:
        """
        Synchronous execution implementation.
        
        This wraps the existing node execution logic.
        """
        with transaction.atomic():
            # Get agent run and pipeline execution
            agent_run = AgentRun.objects.select_related('pipeline_execution').get(pk=agent_run_id)
            pipeline_execution = agent_run.pipeline_execution
            
            # Get agent decision if provided
            agent_decision = None
            if agent_decision_id:
                agent_decision = AgentDecision.objects.get(pk=agent_decision_id)
            
            # Create NodeExecution record (as done by existing pipeline executor)
            node_execution = NodeExecution.objects.create(
                pipeline_execution=pipeline_execution,
                node=self.node,
                status='running',
                started_at=datetime.now(timezone.utc),
                input_data=parameters,  # Parameters provided by agent
            )
            
            # Create ToolExecution record to track agent-initiated execution
            tool_execution = ToolExecution.objects.create(
                agent_run=agent_run,
                node_execution=node_execution,
                agent_decision=agent_decision,
                status='running',
                tool_name=self.node_name,
                tool_parameters=parameters,
                started_at=datetime.now(timezone.utc),
            )
        
        # Execute node using existing backend
        # This is the SAME execution path used by regular pipeline execution
        try:
            # Merge parameters into context for node execution
            execution_context = context.copy()
            execution_context.update(parameters)
            
            # Get execution backend (same as used by views.execute_pipeline_async)
            backend = get_execution_backend()
            
            # Execute node - this calls the EXISTING logic in core/execution/backends.py
            output_data = backend.execute_node(
                node=self.node,
                context=execution_context,
                execution=pipeline_execution,
            )
            
            # Record success
            with transaction.atomic():
                node_execution.status = 'completed'
                node_execution.output_data = output_data
                node_execution.completed_at = datetime.now(timezone.utc)
                node_execution.save()
                
                # Extract artifacts and create summary
                artifact_refs = self._extract_artifact_references(output_data)
                summary = self._create_result_summary(True, output_data)
                
                tool_execution.status = 'completed'
                tool_execution.result_summary = summary
                tool_execution.artifact_references = artifact_refs
                tool_execution.completed_at = datetime.now(timezone.utc)
                tool_execution.save()
            
            duration = time.time() - start_time
            
            return NodeToolResult(
                success=True,
                tool_execution_id=tool_execution.id,
                node_execution_id=node_execution.id,
                duration_seconds=duration,
                summary=summary,
                artifact_references=artifact_refs,
                output_variables=[k for k in output_data.keys() if not k.startswith('_')],
                metadata={
                    'node_name': self.node_name,
                    'node_id': str(self.node_id),
                    'backend': backend.__class__.__name__,
                },
            )
        
        except Exception as e:
            # Record failure
            error_message = str(e)
            error_type = type(e).__name__
            
            with transaction.atomic():
                node_execution.status = 'failed'
                node_execution.error_message = error_message
                node_execution.completed_at = datetime.now(timezone.utc)
                node_execution.save()
                
                tool_execution.status = 'failed'
                tool_execution.result_summary = f"Execution failed: {error_message}"
                tool_execution.completed_at = datetime.now(timezone.utc)
                tool_execution.save()
            
            duration = time.time() - start_time
            
            return NodeToolResult(
                success=False,
                tool_execution_id=tool_execution.id,
                node_execution_id=node_execution.id,
                duration_seconds=duration,
                summary=self._create_result_summary(False, {}, error_message),
                error_message=error_message,
                error_type=error_type,
                metadata={
                    'node_name': self.node_name,
                    'node_id': str(self.node_id),
                },
            )
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate parameters for this node.
        
        Checks that required input variables are provided.
        """
        # Get node's input variable mappings
        if not self.node.input_variable_mappings:
            # No specific inputs required
            return True, None
        
        # Check if all required inputs are in parameters or can be resolved
        required_vars = set(self.node.input_variable_mappings.keys())
        provided_vars = set(parameters.keys())
        
        missing_vars = required_vars - provided_vars
        
        if missing_vars:
            return False, f"Missing required input variables: {', '.join(missing_vars)}"
        
        return True, None
    
    def get_tool_definition(self) -> Dict[str, Any]:
        """
        Get full tool definition including node details.
        """
        base_def = super().get_tool_definition()
        
        # Add node-specific details
        base_def.update({
            'description': self.node.description or f'Execute node: {self.node_name}',
            'input_variables': list(self.node.input_variable_mappings.keys()) if self.node.input_variable_mappings else [],
            'pipeline_id': str(self.node.pipeline_id),
            'pipeline_name': self.node.pipeline.name,
        })
        
        return base_def
