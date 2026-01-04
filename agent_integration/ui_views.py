"""
UI views for agent integration testing.

These views are for engineers, QA, and stakeholders to validate
agent-orchestrated pipeline execution behavior.

NOT for production end users.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib import messages
import json

from core.models import Pipeline, PipelineExecution, NodeExecution
from .models import AgentRun, AgentDecision, ToolExecution, RuntimeSpec
from .runtime.execution_loop import start_agent_execution, AgentExecutionLoop


@login_required
def agent_dashboard(request):
    """
    AGENT RUN DASHBOARD (CORE VIEW)
    
    Lists all agent runs for integration testing.
    Entry point for validation.
    """
    agent_runs = AgentRun.objects.filter(
        pipeline_execution__started_by=request.user
    ).select_related(
        'pipeline_execution',
        'pipeline_execution__pipeline'
    ).order_by('-created_at')
    
    context = {
        'agent_runs': agent_runs,
        'title': 'Agent Run Dashboard [TESTING]'
    }
    
    return render(request, 'agent_integration/dashboard.html', context)


@login_required
def agent_run_detail(request, agent_run_id):
    """
    AGENT RUN DETAIL VIEW
    
    Shows complete execution timeline, guardrails, decisions,
    and debugging information for a specific agent run.
    """
    agent_run = get_object_or_404(
        AgentRun.objects.select_related(
            'pipeline_execution',
            'pipeline_execution__pipeline'
        ),
        pk=agent_run_id,
        pipeline_execution__started_by=request.user
    )
    
    # Safety check
    if not agent_run.pipeline_execution or not agent_run.pipeline_execution.pipeline:
        messages.error(request, "Agent run data is incomplete")
        return redirect('agent_integration:agent_dashboard')
    
    # Get execution timeline (decisions + tool executions)
    decisions = agent_run.decisions.all().order_by('step_number', 'timestamp')
    tool_executions = agent_run.tool_executions.select_related(
        'node_execution',
        'node_execution__node',
        'agent_decision'
    ).order_by('queued_at')
    
    # Build unified timeline
    timeline = []
    
    for decision in decisions:
        timeline.append({
            'type': 'decision',
            'timestamp': decision.timestamp,
            'step': decision.step_number,
            'data': decision
        })
    
    for tool_exec in tool_executions:
        timeline.append({
            'type': 'tool_execution',
            'timestamp': tool_exec.queued_at,
            'step': tool_exec.agent_decision.step_number if tool_exec.agent_decision else None,
            'data': tool_exec
        })
    
    # Sort by timestamp
    timeline.sort(key=lambda x: x['timestamp'])
    
    # Get runtime spec
    runtime_spec = None
    try:
        runtime_spec = agent_run.runtime_spec
    except RuntimeSpec.DoesNotExist:
        pass
    
    # Get node execution states for graph view
    node_executions = NodeExecution.objects.filter(
        pipeline_execution=agent_run.pipeline_execution
    ).select_related('node')
    
    node_states = {}
    for node_exec in node_executions:
        node_states[str(node_exec.node.id)] = {
            'status': node_exec.status,
            'started_at': node_exec.started_at,
            'completed_at': node_exec.completed_at,
        }
    
    # Collect guardrail violations
    all_violations = []
    for decision in decisions:
        if decision.guardrail_violations:
            all_violations.extend(decision.guardrail_violations)
    
    context = {
        'agent_run': agent_run,
        'pipeline': agent_run.pipeline_execution.pipeline,
        'pipeline_execution': agent_run.pipeline_execution,
        'timeline': timeline,
        'decisions': decisions,
        'tool_executions': tool_executions,
        'runtime_spec': runtime_spec,
        'node_states': node_states,
        'all_violations': all_violations,
        'title': f'Agent Run Detail: {agent_run.id}'
    }
    
    return render(request, 'agent_integration/run_detail.html', context)


@login_required
def start_agent_run_ui(request, pipeline_id):
    """
    Start an agent run from UI.
    
    Creates pipeline execution and triggers agent orchestration.
    Accepts both form data and JSON.
    """
    import json
    from django.http import JsonResponse
    from .control_plane_models import AgentProfile
    from .runtime.execution_loop import start_agent_execution
    
    pipeline = get_object_or_404(Pipeline, pk=pipeline_id, created_by=request.user)
    
    # Parse request data (JSON or form)
    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON'}, status=400)
    else:
        data = request.POST.dict()
    
    # Extract configuration
    agent_id = data.get('agent_id')
    max_steps = int(data.get('max_steps', 100))
    temperature = float(data.get('temperature', 0.3))
    enable_human_intervention = data.get('enable_human_intervention', True)
    context_data = data.get('context_data', {})
    
    # Parse context data from form fields if present
    if not context_data:
        for key in data:
            if key.startswith('input_'):
                var_name = key[6:]
                var_value = data[key]
                try:
                    context_data[var_name] = int(var_value)
                except ValueError:
                    try:
                        context_data[var_name] = float(var_value)
                    except ValueError:
                        context_data[var_name] = var_value
    
    # Get agent config
    agent_config = {
        'max_steps': max_steps,
        'enable_human_intervention': enable_human_intervention,
    }
    
    if agent_id:
        try:
            agent_profile = AgentProfile.objects.get(pk=agent_id, status='active')
            agent_config.update({
                'model': agent_profile.llm_config.get('model', 'gpt-4o-mini'),
                'temperature': agent_profile.llm_config.get('temperature', temperature),
                'provider': agent_profile.llm_config.get('provider', 'openai'),
            })
        except AgentProfile.DoesNotExist:
            error_msg = f"Agent profile {agent_id} not found or inactive"
            if request.content_type == 'application/json':
                return JsonResponse({'error': error_msg}, status=404)
            messages.error(request, error_msg)
            return redirect('pipeline_detail', pk=pipeline_id)
    else:
        # Use default config
        agent_config.update({
            'model': 'gpt-4o-mini',
            'temperature': temperature,
            'provider': 'openai',
        })
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=request.user,
        status='pending',
        context_data=context_data
    )
    
    try:
        # Start agent execution
        result = start_agent_execution(
            pipeline_execution,
            agent_config=agent_config
        )
        
        agent_run_id = result.get('agent_run_id')
        
        if request.content_type == 'application/json':
            return JsonResponse({
                'agent_run_id': str(agent_run_id),
                'status': result.get('status'),
                'message': 'Agent run started successfully'
            })
        
        messages.success(
            request,
            f"Agent run started successfully. Status: {result.get('status')}"
        )
        return redirect('agent_integration:agent_run_detail', agent_run_id=agent_run_id)
        
    except Exception as e:
        error_msg = f"Failed to start agent run: {str(e)}"
        if request.content_type == 'application/json':
            return JsonResponse({'error': error_msg}, status=500)
        messages.error(request, error_msg)
        return redirect('pipeline_detail', pk=pipeline_id)


@login_required
@require_POST
def resume_agent_run(request, agent_run_id):
    """
    Resume agent run from human intervention state.
    
    Called when human approves continuation.
    """
    agent_run = get_object_or_404(
        AgentRun,
        pk=agent_run_id,
        pipeline_execution__started_by=request.user
    )
    
    if not agent_run.human_intervention_required:
        messages.error(request, "Agent run is not waiting for human intervention")
        return redirect('agent_integration:agent_run_detail', agent_run_id=agent_run_id)
    
    try:
        # Record human response
        human_response = {
            'action': 'continue',
            'approved_by': request.user.username,
            'notes': request.POST.get('notes', '')
        }
        
        # Resume execution
        loop = AgentExecutionLoop(agent_run.pipeline_execution)
        loop.agent_run = agent_run
        result = loop.resume_from_human_intervention(human_response)
        
        messages.success(request, "Agent run resumed successfully")
        
    except Exception as e:
        messages.error(request, f"Failed to resume agent run: {str(e)}")
    
    return redirect('agent_integration:agent_run_detail', agent_run_id=agent_run_id)


@login_required
@require_POST
def abort_agent_run(request, agent_run_id):
    """
    Abort agent run.
    
    Terminates execution regardless of current state.
    """
    agent_run = get_object_or_404(
        AgentRun,
        pk=agent_run_id,
        pipeline_execution__started_by=request.user
    )
    
    # Mark as cancelled
    agent_run.status = 'cancelled'
    agent_run.human_intervention_required = False
    agent_run.save()
    
    agent_run.pipeline_execution.status = 'cancelled'
    agent_run.pipeline_execution.save()
    
    messages.warning(request, "Agent run aborted")
    
    return redirect('agent_integration:agent_run_detail', agent_run_id=agent_run_id)


@login_required
def agent_run_graph_view(request, agent_run_id):
    """
    Read-only pipeline graph view showing execution state.
    
    Shows which nodes executed, current node, skipped nodes.
    """
    agent_run = get_object_or_404(
        AgentRun,
        pk=agent_run_id,
        pipeline_execution__started_by=request.user
    )
    
    pipeline = agent_run.pipeline_execution.pipeline
    nodes = pipeline.nodes.all().order_by('order')
    
    # Get node execution states
    node_executions = NodeExecution.objects.filter(
        pipeline_execution=agent_run.pipeline_execution
    ).select_related('node')
    
    node_states = {}
    node_exec_details = {}
    
    for node_exec in node_executions:
        node_id = str(node_exec.node.id)
        node_states[node_id] = {
            'status': node_exec.status,
            'started_at': node_exec.started_at,
            'completed_at': node_exec.completed_at,
            'error_message': node_exec.error_message
        }
        
        # Store detailed execution data
        node_exec_details[node_id] = {
            'input_data': node_exec.input_data or {},
            'output_data': node_exec.output_data or {}
        }
    
    # Attach execution status and data to node objects for easier template access
    import json
    nodes_with_status = []
    for node in nodes:
        node_id = str(node.id)
        node.execution_status = node_states.get(node_id, {}).get('status', 'pending')
        node.execution_started_at = node_states.get(node_id, {}).get('started_at')
        node.execution_completed_at = node_states.get(node_id, {}).get('completed_at')
        node.execution_error = node_states.get(node_id, {}).get('error_message')
        
        # Add input/output data as JSON strings for template
        exec_details = node_exec_details.get(node_id, {})
        node.input_data_json = json.dumps(exec_details.get('input_data', {}))
        node.output_data_json = json.dumps(exec_details.get('output_data', {}))
        
        nodes_with_status.append(node)
    
    # Build connections from input_variable_mappings
    connections_data = []
    for node in nodes:
        if node.input_variable_mappings:
            for target_var, mapping in node.input_variable_mappings.items():
                source_node_id = mapping.get('node_id')
                source_var = mapping.get('source_variable')
                
                if source_node_id and source_node_id != '__pipeline__' and source_var:
                    connections_data.append({
                        'from_node': source_node_id,
                        'to_node': str(node.id),
                        'from_output': source_var,
                        'to_input': target_var,
                    })
    
    context = {
        'agent_run': agent_run,
        'pipeline': pipeline,
        'nodes': nodes_with_status,
        'node_states': node_states,
        'connections_data': connections_data,
        'title': f'Agent Run Graph: {agent_run.id}'
    }
    
    return render(request, 'agent_integration/graph_view.html', context)


@login_required
def debug_context_view(request, agent_run_id):
    """
    Debug view showing raw context data.
    
    For integration testing and debugging.
    """
    agent_run = get_object_or_404(
        AgentRun,
        pk=agent_run_id,
        pipeline_execution__started_by=request.user
    )
    
    # Get runtime spec
    runtime_spec = None
    try:
        runtime_spec = agent_run.runtime_spec
    except RuntimeSpec.DoesNotExist:
        pass
    
    context = {
        'agent_run': agent_run,
        'pipeline_execution': agent_run.pipeline_execution,
        'runtime_spec': runtime_spec,
        'title': f'Debug Context: {agent_run.id}'
    }
    
    return render(request, 'agent_integration/debug_context.html', context)
