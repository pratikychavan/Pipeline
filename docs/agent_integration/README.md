# Agent Integration Layer

## Overview

This module provides **LLM-based orchestration ON TOP OF** the existing Django pipeline execution system. The LLM acts as a **CONTROLLER**, not a processor—it decides execution flow but does not execute nodes directly.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    LLM Agent Layer                      │
│  (Decision Making, Flow Control, Human Interaction)     │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ Tool Calls
                  ▼
┌─────────────────────────────────────────────────────────┐
│              Tool Abstraction Layer                     │
│    (NodeToolWrapper - wraps nodes as tools)             │
└─────────────────┬───────────────────────────────────────┘
                  │
                  │ execute_node()
                  ▼
┌─────────────────────────────────────────────────────────┐
│         Django Pipeline Execution Engine                │
│   (UNCHANGED - deterministic execution backend)         │
└─────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Models (`models.py`)

Extended models that **do not modify** core models:

- **AgentRun**: Top-level agent execution entity
- **AgentDecision**: Records each LLM decision with full audit trail
- **ToolExecution**: Wraps NodeExecution with agent context
- **RuntimeSpec**: Immutable runtime specification

### 2. Tool Abstraction (`tools/`)

- **NodeToolWrapper**: Wraps Node as Tool
  - Exposes node as tool definition for LLM
  - Triggers existing node execution logic
  - Returns artifact references only (not raw data)
  
- **ToolRegistry**: Registry of available tools per pipeline

### 3. Runtime Specification (`runtime/spec_builder.py`)

- **RuntimeSpecBuilder**: Converts Pipeline → immutable JSON spec
  - Available tools (nodes)
  - Execution constraints (DAG structure)
  - Business conditions (conditional logic)
  - Global context
  - Execution policies

- **SpecValidator**: Validates and verifies specs

### 4. Guardrails (`guardrails/`)

Graph-aware constraints that enforce:

- **Node ordering**: Respect pipeline DAG
- **Dependency satisfaction**: No execution before prerequisites
- **Loop prevention**: Each node executes exactly once
- **Deadlock detection**: Catches circular dependencies
- **Policy enforcement**: Max iterations, failure limits

**CRITICAL**: Guardrails run BEFORE and AFTER every agent decision.

### 5. Execution Loop (`runtime/execution_loop.py`)

Main orchestration engine:

```python
while not complete:
    # 1. Get safe choices from guardrails
    available_nodes = guardrails.get_safe_choices()
    
    # 2. Call planner (LLM) for decision
    selected_node, reasoning = call_planner(available_nodes)
    
    # 3. Validate with guardrails
    is_valid, violations = guardrails.validate(selected_node)
    
    # 4. Execute tool (node) via existing backend
    result = tool.execute(context)
    
    # 5. Record and update state
    guardrails.record_execution(selected_node, success)
    update_context(result)
```

### 6. API Views (`views.py`)

REST API for agent control:

- `POST /agent/pipelines/<id>/execute/` - Start agent run
- `GET /agent/runs/<id>/` - Get status
- `GET /agent/runs/<id>/decisions/` - Get decision history
- `POST /agent/runs/<id>/respond/` - Respond to human intervention

## Usage

### Start Agent Execution

```python
from agent_integration.runtime import start_agent_execution
from core.models import PipelineExecution

# Create pipeline execution
execution = PipelineExecution.objects.create(
    pipeline=pipeline,
    started_by=user,
    context_data={'input_x': 10}
)

# Start agent
result = start_agent_execution(
    execution,
    agent_config={
        'model': 'gpt-4',
        'temperature': 0.0,
        'max_steps': 100
    }
)
```

### Via API

```bash
# Start execution
curl -X POST http://localhost:8000/agent/pipelines/{pipeline_id}/execute/ \
  -H "Content-Type: application/json" \
  -d '{
    "context_data": {"x": 10},
    "agent_config": {"model": "gpt-4"}
  }'

# Check status
curl http://localhost:8000/agent/runs/{agent_run_id}/

# View decisions
curl http://localhost:8000/agent/runs/{agent_run_id}/decisions/
```

