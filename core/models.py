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
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return self.name

class Node(models.Model):
    """Individual node in the pipeline that contains user-defined functions"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('skipped', 'Skipped'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    pipeline = models.ForeignKey(Pipeline, related_name='nodes', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    code = models.TextField(help_text="User-defined Python code for this node")
    position_x = models.IntegerField(default=0)  # For visual positioning
    position_y = models.IntegerField(default=0)  # For visual positioning
    order = models.PositiveIntegerField(default=0)  # Execution order
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # Store input/output variable names as JSON
    input_variables = models.JSONField(default=list, blank=True)
    output_variables = models.JSONField(default=list, blank=True)
    
    class Meta:
        ordering = ['order']
    
    def __str__(self):
        return f"{self.pipeline.name} - {self.name}"

class NodeConnection(models.Model):
    """Defines connections between nodes for data flow"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    from_node = models.ForeignKey(Node, related_name='outgoing_connections', on_delete=models.CASCADE)
    to_node = models.ForeignKey(Node, related_name='incoming_connections', on_delete=models.CASCADE)
    from_output = models.CharField(max_length=100)  # Output variable name
    to_input = models.CharField(max_length=100)     # Input variable name
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['from_node', 'to_node', 'from_output', 'to_input']
    
    def __str__(self):
        return f"{self.from_node.name}.{self.from_output} -> {self.to_node.name}.{self.to_input}"

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

# Legacy model - keeping for backward compatibility
class UserDefinedFunction(models.Model):
    name = models.CharField(max_length=255)
    code = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return self.name

class Step(models.Model):
    pipeline = models.ForeignKey(Pipeline, related_name='steps', on_delete=models.CASCADE)
    name = models.CharField(max_length=255)
    parent_step = models.ForeignKey('self', null=True, blank=True, related_name='sub_steps', on_delete=models.DO_NOTHING)
    
    def __str__(self):
        return self.name