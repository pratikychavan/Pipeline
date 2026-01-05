"""
Guardrail and Policy Schemas

Schemas for configuring agent guardrails and business policies.

These are CONFIGURATION ONLY - they describe what rules to enforce,
not HOW to enforce them. Enforcement is handled by the platform.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class GuardrailSeverity(Enum):
    """Severity levels for guardrail violations."""
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class GuardrailConfig:
    """
    Configuration for agent guardrails.
    
    Guardrails enforce safety constraints on agent execution:
    - Time limits (prevent infinite loops)
    - Cost limits (prevent runaway spending)
    - Risk detection (pause on dangerous operations)
    - Dependency validation (ensure execution order)
    
    Attributes:
        max_execution_time_seconds: Maximum execution time
        max_cost_usd: Maximum cost in USD
        require_approval_for_high_risk: Pause for approval on risky operations
        allowed_tool_patterns: Regex patterns for allowed tools
        forbidden_tool_patterns: Regex patterns for forbidden tools
        max_retries_per_tool: Maximum retries per tool
        fail_on_guardrail_violation: Stop execution on violation
    
    Example:
        >>> config = GuardrailConfig(
        ...     max_execution_time_seconds=300,
        ...     max_cost_usd=1.0,
        ...     require_approval_for_high_risk=True,
        ...     forbidden_tool_patterns=['.*delete.*', '.*drop.*']
        ... )
    
    WARNING: These are LIMITS, not permissions. The platform enforces
    these constraints - you cannot bypass them from your planner.
    """
    max_execution_time_seconds: Optional[int] = None
    max_cost_usd: Optional[float] = None
    require_approval_for_high_risk: bool = False
    allowed_tool_patterns: List[str] = field(default_factory=list)
    forbidden_tool_patterns: List[str] = field(default_factory=list)
    max_retries_per_tool: int = 3
    fail_on_guardrail_violation: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'max_execution_time_seconds': self.max_execution_time_seconds,
            'max_cost_usd': self.max_cost_usd,
            'require_approval_for_high_risk': self.require_approval_for_high_risk,
            'allowed_tool_patterns': self.allowed_tool_patterns,
            'forbidden_tool_patterns': self.forbidden_tool_patterns,
            'max_retries_per_tool': self.max_retries_per_tool,
            'fail_on_guardrail_violation': self.fail_on_guardrail_violation,
        }
    
    def validate(self) -> None:
        """
        Validate guardrail configuration is well-formed.
        
        Raises:
            ValueError: If configuration is invalid
        """
        if self.max_execution_time_seconds is not None and self.max_execution_time_seconds <= 0:
            raise ValueError(f"max_execution_time_seconds must be positive, got {self.max_execution_time_seconds}")
        
        if self.max_cost_usd is not None and self.max_cost_usd <= 0:
            raise ValueError(f"max_cost_usd must be positive, got {self.max_cost_usd}")
        
        if self.max_retries_per_tool < 0:
            raise ValueError(f"max_retries_per_tool must be non-negative, got {self.max_retries_per_tool}")


class ConditionType(Enum):
    """Types of business conditions."""
    APPROVAL_REQUIRED = "approval_required"
    VALIDATION_REQUIRED = "validation_required"
    THRESHOLD = "threshold"
    CUSTOM = "custom"


@dataclass
class BusinessConditionSpec:
    """
    Specification for a business condition (policy).
    
    Business conditions are rules that must be satisfied during execution:
    - Approval gates (require human approval before proceeding)
    - Validation gates (require validation before proceeding)
    - Thresholds (values must be within bounds)
    - Custom conditions (platform-specific rules)
    
    Attributes:
        condition_id: Unique condition identifier
        name: Human-readable condition name
        description: What the condition checks
        condition_type: Type of condition
        parameters: Condition-specific parameters
        severity: What happens if condition is not met
        applies_to_tools: List of tool IDs this applies to
        metadata: Additional metadata
    
    Example:
        >>> condition = BusinessConditionSpec(
        ...     condition_id="payment_approval",
        ...     name="Payment Approval Required",
        ...     description="Payments over $1000 require approval",
        ...     condition_type=ConditionType.APPROVAL_REQUIRED,
        ...     parameters={'threshold_usd': 1000.0},
        ...     severity=GuardrailSeverity.CRITICAL,
        ...     applies_to_tools=['process_payment']
        ... )
    
    WARNING: This is a SPECIFICATION, not LOGIC. You declare what
    conditions exist, but the platform evaluates and enforces them.
    """
    condition_id: str
    name: str
    description: str = ""
    condition_type: ConditionType = ConditionType.CUSTOM
    parameters: Dict[str, Any] = field(default_factory=dict)
    severity: GuardrailSeverity = GuardrailSeverity.WARNING
    applies_to_tools: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'condition_id': self.condition_id,
            'name': self.name,
            'description': self.description,
            'condition_type': self.condition_type.value,
            'parameters': self.parameters,
            'severity': self.severity.value,
            'applies_to_tools': self.applies_to_tools,
            'metadata': self.metadata,
        }
    
    def validate(self) -> None:
        """
        Validate condition specification is well-formed.
        
        Raises:
            ValueError: If specification is invalid
        """
        if not self.condition_id:
            raise ValueError("condition_id is required")
        
        if not self.name:
            raise ValueError("name is required")
    
    def applies_to_tool(self, tool_id: str) -> bool:
        """
        Check if this condition applies to a specific tool.
        
        Args:
            tool_id: Tool ID to check
            
        Returns:
            True if condition applies to this tool
        """
        if not self.applies_to_tools:
            # Empty list means applies to all tools
            return True
        return tool_id in self.applies_to_tools


@dataclass
class GuardrailViolation:
    """
    Represents a guardrail violation (READ-ONLY).
    
    This is what the platform reports when a guardrail is violated.
    You receive this as information, but you CANNOT ignore it.
    
    Attributes:
        violation_type: Type of violation
        severity: Severity level
        message: Human-readable message
        tool_id: Tool ID that caused violation (if applicable)
        suggested_correction: Suggested fix (if applicable)
    
    Example:
        >>> # Platform reports violation to your planner:
        >>> violation = GuardrailViolation(
        ...     violation_type="time_limit_exceeded",
        ...     severity=GuardrailSeverity.ERROR,
        ...     message="Execution time exceeded 300 seconds",
        ...     suggested_correction="Reduce max_steps or increase timeout"
        ... )
    """
    violation_type: str
    severity: GuardrailSeverity
    message: str
    tool_id: Optional[str] = None
    suggested_correction: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'violation_type': self.violation_type,
            'severity': self.severity.value,
            'message': self.message,
            'tool_id': self.tool_id,
            'suggested_correction': self.suggested_correction,
        }
