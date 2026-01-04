from django.db import models
from django.contrib.auth.models import User
import json
import uuid

# Create your models here.

class Pipeline(models.Model):
    """Main pipeline model that contains nodes and execution flow"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    # Global arguments available to all nodes in the pipeline
    # Format: ["arg_name1", "arg_name2"]
    global_arguments = models.JSONField(default=list, blank=True, 
                                       help_text="Global argument names that will be prompted at execution")
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

class Node(models.Model):
    """Individual node in the pipeline that contains user-defined functions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, related_name='nodes', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    code = models.TextField(help_text="User-defined Python code for this node")
    position_x = models.IntegerField(default=0)  # For visual positioning
    position_y = models.IntegerField(default=0)  # For visual positioning
    order = models.PositiveIntegerField(default=0)  # Execution order
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Store input variable mappings as JSON
    # Format: {"variable_name": {"node_id": "uuid", "source_variable": "var_name"}}
    input_variable_mappings = models.JSONField(default=dict, blank=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.pipeline.name} - {self.name}"

class PipelineExecution(models.Model):
    """Track pipeline execution runs"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, related_name='executions', on_delete=models.CASCADE)
    started_by = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    
    # Store execution context/variables as JSON
    context_data = models.JSONField(default=dict, blank=True)
    
    def __str__(self):
        return f"{self.pipeline.name} execution - {self.started_at}"

class NodeExecution(models.Model):
    """Track individual node execution within pipeline runs"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline_execution = models.ForeignKey(PipelineExecution, related_name='node_executions', on_delete=models.CASCADE)
    node = models.ForeignKey(Node, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)
    output_logs = models.TextField(blank=True)
    
    # Store node input/output data as JSON
    input_data = models.JSONField(default=dict, blank=True)
    output_data = models.JSONField(default=dict, blank=True)
    
    class Meta:
        unique_together = ['pipeline_execution', 'node']
    
    def __str__(self):
        return f"{self.node.name} - {self.status}"