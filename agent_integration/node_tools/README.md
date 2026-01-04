# Node Tool Wrappers

This package provides tool wrappers for existing Pipeline Nodes, allowing LLM agents to execute nodes as tools while maintaining full auditability and observability.

## Design Principles

**CRITICAL**: This package does NOT duplicate or modify node execution logic.

1. **Wraps, Not Replaces**: Uses existing `backend.execute_node()` from `core.execution`
2. **Observability**: Creates `ToolExecution` records for agent-initiated node runs
3. **No Raw Data**: Never returns raw data to agent, only summaries and references
4. **Graph Constraints**: Respects pipeline DAG structure and dependencies
5. **Async Compatible**: Supports async execution for agent orchestration

## Architecture

```
Agent Request
    ↓
NodeToolExecutor.execute()
    ↓
    ├─→ Validate parameters
    ├─→ Create ToolExecution record
    ├─→ Call existing backend.execute_node()  ← REUSES EXISTING LOGIC
    ├─→ Record results
    └─→ Return NodeToolResult (summary only)
```

## Key Components

### 1. NodeToolWrapper (base.py)

Abstract base class defining the tool interface.

```python
class NodeToolWrapper(ABC):
    async def execute(
        self,
        agent_run_id: uuid.UUID,
        agent_decision_id: Optional[uuid.UUID],
        parameters: Dict[str, Any],
        context: Dict[str, Any],
    ) -> NodeToolResult
```

### 2. NodeToolExecutor (executor.py)

Concrete implementation that wraps existing node execution.

**Does NOT:**
- Duplicate node execution code
- Modify core models
- Bypass pipeline constraints
- Execute code directly

**Does:**
- Create ToolExecution tracking records
- Call `backend.execute_node()` (same as pipeline execution)
- Extract artifact references
- Generate execution summaries

```python
# Example usage
executor = NodeToolExecutor(node_id=node.id, node_name=node.name)
result = await executor.execute(
    agent_run_id=run_id,
    agent_decision_id=decision_id,
    parameters={'input_var': 'value'},
    context=execution_context,
)
```

### 3. NodeToolRegistry (registry.py)

Discovers and caches node tool wrappers.

```python
# Get all tools for a pipeline
tools = NodeToolRegistry.get_tools_for_pipeline(pipeline_id)

# Get specific tool
tool = NodeToolRegistry.get_tool_by_node_id(node_id)

# Get tool definitions for agent
tool_defs = NodeToolRegistry.get_tool_definitions(pipeline_id)
```

### 4. NodeToolResult (base.py)

Return value from tool execution - contains NO raw data.

```python
@dataclass
class NodeToolResult:
    success: bool
    tool_execution_id: uuid.UUID
    node_execution_id: uuid.UUID
    duration_seconds: float
    summary: str  # Human-readable for agent
    artifact_references: List[str]  # References, not data
    output_variables: List[str]  # Names, not values
    error_message: Optional[str]
    error_type: Optional[str]
```

## Integration with Existing System

### Execution Flow

This package integrates with the existing pipeline execution system:

1. **Same Backend**: Uses `core.execution.get_execution_backend()`
2. **Same Node Execution**: Calls `backend.execute_node(node, context, execution)`
3. **Same NodeExecution Records**: Creates standard `NodeExecution` instances
4. **Additional Tracking**: Adds `ToolExecution` records for agent observability

### Data Flow

```
Agent Decision
    ↓
NodeToolExecutor.execute()
    ↓
Create NodeExecution (standard)
    ↓
Create ToolExecution (agent tracking)
    ↓
backend.execute_node()  ← EXISTING LOGIC
    ↓
    └─→ WarpDrive context
        └─→ User code execution
            └─→ Artifact save
    ↓
Record results in both:
    ├─→ NodeExecution.output_data
    └─→ ToolExecution.result_summary
    ↓
Return NodeToolResult to agent
```

## Usage Examples

### Basic Node Execution

```python
from agent_integration.node_tools import get_node_tool

# Get tool wrapper for a node
tool = get_node_tool(node_id)

# Execute as tool
result = await tool.execute(
    agent_run_id=agent_run.id,
    agent_decision_id=decision.id,
    parameters={'data_path': '/tmp/input.csv'},
    context={'previous_result': 'some_value'},
)

# Check result
if result.success:
    print(f"✅ {result.summary}")
    print(f"Artifacts: {result.artifact_references}")
else:
    print(f"❌ {result.error_message}")
```

