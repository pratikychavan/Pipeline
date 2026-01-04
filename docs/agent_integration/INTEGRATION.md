# Integration Guide

## Quick Start - Adding Agent Integration to Your Django Project

### Step 1: Update Settings

Edit `pipeline/settings.py`:

```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'core',
    'agent_integration',  # ADD THIS
]
```

### Step 2: Update URLs

Edit `pipeline/urls.py`:

```python
from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/login/', auth_views.LoginView.as_view(template_name='admin/login.html')),
    path('accounts/logout/', auth_views.LogoutView.as_view(next_page='/accounts/login/'), name='logout'),
    path('', include('core.urls')),
    path('agent/', include('agent_integration.urls')),  # ADD THIS
]
```

### Step 3: Create Migrations

```bash
cd /home/pyc/pipeline
python manage.py makemigrations agent_integration
python manage.py migrate agent_integration
```

### Step 4: Verify Installation

```bash
# Start server
python manage.py runserver

# Test API (in another terminal)
curl http://localhost:8000/agent/runs/00000000-0000-0000-0000-000000000000/
# Should return 404 (not found) rather than 500 (server error)
```

### Step 5: Test Agent Execution

```python
# In Django shell
python manage.py shell

from core.models import Pipeline, PipelineExecution, User
from agent_integration.runtime import start_agent_execution

# Get a pipeline
user = User.objects.first()
pipeline = Pipeline.objects.filter(created_by=user).first()

# Create execution
execution = PipelineExecution.objects.create(
    pipeline=pipeline,
    started_by=user,
    context_data={'test_input': 42}
)

# Start agent
result = start_agent_execution(execution)
print(result)
```

## API Examples

### Start Agent Execution

```bash
curl -X POST http://localhost:8000/agent/pipelines/{pipeline-uuid}/execute/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -d '{
    "context_data": {
      "input_variable_1": "value1",
      "input_variable_2": 123
    },
    "agent_config": {
      "model": "gpt-4",
      "temperature": 0.0,
      "max_steps": 50
    }
  }'
```

Response:
```json
{
  "success": true,
  "agent_run_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "summary": "Executed 5 tools across 5 agent decisions in 5 steps"
}
```

### Check Status

```bash
curl http://localhost:8000/agent/runs/{agent-run-uuid}/
```

Response:
```json
{
  "success": true,
  "agent_run": {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "status": "executing",
    "current_step": 3,
    "max_steps": 50,
    "human_intervention_required": false
  }
}
```

### View Decisions

```bash
curl http://localhost:8000/agent/runs/{agent-run-uuid}/decisions/
```

Response:
```json
{
  "success": true,
  "decisions": [
    {
      "step": 1,
      "type": "select_node",
      "reasoning": "Selected node ABC based on execution order",
      "parsed_decision": {
        "selected_node_id": "abc-123",
        "reasoning": "..."
      },
      "guardrail_violations": []
    }
  ]
}
```

### Respond to Human Intervention

```bash
curl -X POST http://localhost:8000/agent/runs/{agent-run-uuid}/respond/ \
  -H "Content-Type: application/json" \
  -d '{
    "action": "continue",
    "response": {
      "user_decision": "proceed",
      "notes": "Reviewed and approved"
    }
  }'
```

## Python API Usage

### Programmatic Execution

```python
from agent_integration.runtime import AgentExecutionLoop
from core.models import PipelineExecution

# Create execution
execution = PipelineExecution.objects.create(...)

# Initialize loop
loop = AgentExecutionLoop(
    pipeline_execution=execution,
    agent_config={
        'model': 'gpt-4',
        'temperature': 0.0,
        'max_steps': 100,
        'enable_human_intervention': True
    }
)

# Execute
try:
    result = loop.execute()
    print(f"Status: {result['status']}")
    print(f"Summary: {result['summary']}")
except Exception as e:
    print(f"Execution failed: {e}")
```

### Custom Guardrails

```python
from agent_integration.guardrails import GuardrailEngine
from agent_integration.runtime.spec_builder import RuntimeSpecBuilder

# Build spec
builder = RuntimeSpecBuilder(pipeline)
spec = builder.build_spec()

# Create guardrails
guardrails = GuardrailEngine(spec)

# Check what's available
available = guardrails.get_safe_choices()
print(f"Available nodes: {available}")

# Validate a selection
is_valid, violations = guardrails.validate_before_execution(
    selected_node_id='node-123',
    current_iteration=5,
    consecutive_failures=0
)

if not is_valid:
    for v in violations:
        print(f"Violation: {v.message}")
```

### Tool Registry Usage

```python
from agent_integration.tools import ToolRegistry

# Create registry
registry = ToolRegistry(pipeline)

# Get all tools
tools = registry.get_all_tools()
for tool in tools:
    definition = tool.to_tool_definition()
    print(f"Tool: {definition.tool_name}")
    print(f"Description: {definition.description}")
    print(f"Parameters: {definition.parameters}")

# Execute a specific tool
tool = registry.get_tool('node-uuid')
if tool:
    result = tool.execute(
        agent_run=agent_run,
        context={'input_x': 10},
        agent_decision=decision
    )
    print(f"Result: {result}")
```

## Monitoring & Debugging

### Django Admin

Visit `http://localhost:8000/admin/` and navigate to:

- **Agent Runs**: View all agent executions
- **Agent Decisions**: See every LLM decision
- **Tool Executions**: Track node executions
- **Runtime Specs**: Inspect materialized specs

### Logging

Add to your settings:

```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'loggers': {
        'agent_integration': {
            'handlers': ['console'],
            'level': 'DEBUG',
        },
    },
}
```

### Troubleshooting

**Problem**: Agent run stuck in "initializing"

**Solution**: Check logs for spec validation errors. Ensure pipeline has at least one node.

**Problem**: Guardrail violations blocking execution

**Solution**: Check `AgentDecision` records for `guardrail_violations` field. Fix pipeline DAG structure.

**Problem**: Human intervention not resuming

**Solution**: Verify `human_intervention_required=True` and use correct API endpoint with valid action.

## Production Deployment

### Async Execution with Celery

```python
# tasks.py
from celery import shared_task
from agent_integration.runtime import start_agent_execution
from core.models import PipelineExecution

@shared_task
def execute_agent_run_async(execution_id, agent_config):
    execution = PipelineExecution.objects.get(id=execution_id)
    return start_agent_execution(execution, agent_config)

# views.py
from .tasks import execute_agent_run_async

@login_required
@require_POST
def start_agent_run(request, pipeline_id):
    # ... create execution ...
    
    # Start async
    task = execute_agent_run_async.delay(
        str(execution.id),
        agent_config
    )
    
    return JsonResponse({
        'success': True,
        'task_id': task.id,
        'execution_id': str(execution.id)
    })
```

### Environment Variables

```bash
# .env
AGENT_MODEL=gpt-4
AGENT_TEMPERATURE=0.0
AGENT_MAX_STEPS=100
AGENT_ENABLE_HUMAN_INTERVENTION=true
```

### Security

- Add proper authentication/authorization
- Rate limit API endpoints
- Validate all user inputs
- Use HTTPS in production
- Restrict admin access

## Next Steps

1. Implement actual LLM integration (OpenAI/Anthropic)
2. Add WebSocket support for real-time updates
3. Implement business condition UI
4. Add retry policies
5. Create monitoring dashboard
6. Add performance metrics
7. Implement cost tracking (LLM API calls)
8. Add execution templates
9. Create agent presets (conservative, aggressive, etc.)
10. Implement multi-agent collaboration
