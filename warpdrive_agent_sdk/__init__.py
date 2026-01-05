"""
Warpdrive Agent SDK

A clean, user-facing SDK for building AI agents that integrate with the Warpdrive platform.

This SDK provides:
- Planner interfaces for implementing custom decision logic
- Agent definitions and configuration schemas
- Tool specifications for declaring capabilities
- Guardrail and policy configuration schemas

IMPORTANT CONSTRAINTS:
- This SDK is for DEFINING agents, not EXECUTING them
- Users CANNOT access execution internals
- Users CANNOT bypass platform guardrails
- Users CANNOT access pipeline/database internals
- All execution happens through the platform

For documentation and examples, see:
- README.md in this package
- examples/ directory
"""

__version__ = "1.0.0"

# Core interfaces
from .interfaces.planner import (
    Planner,
    PlannerDecision,
    PlannerDecisionType,
    PlannerInput,
    PlannerFailure,
)

# Schemas
from .schemas.agent import (
    AgentDefinition,
    AgentConfig,
    RuntimeSpec,
)

from .schemas.tool import (
    ToolSpec,
    ToolParameter,
    ToolParameterType,
    ToolResult,
)

from .schemas.guardrail import (
    GuardrailConfig,
    BusinessConditionSpec,
    GuardrailViolation,
    GuardrailSeverity,
    ConditionType,
)

# Provided planners
from .planners.deterministic import DeterministicPlanner
from .planners.llm_planner import LLMPlanner, LLMClient

__all__ = [
    # Core interfaces
    "Planner",
    "PlannerDecision",
    "PlannerDecisionType",
    "PlannerInput",
    "PlannerFailure",
    
    # Schemas
    "AgentDefinition",
    "AgentConfig",
    "RuntimeSpec",
    "ToolSpec",
    "ToolParameter",
    "ToolParameterType",
    "ToolResult",
    "GuardrailConfig",
    "BusinessConditionSpec",
    "GuardrailViolation",
    "GuardrailSeverity",
    "ConditionType",
    
    # Provided planners
    "DeterministicPlanner",
    "LLMPlanner",
    "LLMClient",
]
