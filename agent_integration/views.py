"""
API views for agent-driven execution.

These endpoints trigger and control agent execution.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
import json

from core.models import Pipeline, PipelineExecution
from .models import AgentRun
from .runtime.execution_loop import start_agent_execution, AgentExecutionLoop


@login_required
@require_POST
def start_agent_run(request, pipeline_id):
    """
    Start an agent-driven execution of a pipeline.
    
    POST /agent/pipelines/<pipeline_id>/execute/
    Body: {
        "context_data": {...},  # Initial pipeline arguments
        "agent_config": {       # Optional
            "model": "gpt-4",
            "temperature": 0.0,
            "max_steps": 100
        }
    }
    """
    try:
        pipeline = get_object_or_404(Pipeline, pk=pipeline_id, created_by=request.user)
        
        # Parse request body
        data = json.loads(request.body)
        context_data = data.get('context_data', {})
        agent_config = data.get('agent_config', {})
        
        # Create pipeline execution
        pipeline_execution = PipelineExecution.objects.create(
            pipeline=pipeline,
            started_by=request.user,
            status='pending',
            context_data=context_data
        )
        
        # Start agent execution (runs synchronously for now)
        # TODO: Move to background task queue (Celery)
        result = start_agent_execution(pipeline_execution, agent_config)
        
        return JsonResponse({
            'success': True,
            'agent_run_id': result['agent_run_id'],
            'status': result['status'],
            'summary': result['summary']
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_agent_run_status(request, agent_run_id):
    """
    Get status of an agent run.
    
    GET /agent/runs/<agent_run_id>/
    """
    try:
        agent_run = get_object_or_404(
            AgentRun,
            pk=agent_run_id,
            pipeline_execution__started_by=request.user
        )
        
        return JsonResponse({
            'success': True,
            'agent_run': {
                'id': str(agent_run.id),
                'status': agent_run.status,
                'current_step': agent_run.current_step,
                'max_steps': agent_run.max_steps,
                'created_at': agent_run.created_at.isoformat(),
                'completed_at': agent_run.completed_at.isoformat() if agent_run.completed_at else None,
                'human_intervention_required': agent_run.human_intervention_required,
                'human_intervention_reason': agent_run.human_intervention_reason,
            },
            'pipeline_execution_id': str(agent_run.pipeline_execution.id)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_agent_decisions(request, agent_run_id):
    """
    Get all decisions made by agent in this run.
    
    GET /agent/runs/<agent_run_id>/decisions/
    """
    try:
        agent_run = get_object_or_404(
            AgentRun,
            pk=agent_run_id,
            pipeline_execution__started_by=request.user
        )
        
        decisions = agent_run.decisions.all().order_by('step_number')
        
        return JsonResponse({
            'success': True,
            'decisions': [
                {
                    'step': d.step_number,
                    'type': d.decision_type,
                    'reasoning': d.reasoning,
                    'timestamp': d.timestamp.isoformat(),
                    'parsed_decision': d.parsed_decision,
                    'guardrail_violations': d.guardrail_violations,
                }
                for d in decisions
            ]
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_POST
def respond_to_human_intervention(request, agent_run_id):
    """
    Respond to human intervention request and resume execution.
    
    POST /agent/runs/<agent_run_id>/respond/
    Body: {
        "action": "continue" | "cancel" | "modify",
        "response": {...}  # Human's response
    }
    """
    try:
        agent_run = get_object_or_404(
            AgentRun,
            pk=agent_run_id,
            pipeline_execution__started_by=request.user
        )
        
        if not agent_run.human_intervention_required:
            return JsonResponse({
                'success': False,
                'error': 'No human intervention pending'
            }, status=400)
        
        # Parse request
        data = json.loads(request.body)
        action = data.get('action')
        response = data.get('response', {})
        
        if action == 'cancel':
            agent_run.status = 'cancelled'
            agent_run.save()
            
            agent_run.pipeline_execution.status = 'cancelled'
            agent_run.pipeline_execution.save()
            
            return JsonResponse({
                'success': True,
                'message': 'Execution cancelled'
            })
        
        elif action == 'continue':
            # Resume execution
            loop = AgentExecutionLoop(agent_run.pipeline_execution)
            loop.agent_run = agent_run
            result = loop.resume_from_human_intervention(response)
            
            return JsonResponse({
                'success': True,
                'result': result
            })
        
        else:
            return JsonResponse({
                'success': False,
                'error': f'Unknown action: {action}'
            }, status=400)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def get_runtime_spec(request, agent_run_id):
    """
    Get the runtime specification for an agent run.
    
    GET /agent/runs/<agent_run_id>/spec/
    """
    try:
        agent_run = get_object_or_404(
            AgentRun,
            pk=agent_run_id,
            pipeline_execution__started_by=request.user
        )
        
        runtime_spec = agent_run.runtime_spec
        
        return JsonResponse({
            'success': True,
            'runtime_spec': {
                'spec_version': runtime_spec.spec_version,
                'spec_data': runtime_spec.spec_data,
                'spec_checksum': runtime_spec.spec_checksum,
                'created_at': runtime_spec.created_at.isoformat()
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
