# Agent Execution Loop - Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────┐
│                        USER REQUEST                                │
│                  "Run pipeline with agent"                         │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│                    1. CREATE AGENT RUN                             │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ PipelineExecution.objects.create(...)                        │ │
│  │ AgentRun.objects.create(pipeline_execution=...)              │ │
│  │ RuntimeSpecService.create_spec_for_agent_run(...)            │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│                  2. START EXECUTION LOOP                           │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ result = await AgentLoopRunner.start_loop(agent_run)        │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│                  3. INITIALIZE LOOP                                │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ loop = AgentExecutionLoop(agent_run, planner)               │ │
│  │ await loop.initialize()                                     │ │
│  │   ├─ Load RuntimeSpec                                       │ │
│  │   ├─ Verify integrity (checksum)                            │ │
│  │   ├─ Create Guardrails                                      │ │
│  │   └─ Create ConditionEvaluator                              │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│              4. PRE-EXECUTION CONDITIONS                           │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ await evaluator.evaluate_conditions('before_execution')     │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│           5. MAIN LOOP (BOUNDED BY max_steps)                      │
│                                                                    │
│  for step in range(max_steps):                                    │
│                                                                    │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5a. PLAN NEXT ACTION                                    │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ decision = await planner.plan_next_action(          │ │   │
│    │ │     runtime_spec=spec,                              │ │   │
│    │ │     execution_history=history,                      │ │   │
│    │ │     current_state=state,                            │ │   │
│    │ │ )                                                    │ │   │
│    │ │                                                      │ │   │
│    │ │ Planner Types:                                       │ │   │
│    │ │   • DeterministicPlanner (rule-based, default)      │ │   │
│    │ │   • LLMPlanner (future)                             │ │   │
│    │ │   • Custom implementations                          │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5b. RECORD DECISION                                     │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ AgentDecision.objects.create(                       │ │   │
│    │ │     agent_run=agent_run,                            │ │   │
│    │ │     step_number=step,                               │ │   │
│    │ │     decision_type=decision.decision_type,           │ │   │
│    │ │     reasoning=decision.reasoning,                   │ │   │
│    │ │ )                                                    │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5c. CHECK TERMINATION                                   │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ if decision.type == COMPLETE:                       │ │   │
│    │ │     return SUCCESS                                  │ │   │
│    │ │                                                      │ │   │
│    │ │ if decision.type == REQUEST_HUMAN:                  │ │   │
│    │ │     request_intervention()                          │ │   │
│    │ │     return PAUSED                                   │ │   │
│    │ │                                                      │ │   │
│    │ │ if decision.type == FAIL:                           │ │   │
│    │ │     return FAILURE                                  │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5d. VALIDATE WITH GUARDRAILS                            │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ result = await guardrails.validate_decision(        │ │   │
│    │ │     decision=decision,                              │ │   │
│    │ │     execution_history=history,                      │ │   │
│    │ │     current_state=state,                            │ │   │
│    │ │ )                                                    │ │   │
│    │ │                                                      │ │   │
│    │ │ Checks:                                              │ │   │
│    │ │   ✓ Tool ID provided                                │ │   │
│    │ │   ✓ Tool exists in spec                             │ │   │
│    │ │   ✓ Tool allowed by agent                           │ │   │
│    │ │   ✓ Max calls not exceeded                          │ │   │
│    │ │   ✓ Dependencies satisfied                          │ │   │
│    │ │                                                      │ │   │
│    │ │ if not result.is_valid:                             │ │   │
│    │ │     if has_critical_violations:                     │ │   │
│    │ │         return FAILURE                              │ │   │
│    │ │     continue  # Skip this step                      │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5e. EXECUTE TOOL                                        │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ executor = NodeToolExecutor(node)                   │ │   │
│    │ │ result = await executor.execute(                    │ │   │
│    │ │     agent_run_id=agent_run.id,                      │ │   │
│    │ │     parameters=decision.tool_parameters,            │ │   │
│    │ │     context={},                                      │ │   │
│    │ │ )                                                    │ │   │
│    │ │                                                      │ │   │
│    │ │ Creates:                                             │ │   │
│    │ │   • NodeExecution (standard pipeline record)        │ │   │
│    │ │   • ToolExecution (agent observability record)      │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5f. EVALUATE POST-EXECUTION CONDITIONS                  │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ results = await evaluator.evaluate_conditions(      │ │   │
│    │ │     'after_tool_execution',                         │ │   │
│    │ │     current_state,                                   │ │   │
│    │ │ )                                                    │ │   │
│    │ │                                                      │ │   │
│    │ │ for result in results:                              │ │   │
│    │ │     if result['on_true_action'] == 'pause':         │ │   │
│    │ │         request_human_intervention()                │ │   │
│    │ │     if result['on_false_action'] == 'fail':         │ │   │
│    │ │         return FAILURE                              │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5g. HANDLE ERRORS & RETRIES                             │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ if not tool_result.success:                         │ │   │
│    │ │     retry_policy = spec['agent_configuration']      │ │   │
│    │ │                        ['retry_policy']             │ │   │
│    │ │     max_retries = retry_policy['max_retries']       │ │   │
│    │ │     retry_count = get_retry_count(tool_id)          │ │   │
│    │ │                                                      │ │   │
│    │ │     if retry_count < max_retries:                   │ │   │
│    │ │         continue  # Retry                           │ │   │
│    │ │     else:                                            │ │   │
│    │ │         return FAILURE                              │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                          ↓                                        │
│    ┌─────────────────────────────────────────────────────────┐   │
│    │ 5h. UPDATE STATE                                        │   │
│    │ ┌─────────────────────────────────────────────────────┐ │   │
│    │ │ if tool_result.success:                             │ │   │
│    │ │     current_state['completed_tools'].append(        │ │   │
│    │ │         decision.tool_id                            │ │   │
│    │ │     )                                                │ │   │
│    │ └─────────────────────────────────────────────────────┘ │   │
│    └─────────────────────────────────────────────────────────┘   │
│                                                                    │
│  # Loop continues until COMPLETE or max_steps reached             │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│                  6. FINALIZE EXECUTION                             │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ agent_run.status = 'completed' or 'failed'                  │ │
│  │ agent_run.completed_at = now()                              │ │
│  │ agent_run.save()                                            │ │
│  │                                                              │ │
│  │ return LoopResult(                                          │ │
│  │     success=True/False,                                     │ │
│  │     termination_reason=...,                                 │ │
│  │     steps_executed=N,                                       │ │
│  │     final_state={...},                                      │ │
│  │ )                                                            │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘
                              ↓
