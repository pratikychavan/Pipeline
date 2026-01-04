"""
Runtime Specification Materialization

Converts a Pipeline into an immutable, JSON-serializable runtime spec
that can be safely passed to an agent runner.
"""

from typing import Dict, Any, List, Optional
import hashlib
import json
from dataclasses import dataclass, asdict
from core.models import Pipeline, Node
from ..tools import ToolRegistry


@dataclass
class ExecutionConstraint:
    """Represents a constraint on execution flow."""
    constraint_type: str  # 'dependency', 'order', 'conditional'
    source_node_id: Optional[str]
    target_node_id: str
    condition: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BusinessCondition:
    """Represents a business logic condition."""
    condition_id: str
    condition_type: str  # 'skip_if', 'execute_if', 'retry_if'
    node_id: str
    expression: str
    description: str
    
    def to_dict(self) -> dict:
        return asdict(self)


class RuntimeSpecBuilder:
    """
    Builds immutable runtime specifications from Pipelines.
    
    This is the bridge between Django models and agent runtime.
    """
    
    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        self.tool_registry = ToolRegistry(pipeline)
    
    def build_spec(self) -> Dict[str, Any]:
        """
        Build complete runtime specification.
        
        Returns:
            Immutable, JSON-serializable spec containing:
            - Pipeline metadata
            - Available tools
            - Execution constraints
            - Business conditions
            - Global context
        """
        spec = {
            'spec_version': '1.0',
            'pipeline_id': str(self.pipeline.id),
            'pipeline_name': self.pipeline.name,
            'pipeline_description': self.pipeline.description,
            'created_at': self.pipeline.created_at.isoformat(),
            
            # Tools (nodes as callable units)
            'available_tools': self._build_tool_specs(),
            
            # Execution constraints (DAG structure)
            'execution_constraints': self._build_constraints(),
            
            # Business conditions (conditional execution)
            'business_conditions': self._build_business_conditions(),
            
            # Global context
            'global_context': self._build_global_context(),
            
            # Execution policies
            'execution_policies': self._build_execution_policies(),
        }
        
        return spec
    
    def _build_tool_specs(self) -> List[Dict[str, Any]]:
        """Build tool specifications from nodes."""
        tool_defs = self.tool_registry.get_tool_definitions()
        return [tool.to_dict() for tool in tool_defs]
    
    def _build_constraints(self) -> List[Dict[str, Any]]:
        """
        Build execution constraints from node dependencies.
        
        Constraints enforce:
        - Node execution order
        - Data dependencies
        - Graph connectivity
        """
        constraints = []
        
        nodes = Node.objects.filter(pipeline=self.pipeline).order_by('order')
        
        for node in nodes:
            # Order constraint
            constraints.append(ExecutionConstraint(
                constraint_type='order',
                source_node_id=None,
                target_node_id=str(node.id),
                condition={'min_order': node.order}
            ).to_dict())
            
            # Dependency constraints from input_variable_mappings
            if node.input_variable_mappings:
                for var_name, mapping in node.input_variable_mappings.items():
                    source_node_id = mapping.get('node_id')
                    if source_node_id and source_node_id != '__pipeline__':
                        constraints.append(ExecutionConstraint(
                            constraint_type='dependency',
                            source_node_id=source_node_id,
                            target_node_id=str(node.id),
                            condition={
                                'required_output': mapping.get('source_variable'),
                                'target_input': var_name
                            }
                        ).to_dict())
        
        return constraints
    
    def _build_business_conditions(self) -> List[Dict[str, Any]]:
        """
        Build business conditions for conditional execution.
        
        TODO: This requires a mechanism to define conditions in the UI.
        For now, return empty list and add conditions as needed.
        """
        # TODO: Implement condition parsing from node metadata
        # For now, all nodes are mandatory
        conditions = []
        
        # Example: Add a condition if node has special metadata
        # nodes = Node.objects.filter(pipeline=self.pipeline)
        # for node in nodes:
        #     if node.metadata and 'execution_condition' in node.metadata:
        #         conditions.append(BusinessCondition(...).to_dict())
        
        return conditions
    
    def _build_global_context(self) -> Dict[str, Any]:
        """
        Build global context from pipeline-level arguments.
        
        This includes pipeline.global_arguments and any other
        pipeline-level configuration.
        """
        return {
            'pipeline_arguments': self.pipeline.global_arguments or [],
            'pipeline_metadata': {
                'created_by': self.pipeline.created_by.username,
                'is_active': self.pipeline.is_active,
            }
        }
    
    def _build_execution_policies(self) -> Dict[str, Any]:
        """
        Build execution policies for agent behavior.
        
        These policies control how the agent should behave during execution.
        """
        return {
            'max_iterations': 100,
            'allow_parallel_execution': False,  # Execute sequentially for safety
            'retry_policy': {
                'max_retries': 3,
                'retry_delay_seconds': 5,
                'retry_on_errors': ['transient', 'timeout']
            },
            'human_intervention': {
                'enabled': True,
                'trigger_on_errors': True,
                'trigger_on_ambiguity': True,
            },
            'safety': {
                'enforce_dag_constraints': True,
                'prevent_infinite_loops': True,
                'max_consecutive_failures': 3,
            }
        }
    
    def compute_checksum(self, spec: Dict[str, Any]) -> str:
        """
        Compute checksum of spec for verification.
        
        This ensures spec hasn't been tampered with.
        """
        spec_json = json.dumps(spec, sort_keys=True)
        return hashlib.sha256(spec_json.encode()).hexdigest()
    
    def materialize_and_save(self, agent_run: 'AgentRun') -> 'RuntimeSpec':
        """
        Build spec and save to database.
        
        Returns:
            RuntimeSpec model instance
        """
        from ..models import RuntimeSpec
        
        spec_data = self.build_spec()
        checksum = self.compute_checksum(spec_data)
        
        runtime_spec = RuntimeSpec.objects.create(
            agent_run=agent_run,
            spec_version='1.0',
            spec_data=spec_data,
            spec_checksum=checksum
        )
        
        return runtime_spec


