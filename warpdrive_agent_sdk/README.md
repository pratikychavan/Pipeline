# Warpdrive Agent SDK

A clean, user-facing SDK for building AI agents that integrate with the Warpdrive platform.

## Overview

The Warpdrive Agent SDK provides everything you need to **define** agents that run on the Warpdrive platform:

- **Planner Interface**: Implement custom decision logic for your agents
- **Agent Definitions**: Declare what your agent does and how it operates
- **Tool Specifications**: Define what tools your agent can use
- **Guardrail Configuration**: Set safety limits and policies

## ⚠️ Critical Constraints

**This SDK is for DEFINING agents, not EXECUTING them.**

- ✅ You CAN: Define agents, implement planners, configure guardrails
- ❌ You CANNOT: Execute tools directly, access pipeline internals, bypass guardrails
- ❌ You CANNOT: Access raw data, mutate runtime state, control execution loop

All execution happens through the platform, which enforces safety constraints.

## Installation

```bash
# SDK is included with Warpdrive platform
# No separate installation needed

# For development, install in editable mode
cd warpdrive_agent_sdk
pip install -e .
```

## Quick Start

### 1. Define an Agent

```python
from warpdrive_agent_sdk import AgentDefinition, AgentConfig

agent = AgentDefinition(
    name="Data Validation Agent",
    objective="Validate and clean incoming data",
    description="Checks data quality and performs cleaning",
    allowed_tools=["validate_schema", "check_quality", "clean_data"],
    config=AgentConfig(
        model='gpt-4o-mini',
        temperature=0.3,
        max_steps=20
    )
)
```

### 2. Implement a Custom Planner

```python
from warpdrive_agent_sdk import Planner, PlannerDecision, PlannerDecisionType, PlannerInput

class MyPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        # Get available tools
        tools = planner_input.get_available_tools()
        executed = planner_input.get_executed_tools()
        
        # Find next tool to execute
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

### 3. Configure Guardrails

```python
from warpdrive_agent_sdk import GuardrailConfig

guardrails = GuardrailConfig(
    max_execution_time_seconds=300,
    max_cost_usd=1.0,
    require_approval_for_high_risk=True,
    forbidden_tool_patterns=['.*delete.*', '.*drop.*']
)
```

### 4. Use Provided Planners

```python
from warpdrive_agent_sdk import LLMPlanner, DeterministicPlanner

# For intelligent planning
llm_planner = LLMPlanner(
    llm_client=my_llm_client,  # Implement LLMClient protocol
    model='gpt-4o-mini',
    temperature=0.3
)

# For simple linear workflows
deterministic_planner = DeterministicPlanner()
```

## Core Concepts

### Planner

A **Planner** decides which tool to execute next based on current state.

**Key Points:**
- Planners are **STATELESS** (no memory between calls)
- Planners are **BOUNDED** (one call per decision)
- Planners return **STRUCTURED** decisions
- Planners CANNOT execute tools directly

### Agent Definition

An **AgentDefinition** describes what your agent does:

```python
AgentDefinition(
    name="My Agent",
    objective="What the agent achieves",
    allowed_tools=["tool1", "tool2"],
    config=AgentConfig(...)
)
```

### Tool Specification

A **ToolSpec** declares what a tool does (not HOW to execute it):

```python
from warpdrive_agent_sdk import ToolSpec, ToolParameter, ToolParameterType

