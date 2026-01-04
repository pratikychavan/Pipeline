from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, authenticate, logout
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views.generic import ListView, CreateView, UpdateView, DeleteView
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy, reverse
from django.db import models
import json
import traceback
import sys
from io import StringIO
import threading
import time
from datetime import datetime, timezone

from .models import Pipeline, Node, PipelineExecution, NodeExecution
from .forms import PipelineForm, NodeForm, CodeExecutionForm
from .execution_engine import execute_pipeline_async
from .execution import get_execution_backend

# Create your views here.

class PipelineListView(LoginRequiredMixin, ListView):
    model = Pipeline
    template_name = 'core/pipeline_list.html'
    context_object_name = 'pipelines'
    
    def get_queryset(self):
        from django.db.models import Subquery, OuterRef
        
        # Subquery to get the last execution for each pipeline
        last_execution = PipelineExecution.objects.filter(
            pipeline=OuterRef('pk')
        ).order_by('-started_at').values('status', 'started_at')[:1]
        
        return Pipeline.objects.filter(
            created_by=self.request.user, 
            is_active=True
        ).annotate(
            last_execution_status=Subquery(last_execution.values('status')),
            last_execution_time=Subquery(last_execution.values('started_at'))
        )

class PipelineCreateView(LoginRequiredMixin, CreateView):
    model = Pipeline
    form_class = PipelineForm
    template_name = 'core/pipeline_form.html'
    success_url = reverse_lazy('pipeline_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        response = super().form_valid(form)
        
        # Return JSON response for AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'pipeline_id': str(self.object.pk),
                'pipeline_name': self.object.name
            })
        
        return response
    
    def form_invalid(self, form):
        # Return JSON response for AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })
        
        return super().form_invalid(form)

class PipelineUpdateView(LoginRequiredMixin, UpdateView):
    model = Pipeline
    form_class = PipelineForm
    template_name = 'core/pipeline_form.html'
    
    def get_queryset(self):
        return Pipeline.objects.filter(created_by=self.request.user)
    
    def get_success_url(self):
        return reverse('pipeline_detail', kwargs={'pk': self.object.pk})
    
    def form_valid(self, form):
        response = super().form_valid(form)
        
        # Return JSON response for AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': True,
                'pipeline_id': str(self.object.pk),
                'pipeline_name': self.object.name
            })
        
        return response
    
    def form_invalid(self, form):
        # Return JSON response for AJAX requests
        if self.request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({
                'success': False,
                'errors': form.errors
            })
        
        return super().form_invalid(form)

class PipelineDeleteView(LoginRequiredMixin, DeleteView):
    model = Pipeline
    template_name = 'core/pipeline_confirm_delete.html'
    success_url = reverse_lazy('pipeline_list')
    
    def get_queryset(self):
        return Pipeline.objects.filter(created_by=self.request.user)
    
    def delete(self, request, *args, **kwargs):
        pipeline = self.get_object()
        pipeline_name = pipeline.name
        
        # Delete all related nodes and executions (cascade should handle this)
        result = super().delete(request, *args, **kwargs)
        
        messages.success(request, f'Pipeline "{pipeline_name}" and all its nodes have been deleted successfully.')
        return result

@login_required
def pipeline_detail(request, pk):
    pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
    nodes = Node.objects.filter(pipeline=pipeline).order_by('order')
    
    # Generate connections from input_variable_mappings
    connections_data = []
    for node in nodes:
        if node.input_variable_mappings:
            for target_var, mapping in node.input_variable_mappings.items():
                source_node_id = mapping.get('node_id')
                source_var = mapping.get('source_variable')
                
                # Only create visual connections for node-to-node mappings (not pipeline-level args)
                if source_node_id and source_node_id != '__pipeline__' and source_var:
                    connections_data.append({
                        'from_node': source_node_id,
                        'to_node': str(node.id),
                        'from_output': source_var,
                        'to_input': target_var,
                    })
    
    context = {
        'pipeline': pipeline,
        'nodes': nodes,
        'connections_data': connections_data,
        'pipeline_global_arguments_json': json.dumps(pipeline.global_arguments or []),
        'pipeline_input_variables': pipeline.global_arguments or [],
    }
    return render(request, 'core/pipeline_detail.html', context)

