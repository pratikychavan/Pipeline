# User Workspace Quick Start

## Create Your First Agent

### 1. Create Workspace Directory

```bash
mkdir my_agent
cd my_agent
```

### 2. Create agent.py

```python
from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)

class MyPlanner(Planner):
    """My custom planner."""
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        # Get available tools
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        
        # Find first unexecuted tool
        for tool in tools:
            if tool['tool_id'] not in executed:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=tool['tool_id'],
                    reasoning=f"Executing {tool['name']}"
                )
        
        # All done
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed"
        )
```

### 3. Create agent.yaml

```yaml
name: "My First Agent"
objective: "Execute pipeline tools sequentially"
description: "A simple agent for learning"

allowed_tools:
  - my_tool_1
  - my_tool_2

config:
  model: "gpt-4o-mini"
  temperature: 0.3
  max_steps: 20
```

### 4. Test Your Workspace

```python
from agent_integration.user_workspace import load_user_workspace

workspace = load_user_workspace('./my_agent')
print(f"✅ Loaded: {workspace.agent_definition.name}")
```

## Common Patterns

### Pattern 1: Sequential Execution

Execute tools in order:

```python
async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
    tools = planner_input.get_available_tools()
    executed = set(planner_input.get_executed_tools())
    
    for tool in tools:
        if tool['tool_id'] not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=tool['tool_id']
            )
    
    return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE)
```

### Pattern 2: Conditional Execution

Execute based on previous results:

```python
async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
    executed = set(planner_input.get_executed_tools())
    
    # Always validate first
    if 'validate' not in executed:
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id='validate'
        )
    
    # Check if validation passed
    for execution in planner_input.execution_history:
        if execution['tool_id'] == 'validate':
            if not execution.get('success'):
                return PlannerDecision(
                    decision_type=PlannerDecisionType.FAIL,
                    reasoning="Validation failed"
                )
    
    # Continue with processing
    if 'process' not in executed:
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id='process'
        )
    
    return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE)
```

### Pattern 3: Priority-Based Execution

Execute highest priority first:

```python
async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
    tools = planner_input.get_available_tools()
    executed = set(planner_input.get_executed_tools())
    
    # Get unexecuted tools with priorities
    remaining = [
        (tool.get('metadata', {}).get('priority', 100), tool)
        for tool in tools
        if tool['tool_id'] not in executed
    ]
    
    if not remaining:
        return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE)
    
    # Sort by priority (lower = higher priority)
    remaining.sort(key=lambda x: x[0])
    next_tool = remaining[0][1]
    
    return PlannerDecision(
        decision_type=PlannerDecisionType.EXECUTE_TOOL,
        tool_id=next_tool['tool_id']
    )
```

### Pattern 4: Human-in-the-Loop

Request human approval for critical operations:

```python
async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
    tools = planner_input.get_available_tools()
    executed = set(planner_input.get_executed_tools())
    
    for tool in tools:
        if tool['tool_id'] in executed:
            continue
        
        # Check if tool requires approval
        if tool.get('metadata', {}).get('requires_approval'):
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                tool_id=tool['tool_id'],
                human_message=f"Approve execution of {tool['name']}?"
            )
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=tool['tool_id']
        )
    
    return PlannerDecision(decision_type=PlannerDecisionType.COMPLETE)
```

## Allowed Imports

```python
# ✅ Always allowed
from warpdrive_agent_sdk import *

# ✅ Standard library
import json
import math
import datetime
from typing import Dict, List
from collections import defaultdict
import re

# ✅ Scientific (read-only)
import numpy as np
import pandas as pd

# ❌ Never allowed
import os          # Forbidden
import subprocess  # Forbidden
import socket      # Forbidden
exec()            # Forbidden
eval()            # Forbidden
```

## Quick Debugging

### Check Workspace Structure

```python
from pathlib import Path

workspace = Path('./my_agent')
print(f"agent.py exists: {(workspace / 'agent.py').exists()}")
print(f"agent.yaml exists: {(workspace / 'agent.yaml').exists()}")
```

### Validate Imports

```python
import ast

with open('./my_agent/agent.py') as f:
    tree = ast.parse(f.read())

imports = [
    node.names[0].name
    for node in ast.walk(tree)
    if isinstance(node, ast.Import)
]
print(f"Imports: {imports}")
```

### Test Planner Logic

```python
from warpdrive_agent_sdk import PlannerInput
import asyncio

async def test():
    workspace = load_user_workspace('./my_agent')
    planner = workspace.planner_class()
    
    # Create test input
    input_data = PlannerInput(
        runtime_spec={'available_tools': [
            {'tool_id': 'test', 'name': 'Test Tool'}
        ]},
        execution_history=[],
        current_state={},
        step_number=0
    )
    
    # Get decision
    decision = await planner.plan_next_action(input_data)
    print(f"Decision: {decision.decision_type.value}")
    print(f"Tool: {decision.tool_id}")

asyncio.run(test())
```

## Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `Forbidden import: 'os'` | Importing forbidden module | Use only allowed imports |
| `No Planner subclass found` | No class inherits from Planner | Add `class MyPlanner(Planner):` |
| `Multiple Planner subclasses` | More than one Planner class | Keep only one planner |
| `Must implement 'plan_next_action()'` | Method missing | Add `async def plan_next_action(...)` |
| `Required field missing: 'name'` | agent.yaml incomplete | Add `name:` field |
| `Temperature must be 0.0-1.0` | Invalid config value | Fix temperature range |

## Next Steps

1. **Review Examples**: Check `examples/` for working patterns
2. **Read SDK Docs**: See `warpdrive_agent_sdk/README.md`
3. **Test Your Planner**: Use mock inputs to verify logic
4. **Deploy**: Platform will load your workspace safely

## Support

- **Documentation**: `/agent_integration/user_workspace/README.md`
- **SDK Reference**: `/warpdrive_agent_sdk/README.md`
- **Examples**: `/agent_integration/user_workspace/examples/`
