# TODO List - Pipeline Orchestration System

**Last Updated:** January 4, 2026

---

## Recently Completed (January 4, 2026)

### ✅ Fail-Fast on Node Failure
- Added `fail_on_node_failure` configuration (default: True)
- Immediately stops execution when any node fails
- Prevents dependent nodes from executing after failures

### ✅ Dependency Failure Cascading
- Nodes with failed dependencies are automatically marked as failed
- Prevents illogical execution of nodes with missing prerequisites
- Proper graph traversal respecting dependency failures

### ✅ Guardrail Configuration Enforcement
- **Time Limits:** `max_execution_time_seconds` now enforced
- **Cost Limits:** `max_cost_usd` tracked and enforced with LLM cost tracking
- **High-Risk Approval:** `require_approval_for_high_risk` detects dangerous operations
- Created comprehensive GUARDRAIL_CONFIGURATION.md guide

---

## Critical (Must Do Soon)

### 1. Async Execution with Celery
**Priority:** HIGH  
**Complexity:** Medium  
**Impact:** High

**Current Problem:**
- Agent runs block the HTTP request thread
- Long-running pipelines timeout
- No way to run multiple executions concurrently

**Solution:**
```python
# Install Celery
pip install celery redis

# Create tasks.py
from celery import shared_task

@shared_task
def run_agent_execution_async(pipeline_execution_id, agent_config):
    pipeline_execution = PipelineExecution.objects.get(pk=pipeline_execution_id)
    result = start_agent_execution(pipeline_execution, agent_config)
    return result

# Update ui_views.py
def start_agent_run_ui(request, pipeline_id):
    # ... create pipeline_execution ...
    task = run_agent_execution_async.delay(pipeline_execution.id, agent_config)
    return JsonResponse({'task_id': task.id, 'status': 'started'})
```

**Files to Modify:**
- `agent_integration/tasks.py` (new)
- `agent_integration/ui_views.py`
- `agent_integration/views.py`
- `pipeline/settings.py` (add Celery config)

---

### 2. Agent Run Cancellation
**Priority:** HIGH  
**Complexity:** Low  
**Impact:** Medium

**Current Problem:**
- No way to stop a running agent execution
- Must wait for completion or error

**Solution:**
```python
# Add to AgentRun model
class AgentRun(models.Model):
    cancellation_requested = models.BooleanField(default=False)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    
# Check in execution loop
def _execute_step(self):
    # Check for cancellation
    self.agent_run.refresh_from_db()
    if self.agent_run.cancellation_requested:
        self._handle_cancellation()
        return {'status': 'cancelled'}
    # ... continue execution ...
```

**Files to Modify:**
- `agent_integration/models.py` (add fields)
- `agent_integration/runtime/execution_loop.py` (check flag)
- `agent_integration/ui_views.py` (add cancel view)
- `agent_integration/templates/agent_integration/run_detail.html` (add button)

---

### 3. Proper Error Handling & Rollback
**Priority:** MEDIUM  
**Complexity:** High  
**Impact:** High

**Current Problem:**
- Failed executions leave partial state
- No automatic retry mechanism
- No rollback of completed nodes

**Solution:**
```python
# Add checkpoint mechanism
class ExecutionCheckpoint(models.Model):
    agent_run = models.ForeignKey(AgentRun, on_delete=models.CASCADE)
    step_number = models.IntegerField()
    state_snapshot = models.JSONField()  # Full execution state
    created_at = models.DateTimeField(auto_now_add=True)

# Implement rollback
def rollback_to_checkpoint(agent_run, checkpoint):
    # Restore execution context
    # Mark subsequent nodes as pending
    # Reset agent_run to previous state
    pass
```

**Files to Create:**
- `agent_integration/models.py` (add ExecutionCheckpoint)
- `agent_integration/checkpoints.py` (checkpoint logic)

**Files to Modify:**
- `agent_integration/runtime/execution_loop.py` (create checkpoints)

---

## Important (Should Do)

### 4. WebSocket Streaming Updates
**Priority:** MEDIUM  
**Complexity:** Medium  
**Impact:** High

**Current Problem:**
- Must refresh page to see execution progress
- No real-time notifications

**Solution:**
```python
# Install Django Channels
pip install channels channels-redis

# Add WebSocket consumer
class AgentRunConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.agent_run_id = self.scope['url_route']['kwargs']['agent_run_id']
        await self.channel_layer.group_add(f"agent_run_{self.agent_run_id}", self.channel_name)
        await self.accept()
    
    async def agent_decision(self, event):
        await self.send(text_data=json.dumps(event['data']))

# Send updates from execution loop
from channels.layers import get_channel_layer
channel_layer = get_channel_layer()
await channel_layer.group_send(
    f"agent_run_{self.agent_run.id}",
    {'type': 'agent_decision', 'data': decision_data}
)
```

