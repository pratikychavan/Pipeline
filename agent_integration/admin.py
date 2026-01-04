"""
Admin interface for agent execution monitoring.
"""

from django.contrib import admin
from .models import AgentRun, AgentDecision, ToolExecution, RuntimeSpec


@admin.register(AgentRun)
class AgentRunAdmin(admin.ModelAdmin):
    list_display = ['id', 'status', 'current_step', 'max_steps', 'human_intervention_required', 'created_at']
    list_filter = ['status', 'human_intervention_required', 'created_at']
    search_fields = ['id', 'pipeline_execution__pipeline__name']
    readonly_fields = [
        'id', 'pipeline_execution', 'created_at', 'updated_at', 'completed_at',
        'agent_config', 'human_intervention_response'
    ]
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'pipeline_execution', 'status', 'created_at', 'updated_at', 'completed_at')
        }),
        ('Execution Progress', {
            'fields': ('current_step', 'max_steps', 'agent_config')
        }),
        ('Human Intervention', {
            'fields': ('human_intervention_required', 'human_intervention_reason', 'human_intervention_response')
        }),
    )


@admin.register(AgentDecision)
class AgentDecisionAdmin(admin.ModelAdmin):
    list_display = ['id', 'agent_run', 'step_number', 'decision_type', 'timestamp']
    list_filter = ['decision_type', 'timestamp']
    search_fields = ['agent_run__id', 'reasoning']
    readonly_fields = [
        'id', 'agent_run', 'step_number', 'decision_type', 'timestamp',
        'prompt', 'llm_response', 'parsed_decision', 'guardrail_violations',
        'guardrail_corrections', 'reasoning', 'confidence'
    ]
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'agent_run', 'step_number', 'decision_type', 'timestamp')
        }),
        ('LLM Interaction', {
            'fields': ('prompt', 'llm_response', 'parsed_decision', 'reasoning', 'confidence')
        }),
        ('Guardrails', {
            'fields': ('guardrail_violations', 'guardrail_corrections')
        }),
    )


@admin.register(ToolExecution)
class ToolExecutionAdmin(admin.ModelAdmin):
    list_display = ['id', 'agent_run', 'tool_name', 'status', 'queued_at', 'completed_at']
    list_filter = ['status', 'queued_at']
    search_fields = ['tool_name', 'agent_run__id']
    readonly_fields = [
        'id', 'agent_run', 'node_execution', 'agent_decision',
        'queued_at', 'started_at', 'completed_at',
        'tool_parameters', 'result_summary', 'artifact_references'
    ]
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'agent_run', 'node_execution', 'agent_decision', 'status')
        }),
        ('Tool Info', {
            'fields': ('tool_name', 'tool_parameters')
        }),
        ('Timing', {
            'fields': ('queued_at', 'started_at', 'completed_at')
        }),
        ('Results', {
            'fields': ('result_summary', 'artifact_references')
        }),
    )


@admin.register(RuntimeSpec)
class RuntimeSpecAdmin(admin.ModelAdmin):
    list_display = ['id', 'agent_run', 'spec_version', 'created_at']
    list_filter = ['spec_version', 'created_at']
    search_fields = ['agent_run__id', 'spec_checksum']
    readonly_fields = ['id', 'agent_run', 'created_at', 'spec_version', 'spec_data', 'spec_checksum']
    fieldsets = (
        ('Basic Info', {
            'fields': ('id', 'agent_run', 'spec_version', 'created_at')
        }),
        ('Specification', {
            'fields': ('spec_data', 'spec_checksum'),
            'classes': ('collapse',)
        }),
    )
