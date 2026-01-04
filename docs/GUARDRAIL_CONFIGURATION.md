# Guardrail Configuration Guide

**Last Updated:** January 4, 2026

---

## Overview

Guardrails are safety mechanisms that prevent agent executions from exceeding defined limits or performing unsafe operations. This document describes how to configure and use guardrails effectively.

## Configuration Structure

Guardrail configuration is stored in the `AgentProfile.guardrail_config` JSON field and passed to the execution loop via `agent_config['guardrail_config']`.

### Example Configuration

```json
{
  "max_execution_time_seconds": 300,
  "max_cost_usd": 1.0,
  "require_approval_for_high_risk": true
}
```

---

## Available Guardrail Settings

### 1. `max_execution_time_seconds` (number)

**Purpose:** Prevent runaway executions that take too long.

**Behavior:**
- Tracks total execution time from start
- Checks limit before each step
- Raises `RuntimeError` if exceeded

**Example:**
```json
{
  "max_execution_time_seconds": 300  // 5 minutes max
}
```

**Use Cases:**
- Prevent infinite loops
- Ensure timely execution for time-sensitive workflows
- Avoid resource hogging in shared environments

**Recommended Values:**
- Simple pipelines: 60-180 seconds
- Complex workflows: 300-600 seconds
- Long-running batch: 1800-3600 seconds

---

### 2. `max_cost_usd` (number)

**Purpose:** Prevent expensive LLM API calls from exceeding budget.

**Behavior:**
- Tracks cumulative LLM API costs
- Uses token counts to estimate costs (gpt-4o-mini pricing)
- Raises `RuntimeError` if exceeded

**Pricing Used (gpt-4o-mini):**
- Input tokens: $0.150 per 1M tokens
- Output tokens: $0.600 per 1M tokens

**Example:**
```json
{
  "max_cost_usd": 1.0  // $1.00 maximum
}
```

**Use Cases:**
- Budget control for production environments
- Cost limits for untested pipelines
- Per-user spending caps

**Recommended Values:**
- Testing: $0.10 - $0.50
- Production: $1.00 - $5.00
- Enterprise: $10.00+

**Note:** Cost tracking only applies when using LLM planner. Fallback planner has zero cost.

---

### 3. `require_approval_for_high_risk` (boolean)

**Purpose:** Pause execution and request human approval before executing potentially dangerous operations.

**Behavior:**
- Checks each node before execution
- Identifies "high-risk" nodes based on keywords
- Pauses execution and sets `human_intervention_required=True`

**High-Risk Keywords Detected:**
- `delete`, `drop`, `remove`, `destroy`
- `payment`, `transfer`, `charge`

**Example:**
```json
{
  "require_approval_for_high_risk": true
}
```

**Use Cases:**
- Production environments with destructive operations
- Financial transactions
- Data modification pipelines
- Compliance requirements

**How It Works:**

1. **Node Analysis:** Before executing a node, checks if its name or description contains high-risk keywords
2. **Pause Execution:** If match found, execution pauses with status `waiting_for_human`
3. **Human Review:** User reviews the pending operation in the UI
4. **Resume:** User approves or rejects via `/agent/runs/<id>/resume/`

**Example High-Risk Node:**
```python
node = Node.objects.create(
    name="DeleteOldRecords",  # Contains "delete" keyword
    description="Permanently removes records older than 90 days",
    code="..."
)
# This will trigger approval requirement
```

---

## Additional Guardrails (Always Active)

These guardrails are always enforced regardless of configuration:

### Dependency Checking
- Prevents nodes from executing before their dependencies complete
- Cascades failures: if Node A fails, all nodes depending on A are marked failed

### Max Steps Limit
- Controlled by `AgentProfile.max_steps` or `agent_config['max_steps']`
- Default: 100 steps
- Prevents infinite decision loops

### Consecutive Failures
- Controlled by `AgentProfile.max_retries` or enforced by policy guardrails
- Default: 3 consecutive failures
- Stops execution after repeated failures

