# Agent Integration Data Flow

## Execution Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         START EXECUTION                              │
│                                                                      │
│  User triggers: start_agent_execution(pipeline_execution)           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    1. INITIALIZE AGENT RUN                           │
│                                                                      │
│  • Create AgentRun record                                           │
│  • Link to PipelineExecution                                        │
│  • Set status: 'initializing'                                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                2. BUILD RUNTIME SPECIFICATION                        │
│                                                                      │
│  • RuntimeSpecBuilder.build_spec()                                  │
│  • Convert Pipeline → JSON spec                                     │
│    - available_tools (from nodes)                                   │
│    - execution_constraints (from DAG)                               │
│    - business_conditions                                            │
│    - global_context                                                 │
│  • Compute checksum                                                 │
│  • Save RuntimeSpec                                                 │
│  • Validate spec                                                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  3. INITIALIZE GUARDRAILS                            │
│                                                                      │
│  • Create GuardrailEngine(runtime_spec)                             │
│  • Build dependency graph                                           │
│  • Initialize execution state                                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  4. INITIALIZE TOOL REGISTRY                         │
│                                                                      │
│  • Create ToolRegistry(pipeline)                                    │
│  • Wrap each Node as NodeToolWrapper                                │
│  • Build tool definitions                                           │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 5. INITIALIZE EXECUTION CONTEXT                      │
│                                                                      │
│  • Load pipeline.global_arguments                                   │
│  • Load pipeline_execution.context_data                             │
│  • Merge into execution context                                     │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  EXECUTION     │
                        │  LOOP BEGINS   │
                        └───────┬────────┘
                                │
                ┌───────────────┴───────────────┐
                │                               │
                ▼                               │
┌─────────────────────────────────────────────┐ │
│         6. GET SAFE CHOICES                 │ │
│                                             │ │
│  • guardrails.get_safe_choices()           │ │
│  • Returns nodes with satisfied deps       │ │
│  • Checks:                                 │ │
│    - Dependencies satisfied?               │ │
│    - Not already executed?                 │ │
│    - Not failed?                           │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│      7. CHECK FOR COMPLETION/DEADLOCK       │ │
│                                             │ │
│  IF no available nodes:                     │ │
│    IF all executed → COMPLETE               │ │
│    ELSE → DEADLOCK → request human          │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         8. CALL PLANNER (LLM)               │ │
│                                             │ │
│  • Build prompt with:                       │ │
│    - Pipeline description                   │ │
│    - Available nodes                        │ │
│    - Current context                        │ │
│    - Previous decisions                     │ │
│  • Call LLM API (TODO: implement)           │ │
│  • Parse response                           │ │
│  • Extract: selected_node_id, reasoning     │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│    9. VALIDATE WITH GUARDRAILS (PRE)        │ │
│                                             │ │
│  • validate_before_execution()              │ │
│  • Checks:                                 │ │
│    ✓ Node exists?                          │ │
│    ✓ Not already executed?                 │ │
│    ✓ Dependencies satisfied?               │ │
│    ✓ No infinite loop?                     │ │
│    ✓ Not failed previously?                │ │
│    ✓ Under max iterations?                 │ │
│    ✓ Not too many failures?                │ │
│                                             │ │
│  IF violations → request human              │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         10. RECORD DECISION                 │ │
│                                             │ │
│  • Create AgentDecision record:            │ │
│    - step_number                           │ │
│    - decision_type: 'select_node'          │ │
│    - prompt (to LLM)                       │ │
│    - llm_response                          │ │
│    - parsed_decision                       │ │
│    - reasoning                             │ │
│    - guardrail_violations                  │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         11. GET TOOL (NODE)                 │ │
│                                             │ │
│  • tool = tool_registry.get_tool(node_id)  │ │
│  • NodeToolWrapper instance                │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         12. EXECUTE TOOL                    │ │
│                                             │ │
│  • tool.execute(agent_run, context,        │ │
│                 agent_decision)             │ │
│  • Creates NodeExecution                    │ │
│  • Creates ToolExecution                    │ │
│  • Calls backend.execute_node()             │ │
│  • USES EXISTING EXECUTION ENGINE           │ │
│  • Returns:                                 │ │
│    - status                                 │ │
│    - artifact_references                    │ │
│    - summary                                │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│    13. UPDATE GUARDRAILS STATE (POST)       │ │
│                                             │ │
│  • record_execution_result(node_id, success)│ │
│  • Updates ExecutionState:                 │ │
│    - Add to executed_nodes                 │ │
│    - Or add to failed_nodes                │ │
│    - Increment execution_count             │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         14. UPDATE CONTEXT                  │ │
│                                             │ │
│  • Retrieve output_data from NodeExecution │ │
│  • Merge into execution_context            │ │
│  • Available for next node                 │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 ▼                              │
┌─────────────────────────────────────────────┐ │
│         15. INCREMENT STEP                  │ │
│                                             │ │
│  • current_step += 1                       │ │
│  • Update AgentRun.current_step            │ │
└────────────────┬────────────────────────────┘ │
                 │                              │
                 └──────────────────────────────┘
                                 │
                                 ▼
                        ┌────────────────┐
                        │  ALL NODES     │
                        │  EXECUTED?     │
                        └───┬────────┬───┘
                            │        │
                       NO   │        │ YES
                            │        │
                            └────────┼─────────────┐
                                     │             │
                                     ▼             ▼
                        ┌─────────────────┐  ┌──────────────────┐
                        │  LOOP BACK TO   │  │   16. FINALIZE   │
                        │  STEP 6         │  │                  │
                        └─────────────────┘  │  • Set status:   │
                                             │    'completed'   │
                                             │  • Record time   │
                                             │  • Update        │
                                             │    execution     │
                                             └─────────┬────────┘
                                                       │
                                                       ▼
                                             ┌────────────────────┐
                                             │   EXECUTION        │
                                             │   COMPLETE         │
                                             └────────────────────┘