@login_required
def node_create(request, pipeline_pk):
    pipeline = get_object_or_404(Pipeline, pk=pipeline_pk, created_by=request.user)
    
    if request.method == 'POST':
        form = NodeForm(request.POST, pipeline=pipeline)
        if form.is_valid():
            node = form.save(commit=False)
            node.pipeline = pipeline
            # Set order as the next available position
            max_order = Node.objects.filter(pipeline=pipeline).aggregate(
                models.Max('order')
            )['order__max'] or 0
            node.order = max_order + 1
            node.save()
            
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'node_id': str(node.pk),
                    'node_name': node.name
                })
            
            messages.success(request, f'Node "{node.name}" created successfully!')
            return redirect('pipeline_detail', pk=pipeline.pk)
        else:
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
            
            # Add form errors to messages for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = NodeForm(pipeline=pipeline)
    
    context = {
        'form': form,
        'pipeline': pipeline,
        'title': 'Create New Node'
    }
    return render(request, 'core/node_form.html', context)

@login_required
def node_edit(request, pk):
    node = get_object_or_404(Node, pk=pk, pipeline__created_by=request.user)
    
    if request.method == 'POST':
        form = NodeForm(request.POST, instance=node, pipeline=node.pipeline)
        if form.is_valid():
            form.save()
            
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': True,
                    'node_id': str(node.pk),
                    'node_name': node.name
                })
            
            messages.success(request, f'Node "{node.name}" updated successfully!')
            return redirect('pipeline_detail', pk=node.pipeline.pk)
        else:
            # Return JSON response for AJAX requests
            if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'errors': form.errors
                })
            
            # Add form errors to messages for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = NodeForm(instance=node, pipeline=node.pipeline)
    
    context = {
        'form': form,
        'node': node,
        'pipeline': node.pipeline,
        'title': f'Edit Node: {node.name}'
    }
    return render(request, 'core/node_form.html', context)

@login_required
@require_http_methods(["POST"])
def node_delete(request, pk):
    node = get_object_or_404(Node, pk=pk, pipeline__created_by=request.user)
    pipeline_pk = node.pipeline.pk
    node.delete()
    messages.success(request, f'Node "{node.name}" deleted successfully!')
    return redirect('pipeline_detail', pk=pipeline_pk)

@login_required
@require_POST
def create_connection(request):
    """
    Create a connection by updating the target node's input_variable_mappings.
    This replaces the old NodeConnection model approach.
    """
    try:
        data = json.loads(request.body)
        from_node_id = data.get('from_node_id')
        output_variable = data.get('output_variable')
        to_node_id = data.get('to_node_id')
        input_variable = data.get('input_variable')
        
        # Validate inputs
        if not all([from_node_id, output_variable, to_node_id, input_variable]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required fields'
            }, status=400)
        
        # Get nodes and verify ownership
        to_node = get_object_or_404(Node, pk=to_node_id, pipeline__created_by=request.user)
        from_node = get_object_or_404(Node, pk=from_node_id, pipeline__created_by=request.user)
        
        # Verify nodes are in the same pipeline
        if to_node.pipeline != from_node.pipeline:
            return JsonResponse({
                'success': False,
                'error': 'Nodes must be in the same pipeline'
            }, status=400)
        
        # Update input_variable_mappings
        if not to_node.input_variable_mappings:
            to_node.input_variable_mappings = {}
        
        to_node.input_variable_mappings[input_variable] = {
            'source_node_id': str(from_node_id),
            'source_variable': output_variable
        }
        
        to_node.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Connected {from_node.name}.{output_variable} to {to_node.name}.{input_variable}'
        })
        
    except json.JSONDecodeError:
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON'
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)

@login_required
def execute_pipeline(request, pk):
    pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
    
    if request.method == 'POST':
        # Collect all input variables from the form
        initial_data = {}
        for key in request.POST:
            if key.startswith('input_'):
                var_name = key[6:]  # Remove 'input_' prefix
                var_value = request.POST[key]
                
                # Try to parse as appropriate type
                try:
                    # Try integer first
                    initial_data[var_name] = int(var_value)
                except ValueError:
                    try:
                        # Try float
                        initial_data[var_name] = float(var_value)
                    except ValueError:
                        # Keep as string
                        initial_data[var_name] = var_value
        
        # Create pipeline execution record
        execution = PipelineExecution.objects.create(
            pipeline=pipeline,
            started_by=request.user,
            status='pending',
            context_data=initial_data
        )
        
        # Start execution in background
        thread = threading.Thread(
            target=execute_pipeline_async,
            args=(execution.id,)
        )
        thread.daemon = True
        thread.start()
        
        messages.success(request, 'Pipeline execution started!')
        return redirect('execution_detail', pk=execution.pk)
    
    return redirect('pipeline_detail', pk=pk)

