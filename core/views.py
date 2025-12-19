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
import ast
import re
from datetime import datetime, timezone

from .models import Pipeline, Node, NodeConnection, PipelineExecution, NodeExecution
from .forms import PipelineForm, NodeForm, NodeConnectionForm, CodeExecutionForm
from .execution_engine import execute_pipeline_async
from .execution import get_execution_backend

# Create your views here.

class PipelineListView(LoginRequiredMixin, ListView):
    model = Pipeline
    template_name = 'core/pipeline_list.html'
    context_object_name = 'pipelines'
    
    def get_queryset(self):
        return Pipeline.objects.filter(created_by=self.request.user, is_active=True)

class PipelineCreateView(LoginRequiredMixin, CreateView):
    model = Pipeline
    form_class = PipelineForm
    template_name = 'core/pipeline_form.html'
    success_url = reverse_lazy('pipeline_list')
    
    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

class PipelineUpdateView(LoginRequiredMixin, UpdateView):
    model = Pipeline
    form_class = PipelineForm
    template_name = 'core/pipeline_form.html'
    
    def get_queryset(self):
        return Pipeline.objects.filter(created_by=self.request.user)
    
    def get_success_url(self):
        return reverse('pipeline_detail', kwargs={'pk': self.object.pk})

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
    connections = NodeConnection.objects.filter(from_node__pipeline=pipeline)
    
    # Collect input variables that are NOT satisfied by connections (external inputs only)
    all_input_vars = set()
    connected_inputs = set()
    
    # First, find all input variables that are satisfied by connections
    for connection in connections:
        connected_inputs.add((connection.to_node.id, connection.to_input))
    
    # Then collect only unsatisfied input variables
    for node in nodes:
        if node.input_variables:
            for input_var in node.input_variables:
                # Only include if this input is not connected from another node
                if (node.id, input_var) not in connected_inputs:
                    all_input_vars.add(input_var)
    
    # Serialize connections for JavaScript
    connections_data = []
    for conn in connections:
        connections_data.append({
            'id': str(conn.id),
            'from_node': str(conn.from_node.id),
            'to_node': str(conn.to_node.id),
            'from_output': conn.from_output,
            'to_input': conn.to_input,
        })
    
    context = {
        'pipeline': pipeline,
        'nodes': nodes,
        'connections': connections,
        'connections_data': connections_data,
        'pipeline_input_variables': sorted(list(all_input_vars)),
    }
    return render(request, 'core/pipeline_detail.html', context)