```

## Human Intervention Flow

```
┌─────────────────────────────────────────────┐
│   DURING EXECUTION:                         │
│   IF guardrail violation OR error:          │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│   PAUSE EXECUTION                           │
│                                             │
│  • Set status: 'waiting_for_human'         │
│  • Set human_intervention_required: True    │
│  • Store reason                            │
│  • Persist full state                      │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│   WAIT FOR HUMAN RESPONSE                   │
│                                             │
│  Human accesses:                            │
│  GET /agent/runs/<id>/                      │
│  - Sees reason for intervention             │
│  - Reviews decisions                        │
│  - Reviews execution state                  │
└────────────────┬────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────┐
│   HUMAN RESPONDS                            │
│                                             │
│  POST /agent/runs/<id>/respond/             │
│  Options:                                   │
│    - "continue": Resume execution           │
│    - "cancel": Abort execution              │
│    - "modify": Change parameters            │
└────────────────┬────────────────────────────┘
                 │
                 ▼
         ┌───────┴────────┐
         │   ACTION?      │
         └───┬────────┬───┘
             │        │
       continue    cancel
             │        │
             ▼        ▼
   ┌──────────────┐  ┌──────────────┐
   │ RESUME       │  │ ABORT        │
   │ EXECUTION    │  │ EXECUTION    │
   │              │  │              │
   │ • Clear flag │  │ • Set status │
   │ • Continue   │  │   'cancelled'│
   │   loop       │  │ • Save       │
   └──────────────┘  └──────────────┘
```

## Data Model Relationships

```
PipelineExecution (core)
         │
         │ 1:1
         ▼
    AgentRun (agent_integration)
         │
         ├────── 1:1 ──────► RuntimeSpec
         │                       │
         │                       └── spec_data (JSON)
         │                           • available_tools
         │                           • execution_constraints
         │                           • business_conditions
         │
         ├────── 1:N ──────► AgentDecision
         │                       │
         │                       └── Records:
         │                           • step_number
         │                           • decision_type
         │                           • prompt
         │                           • llm_response
         │                           • reasoning
         │                           • violations
         │
         └────── 1:N ──────► ToolExecution
                                 │
                                 ├── 1:1 ──► NodeExecution (core)
                                 │
                                 └── N:1 ──► AgentDecision
```

## State Transitions

```
AgentRun Status Flow:

initializing → planning → executing ⇄ waiting_for_human
                             │              │
                             ├──────────────┴→ completed
                             │
                             └──────────────→ failed
                             │
                             └──────────────→ cancelled
```

## Guardrail Decision Tree

```
                    ┌────────────────┐
                    │ Node Selected  │
                    │   by Agent     │
                    └───────┬────────┘
                            │
                            ▼
                    ┌────────────────┐
                    │ Node exists?   │
                    └───┬────────┬───┘
                        │ NO     │ YES
                        ▼        ▼
                    [BLOCK]  ┌────────────────┐
                             │ Already exec?  │
                             └───┬────────┬───┘
                                 │ YES    │ NO
                                 ▼        ▼
                             [BLOCK]  ┌────────────────┐
                                      │ Deps satisfied?│
                                      └───┬────────┬───┘
                                          │ NO     │ YES
                                          ▼        ▼
                                      [BLOCK]  ┌────────────────┐
                                               │ Max iterations?│
                                               └───┬────────┬───┘
                                                   │ YES    │ NO
                                                   ▼        ▼
                                               [BLOCK]  ┌────────────────┐
                                                        │ Too many fails?│
                                                        └───┬────────┬───┘
                                                            │ YES    │ NO
                                                            ▼        ▼
                                                        [BLOCK]  [ALLOW]
                                                                    │
                                                                    ▼
                                                            ┌────────────────┐
                                                            │  EXECUTE NODE  │
                                                            └────────────────┘
```

## Context Evolution

```
Initial Context:
{
  "pipeline_arguments": ["x", "y"],
  "x": 10,
  "y": 20
}
         │
         ▼ Node 1 executes
{
  "x": 10,
  "y": 20,
  "result1": {
    "_artifact": true,
    "_type": "DataFrame",
    "_file": "artifacts/result1.parquet"
  }
}
         │
         ▼ Node 2 executes
{
  "x": 10,
  "y": 20,
  "result1": {...},
  "result2": {
    "_artifact": true,
    "_type": "dict",
    "_file": "artifacts/result2.json"
  }
}
         │
         ▼ Final Context
```

This context flows through the entire execution,
accumulating outputs as nodes execute.
