# Project Structure - Pipeline Orchestration System

**Generated:** January 4, 2026

---

## Directory Tree

```
/home/pyc/pipeline/
│
├── 📄 manage.py                        # Django management script
├── 📄 db.sqlite3                       # SQLite database
├── 📄 demo_agentic_run.py             # Production demo script (751 lines)
│
├── 📚 Documentation Files
│   ├── README.md                       # Quick start guide
│   ├── SYSTEM_DOCUMENTATION.md         # Complete system docs (350+ lines)
│   ├── CHANGELOG.md                    # Version history
│   └── TODO.md                         # Action items and roadmap
│
├── 📂 docs/                            # Additional documentation
│   ├── EXECUTION_LOOP_ARCHITECTURE.md
│   ├── IMPLEMENTATION_EXECUTION_LOOP.md
│   ├── IMPLEMENTATION_NODE_TOOLS.md
│   ├── IMPLEMENTATION_RUNTIME_SPEC.md
│   └── agent_integration/              # Agent-specific docs
│       ├── CHECKLIST.md
│       ├── DATAFLOW.md
│       ├── EXECUTION_LOOP_README.md
│       ├── IMPLEMENTATION_SUMMARY.md
│       ├── INTEGRATION.md
│       ├── LLM_PLANNER_README.md
│       ├── LLM_PLANNER_SUMMARY.md
│       ├── RUNTIME_SPEC_README.md
│       ├── SAFE_PROMPT_QUICK_REFERENCE.md
│       ├── SAFE_PROMPT_TEMPLATE_SUMMARY.md
│       └── UI_IMPLEMENTATION.md
│
├── 📂 examples/                        # Example scripts
│   ├── create_control_plane_examples.py
│   └── setup_test_data.py
│
├── 📂 artifacts/                       # Runtime artifact storage
│   └── (created at runtime)
│
├── 📂 pipeline/                        # Django project configuration
│   ├── __init__.py
│   ├── settings.py                     # Main settings
│   ├── urls.py                         # Root URL configuration
│   ├── asgi.py                         # ASGI configuration
│   └── wsgi.py                         # WSGI configuration
│
├── 📂 core/                            # Core Pipeline App
│   ├── __init__.py
│   ├── apps.py                         # App configuration
│   ├── admin.py                        # Django admin customization
│   ├── models.py                       # Pipeline, Node, NodeExecution
│   ├── views.py                        # Pipeline CRUD and execution views
│   ├── forms.py                        # Django forms
│   ├── urls.py                         # Core URL routing
│   ├── execution_engine.py             # Node execution engine
│   ├── tests.py                        # Unit tests
│   ├── test_views.py                   # View tests
│   │
│   ├── templates/                      # Core templates
│   │   └── core/
│   │       ├── base.html
│   │       ├── pipeline_list.html
│   │       ├── pipeline_detail.html
│   │       ├── pipeline_form.html
│   │       ├── node_form.html
│   │       └── execution_detail.html
│   │
│   ├── migrations/                     # Database migrations
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   │
│   └── execution/                      # Execution utilities
│       └── examples.py
│
└── 📂 agent_integration/               # Agent Orchestration App
    ├── __init__.py
    ├── apps.py
    ├── admin.py
    │
    ├── 🎯 Core Models
    │   ├── models.py                   # AgentRun, AgentDecision, ToolExecution
    │   └── control_plane_models.py     # AgentProfile, ToolDefinition, etc.
    │
    ├── 🎯 Views & APIs
    │   ├── views.py                    # API views
    │   ├── ui_views.py                 # Dashboard and UI views
    │   ├── control_plane_views.py      # Control plane CRUD views
    │   ├── control_plane_forms.py      # Control plane forms
    │   └── urls.py                     # Agent URL routing
    │
    ├── 🤖 LLM & Decision Making
    │   ├── llm_planner.py              # LLM-based planner (1013 lines)
    │   ├── llm_planner_examples.py     # Example usage
    │   └── safe_prompt_template_examples.py
    │
    ├── 🔄 Execution Loop
    │   ├── execution_loop.py           # Legacy execution loop (911 lines)
    │   ├── execution_loop_examples.py  # Example usage
    │   └── runtime/                    # Production runtime
    │       ├── __init__.py
    │       ├── execution_loop.py       # ✅ ACTIVE: Production loop (453 lines)
    │       └── spec_builder.py         # Runtime spec builder
    │
    ├── 🛡️ Guardrails
    │   └── guardrails/
    │       ├── __init__.py
    │       ├── engine.py               # Main guardrail engine
    │       ├── graph.py                # Graph-based guardrails
    │       └── validators.py           # Validation logic
    │
    ├── 🔧 Node Tools
    │   └── node_tools/
    │       ├── __init__.py
    │       ├── base.py                 # Base tool classes
    │       ├── executor.py             # Node executor wrapper
    │       ├── registry.py             # Tool registry
    │       ├── utils.py                # Utilities
    │       └── examples.py             # Example usage
    │
    ├── 📊 Runtime Spec
    │   ├── runtime_spec_builder.py     # Spec builder (legacy)
    │   └── runtime_spec_examples.py    # Example usage
    │
    ├── 🧪 Tests
    │   └── tests/
    │       ├── __init__.py
    │       ├── test_execution_loop.py
    │       ├── test_llm_planner.py
    │       ├── test_node_tools.py
    │       ├── test_runtime_spec.py
    │       └── test_safe_prompt_template.py
    │
    ├── 🌐 Templates
    │   └── templates/
    │       └── agent_integration/
    │           ├── dashboard.html          # Agent run list
    │           ├── run_detail.html         # Agent run detail
    │           ├── graph_view.html         # ✅ Graph visualization
    │           ├── debug_context.html      # Debug view
    │           └── control_plane/          # Control plane UIs
    │               ├── dashboard.html
    │               ├── agent_list.html
    │               ├── agent_detail.html
    │               ├── agent_form.html
    │               └── (more forms...)
    │
    └── 🗄️ Migrations
        └── migrations/
            ├── __init__.py
            ├── 0001_initial.py
            └── 0002_agentprofile_businesscondition_agentconditionbinding_and_more.py
```

