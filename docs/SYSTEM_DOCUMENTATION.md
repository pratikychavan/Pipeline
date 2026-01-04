# Pipeline Orchestration System - Complete Documentation

**Version:** 1.0  
**Date:** January 4, 2026  
**Status:** Production-Ready with OpenAI Integration

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Core Components](#core-components)
4. [Agent Integration](#agent-integration)
5. [Setup & Installation](#setup--installation)
6. [Usage Guide](#usage-guide)
7. [API Reference](#api-reference)
8. [Development Guide](#development-guide)
9. [Known Issues & TODOs](#known-issues--todos)

---

## 1. System Overview

### What is This System?

A Django-based pipeline orchestration platform that enables:
- **Visual Pipeline Building**: Create multi-step workflows with nodes
- **Agent-Driven Execution**: LLM agents (GPT-4o-mini) make intelligent decisions about execution order
- **Guardrails & Safety**: Built-in safeguards prevent infinite loops, deadlocks, and unsafe operations
- **Real-time Monitoring**: Track execution progress, decisions, and costs
- **Human-in-the-Loop**: Optional human approval for critical decisions

### Key Features

✅ **Visual Pipeline Editor** - Drag-and-drop node positioning  
✅ **Python Code Execution** - Execute custom Python code in isolated environments  
✅ **OpenAI Integration** - Real LLM-powered decision making  
✅ **Artifact Management** - Pass data between nodes using WarpDrive I/O  
✅ **Control Plane** - Configure agents, tools, conditions, and mappings  
✅ **Execution Dashboard** - Monitor agent runs with timeline and graph views  

---

## 2. Architecture

### System Layers

```
┌─────────────────────────────────────────────────────┐
│              USER INTERFACE LAYER                    │
│  • Django Templates                                  │
│  • Bootstrap 5 UI                                    │
│  • Interactive Graph View                            │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│              AGENT ORCHESTRATION LAYER               │
│  • LLM Planner (OpenAI GPT-4o-mini)                 │
│  • Guardrail Engine                                  │
│  • Execution Loop                                    │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│              PIPELINE EXECUTION LAYER                │
│  • Node Executor                                     │
│  • Context Manager                                   │
│  • Artifact Storage (WarpDrive)                      │
└─────────────────────────────────────────────────────┘
                      ↓
┌─────────────────────────────────────────────────────┐
│              DATA PERSISTENCE LAYER                  │
│  • Django ORM                                        │
│  • SQLite Database                                   │
│  • Artifact Files                                    │
└─────────────────────────────────────────────────────┘
```

### Django Apps Structure

```
pipeline/
├── core/                    # Core pipeline management
│   ├── models.py           # Pipeline, Node, NodeExecution
│   ├── views.py            # CRUD views, execution views
│   └── execution_engine.py # Node execution logic
│
└── agent_integration/       # Agent orchestration system
    ├── models.py           # AgentRun, AgentDecision, ToolExecution
    ├── control_plane_models.py  # AgentProfile, ToolDefinition, etc.
    ├── llm_planner.py      # LLM-based decision making
    ├── execution_loop.py   # Main agent execution loop (legacy)
    ├── runtime/            # Production runtime components
    │   ├── execution_loop.py    # Production execution loop
    │   └── spec_builder.py      # Runtime specification builder
    ├── guardrails/         # Safety mechanisms
    ├── node_tools/         # Node-as-tool adapters
    └── ui_views.py         # Agent dashboard and control UIs
```

---

## 3. Core Components

### 3.1 Pipeline (core/models.py)

The fundamental workflow container.

**Key Fields:**
- `name`: Pipeline name
- `description`: What the pipeline does
- `created_by`: Owner (Django User)
- `input_schema`: Expected input variables (JSON)

**Relations:**
- `nodes`: One-to-many relationship with Node
- `executions`: One-to-many relationship with PipelineExecution

### 3.2 Node (core/models.py)

Individual execution units within a pipeline.

**Key Fields:**
- `pipeline`: Foreign key to Pipeline
- `name`: Node identifier
- `description`: Node purpose
- `code`: Python code to execute
- `order`: Execution order hint
- `position_x`, `position_y`: Visual layout coordinates
- `input_variable_mappings`: How to get input data (JSON)
- `timeout_seconds`: Max execution time

**Execution Model:**
```python
# Node execution environment
context = {
    'get_arg': lambda key: get_input_value(key),
    'save_artifact': lambda name, data: store_artifact(name, data),
    'log': lambda msg: record_log_message(msg),
    # ... other WarpDrive functions
}
exec(node.code, context)
```

### 3.3 Node Execution Engine (core/execution_engine.py)

Executes node code in isolated Python environment.

**Key Functions:**
- `execute_node(node, context)`: Main execution entry point
- Context management with WarpDrive I/O
- Error handling and timeout enforcement
- Artifact storage and retrieval

### 3.4 WarpDrive I/O System

Artifact-based data flow between nodes.

**Available Functions:**
```python
save_artifact(name, data)           # Store data for downstream nodes
get_arg(name)                       # Get input from previous nodes
log(message, level='INFO')          # Log execution messages
get_execution_context()             # Get full context dictionary
```

**Data Flow:**
```
Node A: save_artifact('customer_data', {...})
         ↓
Node B: customer = get_arg('customer_data')
```

---

## 4. Agent Integration

### 4.1 Agent Run Lifecycle

```
INITIALIZING → PLANNING → EXECUTING → COMPLETED
                  ↓            ↓
              WAITING_FOR_HUMAN → FAILED
```

**States:**
- `initializing`: Setting up runtime spec and guardrails
- `planning`: LLM is deciding next action
- `executing`: Running selected tool/node
- `waiting_for_human`: Paused for human approval
- `completed`: All nodes executed successfully
- `failed`: Execution error occurred

### 4.2 LLM Planner (agent_integration/llm_planner.py)

**Purpose:** Make intelligent decisions about which node to execute next.

**Decision Types:**
1. `EXECUTE_TOOL`: Execute a specific node
2. `COMPLETE`: Mark pipeline as finished
3. `REQUEST_HUMAN`: Ask for human intervention
4. `FAIL`: Cannot proceed safely

**LLM Prompt Structure:**
```
SYSTEM: You are an autonomous agent executor...
USER:
  OBJECTIVE: Complete the pipeline execution successfully
  
  AVAILABLE TOOLS:
  - FetchCustomerData (order: 1)
  - ValidateDataQuality (order: 2)
  ...
  
  COMPLETED TOOLS:
  - FetchCustomerData ✓
  
  CURRENT STATE:
  - customer_id: 12345
  - customer_data: {...}
  
  What should I do next?
```

**Response Format:**
```json
{
  "action": "execute_tool",
  "tool_id": "76c1855f-14a7-493f-8e41-2538cb692fa9",
  "reasoning": "We need to validate the fetched data before proceeding..."
}
```

### 4.3 Guardrails (agent_integration/guardrails/)

**Safety Mechanisms:**

1. **Loop Detection**: Prevents executing same node repeatedly
2. **Deadlock Detection**: Identifies when no progress can be made
3. **Dependency Validation**: Ensures prerequisites are met
4. **Execution Limits**: Max steps, max failures, timeout enforcement
5. **Tool Constraints**: Respects max_calls, is_allowed flags

**Usage:**
```python
guardrails = GuardrailEngine(runtime_spec)
available_nodes = guardrails.get_safe_choices()  # Only safe nodes
is_valid, violations = guardrails.validate_before_execution(node_id)
```

### 4.4 Runtime Execution Loop (agent_integration/runtime/execution_loop.py)

**Production execution engine with OpenAI integration.**

**Key Features:**
- ✅ Real OpenAI client integration (AsyncOpenAI)
- ✅ Async LLM calls with timeout
- ✅ Context building from previous node outputs
- ✅ Decision recording with reasoning
- ✅ Cost tracking (tokens used)

**Main Loop:**
```python
while not is_complete():
    step += 1
    available_nodes = guardrails.get_safe_choices()
    selected_node, reasoning = call_llm_planner(available_nodes)
    is_valid, violations = guardrails.validate(selected_node)
    
    if is_valid:
        result = execute_tool(selected_node)
        update_context(result.outputs)
    else:
        handle_violation(violations)
```

### 4.5 Control Plane (agent_integration/control_plane_models.py)

**Configuration Layer for Agent Behavior**

#### AgentProfile
Defines agent capabilities and constraints.
```python
AgentProfile(
    name="Risk Assessment Agent",
    status='active',
    llm_config={
        'model': 'gpt-4o-mini',
        'temperature': 0.3,
        'provider': 'openai'
    },
    max_steps=100,
    require_human_approval=False
)
```

#### ToolDefinition
Maps pipeline nodes to agent tools.
```python
ToolDefinition(
    name="Validate Data Quality",
    executor_type='node',
    pipeline=pipeline,
    node_name="ValidateDataQuality",
    is_enabled=True
)
```

#### AgentToolMapping
Links tools to agents with constraints.
```python
AgentToolMapping(
    agent=agent_profile,
    tool=tool_definition,
    is_allowed=True,
    max_calls=1,
    priority=2
)
```

#### BusinessCondition
Reusable conditional logic for agent decisions.
```python
BusinessCondition(
    name="High Risk Customer",
    condition_type='python_expression',
    condition_config={
        'expression': 'risk_score > 80',
        'variables': ['risk_score']
    }
)
```

---

## 5. Setup & Installation

### Prerequisites

```bash
# Required
Python 3.12+
Django 6.0
OpenAI API Key

# Python packages
pip install django openai matplotlib numpy pandas
```

### Environment Setup

```bash
# 1. Set OpenAI API Key
export OPENAI_API_KEY="sk-..."

# 2. Run migrations
python manage.py migrate

# 3. Create superuser
python manage.py createsuperuser

# 4. Start development server
python manage.py runserver
```

### Initial Data (Optional)

```bash
# Create demo pipeline with agent setup
python demo_agentic_run.py
```

---

## 6. Usage Guide

### 6.1 Creating a Pipeline

1. Navigate to `/` (Pipeline List)
2. Click "Create New Pipeline"
3. Fill in name, description, input schema
4. Save pipeline

### 6.2 Adding Nodes

1. Open pipeline detail page
2. Click "Add Node"
3. Configure:
   - Name (e.g., "FetchCustomerData")
   - Description
   - Python code using WarpDrive functions
   - Order hint
   - Position (x, y coordinates)
4. Save node

**Example Node Code:**
```python
# Fetch customer data
customer_id = get_arg('customer_id')
log(f"Fetching data for customer {customer_id}")

# Simulate data fetch
customer_data = {
    'id': customer_id,
    'name': f'Customer {customer_id}',
    'credit_score': 720,
    'annual_revenue': 5000000
}

save_artifact('customer_data', customer_data)
log(f"Fetched: {customer_data}")
```

### 6.3 Starting an Agent Run (via UI)

1. Go to `/agent/dashboard/`
2. Click "Start New Agent Run"
3. Select pipeline
4. (Optional) Select agent profile
5. Configure:
   - Max steps (default: 100)
   - Temperature (default: 0.3)
   - Enable human intervention (checkbox)
6. Add context variables (key-value pairs):
   - `customer_id`: `12345`
   - `customer_name`: `Acme Corp`
7. Click "Start Agent Run"

### 6.4 Monitoring Execution

**Agent Run Detail View** (`/agent/runs/<id>/detail/`)
- Execution timeline
- All decisions with reasoning
- Tool executions with status
- Guardrail violations
- Cost tracking

**Graph View** (`/agent/runs/<id>/graph/`)
- Visual representation of pipeline
- Node status colors:
  - 🟢 Green: Completed
  - 🟡 Yellow: Running
  - 🔴 Red: Failed
  - ⚪ Gray: Pending
- Draggable nodes
- Connection lines between dependencies

---

## 7. API Reference

### 7.1 Agent Execution API

#### Start Agent Run
```http
POST /agent/pipelines/<pipeline_id>/start/
Content-Type: application/json

{
  "agent_id": "uuid-optional",
  "max_steps": 100,
  "temperature": 0.3,
  "enable_human_intervention": true,
  "context_data": {
    "customer_id": 12345,
    "risk_threshold": 75
  }
}

Response:
{
  "agent_run_id": "uuid",
  "status": "initializing",
  "message": "Agent run started successfully"
}
```

#### Get Agent Run Status
```http
GET /agent/api/runs/<agent_run_id>/

Response:
{
  "success": true,
  "agent_run": {
    "id": "uuid",
    "status": "executing",
    "current_step": 3,
    "max_steps": 100,
    "created_at": "2026-01-04T08:00:00Z",
    "completed_at": null,
    "human_intervention_required": false
  },
  "pipeline_execution_id": "uuid"
}
```

### 7.2 Pipeline API

#### List Pipelines
```http
GET /api/pipelines/

Response:
[
  {
    "id": "uuid",
    "name": "Customer Risk Assessment",
    "description": "Assess customer onboarding risk",
    "created_at": "2026-01-04T08:00:00Z"
  }
]
```

### 7.3 Control Plane API

#### List Active Agents
```http
GET /agent/control-plane/agents/api/

Response:
{
  "agents": [
    {
      "id": "uuid",
      "name": "Risk Agent",
      "description": "Handles risk assessment",
      "llm_config": {
        "model": "gpt-4o-mini",
        "temperature": 0.3
      },
      "status": "active"
    }
  ]
}
```

---

## 8. Development Guide

### 8.1 Project Structure

```
/home/pyc/pipeline/
├── manage.py                   # Django management
├── db.sqlite3                  # Database
├── artifacts/                  # Stored artifacts from node executions
│
├── pipeline/                   # Django project settings
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── core/                       # Core pipeline app
│   ├── models.py              # Pipeline, Node, NodeExecution
│   ├── views.py               # CRUD and execution views
│   ├── forms.py               # Django forms
│   ├── urls.py                # URL routing
│   ├── execution_engine.py    # Node execution logic
│   └── templates/             # UI templates
│
└── agent_integration/          # Agent orchestration app
    ├── models.py              # AgentRun, AgentDecision
    ├── control_plane_models.py # Agent configuration
    ├── views.py               # API views
    ├── ui_views.py            # Dashboard views
    ├── llm_planner.py         # LLM decision making
    ├── execution_loop.py      # Legacy execution loop
    ├── runtime_spec_builder.py # Spec generation
    │
    ├── runtime/               # Production runtime
    │   ├── execution_loop.py  # Production loop with OpenAI
    │   └── spec_builder.py    # Runtime spec builder
    │
    ├── guardrails/            # Safety mechanisms
    │   ├── engine.py
    │   ├── graph.py
    │   └── validators.py
    │
    ├── node_tools/            # Node-as-tool system
    │   ├── base.py
    │   ├── executor.py
    │   ├── registry.py
    │   └── utils.py
    │
    └── templates/             # Agent UI templates
        └── agent_integration/
            ├── dashboard.html
            ├── run_detail.html
            └── graph_view.html
```

### 8.2 Adding a New Node Type

Nodes use standard Python code with WarpDrive I/O functions.

**Template:**
```python
# 1. Get inputs
input_value = get_arg('input_name')
log(f"Processing {input_value}")

# 2. Your logic here
result = process(input_value)

# 3. Save outputs
save_artifact('output_name', result)
log(f"Completed with result: {result}")
```

### 8.3 Extending the Agent System

#### Adding a New Planner

```python
from agent_integration.execution_loop import Planner, PlannerDecision

class CustomPlanner(Planner):
    async def plan_next_action(self, runtime_spec, execution_history, current_state):
        # Your custom logic
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id="selected-node-id",
            reasoning="Because...",
            confidence=0.9
        )
```

#### Adding a New Guardrail

```python
from agent_integration.guardrails import BaseGuardrail

class CustomGuardrail(BaseGuardrail):
    def validate(self, node_id, state):
        if self.is_safe(node_id, state):
            return True, []
        return False, [GuardrailViolation("Reason")]
```

### 8.4 Testing

```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test agent_integration

# Run specific test
python manage.py test agent_integration.tests.test_llm_planner
```

---

## 9. Known Issues & TODOs

### Current Limitations

1. **Synchronous Execution**: Agent runs block the request thread
   - TODO: Move to Celery/background tasks
   
2. **Single User**: No multi-tenancy or team collaboration
   - TODO: Add workspace/team models

3. **No Rollback**: Failed executions cannot be automatically retried
   - TODO: Implement checkpoint/rollback mechanism

4. **Limited Condition Types**: Only Python expressions supported
   - TODO: Add JSON path, regex, custom function conditions

### Completed Features

✅ OpenAI LLM integration with GPT-4o-mini  
✅ Real-time decision making with reasoning  
✅ Context building from previous node outputs  
✅ Graph view with draggable nodes  
✅ Node status visualization  
✅ Cost tracking (tokens used)  
✅ Agent dashboard with run management  
✅ Control plane for agent configuration  

### Future Enhancements

**High Priority:**
- [ ] Async execution with Celery
- [ ] WebSocket streaming updates
- [ ] Agent run cancellation
- [ ] Execution replay/debug mode

**Medium Priority:**
- [ ] Multi-agent collaboration
- [ ] Conditional branching in pipelines
- [ ] Scheduled/triggered executions
- [ ] Export/import pipeline definitions

**Low Priority:**
- [ ] Anthropic Claude integration
- [ ] Custom LLM provider support
- [ ] Pipeline templates library
- [ ] Performance metrics dashboard

### Critical TODOs in Code

**agent_integration/runtime/execution_loop.py:**
- Line 425: Store actual LLM response (currently just reasoning)
- Line 439: Implement proper prompt engineering

**agent_integration/views.py:**
- Line 52: Move to background task queue (Celery)

**agent_integration/control_plane_models.py:**
- Line 104: Check if agent has active runs before deletion

**agent_integration/llm_planner.py:**
- Line 313: Extract optional_variables from tool definition
- Lines 906-930: OpenAI client stub implementation
- Lines 970-993: Anthropic client stub implementation

---

## Appendix A: Example Workflows

### A.1 Customer Risk Assessment

**Pipeline:** Customer Onboarding & Risk Assessment

**Nodes:**
1. FetchCustomerData - Retrieve customer information
2. ValidateDataQuality - Check data completeness
3. AssessRiskScore - Calculate risk (0-100)
4. GenerateRecommendations - Approve or reject
5. SendNotifications - Notify stakeholders

**Agent Behavior:**
- Executes nodes in intelligent order based on dependencies
- Makes decision: "FetchCustomerData must run first to gather information"
- Makes decision: "ValidateDataQuality ensures data is complete before risk assessment"
- Makes decision: "AssessRiskScore calculates risk based on validated data"
- Makes decision: "GenerateRecommendations makes approval decision based on risk score"
- Makes decision: "SendNotifications completes the workflow"

**Typical Execution:**
- Input: `customer_id=12345`
- Step 1: Fetch data (2s)
- Step 2: Validate (1s)
- Step 3: Assess risk (3s, result: 45/100 - Low Risk)
- Step 4: Generate recommendation (2s, result: APPROVED)
- Step 5: Send notifications (1s)
- Total: 9 seconds, 6 LLM decisions, ~3000 tokens, $0.002

---

## Appendix B: Troubleshooting

### Issue: "LLM planner using fallback deterministic planner"

**Symptoms:**
- Decisions show: "Selected node based on execution order"
- No intelligent reasoning

**Causes & Solutions:**
1. Missing OPENAI_API_KEY
   ```bash
   export OPENAI_API_KEY="sk-..."
   ```

2. Model not set in agent_config
   - Ensure agent_config includes `'model': 'gpt-4o-mini'`

3. OpenAI library not installed
   ```bash
   pip install openai
   ```

### Issue: "Nodes show superimposed in graph view"

**Solution:**
- Nodes may have default (0,0) positions
- Edit each node and set position_x, position_y values
- Or use demo script to auto-position:
  ```python
  python demo_agentic_run.py
  ```

### Issue: "'NoneType' object has no attribute 'get'"

**Cause:** Agent run trying to access non-existent context data

**Solution:**
- Ensure previous nodes saved required artifacts
- Check node input_variable_mappings are correct
- Verify context building in execution loop

### Issue: "Maximum steps exceeded"

**Cause:** Agent loop running too long

**Solutions:**
1. Increase max_steps when starting run
2. Check for guardrail issues preventing completion
3. Verify LLM is making COMPLETE decisions when appropriate

---

## Appendix C: Security Considerations

### Code Execution

**Risk:** Nodes execute arbitrary Python code

**Mitigations:**
1. Code runs in restricted context (no imports allowed by default)
2. Timeout enforcement (default 60s)
3. User-scoped: Only creator can execute their pipelines
4. Future: Sandboxed execution environment

### LLM Prompt Injection

**Risk:** Malicious data in artifacts could manipulate LLM

**Mitigations:**
1. SafePromptTemplate escapes all user data
2. Structured JSON response parsing
3. Guardrails validate LLM decisions
4. Confidence scoring on decisions

### Data Privacy

**Risk:** Sensitive data in artifacts and logs

**Mitigations:**
1. User authentication required
2. User-scoped data access (Django ORM filters)
3. Artifacts stored in user-specific directories
4. Future: Encryption at rest

---

## Appendix D: Performance Optimization

### Current Performance

- **Node Execution:** 1-5s per node (depends on code)
- **LLM Decision:** 0.5-2s per decision (GPT-4o-mini)
- **Total Pipeline:** ~10-30s for 5-node pipeline

### Optimization Tips

1. **Reduce LLM Calls:**
   - Use deterministic ordering where possible
   - Cache common decisions

2. **Optimize Node Code:**
   - Avoid heavy computations
   - Use efficient data structures
   - Minimize logging

3. **Parallel Execution:**
   - Future: Execute independent nodes in parallel
   - Requires async execution infrastructure

4. **Database Queries:**
   - Use select_related() and prefetch_related()
   - Index frequently queried fields

---

**End of Documentation**

For questions or issues, check the code comments or create a GitHub issue.