@login_required
def node_create(request, pipeline_pk):
    pipeline = get_object_or_404(Pipeline, pk=pipeline_pk, created_by=request.user)
    
    if request.method == 'POST':
        form = NodeForm(request.POST)
        if form.is_valid():
            node = form.save(commit=False)
            node.pipeline = pipeline
            # Set order as the next available position
            max_order = Node.objects.filter(pipeline=pipeline).aggregate(
                models.Max('order')
            )['order__max'] or 0
            node.order = max_order + 1
            node.save()
            messages.success(request, f'Node "{node.name}" created successfully!')
            return redirect('pipeline_detail', pk=pipeline.pk)
        else:
            # Add form errors to messages for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = NodeForm()
    
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
        form = NodeForm(request.POST, instance=node)
        if form.is_valid():
            form.save()
            messages.success(request, f'Node "{node.name}" updated successfully!')
            return redirect('pipeline_detail', pk=node.pipeline.pk)
        else:
            # Add form errors to messages for debugging
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
    else:
        form = NodeForm(instance=node)
    
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
        
        # Initialize execution context with initial data
        context = execution.context_data.copy()
        
        # Get all connections for this pipeline to handle variable mapping
        connections = NodeConnection.objects.filter(from_node__pipeline=pipeline)
        
        for node in nodes:
            # Build node-specific context by mapping connected variables
            node_context = context.copy()
            
            # Add connected inputs from previous nodes
            for connection in connections:
                if connection.to_node == node:
                    # Map output variable from source node to input variable for this node
                    source_var = connection.from_output
                    target_var = connection.to_input
                    
                    if source_var in context:
                        # Map the variable with the correct name for this node
                        node_context[target_var] = context[source_var]
                        print(f"Mapping variable: {source_var} -> {target_var} for node {node.name}")
                    else:
                        print(f"Warning: Source variable '{source_var}' not found in context for node {node.name}")
            
            # Extract only the actual input variables for this node
            node_inputs = {}
            if node.input_variables:
                for input_var in node.input_variables:
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
                
                # Update global context with node outputs (using original variable names)
                for var_name in node.output_variables:
                    if var_name in output:
                        # Store with full node.variable naming for later connections
                        context[var_name] = output[var_name]
                
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
def detect_outputs(request):
    """Analyze node code and automatically detect output variables"""
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        code = data.get('code', '')
        
        if not code.strip():
            return JsonResponse({'outputs': []})
        
        # Detect output variables using AST parsing
        outputs = detect_output_variables(code)
        
        return JsonResponse({'outputs': outputs})
        
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def get_pipeline_inputs(request, pk):
    """Get input variables for a pipeline"""
    try:
        pipeline = get_object_or_404(Pipeline, pk=pk, created_by=request.user)
        nodes = Node.objects.filter(pipeline=pipeline).order_by('order')
        connections = NodeConnection.objects.filter(from_node__pipeline=pipeline)
        
        # Collect input variables that are NOT satisfied by connections (external inputs only)
        all_input_vars = set()
        connected_inputs = set()
        
        # First, find all input variables that are satisfied by connections
        for connection in connections:
            connected_inputs.add((connection.to_node.id, connection.to_input))
        
        # Then collect only unsatisfied input variables
        for node in nodes:
            if node.input_variables:
                for input_var in node.input_variables:
                    # Only include if this input is not connected from another node
                    if (node.id, input_var) not in connected_inputs:
                        all_input_vars.add(input_var)
        
        return JsonResponse({
            'input_variables': sorted(list(all_input_vars))
        })
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def detect_output_variables(code):
    """Parse Python code to detect variables that could be outputs"""
    try:
        # Parse the code into an AST
        tree = ast.parse(code)
        
        # Track variable assignments
        assigned_vars = set()
        imported_modules = set()
        
        class OutputDetector(ast.NodeVisitor):
            def visit_Assign(self, node):
                # Handle assignments like: x = 5, df = pd.DataFrame()
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        assigned_vars.add(target.id)
                    elif isinstance(target, ast.Tuple) or isinstance(target, ast.List):
                        # Handle tuple/list unpacking: a, b = func()
                        for elt in target.elts:
                            if isinstance(elt, ast.Name):
                                assigned_vars.add(elt.id)
                self.generic_visit(node)
            
            def visit_AugAssign(self, node):
                # Handle augmented assignments like: x += 5
                if isinstance(node.target, ast.Name):
                    assigned_vars.add(node.target.id)
                self.generic_visit(node)
            
            def visit_Import(self, node):
                # Track imports to filter out module names
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_modules.add(name.split('.')[0])
                self.generic_visit(node)
            
            def visit_ImportFrom(self, node):
                # Track from imports
                for alias in node.names:
                    name = alias.asname if alias.asname else alias.name
                    imported_modules.add(name)
                self.generic_visit(node)
        
        # Visit the AST to detect assignments
        detector = OutputDetector()
        detector.visit(tree)
        
        # Filter out common non-output variables
        filtered_outputs = []
        for var in assigned_vars:
            # Skip private variables, modules, and common temporary variables
            if (not var.startswith('_') and 
                var not in imported_modules and 
                var not in ['i', 'j', 'k', 'idx', 'index', 'temp', 'tmp', 'result']):
                filtered_outputs.append(var)
        
        return sorted(filtered_outputs)
        
    except (SyntaxError, Exception):
        # Fallback to regex if AST parsing fails
        return detect_outputs_regex(code)

