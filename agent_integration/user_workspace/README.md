# User Agent Workspace

Safe loading and validation system for user-written agent code using the Warpdrive Agent SDK.

## Overview

The User Agent Workspace system allows users to write custom agent logic in isolated workspaces while maintaining strict security boundaries. User code is **UNTRUSTED** and all operations are validated before execution.

## Workspace Structure

Each user workspace must contain:

```
my_agent_workspace/
├── agent.py          # User planner implementation (REQUIRED)
├── agent.yaml        # Agent configuration (REQUIRED)
└── requirements.txt  # Optional dependencies (restricted)
```

### agent.py

User planner implementation inheriting from `warpdrive_agent_sdk.Planner`:

```python
from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)

class MyPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        # Your decision logic here
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id="my_tool",
            reasoning="Why this tool"
        )
```

### agent.yaml

Agent configuration and metadata:

```yaml
name: "My Agent"
objective: "What the agent achieves"
description: "Detailed description"

allowed_tools:
  - tool1
  - tool2

config:
  model: "gpt-4o-mini"
  temperature: 0.3
  max_steps: 100
  enable_human_intervention: true

constraints:
  max_execution_time_seconds: 300
  max_cost_usd: 1.0
```

## Security Model

### What Users CAN Do

✅ **Allowed Imports:**
- `warpdrive_agent_sdk` (all components)
- Standard library: `json`, `math`, `datetime`, `typing`, `collections`, `re`, etc.
- Scientific: `numpy`, `pandas` (read-only operations)

✅ **Allowed Operations:**
- Implement custom planner logic
- Process planner input data
- Return PlannerDecision objects
- Use pure computation (math, logic)

### What Users CANNOT Do

❌ **Forbidden Imports:**
- System access: `os`, `sys`, `subprocess`, `shutil`
- Network access: `socket`, `urllib`, `requests`, `http`
- File I/O: `io`, `open`, `tempfile`
- Code execution: `exec`, `eval`, `compile`, `importlib`
- Database: `sqlite3`, `psycopg2`, `sqlalchemy`, `django.db`
- Threading: `threading`, `multiprocessing`, `asyncio`
- Platform internals: `core`, `agent_integration`

❌ **Forbidden Operations:**
- Execute arbitrary code (`eval`, `exec`)
- Access filesystem
- Make network calls
- Access database
- Spawn processes
- Mutate runtime context
- Control execution loop

### Validation Process

1. **File Size Check**: Max 1MB per file
2. **AST Inspection**: Parse without executing
3. **Import Validation**: Check against forbidden list
4. **Planner Validation**: Verify implementation
5. **Config Validation**: Validate YAML schema
6. **Safe Import**: Load only if all checks pass

## Loading a Workspace

```python
from agent_integration.user_workspace import load_user_workspace

# Load workspace
workspace = load_user_workspace('/path/to/workspace')

# Access validated components
planner_class = workspace.planner_class
agent_config = workspace.agent_config
agent_definition = workspace.agent_definition

# Instantiate planner
planner = planner_class()

# Use in execution
decision = await planner.plan_next_action(planner_input)
```

## Validation Errors

### SecurityViolation

Raised when user code violates security constraints:

```python
from agent_integration.user_workspace import SecurityViolation

try:
    workspace = load_user_workspace(path)
except SecurityViolation as e:
    print(f"Security violation: {e}")
```

Common causes:
- Forbidden imports (`os`, `subprocess`, etc.)
- Use of `eval()`, `exec()`, `__import__()`
- Too many imports (> 50)

### InvalidPlannerError

Raised when planner implementation is invalid:

```python
from agent_integration.user_workspace import InvalidPlannerError

try:
    workspace = load_user_workspace(path)
except InvalidPlannerError as e:
    print(f"Invalid planner: {e}")
```

Common causes:
- No `Planner` subclass found
- Multiple `Planner` subclasses
- Missing `plan_next_action()` method
- Overriding forbidden methods (`__init__`, `__getattr__`, etc.)

### InvalidConfigError

Raised when `agent.yaml` is invalid:

```python
from agent_integration.user_workspace import InvalidConfigError

try:
    workspace = load_user_workspace(path)
except InvalidConfigError as e:
    print(f"Invalid config: {e}")
```

Common causes:
- Missing required fields (`name`, `objective`)
- Invalid YAML syntax
- Invalid parameter values (e.g., `temperature > 1.0`)

## Examples

See `examples/` directory:

- **`priority_planner/`**: Priority-based execution
- **`conditional_planner/`**: Conditional branching
- **`invalid_security/`**: Security violations (for testing)

### Priority Planner Example

Execute tools based on priority metadata:

```python
# agent.py
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision, PlannerDecisionType

class PriorityPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        
        # Find highest priority tool
        executable = [
            (t.get('metadata', {}).get('priority', 100), t)
            for t in tools
            if t['tool_id'] not in executed
        ]
        
        if not executable:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="All tools executed"
            )
        
        executable.sort(key=lambda x: x[0])
        priority, tool = executable[0]
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=tool['tool_id'],
            reasoning=f"Priority {priority}"
        )
```

