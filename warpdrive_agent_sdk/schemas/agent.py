"""
Agent Configuration Schemas

Schemas for defining agent behavior and configuration.

These are DECLARATIVE - they describe what the agent should do,
not HOW the platform executes it.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class AgentConfig:
    """
    Agent runtime configuration.
    
    This configures HOW the agent operates during execution.
    
    Attributes:
        model: LLM model name (e.g., 'gpt-4o-mini', 'claude-3-opus')
        temperature: Sampling temperature 0.0-1.0 (lower = more deterministic)
        max_tokens: Maximum tokens for LLM responses
        max_steps: Maximum execution steps before termination
        enable_human_intervention: Whether to allow human-in-the-loop
        fail_on_node_failure: Stop execution on first node failure
        timeout_seconds: Maximum execution time in seconds
    
    Example:
        >>> config = AgentConfig(
        ...     model='gpt-4o-mini',
        ...     temperature=0.3,
        ...     max_steps=50,
        ...     enable_human_intervention=True
        ... )
    """
    model: str = 'gpt-4o-mini'
    temperature: float = 0.3
    max_tokens: int = 2000
    max_steps: int = 100
    enable_human_intervention: bool = True
    fail_on_node_failure: bool = True
    timeout_seconds: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'model': self.model,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'max_steps': self.max_steps,
            'enable_human_intervention': self.enable_human_intervention,
            'fail_on_node_failure': self.fail_on_node_failure,
            'timeout_seconds': self.timeout_seconds,
        }
    
    def validate(self) -> None:
        """
        Validate configuration is well-formed.
        
        Raises:
            ValueError: If configuration is invalid
        """
        if not (0.0 <= self.temperature <= 1.0):
            raise ValueError(f"Temperature must be 0.0-1.0, got {self.temperature}")
        
        if self.max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {self.max_tokens}")
        
        if self.max_steps <= 0:
            raise ValueError(f"max_steps must be positive, got {self.max_steps}")
        
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {self.timeout_seconds}")


@dataclass
class AgentDefinition:
    """
    Complete agent definition.
    
    This is the top-level definition of an agent, including:
    - What the agent is trying to achieve (objective)
    - What tools it can use
    - What constraints it must respect
    - How it should operate (config)
    
    Attributes:
        name: Human-readable agent name
        objective: What the agent is trying to achieve
        description: Detailed description of agent purpose
        allowed_tools: List of tool IDs this agent can use
        config: Runtime configuration
        constraints: Additional constraints (max cost, etc.)
        metadata: Additional metadata
    
    Example:
        >>> agent = AgentDefinition(
        ...     name="Data Validation Agent",
        ...     objective="Validate and clean incoming data",
        ...     allowed_tools=["validate_schema", "check_quality", "clean_data"],
        ...     config=AgentConfig(max_steps=20)
        ... )
    
    WARNING: This is a DEFINITION, not an execution. The platform
    will execute this agent safely according to the definition.
    """
    name: str
    objective: str
    description: str = ""
    allowed_tools: List[str] = field(default_factory=list)
    config: AgentConfig = field(default_factory=AgentConfig)
    constraints: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'objective': self.objective,
            'description': self.description,
            'allowed_tools': self.allowed_tools,
            'config': self.config.to_dict(),
            'constraints': self.constraints,
            'metadata': self.metadata,
        }
    
    def validate(self) -> None:
        """
        Validate agent definition is well-formed.
        
        Raises:
            ValueError: If definition is invalid
        """
        if not self.name:
            raise ValueError("Agent name is required")
        
        if not self.objective:
            raise ValueError("Agent objective is required")
        
        self.config.validate()


@dataclass
class RuntimeSpec:
    """
    Runtime specification (READ-ONLY).
    
    This is what the platform provides to your planner during execution.
    It contains:
    - Available tools (with parameters and constraints)
    - Execution constraints (dependencies, ordering)
    - Business conditions (policies that must be respected)
    - Global context (variables, metadata)
    
    WARNING: This is READ-ONLY. You cannot modify the runtime spec.
    Your planner can only READ this data to make decisions.
    
    Attributes:
        version: Spec version
        pipeline_id: ID of the pipeline being executed
        available_tools: List of tools that can be executed
        execution_constraints: Constraints on tool execution order
        business_conditions: Business policies that must be respected
        global_context: Global execution context
    
    Example:
        >>> # In your planner:
        >>> async def plan_next_action(self, planner_input):
        ...     # Read runtime spec (READ-ONLY)
        ...     tools = planner_input.runtime_spec.get('available_tools', [])
        ...     
        ...     # Make decision based on spec
        ...     return PlannerDecision(...)
    """
    version: str
    pipeline_id: str
    available_tools: List[Dict[str, Any]] = field(default_factory=list)
    execution_constraints: List[Dict[str, Any]] = field(default_factory=list)
    business_conditions: List[Dict[str, Any]] = field(default_factory=list)
    global_context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'version': self.version,
            'pipeline_id': self.pipeline_id,
            'available_tools': self.available_tools,
            'execution_constraints': self.execution_constraints,
            'business_conditions': self.business_conditions,
            'global_context': self.global_context,
        }
    
    def get_tool_by_id(self, tool_id: str) -> Optional[Dict[str, Any]]:
        """
        Get tool definition by ID.
        
        Args:
            tool_id: Tool ID to look up
            
        Returns:
            Tool definition dict or None if not found
        """
        for tool in self.available_tools:
            if tool.get('tool_id') == tool_id:
                return tool
        return None
    
    def get_dependencies_for_tool(self, tool_id: str) -> List[str]:
        """
        Get list of tool IDs that must execute before this tool.
        
        Args:
            tool_id: Tool ID to check dependencies for
            
        Returns:
            List of tool IDs that are dependencies
        """
        dependencies = []
        for constraint in self.execution_constraints:
            if (constraint.get('constraint_type') == 'dependency' and
                constraint.get('target_node_id') == tool_id):
                source = constraint.get('source_node_id')
                if source:
                    dependencies.append(source)
        return dependencies
