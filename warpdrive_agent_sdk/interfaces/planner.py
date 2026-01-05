"""
Planner Interface

This module defines the core planner interface that all agent planners must implement.

CRITICAL CONSTRAINTS:
- Planners are BOUNDED (one call per decision)
- Planners are STATELESS (no internal state between calls)
- Planners return STRUCTURED output (PlannerDecision)
- Planners CANNOT execute tools directly
- Planners CANNOT access pipeline internals
- Planners CANNOT bypass guardrails

The platform calls your planner, validates the decision, and executes it safely.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class PlannerDecisionType(Enum):
    """
    Types of decisions a planner can make.
    
    EXECUTE_TOOL: Execute a specific tool with parameters
    REQUEST_HUMAN: Pause execution and request human intervention
    COMPLETE: Mark the agent run as successfully complete
    FAIL: Mark the agent run as failed
    """
    EXECUTE_TOOL = "execute_tool"
    REQUEST_HUMAN = "request_human"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class PlannerDecision:
    """
    Structured decision output from a planner.
    
    This is what your planner returns after analyzing the current state.
    The platform will validate and execute this decision.
    
    Attributes:
        decision_type: Type of decision (execute, request human, complete, fail)
        tool_id: ID of tool to execute (required for EXECUTE_TOOL)
        tool_parameters: Parameters to pass to tool (for EXECUTE_TOOL)
        reasoning: Human-readable explanation of why this decision was made
        confidence: Confidence score 0.0-1.0 (optional, for monitoring)
        human_message: Message to display to human (for REQUEST_HUMAN)
    
    Example:
        >>> decision = PlannerDecision(
        ...     decision_type=PlannerDecisionType.EXECUTE_TOOL,
        ...     tool_id="data_validation_node",
        ...     tool_parameters={"threshold": 0.95},
        ...     reasoning="Data quality check needed before processing",
        ...     confidence=0.9
        ... )
    """
    decision_type: PlannerDecisionType
    tool_id: Optional[str] = None
    tool_parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 1.0
    human_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'decision_type': self.decision_type.value,
            'tool_id': self.tool_id,
            'tool_parameters': self.tool_parameters,
            'reasoning': self.reasoning,
            'confidence': self.confidence,
            'human_message': self.human_message,
        }
    
    def validate(self) -> None:
        """
        Validate decision is well-formed.
        
        Raises:
            ValueError: If decision is invalid
        """
        if self.decision_type == PlannerDecisionType.EXECUTE_TOOL:
            if not self.tool_id:
                raise ValueError("EXECUTE_TOOL decision requires tool_id")
        
        if self.decision_type == PlannerDecisionType.REQUEST_HUMAN:
            if not self.human_message:
                raise ValueError("REQUEST_HUMAN decision requires human_message")
        
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"Confidence must be between 0.0 and 1.0, got {self.confidence}")


@dataclass
class PlannerInput:
    """
    Input provided to planner for making decisions.
    
    This is READ-ONLY information about the current execution state.
    
    Attributes:
        runtime_spec: Runtime specification (available tools, constraints)
        execution_history: List of completed tool executions
        current_state: Current execution state (variables, outputs)
        step_number: Current step number in execution
    
    WARNING: This is READ-ONLY. Mutating these values will NOT affect execution.
    """
    runtime_spec: Dict[str, Any]
    execution_history: List[Dict[str, Any]]
    current_state: Dict[str, Any]
    step_number: int = 0
    
    def get_available_tools(self) -> List[Dict[str, Any]]:
        """Get list of available tools from runtime spec."""
        return self.runtime_spec.get('available_tools', [])
    
    def get_executed_tools(self) -> List[str]:
        """
        Get list of tool names that have been executed.
        
        Returns tool names (user-friendly) instead of internal IDs.
        """
        return [
            execution.get('tool_name')
            for execution in self.execution_history
            if execution.get('tool_name')
        ]
    
    def get_tool_id_by_name(self, tool_name: str) -> Optional[str]:
        """
        Get the internal tool ID for a given tool name.
        
        This is a convenience method for the platform integration.
        Users should use tool names in their logic, but return tool_id in decisions.
        
        Args:
            tool_name: The user-facing tool name
            
        Returns:
            Internal tool ID (UUID) or None if not found
        """
        for tool in self.get_available_tools():
            if tool.get('tool_name') == tool_name:
                return tool.get('tool_id')
        return None
    
    def get_execution_result(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """
        Get the execution result for a specific tool by name.
        
        Args:
            tool_name: The name of the tool
            
        Returns:
            Execution record dictionary with keys like 'status', 'success', 'output_data', etc.
            Returns None if tool hasn't been executed yet.
        """
        for execution in self.execution_history:
            if execution.get('tool_name') == tool_name:
                return execution
        return None
    
    def get_execution_constraints(self) -> List[Dict[str, Any]]:
        """Get execution constraints from runtime spec."""
        return self.runtime_spec.get('execution_constraints', [])


@dataclass
class PlannerFailure:
    """
    Represents a planner failure (for error handling).
    
    When your planner encounters an error, return this instead of raising
    an exception. The platform will handle the error gracefully.
    
    Attributes:
        error_type: Type of error (e.g., 'timeout', 'invalid_response')
        error_message: Human-readable error message
        raw_response: Raw response from planner (for debugging)
        fallback_decision: Optional fallback decision to use
    """
    error_type: str
    error_message: str
    raw_response: Optional[str] = None
    fallback_decision: Optional[PlannerDecision] = None
    
    def to_decision(self) -> PlannerDecision:
        """Convert failure to a FAIL decision."""
        if self.fallback_decision:
            return self.fallback_decision
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.FAIL,
            reasoning=f"Planner failed: {self.error_type} - {self.error_message}",
        )


class Planner(ABC):
    """
    Abstract base class for agent planners.
    
    Implement this interface to create custom agent decision logic.
    
    CRITICAL CONSTRAINTS:
    - Your planner is called ONCE per decision
    - Your planner receives READ-ONLY state
    - Your planner returns a PlannerDecision
    - Your planner CANNOT execute tools
    - Your planner CANNOT access pipeline internals
    - Your planner CANNOT bypass guardrails
    
    The platform will:
    1. Call your planner with current state
    2. Validate your decision against guardrails
    3. Execute the decision safely
    4. Record results
    5. Call your planner again for next decision
    
    Example:
        >>> class MyPlanner(Planner):
        ...     async def plan_next_action(self, planner_input):
        ...         # Analyze available tools
        ...         tools = planner_input.get_available_tools()
        ...         
        ...         # Make decision
        ...         return PlannerDecision(
        ...             decision_type=PlannerDecisionType.EXECUTE_TOOL,
        ...             tool_id=tools[0]['tool_id'],
        ...             reasoning="Starting with first tool"
        ...         )
    """
    
    @abstractmethod
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan the next action based on current state.
        
        This method is called by the platform to get your next decision.
        
        Args:
            planner_input: Current execution state (READ-ONLY)
            
        Returns:
            PlannerDecision with your next action
            
        Raises:
            DO NOT raise exceptions directly. Return PlannerFailure instead.
            
        Example:
            >>> async def plan_next_action(self, planner_input):
            ...     # Check if we're done
            ...     if len(planner_input.get_executed_tools()) >= 5:
            ...         return PlannerDecision(
            ...             decision_type=PlannerDecisionType.COMPLETE,
            ...             reasoning="All required tools executed"
            ...         )
            ...     
            ...     # Select next tool
            ...     available = planner_input.get_available_tools()
            ...     next_tool = available[0]
            ...     
            ...     return PlannerDecision(
            ...         decision_type=PlannerDecisionType.EXECUTE_TOOL,
            ...         tool_id=next_tool['tool_id'],
            ...         reasoning=f"Executing {next_tool['name']}"
            ...     )
        """
        pass
