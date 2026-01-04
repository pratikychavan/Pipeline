# Runtime Spec Builder

Materializes Pipeline definitions into immutable Agent Runtime Specifications.

## Purpose

This module provides **READ-ONLY transformation** from Pipeline/Node definitions into JSON-serializable runtime specs that can be safely passed to agent runners without requiring Django ORM access.

## What It Does

✅ **Does:**
- Reads Pipeline and Node definitions
- Reads Control Plane configuration (AgentProfile, Conditions, Mappings)
- Produces JSON-serializable spec
- Computes checksum for immutability verification
- Stores spec in RuntimeSpec model
- Validates spec structure

❌ **Does NOT:**
- Store executable code in spec
- Include LLM prompts or model configuration
- Include runtime state (status, current_step, etc.)
- Execute any code
- Modify pipelines or nodes

## Runtime Spec Structure

```json
{
  "version": "1.0",
  "created_at": "2026-01-04T12:00:00Z",
  
  "pipeline": {
    "id": "uuid",
    "name": "Pipeline Name",
    "description": "...",
    "is_active": true,
    "global_arguments": ["arg1", "arg2"]
  },
  
  "available_tools": [
    {
      "tool_id": "node-uuid",
      "tool_name": "node_name",
      "tool_type": "pipeline_node",
      "description": "What this tool does",
      "order": 1,
      "input_variables": ["input1", "input2"],
      "input_mappings": {
        "input1": {
          "node_id": "source-node-uuid",
          "source_variable": "output_var"
        }
      },
      "position": {"x": 100, "y": 200},
      "agent_constraints": {
        "is_allowed": true,
        "max_calls": 10,
        "priority": 5,
        "prerequisites": ["condition_met"]
      }
    }
  ],
  
  "execution_constraints": {
    "dag": {
      "nodes": ["node-uuid-1", "node-uuid-2"],
      "dependencies": {
        "node-uuid-1": {
          "depends_on": [],
          "required_for": ["node-uuid-2"]
        },
        "node-uuid-2": {
          "depends_on": ["node-uuid-1"],
          "required_for": []
        }
      }
    },
    "max_steps": 100,
    "max_execution_time_seconds": 300,
    "max_cost_usd": 50.0,
    "allow_parallel_execution": false
  },
  
  "business_conditions": [
    {
      "condition_id": "uuid",
      "condition_name": "budget_check",
      "condition_type": "threshold",
      "version": "1.0",
      "is_active": true,
      "config": {"threshold": 100},
      "evaluation_point": "before_execution",
      "on_true_action": "proceed",
      "on_false_action": "abort",
      "priority": 100,
      "max_evaluations": 1,
      "parameters": {}
    }
  ],
  
  "agent_configuration": {
    "agent_profile_id": "uuid",
    "agent_name": "Agent Name",
    "max_steps": 50,
    "retry_policy": {
      "max_retries": 3,
      "backoff_multiplier": 2,
      "initial_delay_seconds": 1
    },
    "guardrails": {
      "max_cost_usd": 10.0,
      "max_execution_time_seconds": 300,
      "require_human_approval_for": ["external_api_calls"]
    }
  },
  
  "global_context": {
    "pipeline_id": "uuid",
    "pipeline_name": "Pipeline Name",
    "global_arguments": ["arg1", "arg2"]
  }
}
```

## Key Features

### 1. Immutability

- Checksum computed using SHA256
- Tampering detectable via `verify_spec_integrity()`
- Spec data stored as JSON (no references to live objects)

### 2. No Executable Code

- Node `code` field deliberately NOT included
- Only tool metadata (name, description, inputs)
- Agent runner must use separate execution mechanism

### 3. No Sensitive Configuration

- LLM model config NOT included
- API keys NOT included
- Only execution constraints and policies

### 4. Complete Dependency Graph

- All node dependencies extracted from `input_variable_mappings`
- Both forward (depends_on) and reverse (required_for) dependencies
- Suitable for DAG validation and execution planning

## Usage

### Basic Spec Building

```python
from agent_integration.runtime_spec_builder import RuntimeSpecBuilder

# Build spec from pipeline
builder = RuntimeSpecBuilder(pipeline)
spec = builder.build()

# Validate
is_valid, error = builder.validate_spec(spec)

# Compute checksum
checksum = builder.compute_checksum(spec)

# Export to JSON
json_str = builder.to_json()
```

### With Agent Profile

```python
from agent_integration.runtime_spec_builder import RuntimeSpecBuilder

# Include agent configuration
builder = RuntimeSpecBuilder(pipeline, agent_profile)
spec = builder.build()

# Spec now includes:
# - Agent max_steps
# - Retry policy
# - Guardrails
# - Business conditions
# - Tool constraints
```

### Create and Store

```python
from agent_integration.runtime_spec_builder import RuntimeSpecService

# Create spec for agent run
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
    agent_run=agent_run,
    agent_profile=agent_profile,
)

# Retrieve later
runtime_spec = RuntimeSpecService.get_spec_for_agent_run(agent_run_id)

# Verify integrity
is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
```