### Get Available Tools

```python
from agent_integration.node_tools import NodeToolRegistry

# Get all tools for a pipeline
tools = NodeToolRegistry.get_tools_for_pipeline(pipeline_id)

# Get tool definitions for agent context
tool_defs = NodeToolRegistry.get_tool_definitions(pipeline_id)

# Pass to agent for tool selection
agent_context = {
    'available_tools': tool_defs,
    'executed_tools': get_executed_tools(agent_run_id),
}
```

### Check Execution History

```python
from agent_integration.node_tools.utils import get_tool_execution_history

# Get all tool executions for an agent run
history = get_tool_execution_history(agent_run_id)

for exec in history:
    print(f"{exec.tool_name}: {exec.status}")
    print(f"  Result: {exec.result_summary}")
    print(f"  Artifacts: {exec.artifact_references}")
```

### Validate Before Execution

```python
from agent_integration.node_tools.utils import can_execute_node

# Check if node can be executed
can_run, reason = can_execute_node(
    node_id=node_id,
    agent_run_id=agent_run_id,
    context=current_context,
)

if not can_run:
    print(f"Cannot execute: {reason}")
```

## What NOT to Do

❌ **Do NOT**:
- Call node execution code directly
- Duplicate node execution logic
- Bypass `backend.execute_node()`
- Modify `core.models.Node` or `core.execution` packages
- Return raw data to agents
- Skip graph constraint validation

✅ **Do**:
- Use `NodeToolExecutor` to wrap node execution
- Call existing `backend.execute_node()`
- Create `ToolExecution` records for tracking
- Return `NodeToolResult` with summaries
- Respect pipeline graph structure
- Use artifact references, not raw data

## Database Impact

### New Records Created

Each tool execution creates:

1. **NodeExecution** (existing model):
   - Tracks node execution as normal
   - Same as pipeline execution creates
   - Contains output_data

2. **ToolExecution** (new model):
   - Links to NodeExecution
   - Links to AgentRun and AgentDecision
   - Contains agent-facing summary
   - Records artifact references
   - Tracks tool-specific metadata

### No Modifications To

- `core.models.Node`
- `core.models.Pipeline`
- `core.execution.*` modules
- Existing pipeline execution logic

## Performance Considerations

### Caching

Tool wrappers are cached for 5 minutes:

```python
# Invalidate cache when nodes change
NodeToolRegistry.invalidate_cache(pipeline_id)

# Or clear all caches
NodeToolRegistry.invalidate_cache()
```

### Async Execution

Tool execution is async-compatible:

```python
# Execute multiple tools concurrently
results = await asyncio.gather(
    tool1.execute(...),
    tool2.execute(...),
    tool3.execute(...),
)
```

### Database Optimization

Uses `select_related` and `prefetch_related` to minimize queries:

```python
# Efficient node loading
node = Node.objects.select_related('pipeline').get(pk=node_id)

# Efficient history query
history = ToolExecution.objects.filter(
    agent_run_id=agent_run_id
).select_related('node_execution__node', 'agent_decision')
```

## Testing

To test node tool wrappers:

```python
# Create test node and agent run
node = Node.objects.create(...)
agent_run = AgentRun.objects.create(...)

# Get tool wrapper
tool = get_node_tool(node.id)

# Execute with test parameters
result = await tool.execute(
    agent_run_id=agent_run.id,
    agent_decision_id=None,
    parameters={},
    context={},
)

# Verify result
assert result.success
assert result.tool_execution_id
assert result.node_execution_id

# Check database records
tool_exec = ToolExecution.objects.get(pk=result.tool_execution_id)
assert tool_exec.status == 'completed'
assert tool_exec.result_summary
```

## Future Enhancements

1. **Control Plane Integration**: Filter tools based on `AgentToolMapping`
2. **Dependency Resolution**: Automatic prerequisite checking
3. **Retry Logic**: Configurable retry for transient failures
4. **Rate Limiting**: Prevent excessive tool calls
5. **Cost Tracking**: Record execution costs per tool
6. **Parallel Execution**: Execute independent nodes concurrently