def execute_pipeline_async(execution_id):
    """Execute pipeline nodes in order"""
    try:
        execution = PipelineExecution.objects.get(pk=execution_id)
        execution.status = 'running'
        execution.save()
        
        pipeline = execution.pipeline
        nodes = Node.objects.filter(pipeline=pipeline).order_by('order')
        
        # Initialize execution context with initial data (includes pipeline argument values)
        context = execution.context_data.copy()
        
        for node in nodes:
            # Build node-specific context using the new input_variable_mappings
            node_context = context.copy()
            
            # Handle input variable mappings from the node's configuration
            if node.input_variable_mappings:
                for var_name, mapping in node.input_variable_mappings.items():
                    source_node_id = mapping.get('node_id')
                    source_var = mapping.get('source_variable')
                    
                    if source_node_id and source_var:
                        # Special handling for pipeline-level arguments
                        if source_node_id == '__pipeline__':
                            # Map directly from context (argument values provided at execution time)
                            if source_var in context:
                                node_context[var_name] = context[source_var]
                                print(f"Mapping pipeline argument: {source_var} -> {var_name} for node {node.name}")
                            else:
                                print(f"Warning: Pipeline argument '{source_var}' not found in context for node {node.name}")
                        else:
                            # Look for the source variable in context from previous nodes
                            if source_var in context:
                                # The variable will be available via wd.get_arg(var_name)
                                # Store it in context with the target variable name
                                node_context[var_name] = context[source_var]
                                print(f"Mapping variable: {source_var} (from node {source_node_id}) -> {var_name} for node {node.name}")
                            else:
                                print(f"Warning: Source variable '{source_var}' not found in context for node {node.name}")
            
            # Extract only mapped input variables for this node
            node_inputs = {}
            if node.input_variable_mappings:
                for input_var in node.input_variable_mappings.keys():
                    if input_var in node_context:
                        node_inputs[input_var] = node_context[input_var]
            
            node_execution = NodeExecution.objects.create(
                pipeline_execution=execution,
                node=node,
                status='running',
                started_at=datetime.now(timezone.utc),
                input_data=node_inputs
            )
            
            try:
                # Get execution backend and execute node
                backend = get_execution_backend()
                output = backend.execute_node(node, node_context, execution)
                
                # Update global context with ALL node outputs
                # Since we removed output_variables, we collect everything
                for var_name, var_value in output.items():
                    if not var_name.startswith('_'):  # Skip internal variables
                        context[var_name] = var_value
                
                node_execution.status = 'completed'
                node_execution.output_data = output
                node_execution.completed_at = datetime.now(timezone.utc)
                node_execution.save()
                
                # Update node status
                node.status = 'completed'
                node.save()
                
            except Exception as e:
                error_msg = str(e)
                node_execution.status = 'failed'
                node_execution.error_message = error_msg
                node_execution.completed_at = datetime.now(timezone.utc)
                node_execution.save()
                
                # Update node status
                node.status = 'failed'
                node.save()
                
                # Stop pipeline execution on error
                execution.status = 'failed'
                execution.error_message = f"Node '{node.name}' failed: {error_msg}"
                execution.completed_at = datetime.now(timezone.utc)
                execution.save()
                return
        
        # Pipeline completed successfully
        execution.status = 'completed'
        execution.completed_at = datetime.now(timezone.utc)
        execution.context_data = context
        execution.save()
        
    except Exception as e:
        # Handle execution-level errors
        try:
            execution.status = 'failed'
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            execution.save()
        except:
            pass  # If we can't even save the error, there's not much we can do

