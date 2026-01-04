"""
Runtime Spec Builder

This module converts Pipeline definitions into immutable Agent Runtime Specs.

IMPORTANT:
- This is a READ-ONLY transformation
- No execution logic stored in spec
- No LLM prompts in spec
- Spec is JSON-serializable
- Spec is immutable at runtime
"""

import json
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone

from django.db import transaction
from core.models import Pipeline, Node
from agent_integration.models import AgentRun, RuntimeSpec
from agent_integration.control_plane_models import (
    AgentProfile,
    ToolDefinition,
    AgentToolMapping,
    BusinessCondition,
    AgentConditionBinding,
)


class RuntimeSpecBuilder:
    """
    Builds immutable runtime specifications from Pipeline definitions.
    
    This is a READ-ONLY transformation that:
    1. Reads Pipeline and Node definitions
    2. Reads Control Plane configuration (if applicable)
    3. Produces JSON-serializable spec
    4. Does NOT include executable code
    5. Does NOT include runtime state
    """
    
    SPEC_VERSION = "1.0"
    
    def __init__(self, pipeline: Pipeline, agent_profile: Optional[AgentProfile] = None):
        """
        Initialize builder.
        
        Args:
            pipeline: Pipeline to materialize
            agent_profile: Optional agent profile for configuration
        """
        self.pipeline = pipeline
        self.agent_profile = agent_profile
        self._spec_data = None
    
    def build(self) -> Dict[str, Any]:
        """
        Build runtime spec from pipeline.
        
        Returns:
            Runtime spec dictionary (JSON-serializable)
        """
        if self._spec_data is None:
            self._spec_data = {
                'version': self.SPEC_VERSION,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'pipeline': self._build_pipeline_metadata(),
                'available_tools': self._build_tools(),
                'execution_constraints': self._build_constraints(),
                'business_conditions': self._build_conditions(),
                'agent_configuration': self._build_agent_config(),
                'global_context': self._build_global_context(),
            }
        
        return self._spec_data
    
    def _build_pipeline_metadata(self) -> Dict[str, Any]:
        """Build pipeline metadata section."""
        return {
            'id': str(self.pipeline.id),
            'name': self.pipeline.name,
            'description': self.pipeline.description,
            'is_active': self.pipeline.is_active,
            'global_arguments': self.pipeline.global_arguments or [],
        }
    
    def _build_tools(self) -> List[Dict[str, Any]]:
        """
        Build available tools list from pipeline nodes.
        
        Returns list of tool definitions (NOT executable code).
        """
        tools = []
        
        # Get all nodes for this pipeline
        nodes = Node.objects.filter(
            pipeline=self.pipeline
        ).order_by('order')
        
        # Get agent tool mappings if agent profile provided
        tool_mappings = {}
        if self.agent_profile:
            mappings = AgentToolMapping.objects.filter(
                agent=self.agent_profile
            ).select_related('tool')
            
            for mapping in mappings:
                if mapping.tool.executor_type == 'node' and mapping.tool.node_name:
                    tool_mappings[mapping.tool.node_name] = {
                        'is_allowed': mapping.is_allowed,
                        'max_calls': mapping.max_calls,
                        'priority': mapping.priority,
                        'prerequisites': mapping.prerequisites or [],
                    }
        
        for node in nodes:
            # Build tool definition from node (NO code included)
            tool_def = {
                'tool_id': str(node.id),
                'tool_name': node.name,
                'tool_type': 'pipeline_node',
                'description': node.description or f'Execute node: {node.name}',
                'order': node.order,
                
                # Input/output specifications (structure only, no data)
                'input_variables': list(node.input_variable_mappings.keys()) if node.input_variable_mappings else [],
                'input_mappings': node.input_variable_mappings or {},
                
                # Position in graph (for visualization)
                'position': {
                    'x': node.position_x,
                    'y': node.position_y,
                },
            }
            
            # Add agent-specific constraints if available
            if node.name in tool_mappings:
                tool_def['agent_constraints'] = tool_mappings[node.name]
            
            tools.append(tool_def)
        
        return tools
    
    def _build_constraints(self) -> Dict[str, Any]:
        """
        Build execution constraints (graph structure, dependencies).
        
        This defines WHAT can execute WHEN, not HOW to execute.
        """
        # Get nodes to build dependency graph
        nodes = Node.objects.filter(
            pipeline=self.pipeline
        ).order_by('order')
        
        # Build dependency map from input_variable_mappings
        dependencies = {}
        execution_order = []
        
        for node in nodes:
            node_id = str(node.id)
            execution_order.append(node_id)
            
            # Extract dependencies from input mappings
            deps = []
            if node.input_variable_mappings:
                for var_name, mapping in node.input_variable_mappings.items():
                    source_node_id = mapping.get('node_id')
                    if source_node_id and source_node_id != '__pipeline__':
                        deps.append(source_node_id)
            
            dependencies[node_id] = {
                'depends_on': list(set(deps)),  # Remove duplicates
                'required_for': [],  # Will be populated below
            }
        
        # Populate reverse dependencies (required_for)
        for node_id, dep_info in dependencies.items():
            for dep_node_id in dep_info['depends_on']:
                if dep_node_id in dependencies:
                    dependencies[dep_node_id]['required_for'].append(node_id)
        
        constraints = {
            'dag': {
                'nodes': execution_order,
                'dependencies': dependencies,
            },
            'max_steps': self.agent_profile.max_steps if self.agent_profile else 100,
            'max_execution_time_seconds': None,  # Set from agent profile if available
            'allow_parallel_execution': False,  # Conservative default
        }
        
        # Add agent-specific constraints
        if self.agent_profile and self.agent_profile.guardrail_config:
            guardrails = self.agent_profile.guardrail_config
            if 'max_execution_time_seconds' in guardrails:
                constraints['max_execution_time_seconds'] = guardrails['max_execution_time_seconds']
            if 'max_cost_usd' in guardrails:
                constraints['max_cost_usd'] = guardrails['max_cost_usd']
        
        return constraints
    
    def _build_conditions(self) -> List[Dict[str, Any]]:
        """
        Build business conditions that apply to this execution.
        
        Returns condition definitions (NOT evaluation logic).
        """
        conditions = []
        
        if not self.agent_profile:
            return conditions
        
        # Get condition bindings for this agent
        bindings = AgentConditionBinding.objects.filter(
            agent=self.agent_profile,
            is_enabled=True,
        ).select_related('condition').order_by('priority')
        
        for binding in bindings:
            condition = binding.condition
            
            # Build condition spec (structure only, not evaluation code)
            condition_spec = {
                'condition_id': str(condition.id),
                'condition_name': condition.name,
                'condition_type': condition.condition_type,
                'version': condition.version,
                'is_active': condition.is_active,
                
                # Configuration (declarative, not code)
                'config': condition.condition_config or {},
                
                # Binding parameters
                'evaluation_point': binding.evaluation_point,
                'on_true_action': binding.on_true_action,
                'on_false_action': binding.on_false_action,
                'priority': binding.priority,
                'max_evaluations': binding.max_evaluations,
                'parameters': binding.parameters or {},
            }
            
            conditions.append(condition_spec)
        
        return conditions
    
    def _build_agent_config(self) -> Dict[str, Any]:
        """
        Build agent configuration section.
        
        This contains agent constraints and policies, NOT prompts or model config.
        """
        if not self.agent_profile:
            return {
                'max_steps': 100,
                'retry_policy': {},
                'guardrails': {},
            }
        
        return {
            'agent_profile_id': str(self.agent_profile.id),
            'agent_name': self.agent_profile.name,
            'max_steps': self.agent_profile.max_steps,
            'retry_policy': self.agent_profile.retry_policy or {},
            'guardrails': self.agent_profile.guardrail_config or {},
            # NOTE: llm_config deliberately NOT included - that's for the agent runner
        }
    
    def _build_global_context(self) -> Dict[str, Any]:
        """
        Build global context section.
        
        This contains pipeline-level variables and constants.
        """
        return {
            'pipeline_id': str(self.pipeline.id),
            'pipeline_name': self.pipeline.name,
            'global_arguments': self.pipeline.global_arguments or [],
        }
    
    def compute_checksum(self, spec_data: Dict[str, Any]) -> str:
        """
        Compute checksum for spec immutability verification.
        
        Args:
            spec_data: Spec dictionary
        
        Returns:
            SHA256 checksum hex string
        """
        # Convert to canonical JSON (sorted keys)
        canonical_json = json.dumps(spec_data, sort_keys=True, separators=(',', ':'))
        
        # Compute SHA256
        return hashlib.sha256(canonical_json.encode('utf-8')).hexdigest()
    
    def validate_spec(self, spec_data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate runtime spec structure.
        
        Args:
            spec_data: Spec to validate
        
        Returns:
            (is_valid, error_message)
        """
        # Check required top-level keys
        required_keys = [
            'version',
            'created_at',
            'pipeline',
            'available_tools',
            'execution_constraints',
            'business_conditions',
            'agent_configuration',
            'global_context',
        ]
        
        for key in required_keys:
            if key not in spec_data:
                return False, f"Missing required key: {key}"
        
        # Validate version
        if spec_data['version'] != self.SPEC_VERSION:
            return False, f"Unsupported spec version: {spec_data['version']}"
        
        # Validate tools list
        if not isinstance(spec_data['available_tools'], list):
            return False, "available_tools must be a list"
        
        # Check for executable code (should not be present)
        spec_json = json.dumps(spec_data)
        dangerous_patterns = ['exec(', 'eval(', '__import__', 'compile(']
        for pattern in dangerous_patterns:
            if pattern in spec_json:
                return False, f"Spec contains dangerous pattern: {pattern}"
        
        return True, None
    
    def to_json(self) -> str:
        """
        Convert spec to JSON string.
        
        Returns:
            JSON string (pretty-printed)
        """
        spec = self.build()
        return json.dumps(spec, indent=2, sort_keys=False)


class RuntimeSpecService:
    """
    Service for creating and managing Runtime Specs.
    
    This service handles:
    - Creating specs from pipelines
    - Storing specs in database
    - Retrieving specs for agent runs
    """
    
    @staticmethod
    def create_spec_for_agent_run(
        agent_run: AgentRun,
        agent_profile: Optional[AgentProfile] = None,
    ) -> RuntimeSpec:
        """
        Create and store runtime spec for an agent run.
        
        Args:
            agent_run: Agent run to create spec for
            agent_profile: Optional agent profile for configuration
        
        Returns:
            RuntimeSpec instance
        """
        pipeline = agent_run.pipeline_execution.pipeline
        
        # Build spec
        builder = RuntimeSpecBuilder(pipeline, agent_profile)
        spec_data = builder.build()
        
        # Validate
        is_valid, error = builder.validate_spec(spec_data)
        if not is_valid:
            raise ValueError(f"Invalid runtime spec: {error}")
        
        # Compute checksum
        checksum = builder.compute_checksum(spec_data)
        
        # Create and save RuntimeSpec
        with transaction.atomic():
            runtime_spec = RuntimeSpec.objects.create(
                agent_run=agent_run,
                spec_version=builder.SPEC_VERSION,
                spec_data=spec_data,
                spec_checksum=checksum,
            )
        
        return runtime_spec
    
    @staticmethod
    def get_spec_for_agent_run(agent_run_id) -> Optional[RuntimeSpec]:
        """
        Get runtime spec for an agent run.
        
        Args:
            agent_run_id: Agent run ID
        
        Returns:
            RuntimeSpec or None
        """
        try:
            return RuntimeSpec.objects.get(agent_run_id=agent_run_id)
        except RuntimeSpec.DoesNotExist:
            return None
    
    @staticmethod
    def verify_spec_integrity(runtime_spec: RuntimeSpec) -> bool:
        """
        Verify runtime spec has not been tampered with.
        
        Args:
            runtime_spec: RuntimeSpec to verify
        
        Returns:
            True if checksum matches
        """
        builder = RuntimeSpecBuilder(None, None)
        computed_checksum = builder.compute_checksum(runtime_spec.spec_data)
        return computed_checksum == runtime_spec.spec_checksum
    
    @staticmethod
    def export_spec_to_json(runtime_spec: RuntimeSpec) -> str:
        """
        Export runtime spec to JSON string.
        
        Args:
            runtime_spec: RuntimeSpec to export
        
        Returns:
            JSON string
        """
        return json.dumps(runtime_spec.spec_data, indent=2)
    
    @staticmethod
    def preview_spec_for_pipeline(
        pipeline: Pipeline,
        agent_profile: Optional[AgentProfile] = None,
    ) -> Dict[str, Any]:
        """
        Preview runtime spec for a pipeline without creating AgentRun.
        
        Useful for testing and validation.
        
        Args:
            pipeline: Pipeline to preview
            agent_profile: Optional agent profile
        
        Returns:
            Runtime spec dictionary
        """
        builder = RuntimeSpecBuilder(pipeline, agent_profile)
        return builder.build()