def detect_outputs_regex(code):
    """Fallback regex-based output detection for invalid Python syntax"""
    # Simple regex to find variable assignments
    pattern = r'^\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*[+\-*/%&|^]?=\s*(?!=)'
    matches = re.findall(pattern, code, re.MULTILINE)
    
    # Filter common non-outputs
    filtered = [var for var in matches if not var.startswith('_') and 
               var not in ['i', 'j', 'k', 'idx', 'index', 'temp', 'tmp']]
    
    return sorted(list(set(filtered)))

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
        import matplotlib.pyplot as plt
    except ImportError:
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
        
        # Collect loaded data ids from all WarpDrive instances to exclude them
        loaded_data_ids = set()
        for wd in warpdrive_instances:
            if hasattr(wd, 'loaded_data_ids'):
                loaded_data_ids.update(wd.loaded_data_ids)
        
        # Collect other output variables (exclude WarpDrive instances and artifacts)
        artifact_names = set(result.keys())
        for key, value in exec_locals.items():
            # Skip internal variables
            if key.startswith('_'):
                continue
            
            # Skip WarpDrive instances
            if isinstance(value, WarpDrive):
                continue
            
            # Skip module imports
            if isinstance(value, types.ModuleType):
                continue
            
            # Skip variables that are already in artifacts
            if key in artifact_names:
                continue
            
            # Skip variables loaded via get_arg() by checking object id
            if id(value) in loaded_data_ids:
                continue
                
            # Skip unchanged context (use 'is' comparison to avoid pandas issues)
            if key in context and context[key] is value:
                continue
            
            # Check if this variable was modified or newly created
            if key not in context or context[key] is not value:
                # Try JSON serialization first
                try:
                    json.dumps(value)
                    result[key] = value
                except (TypeError, ValueError):
                    # Non-serializable - convert to string
                    result[key] = str(value)
        
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
def get_node_variables(request, pk):
    """Get input/output variables for a node"""
    node = get_object_or_404(Node, pk=pk, pipeline__created_by=request.user)
    return JsonResponse({
        'input_variables': node.input_variables,
        'output_variables': node.output_variables,
    })

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

@require_POST
@login_required
def create_connection(request):
    """Create a connection between two nodes via AJAX"""
    try:
        import json
        data = json.loads(request.body)
        
        from_node_id = data.get('from_node_id')
        output_variable = data.get('output_variable')
        to_node_id = data.get('to_node_id')
        input_variable = data.get('input_variable')
        
        # Get the nodes and verify ownership
        from_node = get_object_or_404(Node, pk=from_node_id, pipeline__created_by=request.user)
        to_node = get_object_or_404(Node, pk=to_node_id, pipeline__created_by=request.user)
        
        # Verify nodes are in the same pipeline
        if from_node.pipeline != to_node.pipeline:
            return JsonResponse({'success': False, 'error': 'Nodes must be in the same pipeline'})
        
        # Verify variables exist
        if output_variable not in (from_node.output_variables or []):
            return JsonResponse({'success': False, 'error': f'Output variable "{output_variable}" not found in source node'})
            
        if input_variable not in (to_node.input_variables or []):
            return JsonResponse({'success': False, 'error': f'Input variable "{input_variable}" not found in target node'})
        
        # Check if connection already exists
        existing = NodeConnection.objects.filter(
            from_node=from_node,
            from_output=output_variable,
            to_node=to_node,
            to_input=input_variable
        ).exists()
        
        if existing:
            return JsonResponse({'success': False, 'error': 'Connection already exists'})
        
        # Create the connection
        connection = NodeConnection.objects.create(
            from_node=from_node,
            from_output=output_variable,
            to_node=to_node,
            to_input=input_variable
        )
        
        return JsonResponse({'success': True, 'connection_id': str(connection.pk)})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})

@login_required
def get_node_code(request, pk):
    """Get node code for display in modal"""
    try:
        node = get_object_or_404(Node, pk=pk, pipeline__created_by=request.user)
        
        return JsonResponse({
            'success': True,
            'node_name': node.name,
            'code': node.code or '# No code defined for this node',
            'input_variables': node.input_variables or [],
            'output_variables': node.output_variables or [],
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