@login_required
def get_pipeline_inputs(request, pk):
    """Get input variables for a pipeline (pipeline-level global arguments)"""
    try:
        pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
        
        # Return only pipeline-level global arguments
        return JsonResponse({
            'input_variables': pipeline.global_arguments or []
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def execute_node_code(code, context):
    """Execute user-defined code in a controlled environment"""
    # Import commonly used libraries
    import pandas as pd
    import numpy as np
    import json
    import math
    import datetime
    try:
        import sklearn
    except ImportError:
        sklearn = None
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=DeprecationWarning)
            warnings.filterwarnings("ignore", category=UserWarning)
            import matplotlib.pyplot as plt
    except (ImportError, Exception):
        plt = None
    try:
        import seaborn as sns
    except ImportError:
        sns = None
    
    # Import WarpDrive for user access
    from .execution.warpdrive import WarpDrive
    
    # Create a safe execution environment
    exec_globals = {
        '__builtins__': {
            'len': len, 'str': str, 'int': int, 'float': float, 'bool': bool,
            'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
            'range': range, 'enumerate': enumerate, 'zip': zip,
            'print': print, 'abs': abs, 'min': min, 'max': max, 'sum': sum,
            'round': round, 'sorted': sorted, 'reversed': reversed,
            '__import__': __import__,  # Enable imports
        },
        # Pre-import commonly used libraries
        'pandas': pd,
        'pd': pd,
        'numpy': np,
        'np': np,
        'json': json,
        'math': math,
        'datetime': datetime,
        'WarpDrive': WarpDrive,
    }
    
    # Add optional libraries if available
    if sklearn:
        exec_globals['sklearn'] = sklearn
    if plt:
        exec_globals['plt'] = plt
        exec_globals['matplotlib'] = plt
    if sns:
        exec_globals['sns'] = sns
        exec_globals['seaborn'] = sns
    
    # Add context variables
    exec_locals = context.copy()
    
    # Capture stdout
    old_stdout = sys.stdout
    captured_output = StringIO()
    sys.stdout = captured_output
    
    try:
        # Execute the code
        exec(code, exec_globals, exec_locals)
        
        # Get output
        output_logs = captured_output.getvalue()
        
        # Collect output variables
        result = {}
        import types
        
        # Find WarpDrive instances to get artifacts
        warpdrive_instances = []
        for value in exec_locals.values():
            if isinstance(value, WarpDrive):
                warpdrive_instances.append(value)
        
        # Collect artifacts from WarpDrive instances
        # Artifacts are saved with metadata dicts containing _artifact marker
        for wd in warpdrive_instances:
            if hasattr(wd, 'artifacts') and wd.artifacts:
                # Get the artifact reference dicts from caller_globals
                if hasattr(wd, 'caller_globals'):
                    for artifact_name in wd.artifacts.keys():
                        if artifact_name in wd.caller_globals:
                            artifact_ref = wd.caller_globals[artifact_name]
                            # Only include if it's an artifact reference dict
                            if isinstance(artifact_ref, dict) and artifact_ref.get('_artifact'):
                                result[artifact_name] = artifact_ref
        
        # Only return explicitly saved artifacts, no automatic variable collection
        
        if output_logs:
            result['_output_logs'] = output_logs
            
        return result
        
    except Exception as e:
        # Get detailed traceback
        import traceback
        tb = traceback.format_exc()
        
        # Extract the relevant line from the traceback
        lines = tb.split('\n')
        error_info = []
        
        # Find the line in user code that caused the error
        for i, line in enumerate(lines):
            if 'exec(code, exec_globals, exec_locals)' in line:
                # Look for the next few lines which show the actual error location
                for j in range(i+1, min(i+5, len(lines))):
                    if lines[j].strip():
                        error_info.append(lines[j])
        
        # Create detailed error message
        if error_info:
            error_details = '\n'.join(error_info)
            raise Exception(f"Code execution error: {str(e)}\n\nTraceback:\n{error_details}")
        else:
            raise Exception(f"Code execution error: {str(e)}\n\nFull traceback:\n{tb}")
    finally:
        sys.stdout = old_stdout

@login_required
def execution_detail(request, pk):
    execution = get_object_or_404(PipelineExecution, pk=pk, started_by=request.user)
    node_executions = NodeExecution.objects.filter(
        pipeline_execution=execution
    ).order_by('node__order')
    
    # Get all nodes for the pipeline with their positions
    pipeline_nodes = Node.objects.filter(pipeline=execution.pipeline).order_by('order')
    
    # Create a mapping of node_id to node_execution for status lookup
    node_exec_map = {str(ne.node.id): ne for ne in node_executions}
    
    # Generate connections from input_variable_mappings
    connections_data = []
    for node in pipeline_nodes:
        if node.input_variable_mappings:
            for target_var, mapping in node.input_variable_mappings.items():
                source_node_id = mapping.get('node_id')
                source_var = mapping.get('source_variable')
                
                # Only create visual connections for node-to-node mappings
                if source_node_id and source_node_id != '__pipeline__' and source_var:
                    connections_data.append({
                        'from_node': source_node_id,
                        'to_node': str(node.id),
                        'from_output': source_var,
                        'to_input': target_var,
                    })
    
    # Serialize JSON data properly for JavaScript
    import json
    for node_exec in node_executions:
        if node_exec.input_data:
            if isinstance(node_exec.input_data, str):
                try:
                    node_exec.input_data_json = node_exec.input_data
                except:
                    node_exec.input_data_json = '{}'
            else:
                node_exec.input_data_json = json.dumps(node_exec.input_data)
        else:
            node_exec.input_data_json = '{}'
            
        if node_exec.output_data:
            if isinstance(node_exec.output_data, str):
                try:
                    node_exec.output_data_json = node_exec.output_data
                except:
                    node_exec.output_data_json = '{}'
            else:
                node_exec.output_data_json = json.dumps(node_exec.output_data)
        else:
            node_exec.output_data_json = '{}'
    
    context = {
        'execution': execution,
        'node_executions': node_executions,
        'pipeline_nodes': pipeline_nodes,
        'node_exec_map': node_exec_map,
        'connections_json': json.dumps(connections_data),
    }
    return render(request, 'core/execution_detail.html', context)

@login_required
def execution_list(request):
    executions = PipelineExecution.objects.filter(
        started_by=request.user
    ).order_by('-started_at')[:50]  # Show last 50 executions
    
    context = {
        'executions': executions,
    }
    return render(request, 'core/execution_list.html', context)

# AJAX Views for dynamic functionality

@login_required
@require_http_methods(["POST"])
def update_node_position(request):
    """Update node position for visual editor"""
    try:
        data = json.loads(request.body)
        node_id = data.get('node_id')
        x = data.get('x', 0)
        y = data.get('y', 0)
        
        node = get_object_or_404(Node, pk=node_id, pipeline__created_by=request.user)
        node.position_x = x
        node.position_y = y
        node.save()
        
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
@require_http_methods(["GET"])
def pipeline_status(request, pk):
    """Get current pipeline execution status"""
    pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
    
    # Get latest execution
    latest_execution = PipelineExecution.objects.filter(
        pipeline=pipeline
    ).order_by('-started_at').first()
    
    if latest_execution:
        node_statuses = {}
        for node_exec in latest_execution.node_executions.all():
            node_statuses[str(node_exec.node.pk)] = {
                'status': node_exec.status,
                'error': node_exec.error_message,
                'output': node_exec.output_logs,
            }
        
        return JsonResponse({
            'execution_status': latest_execution.status,
            'execution_id': str(latest_execution.pk),
            'node_statuses': node_statuses,
        })
    
    return JsonResponse({'execution_status': 'none', 'node_statuses': {}})



@login_required
def get_node_code(request, pk):
    """Get node code for display in modal"""
    try:
        node = get_object_or_404(Node, pk=pk, pipeline__created_by=request.user)
        
        return JsonResponse({
            'success': True,
            'node_name': node.name,
            'code': node.code or '# No code defined for this node',
            'description': node.description or 'No description provided'
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def pipeline_executions(request, pk):
    """View execution history for a specific pipeline"""
    pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
    executions = PipelineExecution.objects.filter(
        pipeline=pipeline
    ).order_by('-started_at')
    
    # Calculate statistics
    total_executions = executions.count()
    completed_count = executions.filter(status='completed').count()
    failed_count = executions.filter(status='failed').count()
    running_count = executions.filter(status='running').count()
    
    context = {
        'pipeline': pipeline,
        'executions': executions,
        'stats': {
            'total': total_executions,
            'completed': completed_count,
            'failed': failed_count,
            'running': running_count,
        }
    }
    return render(request, 'core/pipeline_executions.html', context)


@login_required
def pipeline_list_api(request):
    """API endpoint to list pipelines for the current user."""
    pipelines = Pipeline.objects.filter(created_by=request.user).values(
        'id', 'name', 'description', 'created_at'
    ).order_by('-created_at')
    
    return JsonResponse(list(pipelines), safe=False)