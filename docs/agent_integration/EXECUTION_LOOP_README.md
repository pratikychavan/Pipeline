# Agent Execution Loop

Complete documentation for the Agent Execution Loop system.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Components](#components)
4. [Usage](#usage)
5. [Planner Interface](#planner-interface)
6. [Guardrails](#guardrails)
7. [Conditions](#conditions)
8. [Human-in-the-Loop](#human-in-the-loop)
9. [Error Handling](#error-handling)
10. [Integration](#integration)
11. [Testing](#testing)
12. [Examples](#examples)

## Overview

The Agent Execution Loop is the control system for agent-driven pipeline execution. It orchestrates pipeline flow WITHOUT executing pipeline logic directly.

### What It Does

✅ **Controls pipeline flow** - Decides which nodes to execute and when  
✅ **Bounded iteration** - Always terminates (max_steps limit)  
✅ **Enforces graph constraints** - Respects DAG dependencies  
✅ **Validates decisions** - Guardrails check planner output  
✅ **Evaluates conditions** - Business rules at checkpoints  
✅ **Supports human approval** - Pause/resume workflows  
✅ **Handles errors** - Retry logic and error recovery  
✅ **Fully observable** - Records all decisions and executions  

### What It Does NOT Do

❌ **Execute nodes directly** - Uses NodeToolExecutor  
❌ **Allow infinite loops** - Bounded by max_steps  
❌ **Bypass graph constraints** - DAG always respected  
❌ **Mutate pipeline definitions** - Read-only on pipeline  

## Architecture

```
AgentRun
    ↓
RuntimeSpec (immutable)
    ↓
AgentExecutionLoop
    ├─ Planner (decides next action)
    │   ├─ LLM-based (future)
    │   └─ DeterministicPlanner (current)
    │
    ├─ Guardrails (validates decisions)
    │   ├─ Check tool allowed
    │   ├─ Check max calls
    │   ├─ Check dependencies
    │   └─ Record violations
    │
    ├─ ConditionEvaluator (business rules)
    │   ├─ before_execution
    │   ├─ after_tool_execution
    │   ├─ on_error
    │   └─ before_completion
    │
    └─ NodeToolExecutor (executes tools)
        ↓
    NodeExecution + ToolExecution
        ↓
    Update state, continue loop
```

## Components

### 1. AgentExecutionLoop

Main controller that runs the execution loop.

**Responsibilities:**
- Load runtime spec
- Iterate (bounded by max_steps)
- Call planner for decisions
- Validate with guardrails
- Execute tools
- Evaluate conditions
- Handle errors/retries
- Manage termination

**Key Methods:**
```python
async def initialize():
    """Load and verify runtime spec."""

async def run() -> LoopResult:
    """Run the execution loop."""
```

### 2. Planner

Abstract interface for planning next actions.

**Interface:**
```python
class Planner(ABC):
    @abstractmethod
    async def plan_next_action(
        self,
        runtime_spec: Dict[str, Any],
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> PlannerDecision:
        pass
```

**Implementations:**
- `DeterministicPlanner` - Rule-based fallback (current)
- `LLMPlanner` - LLM-based planning (future)

### 3. Guardrails

Validates planner decisions before execution.

**Checks:**
- Tool exists in spec
- Tool is allowed by agent
- Max calls not exceeded
- Dependencies satisfied
- No critical violations

**Violations:**
- `warning` - Logged but allowed
- `error` - Blocks execution
- `critical` - Terminates loop

### 4. ConditionEvaluator

Evaluates business conditions at checkpoints.

**Evaluation Points:**
- `before_execution` - Before loop starts
- `after_tool_execution` - After each tool
- `on_error` - When errors occur
- `before_completion` - Before loop ends

**Actions:**
- `continue` - Keep executing
- `pause` - Request human intervention
- `fail` - Terminate with error

### 5. AgentLoopRunner

High-level service for running loops.

**Methods:**
```python
async def start_loop(agent_run, planner=None) -> LoopResult:
    """Start new execution loop."""

async def resume_loop(agent_run) -> LoopResult:
    """Resume after human intervention."""
```

## Usage

### Basic Usage

```python
from agent_integration.execution_loop import AgentLoopRunner

# Create agent run (with runtime spec)
agent_run = create_agent_run(pipeline, user)

# Run loop
result = await AgentLoopRunner.start_loop(agent_run)

if result.success:
    print(f"Completed in {result.steps_executed} steps")
else:
    print(f"Failed: {result.error_message}")
```

### With Custom Planner

```python
class MyPlanner(Planner):
    async def plan_next_action(self, runtime_spec, execution_history, current_state):
        # Custom planning logic
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id="...",
            reasoning="...",
        )

# Use custom planner
planner = MyPlanner()
result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
```

### With Agent Profile

```python
from agent_integration.control_plane_models import AgentProfile

# Get agent profile
agent_profile = AgentProfile.objects.get(name="Data Analyst Agent")

# Create runtime spec with profile
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
    agent_run=agent_run,
    agent_profile=agent_profile,
)

# Run loop (profile config automatically applied)
result = await AgentLoopRunner.start_loop(agent_run)
```

## Planner Interface

### PlannerDecision

Decision returned by planner:

```python
@dataclass
class PlannerDecision:
    decision_type: PlannerDecisionType  # EXECUTE_TOOL, REQUEST_HUMAN, COMPLETE, FAIL
    tool_id: Optional[str] = None
    tool_parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 1.0
    human_message: Optional[str] = None
```

### Decision Types

**EXECUTE_TOOL**
- Execute a specific tool
- Must provide `tool_id`
- Optional `tool_parameters`

**REQUEST_HUMAN**
- Pause for human intervention
- Provide `human_message`
- Loop will pause and wait

**COMPLETE**
- All work done
- Loop terminates successfully
- Provide `reasoning`

**FAIL**
- Error occurred
- Loop terminates with failure
- Provide `reasoning`

### DeterministicPlanner

Rule-based planner (current default):

**Rules:**
1. Execute tools in DAG order
2. Respect dependencies
3. Execute each tool once
4. Complete when all done

**Example:**
```python
planner = DeterministicPlanner()

decision = await planner.plan_next_action(
    runtime_spec=runtime_spec,
    execution_history=history,
    current_state=state,
)

if decision.decision_type == PlannerDecisionType.EXECUTE_TOOL:
    print(f"Execute: {decision.tool_id}")
```

### Custom Planner Example

```python
class PriorityPlanner(Planner):
    """Execute tools by priority."""
    
    async def plan_next_action(self, runtime_spec, execution_history, current_state):
        tools = runtime_spec['available_tools']
        executed = {ex['tool_id'] for ex in execution_history}
        
        # Sort by priority
        remaining = [t for t in tools if t['tool_id'] not in executed]
        remaining.sort(key=lambda t: t.get('agent_constraints', {}).get('priority', 0), reverse=True)
        
        if remaining:
            tool = remaining[0]
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=tool['tool_id'],
                reasoning=f"Execute highest priority tool: {tool['tool_name']}",
            )
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed",
        )
```

## Guardrails

### GuardrailResult

Result of validation:

```python
@dataclass
class GuardrailResult:
    is_valid: bool
    violations: List[GuardrailViolation]
    corrected_decision: Optional[PlannerDecision] = None
```

### Validation Rules

**1. Tool ID Required**
- Severity: `critical`
- Blocks: EXECUTE_TOOL without tool_id

**2. Tool Not Found**
- Severity: `critical`
- Blocks: Tool not in runtime spec

**3. Tool Not Allowed**
- Severity: `error`
- Blocks: Agent constraints `is_allowed=False`

**4. Max Calls Exceeded**
- Severity: `error`
- Blocks: Tool called more than `max_calls`

**5. Missing Dependencies**
- Severity: `error`
- Blocks: Dependencies not satisfied

### Example

```python
guardrails = Guardrails(runtime_spec)

result = await guardrails.validate_decision(
    decision=decision,
    execution_history=history,
    current_state=state,
)

if not result.is_valid:
    for violation in result.violations:
        print(f"{violation.severity}: {violation.message}")
```

## Conditions

### Business Conditions

Conditions are defined in runtime spec:

```python
{
    'condition_id': 'uuid',
    'condition_name': 'Check Budget',
    'condition_type': 'variable_equals',
    'config': {
        'variable': 'budget_exceeded',
        'value': True,
    },
    'evaluation_point': 'after_tool_execution',
    'on_true_action': 'pause',
    'on_false_action': 'continue',
}
```

### Evaluation Points

**before_execution**
- Before loop starts
- Check pre-conditions

**after_tool_execution**
- After each tool
- Check invariants

**on_error**
- When errors occur
- Custom error handling

**before_completion**
- Before loop ends
- Validate final state

### Condition Types

**always_true**
- Always evaluates to true
- For testing

**variable_equals**
- Check if variable equals value
- Config: `{'variable': 'name', 'value': value}`

**Custom types** (implement as needed)
- threshold_exceeded
- time_limit_reached
- cost_limit_reached
- etc.

### Example

```python
evaluator = ConditionEvaluator(runtime_spec)

results = await evaluator.evaluate_conditions(
    evaluation_point='after_tool_execution',
    current_state=state,
)

for result in results:
    if result['is_true']:
        action = result['on_true_action']
        if action == 'pause':
            # Request human intervention
            pass
```

## Human-in-the-Loop

### Requesting Intervention

Planner can request human intervention:

```python
return PlannerDecision(
    decision_type=PlannerDecisionType.REQUEST_HUMAN,
    reasoning="Need approval",
    human_message="Please review results and approve continuation",
)
```

### Loop Pauses

When human intervention requested:

1. Loop terminates with `HUMAN_INTERVENTION_REQUIRED`
2. `AgentRun.status` = `'waiting_for_human'`
3. `AgentRun.human_intervention_required` = `True`
4. `AgentRun.human_intervention_reason` set
5. Loop waits for response

### Providing Response

Human provides response:

```python
agent_run.human_intervention_response = {
    'approved': True,
    'notes': 'Looks good, continue',
}
agent_run.save()
```

### Resuming Loop

Resume after approval:

```python
result = await AgentLoopRunner.resume_loop(agent_run)
```

This:
1. Clears intervention flags
2. Sets status to `'executing'`
3. Resumes loop from where it paused

## Error Handling

### Retry Logic

Retry policy from runtime spec:

```python
{
    'agent_configuration': {
        'retry_policy': {
            'max_retries': 3,
            'backoff_multiplier': 2.0,
            'retry_on_errors': ['timeout', 'transient'],
        }
    }
}
```

### Handling Errors

When tool execution fails:

1. Check retry policy
2. Count prior attempts
3. If retries available, retry
4. If no retries, fail loop

### Example

```python
async def _handle_execution_error(decision, tool_result):
    retry_policy = runtime_spec['agent_configuration']['retry_policy']
    max_retries = retry_policy.get('max_retries', 0)
    
    retry_count = await get_retry_count(decision.tool_id)
    
    if retry_count < max_retries:
        return True  # Retry
    
    return False  # Fail
```

## Integration

### Complete Flow

```python
# 1. Create pipeline execution
pipeline_execution = PipelineExecution.objects.create(
    pipeline=pipeline,
    started_by=user,
)

# 2. Create agent run
agent_run = AgentRun.objects.create(
    pipeline_execution=pipeline_execution,
    max_steps=100,
)

# 3. Create runtime spec
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
    agent_run=agent_run,
    agent_profile=agent_profile,  # Optional
)

# 4. Run loop
result = await AgentLoopRunner.start_loop(agent_run)

# 5. Check result
if result.success:
    print("Pipeline completed!")
else:
    print(f"Failed: {result.error_message}")

# 6. Review execution
agent_run.refresh_from_db()
print(f"Decisions: {agent_run.decisions.count()}")
print(f"Tools executed: {agent_run.tool_executions.count()}")
```

### With Control Plane

Using agent profiles and conditions:

```python
# Create agent profile with policies
agent_profile = AgentProfile.objects.create(
    name="Production Agent",
    max_steps=50,
    retry_policy={'max_retries': 3},
    guardrails={'cost_limit': 100.0},
)

# Create business condition
condition = BusinessCondition.objects.create(
    name="Check Budget",
    condition_type="threshold",
    config={'threshold': 1000},
    evaluation_point="after_tool_execution",
)

# Bind condition to agent
AgentConditionBinding.objects.create(
    agent=agent_profile,
    condition=condition,
)

# Runtime spec includes all configuration
runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
    agent_run=agent_run,
    agent_profile=agent_profile,
)

# Loop automatically applies policies
result = await AgentLoopRunner.start_loop(agent_run)
```

## Testing

### Unit Tests

Test individual components:

```python
def test_planner():
    planner = DeterministicPlanner()
    decision = asyncio.run(planner.plan_next_action(spec, history, state))
    assert decision.decision_type == PlannerDecisionType.EXECUTE_TOOL

def test_guardrails():
    guardrails = Guardrails(runtime_spec)
    result = asyncio.run(guardrails.validate_decision(decision, history, state))
    assert result.is_valid

def test_condition_evaluator():
    evaluator = ConditionEvaluator(runtime_spec)
    results = asyncio.run(evaluator.evaluate_conditions('before_execution', state))
    assert len(results) > 0
```

### Integration Tests

Test full loop:

```python
@patch('agent_integration.node_tools.executor.NodeToolExecutor.execute')
def test_full_loop(mock_execute):
    mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
        success=True,
        duration=1.0,
        summary="Success",
    ))()
    
    result = asyncio.run(AgentLoopRunner.start_loop(agent_run))
    
    assert result.success
    assert result.termination_reason == LoopTerminationReason.COMPLETED
```

### Run Tests

```bash
# Run all tests
python manage.py test agent_integration.tests.test_execution_loop

# Run specific test
python manage.py test agent_integration.tests.test_execution_loop.PlannerTests.test_deterministic_planner_basic
```

## Examples

See `agent_integration/execution_loop_examples.py` for complete examples:

1. **Basic Loop** - Simple execution with deterministic planner
2. **Custom Planner** - Implement custom planning logic
3. **Human-in-the-Loop** - Pause for approval
4. **Monitoring** - Real-time execution monitoring
5. **With Agent Profile** - Use agent configuration
6. **Error Handling** - Handle failures and retries

### Run Examples

```bash
python manage.py shell < agent_integration/execution_loop_examples.py
```

Or individually:

```python
import asyncio
from agent_integration.execution_loop_examples import example_basic_loop

asyncio.run(example_basic_loop())
```

## Key Design Principles

### 1. Bounded Execution

✅ Loop ALWAYS terminates:
- Max steps limit enforced
- No infinite loops possible
- Explicit termination reasons

### 2. Observable

✅ Everything is recorded:
- All decisions logged
- All executions tracked
- Full audit trail

### 3. Safe

✅ Multiple safety layers:
- Guardrails validate decisions
- Dependencies enforced
- Tool call limits respected
- No direct node execution

### 4. Flexible

✅ Extensible architecture:
- Custom planners
- Custom conditions
- Custom guardrails
- Plugin-friendly

### 5. Deterministic Fallback

✅ Always have working planner:
- DeterministicPlanner as default
- Rule-based, predictable
- No external dependencies
- Good for testing

## Termination Reasons

### COMPLETED

✅ Success - All work done
- Planner returned COMPLETE
- All tools executed successfully
- No errors

### MAX_STEPS_REACHED

❌ Failure - Exceeded step limit
- Reached max_steps
- Work incomplete
- Possible infinite loop prevented

### HUMAN_INTERVENTION_REQUIRED

⏸️ Paused - Waiting for human
- Planner requested human
- Loop paused
- Can be resumed

### ERROR

❌ Failure - Error occurred
- Tool execution failed
- Critical guardrail violation
- No retries available

### CANCELLED

⏹️ Cancelled - User cancelled
- User requested cancellation
- Graceful shutdown

## Troubleshooting

### Loop Never Completes

**Symptom:** Loop reaches max_steps

**Causes:**
- Planner never returns COMPLETE
- Dependencies circular
- Tools failing repeatedly

**Solutions:**
- Check planner logic
- Verify DAG has no cycles
- Review error logs

### Guardrail Violations

**Symptom:** Tools not executing

**Causes:**
- Tool not allowed
- Max calls exceeded
- Dependencies not satisfied

**Solutions:**
- Check agent tool mappings
- Increase max_calls
- Review execution order

### Human Intervention Not Working

**Symptom:** Loop doesn't pause

**Causes:**
- Planner not returning REQUEST_HUMAN
- Status not updating
- Response not provided

**Solutions:**
- Check planner decision
- Verify agent_run.status
- Provide intervention response

## Next Steps

### Future Enhancements

1. **LLM Planner** - Integrate with OpenAI, Anthropic, etc.
2. **Advanced Conditions** - More condition types
3. **Cost Tracking** - Track execution costs
4. **Parallel Execution** - Execute independent tools in parallel
5. **Checkpointing** - Save/restore loop state
6. **Metrics Dashboard** - Visualize execution metrics

### Integration Points

1. **Control Plane UI** - Manage execution from UI
2. **Monitoring Dashboard** - Real-time execution view
3. **LLM Integration** - Connect to LLM providers
4. **Webhooks** - Notify on events
5. **API** - REST API for external control

## Summary

The Agent Execution Loop provides **safe, bounded, observable control** over pipeline execution:

✅ **Controls flow** - Decides what to execute  
✅ **Never infinite** - Always terminates  
✅ **Enforces rules** - Guardrails and conditions  
✅ **Supports humans** - Pause for approval  
✅ **Handles errors** - Retry and recovery  
✅ **Fully auditable** - Complete history  

**Files:**
- `agent_integration/execution_loop.py` - Main implementation
- `agent_integration/execution_loop_examples.py` - Usage examples
- `agent_integration/tests/test_execution_loop.py` - Tests
- `agent_integration/EXECUTION_LOOP_README.md` - This document
