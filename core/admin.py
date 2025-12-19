from django.contrib import admin
from .models import Pipeline, Node, NodeConnection, PipelineExecution, NodeExecution, UserDefinedFunction, Step

# Register your models here.

@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at', 'is_active')
    list_filter = ('is_active', 'created_at')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(Node)
class NodeAdmin(admin.ModelAdmin):
    list_display = ('name', 'pipeline', 'order', 'status')
    list_filter = ('status', 'pipeline')
    search_fields = ('name', 'description')
    readonly_fields = ('id', 'created_at', 'updated_at')

@admin.register(NodeConnection)
class NodeConnectionAdmin(admin.ModelAdmin):
    list_display = ('from_node', 'to_node', 'from_output', 'to_input')
    list_filter = ('from_node__pipeline',)

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

@admin.register(UserDefinedFunction)
class UserDefinedFunctionAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)

@admin.register(Step)
class StepAdmin(admin.ModelAdmin):
    list_display = ('name', 'pipeline', 'parent_step')
    list_filter = ('pipeline',)
    search_fields = ('name',)