### Fail-Fast Mode
- Controlled by `agent_config['fail_on_node_failure']`
- Default: `True`
- When enabled, stops immediately if any node fails

---

## Configuration Examples

### Development Environment
```json
{
  "max_execution_time_seconds": 600,
  "max_cost_usd": 5.0,
  "require_approval_for_high_risk": false
}
```

### Production Environment
```json
{
  "max_execution_time_seconds": 300,
  "max_cost_usd": 1.0,
  "require_approval_for_high_risk": true
}
```

### Testing/Sandbox
```json
{
  "max_execution_time_seconds": 60,
  "max_cost_usd": 0.10,
  "require_approval_for_high_risk": false
}
```

### Financial Operations
```json
{
  "max_execution_time_seconds": 180,
  "max_cost_usd": 2.0,
  "require_approval_for_high_risk": true
}
```

---

## Setting Guardrails

### Method 1: Via AgentProfile (Recommended)

Create or update an agent profile with guardrail configuration:

```python
from agent_integration.control_plane_models import AgentProfile

agent = AgentProfile.objects.create(
    name="Production Agent",
    status="active",
    max_steps=50,
    guardrail_config={
        "max_execution_time_seconds": 300,
        "max_cost_usd": 1.0,
        "require_approval_for_high_risk": True
    },
    llm_model="gpt-4o-mini",
    llm_temperature=0.3
)
```

### Method 2: Via agent_config Parameter

Pass directly when starting execution:

```python
from agent_integration.runtime.execution_loop import start_agent_execution

result = start_agent_execution(
    pipeline_execution=pipeline_execution,
    agent_config={
        'model': 'gpt-4o-mini',
        'temperature': 0.3,
        'fail_on_node_failure': True,
        'guardrail_config': {
            'max_execution_time_seconds': 300,
            'max_cost_usd': 1.0,
            'require_approval_for_high_risk': True
        }
    }
)
```

### Method 3: Via UI

When starting an agent run from the dashboard, configure in the modal:

1. Navigate to `/agent/dashboard/`
2. Click "Start New Agent Run"
3. Expand "Advanced Configuration"
4. Enter JSON in "Guardrail Config" field:
   ```json
   {
     "max_execution_time_seconds": 300,
     "max_cost_usd": 1.0,
     "require_approval_for_high_risk": true
   }
   ```

---

## Monitoring Guardrails

### Execution Summary

After execution completes, the summary includes guardrail metrics:

```
Executed 5 tools across 5 agent decisions in 5 steps | Total LLM cost: $0.0234 | Execution time: 12.3s
```

### AgentRun Model

Query the database to check guardrail violations:

```python
from agent_integration.models import AgentRun

run = AgentRun.objects.get(id=run_id)
print(f"Status: {run.status}")
print(f"Steps: {run.current_step}/{run.max_steps}")
print(f"Config: {run.agent_config.get('guardrail_config', {})}")
```

### AgentDecision Model

Check individual decisions for guardrail violations:

```python
from agent_integration.models import AgentDecision

decisions = AgentDecision.objects.filter(agent_run=run)
for decision in decisions:
    if decision.guardrail_violations:
        print(f"Step {decision.step_number}: {decision.guardrail_violations}")
```

---

## Error Handling

### Time Limit Exceeded

```
RuntimeError: Maximum execution time exceeded: 305.2s > 300s
```

**Resolution:**
- Increase `max_execution_time_seconds`
- Optimize pipeline nodes
- Reduce pipeline complexity

### Cost Limit Exceeded

```
RuntimeError: Maximum cost exceeded: $1.0234 > $1.0000
```

**Resolution:**
- Increase `max_cost_usd`
- Use cheaper model (already using gpt-4o-mini)
- Reduce temperature to get shorter responses
- Simplify prompts

### High-Risk Approval Required

```
Human intervention required: Node <id> requires approval before execution
```

**Resolution:**
- Review the operation in UI at `/agent/runs/<id>/detail/`
- Click "Resume" to approve
- Or set `require_approval_for_high_risk: false` (not recommended for production)

---

## Extending Guardrails

### Adding Custom High-Risk Keywords