---

## Key File Descriptions

### Production Files (Active in Runtime)

#### `agent_integration/runtime/execution_loop.py` ⭐
**Status:** ✅ ACTIVE - Main production execution loop  
**Lines:** 453  
**Purpose:** Orchestrates agent-driven pipeline execution with OpenAI integration  
**Key Features:**
- OpenAI client wrapper (`OpenAIClientWrapper`)
- Real LLM decision making via `_call_planner()`
- Context building from previous node outputs
- Guardrail enforcement
- Decision and execution tracking
- Proper error handling with logging

#### `agent_integration/llm_planner.py` ⭐
**Status:** ✅ ACTIVE - LLM decision making  
**Lines:** 1013  
**Purpose:** Structured LLM prompting and decision parsing  
**Key Classes:**
- `LLMPlanner`: Main planner class
- `SafePromptTemplate`: Safe prompt construction
- `OutputParser`: Parse and validate LLM responses
- `PlannerDecision`: Structured decision output

#### `demo_agentic_run.py` ⭐
**Status:** ✅ ACTIVE - Production demo script  
**Lines:** 751  
**Purpose:** Complete end-to-end demo of the agent system  
**Creates:**
- 5-node customer risk assessment pipeline
- Agent profile with LLM config
- Tool definitions and mappings
- Business conditions
- Full execution with OpenAI

### Legacy Files (Kept for Reference)

#### `agent_integration/execution_loop.py`
**Status:** ⚠️ LEGACY - Superseded by runtime/execution_loop.py  
**Lines:** 911  
**Purpose:** Original execution loop implementation  
**Note:** Still contains useful patterns and documentation

#### `agent_integration/runtime_spec_builder.py`
**Status:** ⚠️ LEGACY - Logic moved to runtime/spec_builder.py  
**Purpose:** Runtime specification generation  

### Example Files (Educational)

All `*_examples.py` files are educational references:
- `llm_planner_examples.py`
- `execution_loop_examples.py`
- `runtime_spec_examples.py`
- `safe_prompt_template_examples.py`

---

## Database Schema Overview

### Core App Tables

