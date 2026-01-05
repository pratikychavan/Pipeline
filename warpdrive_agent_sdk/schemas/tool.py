"""
Tool Specification Schemas

Schemas for declaring tool capabilities and contracts.

These are DECLARATIONS ONLY - they describe what tools do,
not HOW to execute them. Execution is handled by the platform.
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum


class ToolParameterType(Enum):
    """Types of tool parameters."""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    OBJECT = "object"
    ARRAY = "array"


@dataclass
class ToolParameter:
    """
    Specification for a tool parameter.
    
    This declares what parameters a tool accepts.
    
    Attributes:
        name: Parameter name
        type: Parameter type (string, integer, etc.)
        description: Human-readable description
        required: Whether parameter is required
        default: Default value if not provided
        constraints: Validation constraints (min, max, pattern, etc.)
    
    Example:
        >>> param = ToolParameter(
        ...     name="threshold",
        ...     type=ToolParameterType.FLOAT,
        ...     description="Minimum confidence threshold",
        ...     required=True,
        ...     constraints={'min': 0.0, 'max': 1.0}
        ... )
    """
    name: str
    type: ToolParameterType
    description: str = ""
    required: bool = False
    default: Any = None
    constraints: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'name': self.name,
            'type': self.type.value,
            'description': self.description,
            'required': self.required,
            'default': self.default,
            'constraints': self.constraints,
        }
    
    def validate_value(self, value: Any) -> None:
        """
        Validate a value against this parameter spec.
        
        Args:
            value: Value to validate
            
        Raises:
            ValueError: If value is invalid
        """
        # Check required
        if self.required and value is None:
            raise ValueError(f"Parameter '{self.name}' is required")
        
        # Check type
        if value is not None:
            if self.type == ToolParameterType.STRING and not isinstance(value, str):
                raise ValueError(f"Parameter '{self.name}' must be string")
            elif self.type == ToolParameterType.INTEGER and not isinstance(value, int):
                raise ValueError(f"Parameter '{self.name}' must be integer")
            elif self.type == ToolParameterType.FLOAT and not isinstance(value, (int, float)):
                raise ValueError(f"Parameter '{self.name}' must be float")
            elif self.type == ToolParameterType.BOOLEAN and not isinstance(value, bool):
                raise ValueError(f"Parameter '{self.name}' must be boolean")
        
        # Check constraints
        if value is not None and self.constraints:
            if 'min' in self.constraints and value < self.constraints['min']:
                raise ValueError(f"Parameter '{self.name}' must be >= {self.constraints['min']}")
            if 'max' in self.constraints and value > self.constraints['max']:
                raise ValueError(f"Parameter '{self.name}' must be <= {self.constraints['max']}")


@dataclass
class ToolResult:
    """
    Result of a tool execution.
    
    This is what the platform provides back to your planner after
    executing a tool. It contains only SAFE information - no raw data.
    
    Attributes:
        success: Whether tool executed successfully
        tool_id: ID of tool that was executed
        summary: Human-readable summary of what happened
        artifact_references: List of artifact IDs created
        output_variables: List of variable names set
        error_message: Error message if execution failed
        metadata: Additional metadata
    
    WARNING: You DO NOT get raw data. You only get references and summaries.
    This is for safety - the platform controls data access.
    
    Example:
        >>> # After tool execution, planner receives:
        >>> result = ToolResult(
        ...     success=True,
        ...     tool_id="data_validation",
        ...     summary="Validated 1000 records, 950 passed",
        ...     artifact_references=["artifact_123"],
        ...     output_variables=["validation_passed"]
        ... )
    """
    success: bool
    tool_id: str
    summary: str = ""
    artifact_references: List[str] = field(default_factory=list)
    output_variables: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'success': self.success,
            'tool_id': self.tool_id,
            'summary': self.summary,
            'artifact_references': self.artifact_references,
            'output_variables': self.output_variables,
            'error_message': self.error_message,
            'metadata': self.metadata,
        }


@dataclass
class ToolSpec:
    """
    Complete tool specification.
    
    This declares what a tool does and what parameters it accepts.
    It does NOT contain execution logic - that's internal to the platform.
    
    Attributes:
        tool_id: Unique tool identifier
        name: Human-readable tool name
        description: What the tool does
        parameters: List of parameters the tool accepts
        output_description: Description of what the tool outputs
        tags: Tags for categorization
        metadata: Additional metadata
    
    Example:
        >>> tool = ToolSpec(
        ...     tool_id="validate_data",
        ...     name="Data Validation",
        ...     description="Validates incoming data against schema",
        ...     parameters=[
        ...         ToolParameter(
        ...             name="threshold",
        ...             type=ToolParameterType.FLOAT,
        ...             required=True
        ...         )
        ...     ],
        ...     output_description="Returns validation results"
        ... )
    
    WARNING: This is a SPECIFICATION, not an IMPLEMENTATION.
    You cannot execute tools directly - the platform does that.
    """
    tool_id: str
    name: str
    description: str = ""
    parameters: List[ToolParameter] = field(default_factory=list)
    output_description: str = ""
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'tool_id': self.tool_id,
            'name': self.name,
            'description': self.description,
            'parameters': [p.to_dict() for p in self.parameters],
            'output_description': self.output_description,
            'tags': self.tags,
            'metadata': self.metadata,
        }
    
    def validate_parameters(self, parameters: Dict[str, Any]) -> None:
        """
        Validate parameters against this tool spec.
        
        Args:
            parameters: Parameters to validate
            
        Raises:
            ValueError: If parameters are invalid
        """
        # Check all required parameters are provided
        param_map = {p.name: p for p in self.parameters}
        
        for param in self.parameters:
            if param.required and param.name not in parameters:
                raise ValueError(f"Required parameter '{param.name}' not provided")
        
        # Validate each provided parameter
        for name, value in parameters.items():
            if name not in param_map:
                raise ValueError(f"Unknown parameter '{name}'")
            param_map[name].validate_value(value)
    
    def get_parameter(self, name: str) -> Optional[ToolParameter]:
        """
        Get parameter specification by name.
        
        Args:
            name: Parameter name
            
        Returns:
            ToolParameter or None if not found
        """
        for param in self.parameters:
            if param.name == name:
                return param
        return None