Edit `execution_loop.py` method `_is_high_risk_node()`:

```python
def _is_high_risk_node(self, node_id: str) -> bool:
    """Determine if a node is considered high-risk."""
    from core.models import Node
    try:
        node = Node.objects.get(id=node_id)
        # Add your custom keywords here
        high_risk_keywords = [
            'delete', 'drop', 'remove', 'destroy',
            'payment', 'transfer', 'charge',
            'email',  # Custom: require approval for emails
            'api_call',  # Custom: require approval for external APIs
        ]
        node_text = f"{node.name} {node.description or ''}".lower()
        return any(keyword in node_text for keyword in high_risk_keywords)
    except Node.DoesNotExist:
        return False
```

### Adding New Guardrail Types

1. **Add configuration field** to guardrail_config:
   ```json
   {
     "max_memory_mb": 512
   }
   ```

2. **Add tracking** in `AgentExecutionLoop.__init__()`:
   ```python
   self.memory_usage_mb = 0.0
   ```

3. **Add check** in `_check_guardrail_limits()`:
   ```python
   max_memory = self.guardrail_config.get('max_memory_mb')
   if max_memory and self.memory_usage_mb > max_memory:
       raise RuntimeError(f"Memory limit exceeded: {self.memory_usage_mb}MB > {max_memory}MB")
   ```

4. **Update tracking** where relevant:
   ```python
   import psutil
   self.memory_usage_mb = psutil.Process().memory_info().rss / 1024 / 1024
   ```

---

## Best Practices

### 1. Always Set Time Limits
Even for development, set reasonable time limits to prevent runaway processes.

### 2. Start with Low Cost Limits
Begin with low cost limits ($0.10-$0.50) and increase as needed after testing.

### 3. Enable High-Risk Approval in Production
Always require approval for high-risk operations in production environments.

### 4. Monitor and Adjust
Review execution summaries regularly and adjust limits based on actual usage patterns.

### 5. Use Environment-Specific Profiles
Create different `AgentProfile` instances for dev, staging, and production with appropriate guardrails.

### 6. Document Custom Keywords
If you add custom high-risk keywords, document them for your team.

### 7. Test Guardrail Violations
Intentionally trigger guardrail violations in testing to ensure proper behavior.

---

## Troubleshooting

### Guardrails Not Enforced

**Check:**
1. Is guardrail_config being passed to execution loop?
2. Is the config structure correct (JSON dictionary)?
3. Check logs for errors during guardrail initialization

### Cost Tracking Shows $0.00

**Possible causes:**
1. Using fallback planner instead of LLM planner
2. OpenAI API key not set
3. LLM response doesn't include usage data

**Solution:**
- Verify `OPENAI_API_KEY` is set
- Check that `model` is set to 'gpt-4o-mini' (not 'fallback-ordering')
- Review logs for LLM planner errors

### High-Risk Detection Not Working

**Check:**
1. Is `require_approval_for_high_risk` set to `true`?
2. Does node name/description contain high-risk keywords?
3. Keywords are case-insensitive - check exact matching

---

## Future Enhancements

Planned guardrail features (see TODO.md):

- [ ] **Rate Limiting:** Limit API calls per minute
- [ ] **Memory Limits:** Track and limit memory usage
- [ ] **Parallel Execution Limits:** Control concurrent node execution
- [ ] **Custom Approval Rules:** User-defined approval logic
- [ ] **Audit Logging:** Detailed guardrail violation logs
- [ ] **Cost Prediction:** Warn before expensive operations
- [ ] **Dynamic Limits:** Adjust limits based on context
- [ ] **Guardrail Analytics:** Dashboard for guardrail metrics

---

## Related Documentation

- **SYSTEM_DOCUMENTATION.md** - Complete system overview
- **TODO.md** - Planned guardrail enhancements
- **Agent Integration README** - docs/agent_integration/
- **Control Plane Guide** - Agent profile configuration

---

**Questions or Issues?**

Review the execution logs for detailed guardrail enforcement information, or check the AgentRun and AgentDecision models for historical violation data.