## Human-in-the-Loop

When agent encounters ambiguity or error:

1. Sets status to `waiting_for_human`
2. Pauses execution
3. Stores reason in `human_intervention_reason`
4. Waits for human response via API

Resume:

```bash
curl -X POST http://localhost:8000/agent/runs/{id}/respond/ \
  -d '{
    "action": "continue",
    "response": {"decision": "proceed"}
  }'
```

## Safety Guarantees

### What the Agent CANNOT Do

- ❌ Execute nodes directly (must go through backend)
- ❌ Bypass DAG constraints
- ❌ Skip mandatory nodes
- ❌ Execute nodes multiple times
- ❌ Mutate pipeline definitions
- ❌ Access raw artifact data (only references)

### What Guardrails ENFORCE

- ✅ Dependency satisfaction before execution
- ✅ Respect node ordering
- ✅ Prevent infinite loops
- ✅ Detect deadlocks
- ✅ Enforce iteration limits
- ✅ Trigger human intervention on errors

## Observability

Every agent run records:

1. **Full decision trace**: Every LLM call and response
2. **Guardrail violations**: What was blocked and why
3. **Tool executions**: What was executed and results
4. **Timing data**: When each step occurred
5. **Context evolution**: How data flowed through pipeline

View in Django admin:

- Agent Runs
- Agent Decisions
- Tool Executions
- Runtime Specs

## Database Migrations

```bash
# Create migrations for agent_integration models
python manage.py makemigrations agent_integration

# Apply migrations
python manage.py migrate agent_integration
```

## Configuration

Add to `INSTALLED_APPS` in `settings.py`:

```python
INSTALLED_APPS = [
    # ...
    'core',
    'agent_integration',
]
```

Add URLs to `urls.py`:

```python
from django.urls import path, include

urlpatterns = [
    # ...
    path('agent/', include('agent_integration.urls')),
]
```

## Future Enhancements

### TODO: Implement LLM Integration

Currently uses simple ordering-based selection. Replace with actual LLM:

```python
def _call_planner(self, available_nodes):
    # TODO: Call OpenAI/Anthropic API
    # Build prompt with:
    # - Pipeline description
    # - Available nodes
    # - Current context
    # - Previous decisions
    
    # Parse response
    # Extract selected node + reasoning
    pass
```

### TODO: Async Execution

Move to Celery/background tasks:

```python
from celery import shared_task

@shared_task
def execute_agent_run_async(execution_id, agent_config):
    execution = PipelineExecution.objects.get(id=execution_id)
    return start_agent_execution(execution, agent_config)
```

### TODO: Business Conditions

Add UI for defining conditional execution rules:

- Skip node if condition X
- Execute node only if Y
- Retry on specific errors

Store in node metadata, parse in RuntimeSpecBuilder.

### TODO: Streaming Updates

WebSocket support for real-time execution monitoring:

```python
# Send updates via channels
channel_layer.group_send(
    f"agent_run_{agent_run_id}",
    {
        'type': 'execution.update',
        'step': current_step,
        'status': status
    }
)
```

## Testing

```python
from agent_integration.runtime import AgentExecutionLoop
from agent_integration.guardrails import GuardrailEngine

# Test guardrails
def test_guardrails_block_invalid_node():
    spec = {...}
    guardrails = GuardrailEngine(spec)
    
    is_valid, violations = guardrails.validate_before_execution(
        'invalid-node-id', 0, 0
    )
    
    assert not is_valid
    assert any(v.violation_type == 'invalid_node' for v in violations)

# Test execution loop
def test_execution_completes():
    execution = create_test_execution()
    result = start_agent_execution(execution)
    
    assert result['status'] == 'completed'
```

## License

Same as parent project.
