from django.contrib import admin
from .models import Pipeline, Node, PipelineExecution, NodeExecution, AgentWorkspace

# Register your models here.

@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('name', 'pipeline', 'order')
    list_filter = ('pipeline',)
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(PipelineExecution)
class PipelineExecutionAdmin(admin.ModelAdmin):
    list_display = ('pipeline', 'started_by', 'status', 'started_at', 'completed_at')
    list_filter = ('status', 'started_at')
    readonly_fields = ('id', 'started_at', 'completed_at')

@admin.register(NodeExecution)
class NodeExecutionAdmin(admin.ModelAdmin):
    list_display = ('node', 'pipeline_execution', 'status', 'started_at', 'completed_at')
    list_filter = ('status', 'started_at')
    readonly_fields = ('id', 'started_at', 'completed_at')

@admin.register(AgentWorkspace)
class AgentWorkspaceAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'validation_status', 'planner_type', 'last_validated_at', 'pipeline')
    list_filter = ('validation_status', 'planner_type', 'created_at')
    search_fields = ('name', 'description', 'planner_class_name')
    readonly_fields = ('id', 'created_at', 'updated_at', 'last_validated_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'pipeline', 'created_by')
        }),
        ('Files', {
            'fields': ('agent_code', 'agent_config', 'requirements')
        }),
        ('Validation', {
            'fields': ('validation_status', 'validation_errors', 'last_validated_at', 'planner_type', 'planner_class_name')
        }),
        ('Metadata', {
            'fields': ('id', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
