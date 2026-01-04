# Runtime Spec Builder - Implementation Summary

## Task Completion

✅ **COMPLETED**: Materialize Pipelines into Agent Runtime Specs

## What Was Built

Created runtime spec materialization system with:

1. **runtime_spec_builder.py** (530 lines)
   - `RuntimeSpecBuilder`: Builds immutable specs from pipelines
   - `RuntimeSpecService`: Service layer for creating/managing specs
   - Checksum computation (SHA256)
   - Validation (structure, no code, JSON-serializable)
   - JSON export

2. **runtime_spec_examples.py** (380 lines)
   - 6 working examples
   - Basic spec building
   - Agent profile integration
   - Creating and storing
   - Validation
   - JSON export
   - Dependency graph extraction

3. **tests/test_runtime_spec.py** (450 lines)
   - RuntimeSpecBuilder tests
   - RuntimeSpecService tests
   - Immutability tests
   - 20+ test cases

4. **RUNTIME_SPEC_README.md** (500 lines)
   - Complete documentation
   - Spec structure
   - Usage examples
   - Integration patterns
   - Troubleshooting

## Runtime Spec Structure

```json
{
  "version": "1.0",
  "created_at": "ISO-8601 timestamp",
  
  "pipeline": {
    "id": "uuid",
    "name": "string",
    "description": "string",
    "global_arguments": ["array"]
  },
  
  "available_tools": [
    {
      "tool_id": "node-uuid",
      "tool_name": "string",
      "tool_type": "pipeline_node",
      "description": "string",
      "order": 1,
      "input_variables": ["array"],
      "input_mappings": {"object"},
      "position": {"x": 0, "y": 0},
      "agent_constraints": {
        "is_allowed": true,
        "max_calls": 10,
        "priority": 5
      }
    }
  ],
  
  "execution_constraints": {
    "dag": {
      "nodes": ["array"],
      "dependencies": {
        "node-uuid": {
          "depends_on": ["array"],
          "required_for": ["array"]
        }
      }
    },
    "max_steps": 100,
    "max_execution_time_seconds": 300,
    "max_cost_usd": 50.0
  },
  
  "business_conditions": [
    {
      "condition_id": "uuid",
      "condition_name": "string",
      "condition_type": "string",
      "config": {"object"},
      "evaluation_point": "string",
      "on_true_action": "string",
      "on_false_action": "string"
    }
  ],
  
  "agent_configuration": {
    "max_steps": 100,
    "retry_policy": {"object"},
    "guardrails": {"object"}
  },
  
  "global_context": {
    "pipeline_id": "uuid",
    "pipeline_name": "string",
    "global_arguments": ["array"]
  }
}
```

## Key Design Principles

### ✅ What We Did

1. **READ-ONLY Transformation**
   - Reads Pipeline/Node definitions
   - Reads Control Plane configuration
   - Produces immutable spec
   - No execution happens

2. **No Executable Code**
   - Node `code` field NOT included
   - Only tool metadata (name, description, inputs)
   - Agent runner uses NodeToolExecutor separately

3. **No LLM Prompts**
   - Model configuration NOT in spec
   - API keys NOT in spec
   - Only execution constraints and policies

4. **No Runtime State**
   - No status fields
   - No current_step
   - No execution_id
   - Pure structural description

5. **JSON-Serializable**
   - All values are primitives or nested structures
   - No Python objects
   - No references to Django models

6. **Immutable**
   - Checksum computed with SHA256
   - Tampering detectable
   - Stored as JSON blob

7. **Complete Dependency Graph**
   - Extracted from `input_variable_mappings`
   - Both forward and reverse dependencies
   - Suitable for DAG validation

### ❌ What We Did NOT Do

1. **Did NOT store code**
   - No `code` field in spec
   - No `exec()`, `eval()`, `compile()`
   - Only structural metadata

2. **Did NOT include prompts**
   - No system prompts
   - No user prompts
   - No LLM configuration

3. **Did NOT include runtime state**
   - No execution status
   - No current position
   - No runtime variables

4. **Did NOT make it executable**
   - Spec is description, not implementation
   - Execution happens via NodeToolExecutor
   - Spec is input to agent runner

## Integration Flow

```
Pipeline + AgentProfile
    ↓
RuntimeSpecBuilder.build()
    ├─ _build_pipeline_metadata()
    ├─ _build_tools()              ← From Nodes (no code)
    ├─ _build_constraints()        ← From input_mappings
    ├─ _build_conditions()         ← From AgentConditionBinding
    ├─ _build_agent_config()       ← From AgentProfile
    └─ _build_global_context()     ← From Pipeline
    ↓
Validate spec
    ↓
Compute checksum (SHA256)
    ↓
Store in RuntimeSpec model
    ↓
Pass to Agent Runner (no Django ORM needed)
```

## Usage Examples

### Basic Spec Building

```python
from agent_integration.runtime_spec_builder import RuntimeSpecBuilder

builder = RuntimeSpecBuilder(pipeline)
spec = builder.build()

# Validate
is_valid, error = builder.validate_spec(spec)

# Compute checksum
checksum = builder.compute_checksum(spec)

# Export JSON
json_str = builder.to_json()
```

### With Agent Profile