### Preview Without Creating Run

```python
from agent_integration.runtime_spec_builder import RuntimeSpecService

# Preview what spec would look like
spec = RuntimeSpecService.preview_spec_for_pipeline(
    pipeline=pipeline,
    agent_profile=agent_profile,
)

# No AgentRun or RuntimeSpec created
```

## Integration with Agent Runner

The runtime spec provides everything an agent runner needs:

1. **Tool Discovery**: List of available tools (nodes) with metadata
2. **Execution Constraints**: DAG structure, max steps, timeouts
3. **Business Rules**: Conditions to evaluate at specific points
4. **Agent Policies**: Retry logic, guardrails, human approval triggers

Agent runner workflow:

```python
# 1. Get runtime spec
runtime_spec = RuntimeSpecService.get_spec_for_agent_run(agent_run_id)
spec = runtime_spec.spec_data

# 2. Verify integrity
assert RuntimeSpecService.verify_spec_integrity(runtime_spec)

# 3. Extract tools
tools = spec['available_tools']

# 4. Check constraints
max_steps = spec['execution_constraints']['max_steps']
dependencies = spec['execution_constraints']['dag']['dependencies']

# 5. Evaluate conditions
for condition in spec['business_conditions']:
    if condition['evaluation_point'] == 'before_execution':
        # Evaluate condition
        pass

# 6. Execute tools via NodeToolExecutor
from agent_integration.node_tools import get_node_tool

for tool_def in tools:
    tool = get_node_tool(tool_def['tool_id'])
    result = await tool.execute(...)
```

## Spec Validation

The spec validator checks:

1. **Required Keys**: All top-level keys present
2. **Version**: Spec version matches builder version
3. **Data Types**: Lists are lists, dicts are dicts
4. **No Executable Code**: No `exec()`, `eval()`, `__import__`, `compile()`
5. **JSON Serializable**: Can be converted to/from JSON

```python
builder = RuntimeSpecBuilder(pipeline)
spec = builder.build()

is_valid, error = builder.validate_spec(spec)
if not is_valid:
    print(f"Invalid spec: {error}")
```

## Checksum Verification

Detect tampering or corruption:

```python
# Create spec
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
original_checksum = runtime_spec.spec_checksum

# Later, verify integrity
is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)

if not is_valid:
    # Spec has been tampered with
    print("Spec integrity compromised!")
```

## Examples

See `runtime_spec_examples.py` for:

1. Basic spec building
2. Spec with agent profile
3. Creating and storing specs
4. Spec validation
5. JSON export
6. Dependency graph extraction

Run examples:
```bash
python manage.py shell < agent_integration/runtime_spec_examples.py
```

## Testing

Comprehensive test suite in `tests/test_runtime_spec.py`:

```bash
python manage.py test agent_integration.tests.test_runtime_spec
```

Tests cover:
- Basic spec building
- Agent profile integration
- Tool extraction
- Constraint building
- Condition binding
- Checksum computation
- Validation
- Immutability guarantees
- JSON serialization

## Design Decisions

### Why No Code in Spec?

**Security**: Code execution should happen through controlled execution backend, not by parsing spec.

**Portability**: Spec can be sent to remote agent runners without security concerns.

**Immutability**: Code changes would invalidate spec. Spec describes structure, not implementation.

### Why Checksum?

**Integrity**: Detect tampering or accidental corruption.

**Audit**: Verify spec used in execution matches original.

**Reproducibility**: Same pipeline + same config = same checksum.

### Why No LLM Config?

**Separation**: Spec describes WHAT to execute, not HOW to reason about it.

**Flexibility**: Different agent runners can use different LLMs with same spec.

**Security**: LLM API keys should not be in spec.

### Why Include Business Conditions?

**Governance**: Business rules are part of execution specification.

**Declarative**: Conditions described, not implemented.

**Auditable**: Shows what conditions applied during execution.

## Future Enhancements

1. **Spec Versioning**: Support multiple spec versions
2. **Partial Specs**: Support for sub-pipeline specs
3. **Spec Diff**: Compare specs to show what changed
4. **Spec Templates**: Reusable spec patterns
5. **Spec Optimization**: Remove unused tools, simplify constraints
6. **Spec Visualization**: Generate diagrams from spec

## Troubleshooting

### Spec Missing Tools

Check that pipeline has nodes:
```python
pipeline.nodes.count()  # Should be > 0
```

### Spec Missing Conditions

Check that agent profile has bindings:
```python
AgentConditionBinding.objects.filter(agent=agent_profile).count()
```

### Checksum Mismatch

Spec data was modified after creation:
```python
# Reload from database
runtime_spec.refresh_from_db()
is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
```

### Validation Fails

Check error message:
```python
is_valid, error = builder.validate_spec(spec)
if not is_valid:
    print(f"Validation error: {error}")
```