**Files to Create:**
- `agent_integration/consumers.py` (WebSocket handlers)
- `agent_integration/routing.py` (WebSocket routes)

**Files to Modify:**
- `pipeline/settings.py` (add Channels)
- `pipeline/asgi.py` (configure Channels)
- `agent_integration/templates/agent_integration/run_detail.html` (add WebSocket JS)

---

### 5. Execution Replay/Debug Mode
**Priority:** MEDIUM  
**Complexity:** Low  
**Impact:** Medium

**Current Problem:**
- Cannot replay failed executions
- Hard to debug what went wrong

**Solution:**
```python
# Add replay view
def replay_agent_run(request, agent_run_id):
    original_run = get_object_or_404(AgentRun, pk=agent_run_id)
    
    # Create new execution with same config
    new_execution = PipelineExecution.objects.create(
        pipeline=original_run.pipeline_execution.pipeline,
        started_by=request.user,
        context_data=original_run.pipeline_execution.context_data
    )
    
    # Start with same agent config
    result = start_agent_execution(new_execution, original_run.agent_config)
    return redirect('agent_integration:agent_run_detail', agent_run_id=result['agent_run_id'])
```

**Files to Create:**
- None

**Files to Modify:**
- `agent_integration/ui_views.py` (add replay view)
- `agent_integration/urls.py` (add route)
- `agent_integration/templates/agent_integration/run_detail.html` (add button)

---

### 6. Conditional Branching in Pipelines
**Priority:** MEDIUM  
**Complexity:** High  
**Impact:** High

**Current Problem:**
- All nodes must execute in sequence
- No if/else logic in pipeline structure

**Solution:**
```python
# Add to Node model
class Node(models.Model):
    conditional_expression = models.TextField(blank=True)
    # If expression evaluates to False, skip this node

# Evaluate in execution loop
def should_execute_node(node, context):
    if not node.conditional_expression:
        return True
    
    try:
        return eval(node.conditional_expression, {}, context)
    except Exception:
        return True  # Default to execute on error
```

**Files to Modify:**
- `core/models.py` (add field)
- `agent_integration/guardrails/graph.py` (evaluate conditions)
- `agent_integration/runtime/execution_loop.py` (skip logic)

---

## Nice to Have (Future)

### 7. Anthropic Claude Integration
**Priority:** LOW  
**Complexity:** Low  
**Impact:** Low

**Current Status:**
- Stub exists in `llm_planner.py` lines 970-993
- Not implemented

**Solution:**
```python
# Implement AnthropicClient
class AnthropicClient:
    def __init__(self, api_key: str):
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
    
    async def create_completion(self, messages, model, max_tokens, temperature, timeout):
        response = await self.client.messages.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
            timeout=timeout
        )
        return {
            'content': response.content[0].text,
            'usage': {
                'prompt_tokens': response.usage.input_tokens,
                'completion_tokens': response.usage.output_tokens,
                'total_tokens': response.usage.input_tokens + response.usage.output_tokens
            }
        }
```

**Files to Modify:**
- `agent_integration/llm_planner.py` (lines 970-993)

---

### 8. Multi-Tenancy & Workspaces
**Priority:** LOW  
**Complexity:** High  
**Impact:** High

**Current Problem:**
- Single user system
- No team collaboration
- No workspace isolation

**Solution:**
```python
# Add Workspace model
class Workspace(models.Model):
    name = models.CharField(max_length=255)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    members = models.ManyToManyField(User, through='WorkspaceMembership')

class WorkspaceMembership(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=50)  # admin, member, viewer

# Add workspace FK to Pipeline
class Pipeline(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE)
    # ... existing fields ...
```

**Files to Create:**
- `workspaces/` (new Django app)

**Files to Modify:**
- `core/models.py` (add workspace FK)
- All views (filter by workspace)

---

### 9. Pipeline Templates Library
**Priority:** LOW  
**Complexity:** Medium  
**Impact:** Medium

**Current Problem:**
- Must build pipelines from scratch
- No way to share common patterns

**Solution:**
```python
# Add PipelineTemplate model
class PipelineTemplate(models.Model):
    name = models.CharField(max_length=255)
    description = models.TextField()
    category = models.CharField(max_length=100)
    is_public = models.BooleanField(default=False)
    pipeline_json = models.JSONField()  # Serialized pipeline structure
    
    def instantiate(self, user, name):
        """Create a new Pipeline from this template."""
        pipeline = Pipeline.objects.create(
            name=name,
            created_by=user,
            description=self.description
        )
        # Recreate nodes from template
        for node_data in self.pipeline_json['nodes']:
            Node.objects.create(pipeline=pipeline, **node_data)
        return pipeline
```

**Files to Create:**
- `templates/` (new Django app)

