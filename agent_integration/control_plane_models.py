"""
Control Plane models for agent configuration and management.

These models are for CONFIGURATION only, not runtime execution.
They define what agents CAN do, not what they ARE DOING.
"""

from django.db import models
from django.core.exceptions import ValidationError
from core.models import Pipeline
import uuid
import json


class AgentProfile(models.Model):
    """
    Agent configuration profile (NOT runtime state).
    
    This defines an agent's capabilities, constraints, and behavior.
    Agents can be in draft, active, or archived states.
    """
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('archived', 'Archived'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    # Execution constraints
    max_steps = models.IntegerField(
        default=100,
        help_text="Maximum number of decision steps before termination"
    )
    max_retries = models.IntegerField(
        default=3,
        help_text="Maximum consecutive failures before giving up"
    )
    require_human_approval = models.BooleanField(
        default=False,
        help_text="Pause execution and wait for human approval"
    )
    
    # Retry policy
    retry_policy = models.JSONField(
        default=dict,
        help_text="Retry configuration: backoff, conditions, etc."
    )
    
    # Guardrail configuration
    guardrail_config = models.JSONField(
        default=dict,
        help_text="Guardrail enforcement settings: loop detection, deadlock prevention, etc."
    )
    
    # LLM configuration (for future use)
    llm_model = models.CharField(
        max_length=100,
        default='fallback-ordering',
        help_text="LLM model identifier or 'fallback-ordering' for deterministic mode"
    )
    llm_temperature = models.FloatField(
        default=0.0,
        help_text="Temperature for LLM sampling (0.0 = deterministic)"
    )
    llm_config = models.JSONField(
        default=dict,
        help_text="Additional LLM configuration parameters"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_agents'
    )
    
    class Meta:
        ordering = ['name']
        indexes = [
            models.Index(fields=['status', 'name']),
        ]
    
    def __str__(self):
        return f"{self.name} ({self.status})"
    
    def clean(self):
        """Validate configuration."""
        if self.max_steps < 1:
            raise ValidationError("max_steps must be at least 1")
        if self.max_retries < 0:
            raise ValidationError("max_retries cannot be negative")
        if not (0.0 <= self.llm_temperature <= 2.0):
            raise ValidationError("llm_temperature must be between 0.0 and 2.0")
    
    def can_be_edited(self) -> bool:
        """Check if agent can be safely edited."""
        # TODO: Check if agent has active runs
        return True


class ToolDefinition(models.Model):
    """
    Tool registry entry (NOT runtime execution).
    
    Tools are backed by Pipeline Nodes. This model defines
    tool metadata and availability for agent planning.
    """
    EXECUTOR_TYPES = [
        ('node', 'Pipeline Node'),
        ('function', 'Python Function'),
        ('external', 'External API'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    executor_type = models.CharField(max_length=20, choices=EXECUTOR_TYPES, default='node')
    
    # Schema definition
    input_schema = models.JSONField(
        help_text="JSON Schema defining required/optional inputs"
    )
    output_schema = models.JSONField(
        help_text="JSON Schema defining expected outputs"
    )
    
    # Node backing (for executor_type='node')
    pipeline = models.ForeignKey(
        Pipeline,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Pipeline containing the backing node"
    )
    node_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Name of the node in the pipeline"
    )
    
    # Availability
    is_enabled = models.BooleanField(
        default=True,
        help_text="Whether this tool is available for agent use"
    )
    
    # Execution hints
    estimated_duration_seconds = models.IntegerField(
        null=True,
        blank=True,
        help_text="Estimated execution time for planning"
    )
    cost_estimate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Estimated cost per execution"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.executor_type})"
    
    def clean(self):
        """Validate tool definition."""
        if self.executor_type == 'node' and not self.pipeline:
            raise ValidationError("Node-backed tools must specify a pipeline")


class AgentToolMapping(models.Model):
    """
    Maps tools to agents with constraints.
    
    This defines which tools an agent CAN use and under what conditions.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name='tool_mappings'
    )
    tool = models.ForeignKey(
        ToolDefinition,
        on_delete=models.CASCADE,
        related_name='agent_mappings'
    )
    
    # Constraints
    is_allowed = models.BooleanField(
        default=True,
        help_text="Whether agent can use this tool"
    )
    max_calls = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum calls per execution (null = unlimited)"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Priority for tool selection (higher = preferred)"
    )
    
    # Conditions
    prerequisites = models.JSONField(
        default=list,
        help_text="List of tool names that must execute first"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        unique_together = [('agent', 'tool')]
        ordering = ['-priority', 'tool__name']
        indexes = [
            models.Index(fields=['agent', 'is_allowed']),
        ]
    
    def __str__(self):
        return f"{self.agent.name} -> {self.tool.name}"


class BusinessCondition(models.Model):
    """
    Reusable business condition definition.
    
    These are versioned, testable conditions that can be
    bound to agents for conditional execution logic.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255, unique=True)
    description = models.TextField()
    version = models.CharField(max_length=20, default='1.0')
    
    # Condition expression (NOT executable code)
    condition_type = models.CharField(
        max_length=50,
        choices=[
            ('artifact_exists', 'Artifact Exists'),
            ('value_comparison', 'Value Comparison'),
            ('pattern_match', 'Pattern Match'),
            ('custom', 'Custom Logic'),
        ]
    )
    condition_config = models.JSONField(
        help_text="Configuration for condition evaluation"
    )
    
    # Test cases
    test_cases = models.JSONField(
        default=list,
        help_text="List of test cases with inputs and expected outputs"
    )
    
    # Status
    is_active = models.BooleanField(default=True)
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name', '-version']
        unique_together = [('name', 'version')]
    
    def __str__(self):
        return f"{self.name} v{self.version}"


class AgentConditionBinding(models.Model):
    """
    Binds a business condition to an agent with behavior configuration.
    
    This defines WHEN and HOW conditions are evaluated during execution.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent = models.ForeignKey(
        AgentProfile,
        on_delete=models.CASCADE,
        related_name='condition_bindings'
    )
    condition = models.ForeignKey(
        BusinessCondition,
        on_delete=models.CASCADE,
        related_name='agent_bindings'
    )
    
    # Evaluation timing
    evaluation_point = models.CharField(
        max_length=50,
        choices=[
            ('before_execution', 'Before Execution'),
            ('after_tool', 'After Each Tool'),
            ('on_failure', 'On Failure'),
            ('on_completion', 'On Completion'),
        ],
        default='before_execution'
    )
    
    # Parameters
    parameters = models.JSONField(
        default=dict,
        help_text="Parameters to pass to condition evaluator"
    )
    
    # Behavior
    on_true_action = models.CharField(
        max_length=50,
        choices=[
            ('continue', 'Continue'),
            ('skip_tool', 'Skip Tool'),
            ('pause', 'Pause for Human'),
            ('terminate', 'Terminate'),
        ],
        default='continue'
    )
    on_false_action = models.CharField(
        max_length=50,
        choices=[
            ('continue', 'Continue'),
            ('skip_tool', 'Skip Tool'),
            ('pause', 'Pause for Human'),
            ('terminate', 'Terminate'),
        ],
        default='continue'
    )
    
    # Constraints
    max_evaluations = models.IntegerField(
        null=True,
        blank=True,
        help_text="Maximum times this condition can be evaluated (null = unlimited)"
    )
    priority = models.IntegerField(
        default=0,
        help_text="Evaluation order (higher = evaluated first)"
    )
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    is_enabled = models.BooleanField(default=True)
    
    class Meta:
        unique_together = [('agent', 'condition', 'evaluation_point')]
        ordering = ['-priority', 'condition__name']
        indexes = [
            models.Index(fields=['agent', 'is_enabled']),
        ]
    
    def __str__(self):
        return f"{self.agent.name} -> {self.condition.name} @ {self.evaluation_point}"
