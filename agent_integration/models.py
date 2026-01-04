"""
Extended models for agent-driven execution.

These models extend the existing Pipeline/Node/Execution models
without modifying them.
"""

from django.db import models
from core.models import PipelineExecution, NodeExecution
import uuid
import json

# Import control plane models
from .control_plane_models import (
    AgentProfile,
    ToolDefinition,
    AgentToolMapping,
    BusinessCondition,
    AgentConditionBinding,
)


class AgentRun(models.Model):
    """
    Represents an LLM agent-controlled pipeline execution.
    
    This is the top-level entity for agent orchestration.
    It wraps a PipelineExecution and adds agent-specific metadata.
    """
    STATUS_CHOICES = [
        ('initializing', 'Initializing'),
        ('planning', 'Planning'),
        ('executing', 'Executing'),
        ('waiting_for_human', 'Waiting for Human'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_execution = models.OneToOneField(
        PipelineExecution,
        on_delete=models.CASCADE,
        related_name='agent_run'
    )
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='initializing')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Agent configuration
    agent_config = models.JSONField(
        default=dict,
        help_text="Agent configuration: model, temperature, max_iterations, etc."
    )
    
    # Runtime state
    current_step = models.IntegerField(default=0)
    max_steps = models.IntegerField(default=100)
    
    # Human intervention
    human_intervention_required = models.BooleanField(default=False)
    human_intervention_reason = models.TextField(blank=True)
    human_intervention_response = models.JSONField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at']),
        ]
    
    def __str__(self):
        return f"AgentRun {self.id} - {self.status}"


class AgentDecision(models.Model):
    """
    Records each decision made by the LLM agent.
    
    This provides full audit trail of agent reasoning.
    """
    DECISION_TYPES = [
        ('plan', 'Initial Plan'),
        ('select_node', 'Node Selection'),
        ('evaluate_condition', 'Condition Evaluation'),
        ('handle_error', 'Error Handling'),
        ('request_human', 'Human Intervention Request'),
        ('finalize', 'Finalization'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name='decisions'
    )
    step_number = models.IntegerField()
    decision_type = models.CharField(max_length=30, choices=DECISION_TYPES)
    timestamp = models.DateTimeField(auto_now_add=True)
    
    # LLM interaction
    prompt = models.TextField(help_text="Prompt sent to LLM")
    llm_response = models.TextField(help_text="Raw LLM response")
    parsed_decision = models.JSONField(help_text="Structured decision output")
    
    # Guardrail enforcement
    guardrail_violations = models.JSONField(
        default=list,
        help_text="Any guardrail violations detected"
    )
    guardrail_corrections = models.JSONField(
        default=list,
        help_text="Corrections applied by guardrails"
    )
    
    # Reasoning trace
    reasoning = models.TextField(blank=True, help_text="Agent's reasoning")
    confidence = models.FloatField(null=True, blank=True)
    
    class Meta:
        ordering = ['step_number', 'timestamp']
        indexes = [
            models.Index(fields=['agent_run', 'step_number']),
        ]
    
    def __str__(self):
        return f"Decision {self.step_number} - {self.decision_type}"


class ToolExecution(models.Model):
    """
    Records tool (node) execution as triggered by agent.
    
    This wraps NodeExecution and adds agent-specific context.
    """
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.ForeignKey(
        AgentRun,
        on_delete=models.CASCADE,
        related_name='tool_executions'
    )
    node_execution = models.OneToOneField(
        NodeExecution,
        on_delete=models.CASCADE,
        related_name='tool_execution'
    )
    agent_decision = models.ForeignKey(
        AgentDecision,
        on_delete=models.SET_NULL,
        null=True,
        related_name='triggered_executions'
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    queued_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Tool call metadata
    tool_name = models.CharField(max_length=255)
    tool_parameters = models.JSONField(default=dict)
    
    # Result summary for agent
    result_summary = models.TextField(
        blank=True,
        help_text="Human-readable summary for agent consumption"
    )
    artifact_references = models.JSONField(
        default=list,
        help_text="List of artifact IDs/paths produced"
    )
    
    class Meta:
        ordering = ['queued_at']
        indexes = [
            models.Index(fields=['agent_run', 'status']),
        ]
    
    def __str__(self):
        return f"ToolExecution {self.tool_name} - {self.status}"


class RuntimeSpec(models.Model):
    """
    Immutable runtime specification materialized from Pipeline.
    
    This is what gets passed to the agent runner.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    agent_run = models.OneToOneField(
        AgentRun,
        on_delete=models.CASCADE,
        related_name='runtime_spec'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    
    # Immutable specification
    spec_version = models.CharField(max_length=20, default='1.0')
    spec_data = models.JSONField(
        help_text="""
        Complete runtime specification including:
        - available_tools: list of tool definitions
        - execution_constraints: DAG constraints, dependencies
        - business_conditions: conditional execution rules
        - global_context: pipeline-level variables
        """
    )
    
    # Checksum for verification
    spec_checksum = models.CharField(max_length=64)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"RuntimeSpec for {self.agent_run.id}"