---

### 10. Performance Metrics Dashboard
**Priority:** LOW  
**Complexity:** Medium  
**Impact:** Low

**Current Problem:**
- No visibility into system performance
- Hard to identify bottlenecks

**Solution:**
```python
# Add metrics tracking
class ExecutionMetrics(models.Model):
    agent_run = models.OneToOneField(AgentRun, on_delete=models.CASCADE)
    total_duration_ms = models.IntegerField()
    llm_call_count = models.IntegerField()
    llm_total_duration_ms = models.IntegerField()
    llm_total_tokens = models.IntegerField()
    node_execution_count = models.IntegerField()
    average_node_duration_ms = models.IntegerField()

# Create dashboard view
def metrics_dashboard(request):
    metrics = ExecutionMetrics.objects.all()
    # Aggregate and visualize
    pass
```

**Files to Create:**
- `agent_integration/metrics.py`
- `agent_integration/templates/agent_integration/metrics_dashboard.html`

---

## Code Quality Improvements

### 11. Add Comprehensive Tests
**Priority:** MEDIUM  
**Complexity:** Medium  
**Impact:** High

**Current Status:**
- Basic tests exist in `agent_integration/tests/`
- Coverage is incomplete

**TODO:**
- [ ] Add integration tests for full agent runs
- [ ] Add tests for error scenarios
- [ ] Add performance benchmarks
- [ ] Set up CI/CD pipeline
- [ ] Achieve 80%+ code coverage

---

### 12. Extract Optional Variables from Tool Definitions
**Priority:** LOW  
**Complexity:** Low  
**Impact:** Low

**Location:** `agent_integration/llm_planner.py` line 313

**Current Code:**
```python
'optional_variables': [],  # TODO: Extract from tool definition
```

**Solution:**
```python
# Parse node code to detect optional inputs
def extract_optional_variables(node):
    optional = []
    for line in node.code.split('\n'):
        if 'get_arg' in line and 'default=' in line:
            # Extract variable name
            match = re.search(r"get_arg\('(\w+)'.*default", line)
            if match:
                optional.append(match.group(1))
    return optional
```

---

### 13. Store Actual LLM Response
**Priority:** LOW  
**Complexity:** Low  
**Impact:** Low

**Location:** `agent_integration/runtime/execution_loop.py` line 425

**Current Code:**
```python
llm_response=reasoning,  # TODO: Store actual LLM response
```

**Solution:**
```python
# Store full LLM response object
llm_response=json.dumps({
    'content': response['content'],
    'model': response['model'],
    'usage': response['usage'],
    'finish_reason': response['finish_reason']
})
```

---

### 14. Implement Proper Prompt Engineering
**Priority:** LOW  
**Complexity:** Medium  
**Impact:** Medium

**Location:** `agent_integration/runtime/execution_loop.py` line 439

**Current Code:**
```python
# TODO: Implement proper prompt engineering
```

**Solution:**
- Add few-shot examples to prompts
- Include success/failure examples
- Add chain-of-thought prompting
- Optimize token usage

---

## Documentation TODOs

### 15. API Documentation with Swagger/OpenAPI
**Priority:** LOW  
**Complexity:** Low  
**Impact:** Medium

**Solution:**
```bash
pip install drf-yasg  # For Django REST Swagger

# Add to urls.py
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

schema_view = get_schema_view(
    openapi.Info(
        title="Pipeline Orchestration API",
        default_version='v1',
    )
)

urlpatterns += [
    path('api/docs/', schema_view.with_ui('swagger')),
]
```

---

### 16. Video Tutorials
**Priority:** LOW  
**Complexity:** Low  
**Impact:** Medium

**TODO:**
- [ ] Create "Getting Started" video (5 min)
- [ ] Create "Building Your First Pipeline" video (10 min)
- [ ] Create "Agent Configuration" video (8 min)
- [ ] Create "Troubleshooting" video (7 min)

---

## Summary by Priority

### Critical (Do Now)
1. ✅ Async Execution with Celery
2. ✅ Agent Run Cancellation
3. ✅ Error Handling & Rollback

### Important (Do Soon)
4. ✅ WebSocket Streaming
5. ✅ Execution Replay
6. ✅ Conditional Branching

### Nice to Have (Future)
7. ⏸ Anthropic Claude Integration
8. ⏸ Multi-Tenancy
9. ⏸ Pipeline Templates
10. ⏸ Metrics Dashboard

### Code Quality
11. ⏸ Comprehensive Tests
12. ⏸ Extract Optional Variables
13. ⏸ Store Full LLM Response
14. ⏸ Prompt Engineering

### Documentation
15. ⏸ API Docs (Swagger)
16. ⏸ Video Tutorials

---

**Legend:**
- ✅ Critical/Must Do
- ⏸ Future/Nice to Have