tool = ToolSpec(
    tool_id="validate_data",
    name="Data Validation",
    description="Validates data against schema",
    parameters=[
        ToolParameter(
            name="threshold",
            type=ToolParameterType.FLOAT,
            required=True,
            constraints={'min': 0.0, 'max': 1.0}
        )
    ]
)
```

### Guardrail Configuration

**GuardrailConfig** sets safety limits:

```python
GuardrailConfig(
    max_execution_time_seconds=300,  # 5 minutes
    max_cost_usd=1.0,  # $1 maximum
    require_approval_for_high_risk=True,
    max_retries_per_tool=3
)
```

## Decision Types

Your planner can make four types of decisions:

1. **EXECUTE_TOOL**: Execute a specific tool
   ```python
   PlannerDecision(
       decision_type=PlannerDecisionType.EXECUTE_TOOL,
       tool_id="my_tool",
       tool_parameters={"param": "value"},
       reasoning="Why execute this tool"
   )
   ```

2. **COMPLETE**: Mark execution as successfully complete
   ```python
   PlannerDecision(
       decision_type=PlannerDecisionType.COMPLETE,
       reasoning="All work done"
   )
   ```

3. **REQUEST_HUMAN**: Pause and request human intervention
   ```python
   PlannerDecision(
       decision_type=PlannerDecisionType.REQUEST_HUMAN,
       human_message="Please review the data",
       reasoning="Data looks suspicious"
   )
   ```

4. **FAIL**: Mark execution as failed
   ```python
   PlannerDecision(
       decision_type=PlannerDecisionType.FAIL,
       reasoning="Cannot proceed due to error"
   )
   ```

## Safety Model

### What You Get (READ-ONLY)

- **Runtime Spec**: Available tools, constraints, conditions
- **Execution History**: What's been executed, results (summaries only)
- **Current State**: Variables, status (no raw data)

### What You CANNOT Do

- ❌ Execute tools directly
- ❌ Access pipeline internals
- ❌ Bypass guardrails
- ❌ Access raw data
- ❌ Mutate runtime state
- ❌ Control retry logic
- ❌ Control execution loop

### What the Platform Does

- ✅ Validates your decisions
- ✅ Enforces guardrails
- ✅ Executes tools safely
- ✅ Handles retries
- ✅ Records results
- ✅ Manages data access

## Examples

See `examples/` directory for:

- `simple_agent.py`: Basic agent definition
- `custom_planner.py`: Custom planner implementation
- `llm_planner_example.py`: LLM-based planning
- `guardrails_example.py`: Guardrail configuration
- `tool_spec_example.py`: Tool specification

## API Reference

### Interfaces

- `Planner`: Base class for planners
- `PlannerDecision`: Structured decision output
- `PlannerDecisionType`: Decision type enum
- `PlannerInput`: Input provided to planner (READ-ONLY)
- `PlannerFailure`: Failure representation

### Schemas

- `AgentDefinition`: Complete agent definition
- `AgentConfig`: Runtime configuration
- `RuntimeSpec`: Runtime specification (READ-ONLY)
- `ToolSpec`: Tool specification
- `ToolParameter`: Parameter specification
- `ToolResult`: Tool execution result (READ-ONLY)
- `GuardrailConfig`: Guardrail configuration
- `BusinessConditionSpec`: Business condition specification

### Planners

- `DeterministicPlanner`: Rule-based planner
- `LLMPlanner`: LLM-based planner
- `LLMClient`: Protocol for LLM clients

## Best Practices

### 1. Keep Planners Stateless

❌ **Don't do this:**
```python
class BadPlanner(Planner):
    def __init__(self):
        self.counter = 0  # State!
    
    async def plan_next_action(self, planner_input):
        self.counter += 1  # Mutating state!
        ...
```

✅ **Do this:**
```python
class GoodPlanner(Planner):
    async def plan_next_action(self, planner_input):
        # Use planner_input.step_number instead
        step = planner_input.step_number
        ...
```

### 2. Return Failures, Don't Raise Exceptions

❌ **Don't do this:**
```python
async def plan_next_action(self, planner_input):
    if error:
        raise Exception("Error!")  # Bad!
```

✅ **Do this:**
```python
async def plan_next_action(self, planner_input):
    if error:
        return PlannerDecision(
            decision_type=PlannerDecisionType.FAIL,
            reasoning="Error description"
        )
```

### 3. Validate Decisions

```python
decision = PlannerDecision(...)
decision.validate()  # Raises ValueError if invalid
return decision
```

### 4. Use Type Hints

```python
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision

class MyPlanner(Planner):
    async def plan_next_action(
        self,
        planner_input: PlannerInput
    ) -> PlannerDecision:
        ...
```

## Troubleshooting

### "Cannot access pipeline internals"

You're trying to do something forbidden. Remember: this SDK is for DEFINING agents, not EXECUTING them.

### "Guardrail violation"

The platform blocked your decision because it violated a guardrail. Check your guardrail configuration.

### "Invalid decision"

Your PlannerDecision is malformed. Call `decision.validate()` to get detailed error.

### "Tool not found"

You're trying to execute a tool that's not in the available_tools list. Check `planner_input.get_available_tools()`.

## Support

For issues, questions, or contributions:
- File an issue on GitHub
- Check platform documentation
- Contact platform team

## License

[License information]

## Version

Current version: 1.0.0