```python
builder = RuntimeSpecBuilder(pipeline, agent_profile)
spec = builder.build()

# Spec includes:
# - Agent max_steps
# - Retry policy from agent profile
# - Guardrails from agent profile
# - Business conditions bound to agent
# - Tool constraints from AgentToolMapping
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
runtime_spec = RuntimeSpecService.get_spec_for_agent_run(agent_run.id)

# Verify integrity
is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
```

### Preview Without Creating Run

```python
# Preview spec without creating AgentRun
spec = RuntimeSpecService.preview_spec_for_pipeline(
    pipeline=pipeline,
    agent_profile=agent_profile,
)

# No database records created
```

## Agent Runner Integration

Agent runner workflow:

```python
# 1. Get runtime spec
runtime_spec = RuntimeSpecService.get_spec_for_agent_run(agent_run_id)
spec = runtime_spec.spec_data

# 2. Verify integrity
assert RuntimeSpecService.verify_spec_integrity(runtime_spec)

# 3. Extract available tools
tools = spec['available_tools']
for tool_def in tools:
    print(f"Tool: {tool_def['tool_name']}")

# 4. Check constraints
max_steps = spec['execution_constraints']['max_steps']
dependencies = spec['execution_constraints']['dag']['dependencies']

# 5. Evaluate business conditions
for condition in spec['business_conditions']:
    if condition['evaluation_point'] == 'before_execution':
        # Evaluate condition using condition config
        pass

# 6. Execute tools via NodeToolExecutor
from agent_integration.node_tools import get_node_tool

tool = get_node_tool(tool_def['tool_id'])
result = await tool.execute(
    agent_run_id=agent_run.id,
    parameters={},
    context={},
)
```

## Immutability Guarantees

### Checksum Verification

```python
# Create spec
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
original_checksum = runtime_spec.spec_checksum

# Verify later
is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)

if not is_valid:
    print("Spec has been tampered with!")
```

### Deterministic Checksums

Same pipeline + same config → same checksum:

```python
builder1 = RuntimeSpecBuilder(pipeline, agent_profile)
spec1 = builder1.build()
checksum1 = builder1.compute_checksum(spec1)

builder2 = RuntimeSpecBuilder(pipeline, agent_profile)
spec2 = builder2.build()
checksum2 = builder2.compute_checksum(spec2)

assert checksum1 == checksum2  # Deterministic
```

## Validation

Spec validation checks:

1. **Required keys present**: version, pipeline, available_tools, etc.
2. **Version matches**: Spec version = builder version
3. **Correct types**: Lists are lists, dicts are dicts
4. **No executable code**: No `exec()`, `eval()`, `__import__`
5. **JSON serializable**: Can convert to/from JSON

```python
is_valid, error = builder.validate_spec(spec)
if not is_valid:
    print(f"Validation failed: {error}")
```

## Testing

Run examples:
```bash
python manage.py shell < agent_integration/runtime_spec_examples.py
```

Run tests:
```bash
python manage.py test agent_integration.tests.test_runtime_spec
```

Test coverage:
- Basic spec building (no agent profile)
- Spec with agent profile
- Tool extraction from nodes
- Constraint building from dependencies
- Condition extraction from bindings
- Checksum computation
- Validation
- Immutability verification
- JSON serialization
- Service methods

## Files Created

```
agent_integration/
├── runtime_spec_builder.py       530 lines   Core implementation
├── runtime_spec_examples.py      380 lines   6 usage examples
├── RUNTIME_SPEC_README.md        500 lines   Complete documentation
└── tests/
    └── test_runtime_spec.py      450 lines   20+ test cases

Total: ~1,860 lines
```

## Verification Results

✅ All imports successful  
✅ Spec building works  
✅ Agent profile integration works  
✅ Validation works  
✅ Checksum computation deterministic  
✅ No executable code in spec  
✅ JSON serializable  
✅ All required keys present  
✅ Service methods available  

## Design Rationale

### Why No Code?

**Security**: Code execution via controlled backend, not spec parsing.  
**Portability**: Spec can be sent to remote runners safely.  
**Immutability**: Code changes would invalidate spec.

### Why Checksum?

**Integrity**: Detect tampering or corruption.  
**Audit**: Verify spec used matches original.  
**Reproducibility**: Same inputs → same checksum.

### Why No LLM Config?

**Separation**: Spec describes WHAT, not HOW to reason.  
**Flexibility**: Different runners can use different LLMs.  
**Security**: API keys shouldn't be in spec.

### Why Include Conditions?

**Governance**: Business rules are part of spec.  
**Declarative**: Conditions described, not implemented.  
**Auditable**: Shows what rules applied.

## Next Steps

Runtime specs are now ready for agent runner integration:

1. Agent runner retrieves spec from RuntimeSpec
2. Agent runner verifies spec integrity
3. Agent runner extracts available tools
4. Agent runner respects execution constraints
5. Agent runner evaluates business conditions
6. Agent runner executes tools via NodeToolExecutor

Future enhancements:
- Spec versioning (support multiple versions)
- Spec diff (compare specs)
- Spec templates (reusable patterns)
- Spec optimization (remove unused tools)
- Spec visualization (generate diagrams)

## Summary

**Task Complete**: Every pipeline can now be materialized into an immutable, JSON-serializable runtime spec that:

- Contains no executable code
- Contains no LLM prompts
- Contains no runtime state
- Is fully JSON-serializable
- Is verifiable via checksum
- Includes complete dependency graph
- Includes business conditions
- Includes agent constraints
- Can be safely passed to agent runners
- Does not require Django ORM to use