### Conditional Planner Example

Branch based on execution results:

```python
# agent.py
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision, PlannerDecisionType

class ConditionalPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        executed = set(planner_input.get_executed_tools())
        history = planner_input.execution_history
        
        # Always validate first
        if 'validate' not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='validate',
                reasoning="Start with validation"
            )
        
        # Check validation result
        for execution in history:
            if execution.get('tool_id') == 'validate':
                if not execution.get('success'):
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.REQUEST_HUMAN,
                        human_message="Validation failed",
                        reasoning="Need human review"
                    )
        
        # Continue with processing...
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id='process',
            reasoning="Validation passed"
        )
```

## Best Practices

### ✅ DO

- Use SDK imports only
- Keep planners stateless
- Use `planner_input` for state
- Return valid `PlannerDecision` objects
- Add clear reasoning messages
- Handle all edge cases
- Test with example data

### ❌ DON'T

- Import forbidden modules
- Store state in planner instance
- Use `eval()`, `exec()`, or dynamic code
- Access filesystem or network
- Raise exceptions (return `PlannerDecision` with `FAIL` instead)
- Override forbidden methods
- Execute tools directly

## Testing

```python
# Test your workspace
from agent_integration.user_workspace import load_user_workspace

def test_my_workspace():
    workspace = load_user_workspace('./my_workspace')
    
    # Validate planner loaded
    assert workspace.planner_class_name == 'MyPlanner'
    
    # Validate config
    assert workspace.agent_definition.name == 'My Agent'
    
    # Test planner instantiation
    planner = workspace.planner_class()
    
    print("✅ Workspace valid!")

if __name__ == '__main__':
    test_my_workspace()
```

## Integration with Platform

The platform uses loaded workspaces like this:

```python
# Platform code
workspace = load_user_workspace(user_workspace_path)

# Create agent run with user's planner
planner = workspace.planner_class()
agent_config = workspace.agent_config

# Execute with platform control
execution_loop = AgentExecutionLoop(
    pipeline_execution=execution,
    planner=planner,
    agent_config=agent_config
)

result = execution_loop.execute()
```

**Key Points:**
- User planner is instantiated by platform
- Only `plan_next_action()` is called
- All execution happens through platform
- User cannot bypass guardrails
- Results are audited and logged

## Troubleshooting

### "Forbidden import" Error

**Problem:** Your code imports a forbidden module.

**Solution:** Use only allowed imports from SDK and approved stdlib.

```python
# ❌ Wrong
import os

# ✅ Right
import json
from warpdrive_agent_sdk import Planner
```

### "No Planner subclass found"

**Problem:** No class inherits from `Planner`.

**Solution:** Define a class that inherits from `Planner`:

```python
# ❌ Wrong
class MyClass:
    pass

# ✅ Right
class MyPlanner(Planner):
    async def plan_next_action(self, planner_input):
        ...
```

### "Multiple Planner subclasses"

**Problem:** More than one class inherits from `Planner`.

**Solution:** Define only ONE planner class per workspace.

### "Must implement 'plan_next_action()'"

**Problem:** Your planner doesn't implement the required method.

**Solution:** Add the method:

```python
class MyPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="Done"
        )
```

## Security Audit

All workspace loading is logged for security audit:

```
2026-01-04 15:30:00 INFO Loading workspace from /path/to/workspace
2026-01-04 15:30:00 INFO Validating imports...
2026-01-04 15:30:00 INFO Validating planner class...
2026-01-04 15:30:00 INFO Validating configuration...
2026-01-04 15:30:01 INFO ✅ Workspace loaded successfully: My Agent
```

Violations are logged with full details:

```
2026-01-04 15:30:00 ERROR Security violation in /path/to/workspace
2026-01-04 15:30:00 ERROR   - Forbidden import: 'os' at line 9
2026-01-04 15:30:00 ERROR   - Forbidden function call: 'eval' at line 15
```

## API Reference

### load_user_workspace(path)

Main entry point for loading workspaces.

**Parameters:**
- `path` (str | Path): Path to workspace directory

**Returns:**
- `LoadedWorkspace`: Validated workspace with planner and config

**Raises:**
- `WorkspaceValidationError`: General validation error
- `SecurityViolation`: Security constraint violated
- `InvalidPlannerError`: Planner implementation invalid
- `InvalidConfigError`: Configuration invalid

### LoadedWorkspace

Result of loading a workspace.

**Attributes:**
- `workspace_path` (Path): Workspace directory path
- `planner_class` (Type[Planner]): Validated planner class
- `planner_class_name` (str): Name of planner class
- `agent_config` (AgentConfig): Agent runtime configuration
- `agent_definition` (AgentDefinition): Complete agent definition

## Version

Current version: 1.0.0

Compatible with Warpdrive Agent SDK 1.0.0+