class SpecValidator:
    """
    Validates runtime specifications for correctness and safety.
    """
    
    @staticmethod
    def validate_spec(spec: Dict[str, Any]) -> tuple[bool, List[str]]:
        """
        Validate a runtime specification.
        
        Returns:
            (is_valid, list_of_errors)
        """
        errors = []
        
        # Check required fields
        required_fields = [
            'spec_version',
            'pipeline_id',
            'available_tools',
            'execution_constraints',
            'global_context',
            'execution_policies'
        ]
        
        for field in required_fields:
            if field not in spec:
                errors.append(f"Missing required field: {field}")
        
        # Validate tools
        if 'available_tools' in spec:
            if not isinstance(spec['available_tools'], list):
                errors.append("available_tools must be a list")
            elif len(spec['available_tools']) == 0:
                errors.append("Pipeline has no tools (nodes)")
        
        # Validate constraints
        if 'execution_constraints' in spec:
            if not isinstance(spec['execution_constraints'], list):
                errors.append("execution_constraints must be a list")
        
        # Validate policies
        if 'execution_policies' in spec:
            policies = spec['execution_policies']
            if 'max_iterations' not in policies:
                errors.append("execution_policies missing max_iterations")
            elif policies['max_iterations'] <= 0:
                errors.append("max_iterations must be positive")
        
        return (len(errors) == 0, errors)
    
    @staticmethod
    def verify_checksum(spec: Dict[str, Any], expected_checksum: str) -> bool:
        """Verify spec checksum matches expected value."""
        builder = RuntimeSpecBuilder(None)  # Checksum doesn't need pipeline
        actual_checksum = builder.compute_checksum(spec)
        return actual_checksum == expected_checksum