```sql
-- Pipelines
CREATE TABLE core_pipeline (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    input_schema JSON,
    created_by_id INTEGER,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- Nodes
CREATE TABLE core_node (
    id UUID PRIMARY KEY,
    pipeline_id UUID,
    name VARCHAR(255),
    description TEXT,
    code TEXT,
    order INTEGER,
    position_x INTEGER,
    position_y INTEGER,
    input_variable_mappings JSON,
    timeout_seconds INTEGER,
    created_at TIMESTAMP
);

-- Pipeline Executions
CREATE TABLE core_pipelineexecution (
    id UUID PRIMARY KEY,
    pipeline_id UUID,
    started_by_id INTEGER,
    status VARCHAR(20),
    context_data JSON,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Node Executions
CREATE TABLE core_nodeexecution (
    id UUID PRIMARY KEY,
    pipeline_execution_id UUID,
    node_id UUID,
    status VARCHAR(20),
    output_data JSON,
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

### Agent Integration Tables

```sql
-- Agent Runs
CREATE TABLE agent_integration_agentrun (
    id UUID PRIMARY KEY,
    pipeline_execution_id UUID,
    status VARCHAR(30),
    agent_config JSON,
    max_steps INTEGER,
    current_step INTEGER,
    human_intervention_required BOOLEAN,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Agent Decisions
CREATE TABLE agent_integration_agentdecision (
    id UUID PRIMARY KEY,
    agent_run_id UUID,
    step_number INTEGER,
    decision_type VARCHAR(50),
    prompt TEXT,
    llm_response TEXT,
    parsed_decision JSON,
    reasoning TEXT,
    guardrail_violations JSON,
    timestamp TIMESTAMP
);

-- Tool Executions
CREATE TABLE agent_integration_toolexecution (
    id UUID PRIMARY KEY,
    agent_run_id UUID,
    agent_decision_id UUID,
    node_execution_id UUID,
    status VARCHAR(20),
    result_summary TEXT,
    queued_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- Agent Profiles (Control Plane)
CREATE TABLE agent_integration_agentprofile (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    description TEXT,
    status VARCHAR(20),
    llm_config JSON,
    max_steps INTEGER,
    require_human_approval BOOLEAN,
    guardrail_config JSON
);

-- Tool Definitions
CREATE TABLE agent_integration_tooldefinition (
    id UUID PRIMARY KEY,
    name VARCHAR(255),
    executor_type VARCHAR(50),
    pipeline_id UUID,
    node_name VARCHAR(255),
    is_enabled BOOLEAN
);

-- Agent Tool Mappings
CREATE TABLE agent_integration_agenttoolmapping (
    id UUID PRIMARY KEY,
    agent_id UUID,
    tool_id UUID,
    is_allowed BOOLEAN,
    max_calls INTEGER,
    priority INTEGER
);
```

---

## URL Structure

```
# Root URLs
/                                       → Pipeline list (core.views.PipelineListView)
/create/                                → Create pipeline
/<uuid>/                                → Pipeline detail
/<uuid>/execute/                        → Execute pipeline manually

# API Endpoints
/api/pipelines/                         → List pipelines (JSON)

# Agent Dashboard
/agent/dashboard/                       → Agent run list
/agent/runs/<uuid>/detail/              → Agent run detail with timeline
/agent/runs/<uuid>/graph/               → Graph visualization
/agent/runs/<uuid>/debug/               → Debug context view
/agent/pipelines/<uuid>/start/          → Start agent run (POST)
/agent/runs/<uuid>/resume/              → Resume from human intervention
/agent/runs/<uuid>/abort/               → Abort running execution

# Control Plane
/agent/control-plane/                   → Control plane dashboard
/agent/control-plane/agents/            → Agent profile list
/agent/control-plane/agents/api/        → Agent list API (JSON)
/agent/control-plane/agents/create/     → Create agent
/agent/control-plane/agents/<uuid>/     → Agent detail
/agent/control-plane/tools/             → Tool definition list
/agent/control-plane/conditions/        → Business condition list

# API (Legacy/Reference)
/agent/api/runs/<uuid>/                 → Agent run status (JSON)
/agent/api/runs/<uuid>/decisions/       → Agent decisions list
```

---

## Configuration Files

### `pipeline/settings.py`
**Key Settings:**
```python
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    # ...
    'core',                    # Core pipeline app
    'agent_integration',       # Agent orchestration
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Artifact storage
ARTIFACTS_DIR = BASE_DIR / 'artifacts'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'agent_integration': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}
```

### Environment Variables
```bash
# Required
export OPENAI_API_KEY="sk-..."

# Optional
export DJANGO_SECRET_KEY="..."
export DEBUG=True
```

---

## Data Flow Diagram

```
┌─────────────┐
│   Browser   │
└──────┬──────┘
       │ HTTP POST /agent/pipelines/<id>/start/
       ↓
┌─────────────────────────────────────────────┐
│  ui_views.start_agent_run_ui()             │
│  • Parse config (model, temperature, etc.)  │
│  • Create PipelineExecution                 │
│  • Call start_agent_execution()             │
└──────┬──────────────────────────────────────┘
       │
       ↓
┌─────────────────────────────────────────────┐
│  runtime/execution_loop.py                  │
│  AgentExecutionLoop.__init__()              │
│  • Create AgentRun                          │
│  • Build RuntimeSpec                        │
│  • Initialize GuardrailEngine               │
│  • Initialize ToolRegistry                  │
└──────┬──────────────────────────────────────┘
       │
       ↓ execute()
┌─────────────────────────────────────────────┐
│  Main Loop:                                 │
│  while not is_complete():                   │
│    1. Get available nodes from guardrails   │
│    2. Call _call_planner(available_nodes)   │
│    3. Validate with guardrails              │
│    4. Execute tool                          │
│    5. Update context                        │
└──────┬──────────────────────────────────────┘
       │
       ↓ _call_planner()
┌─────────────────────────────────────────────┐
│  LLM Decision Making:                       │
│  1. Create OpenAIClientWrapper              │
│  2. Initialize LLMPlanner                   │
│  3. Build runtime_spec, execution_history   │
│  4. Call planner.plan_next_action()         │
│     → Makes OpenAI API call                 │
│     → Parses JSON response                  │
│  5. Return (tool_id, reasoning)             │
└──────┬──────────────────────────────────────┘
       │
       ↓ _execute_tool()
┌─────────────────────────────────────────────┐
│  Tool Execution:                            │
│  1. Build context from previous outputs     │
│  2. Get NodeToolExecutor                    │
│  3. Execute node code                       │
│  4. Save outputs as artifacts               │
│  5. Update guardrail state                  │
└──────┬──────────────────────────────────────┘
       │
       ↓ Complete
┌─────────────────────────────────────────────┐
│  Finalization:                              │
│  • Mark AgentRun as completed               │
│  • Calculate total cost                     │
│  • Return result summary                    │
└─────────────────────────────────────────────┘
```

---

## File Size Statistics

```
File                                          Lines    Size
────────────────────────────────────────────────────────────
agent_integration/llm_planner.py              1013    54 KB
agent_integration/execution_loop.py            911    48 KB
core/views.py                                  786    42 KB
demo_agentic_run.py                            751    40 KB
agent_integration/runtime/execution_loop.py    453    24 KB
agent_integration/control_plane_views.py       556    30 KB
agent_integration/ui_views.py                  411    22 KB
SYSTEM_DOCUMENTATION.md                        850    60 KB
```

---

## Maintenance Notes

### Regular Tasks
- [ ] Review and update CHANGELOG.md with each release
- [ ] Keep TODO.md prioritized and current
- [ ] Update SYSTEM_DOCUMENTATION.md when features change
- [ ] Run tests before committing: `python manage.py test`
- [ ] Check for security updates: `pip list --outdated`

### Before Production Deployment
- [ ] Set DEBUG=False
- [ ] Configure proper SECRET_KEY
- [ ] Set up PostgreSQL (replace SQLite)
- [ ] Configure static files serving
- [ ] Set up Celery for async execution
- [ ] Enable HTTPS
- [ ] Set up monitoring (Sentry, etc.)
- [ ] Configure backup strategy

### Code Review Checklist
- [ ] All TODOs addressed or documented
- [ ] No debug print statements (use logging)
- [ ] Error handling implemented
- [ ] Tests added for new features
- [ ] Documentation updated
- [ ] Security implications considered

---

**Last Updated:** January 4, 2026  
**Maintainer:** System Architect  
**Status:** Production Ready with Known TODOs