┌────────────────────────────────────────────────────────────────────┐
│                     7. RESULT TO USER                              │
│  ┌──────────────────────────────────────────────────────────────┐ │
│  │ if result.success:                                          │ │
│  │     print(f"Completed in {result.steps_executed} steps")   │ │
│  │ else:                                                        │ │
│  │     print(f"Failed: {result.error_message}")               │ │
│  │                                                              │ │
│  │ # View execution history                                    │ │
│  │ decisions = agent_run.decisions.all()                       │ │
│  │ executions = agent_run.tool_executions.all()                │ │
│  └──────────────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════
HUMAN-IN-THE-LOOP FLOW
═══════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────┐
│ Loop encounters REQUEST_HUMAN decision                              │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ agent_run.status = 'waiting_for_human'                              │
│ agent_run.human_intervention_required = True                        │
│ agent_run.human_intervention_reason = "..."                         │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Loop returns PAUSED                                                 │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Human reviews via UI or API                                         │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ agent_run.human_intervention_response = {'approved': True}          │
│ agent_run.save()                                                    │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ await AgentLoopRunner.resume_loop(agent_run)                        │
└─────────────────────────────────────────────────────────────────────┘
                               ↓
┌─────────────────────────────────────────────────────────────────────┐
│ Loop continues from where it paused                                 │
└─────────────────────────────────────────────────────────────────────┘


═══════════════════════════════════════════════════════════════════════
KEY SAFETY GUARANTEES
═══════════════════════════════════════════════════════════════════════

🛡️  BOUNDED EXECUTION
   • Loop ALWAYS terminates (max_steps)
   • No while True loops
   • Explicit termination reasons

🛡️  PLANNER ISOLATION
   • Planner returns decisions ONLY
   • Cannot execute nodes directly
   • No access to NodeToolExecutor

🛡️  GRAPH CONSTRAINTS
   • Guardrails validate dependencies
   • DAG structure enforced
   • No circular dependencies

🛡️  IMMUTABILITY
   • Runtime spec is read-only
   • Pipeline definitions not modified
   • Node code not changed

🛡️  OBSERVABILITY
   • All decisions recorded (AgentDecision)
   • All executions tracked (ToolExecution)
   • Complete audit trail

🛡️  EXPLICIT TERMINATION
   • Every run has LoopResult
   • Termination reason recorded
   • Status updated in database
