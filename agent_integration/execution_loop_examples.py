"""
Agent Execution Loop - Usage Examples

This file demonstrates how to use the agent execution loop.
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

import asyncio
from datetime import datetime

from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentRun, RuntimeSpec
from agent_integration.runtime_spec_builder import RuntimeSpecService
from agent_integration.execution_loop import (
    AgentExecutionLoop,
    AgentLoopRunner,
    DeterministicPlanner,
    Planner,
    PlannerDecision,
    PlannerDecisionType,
)


# ============================================================================
# EXAMPLE 1: Basic execution loop with deterministic planner
# ============================================================================

async def example_basic_loop():
    """
    Basic example: Run pipeline with deterministic planner.
    
    This is the simplest way to run an agent-controlled pipeline.
    """
    print("="*70)
    print("EXAMPLE 1: Basic Execution Loop")
    print("="*70)
    
    # Get a pipeline
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found. Create one first.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    print(f"Nodes: {pipeline.nodes.count()}")
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=100,
    )
    
    print(f"\nAgent Run ID: {agent_run.id}")
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
        agent_run=agent_run,
        agent_profile=None,  # No agent profile
    )
    
    print(f"Runtime Spec: {runtime_spec.spec_version}")
    print(f"Tools: {len(runtime_spec.spec_data['available_tools'])}")
    
    # Run loop with deterministic planner
    result = await AgentLoopRunner.start_loop(agent_run)
    
    print(f"\n✅ Loop completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps: {result.steps_executed}")
    print(f"Success: {result.success}")
    
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    # Refresh agent run
    agent_run.refresh_from_db()
    print(f"\nFinal status: {agent_run.status}")
    print(f"Decisions made: {agent_run.decisions.count()}")
    print(f"Tools executed: {agent_run.tool_executions.count()}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 2: Custom planner implementation
# ============================================================================

class CustomPlanner(Planner):
    """
    Custom planner that executes tools in reverse order.
    
    This is a demonstration of how to implement a custom planner.
    """
    
    async def plan_next_action(
        self,
        runtime_spec,
        execution_history,
        current_state,
    ):
        """Plan next action - execute tools in reverse order."""
        
        # Get available tools
        available_tools = runtime_spec.get('available_tools', [])
        if not available_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="No tools available",
            )
        
        # Build set of executed tool IDs
        executed_tool_ids = {
            exec_record['tool_id']
            for exec_record in execution_history
            if exec_record.get('success', False)
        }
        
        # Execute tools in reverse order
        for tool in reversed(available_tools):
            tool_id = tool['tool_id']
            
            if tool_id not in executed_tool_ids:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=tool_id,
                    tool_parameters={},
                    reasoning=f"Execute tool '{tool['tool_name']}' (reverse order)",
                    confidence=1.0,
                )
        
        # All tools executed
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed",
        )


async def example_custom_planner():
    """
    Example: Run pipeline with custom planner.
    """
    print("="*70)
    print("EXAMPLE 2: Custom Planner")
    print("="*70)
    
    # Get a pipeline
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found. Create one first.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=50,
    )
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
        agent_run=agent_run,
    )
    
    print(f"\nUsing CustomPlanner (reverse order)")
    
    # Run loop with custom planner
    custom_planner = CustomPlanner()
    result = await AgentLoopRunner.start_loop(agent_run, planner=custom_planner)
    
    print(f"\n✅ Loop completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps: {result.steps_executed}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 3: Human-in-the-loop
# ============================================================================

class HumanApprovalPlanner(Planner):
    """
    Planner that requests human approval after certain steps.
    """
    
    async def plan_next_action(
        self,
        runtime_spec,
        execution_history,
        current_state,
    ):
        """Plan next action with human approval checkpoints."""
        
        # After 3 tools, request human approval
        if len(execution_history) == 3:
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                reasoning="Requesting human approval after 3 tools",
                human_message="Please review execution and approve continuation",
            )
        
        # Otherwise, use deterministic planning
        available_tools = runtime_spec.get('available_tools', [])
        executed_tool_ids = {
            exec_record['tool_id']
            for exec_record in execution_history
        }
        
        for tool in available_tools:
            if tool['tool_id'] not in executed_tool_ids:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=tool['tool_id'],
                    tool_parameters={},
                    reasoning=f"Execute tool '{tool['tool_name']}'",
                )
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed",
        )


async def example_human_in_the_loop():
    """
    Example: Run pipeline with human approval checkpoints.
    """
    print("="*70)
    print("EXAMPLE 3: Human-in-the-Loop")
    print("="*70)
    
    # Get a pipeline with multiple nodes
    pipeline = Pipeline.objects.annotate(
        node_count=models.Count('nodes')
    ).filter(node_count__gte=3).first()
    
    if not pipeline:
        print("No pipeline with 3+ nodes found.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    print(f"Nodes: {pipeline.nodes.count()}")
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=100,
    )
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
    
    print(f"\nUsing HumanApprovalPlanner")
    
    # Run loop
    planner = HumanApprovalPlanner()
    result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
    
    print(f"\n✅ Loop paused")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps: {result.steps_executed}")
    
    # Refresh agent run
    agent_run.refresh_from_db()
    print(f"\nStatus: {agent_run.status}")
    print(f"Human intervention required: {agent_run.human_intervention_required}")
    print(f"Reason: {agent_run.human_intervention_reason}")
    
    # Simulate human approval
    print("\n[Simulating human approval...]")
    agent_run.human_intervention_response = {'approved': True}
    agent_run.save()
    
    # Resume loop
    print("\nResuming loop...")
    result = await AgentLoopRunner.resume_loop(agent_run)
    
    print(f"\n✅ Loop resumed and completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Total steps: {result.steps_executed}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 4: Monitoring loop execution
# ============================================================================

async def example_monitoring():
    """
    Example: Monitor loop execution in real-time.
    """
    print("="*70)
    print("EXAMPLE 4: Monitoring Loop Execution")
    print("="*70)
    
    # Get a pipeline
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found.")
        return
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=100,
    )
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
    
    print(f"\nPipeline: {pipeline.name}")
    print(f"Agent Run: {agent_run.id}")
    print(f"\nStarting loop...")
    
    # Run loop
    result = await AgentLoopRunner.start_loop(agent_run)
    
    # Refresh agent run
    agent_run.refresh_from_db()
    
    print(f"\n{'='*70}")
    print("EXECUTION SUMMARY")
    print('='*70)
    
    print(f"\nStatus: {agent_run.status}")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps executed: {result.steps_executed}")
    print(f"Success: {result.success}")
    
    # Show decisions
    print(f"\n{'='*70}")
    print("DECISIONS")
    print('='*70)
    
    decisions = agent_run.decisions.order_by('step_number')
    for decision in decisions:
        print(f"\nStep {decision.step_number}:")
        print(f"  Type: {decision.decision_type}")
        print(f"  Reasoning: {decision.reasoning}")
        print(f"  Confidence: {decision.confidence}")
        
        if decision.guardrail_violations:
            print(f"  ⚠️  Violations: {len(decision.guardrail_violations)}")
    
    # Show tool executions
    print(f"\n{'='*70}")
    print("TOOL EXECUTIONS")
    print('='*70)
    
    tool_executions = agent_run.tool_executions.order_by('queued_at')
    for tool_exec in tool_executions:
        print(f"\n{tool_exec.tool_name}:")
        print(f"  Status: {tool_exec.status}")
        print(f"  Queued: {tool_exec.queued_at}")
        print(f"  Started: {tool_exec.started_at}")
        print(f"  Completed: {tool_exec.completed_at}")
        
        if tool_exec.result_summary:
            print(f"  Result: {tool_exec.result_summary[:100]}...")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 5: With agent profile
# ============================================================================

async def example_with_agent_profile():
    """
    Example: Run loop with agent profile configuration.
    """
    print("="*70)
    print("EXAMPLE 5: With Agent Profile")
    print("="*70)
    
    from agent_integration.control_plane_models import AgentProfile
    
    # Get pipeline and agent profile
    pipeline = Pipeline.objects.first()
    agent_profile = AgentProfile.objects.filter(status='active').first()
    
    if not pipeline or not agent_profile:
        print("Pipeline or agent profile not found.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    print(f"Agent: {agent_profile.name}")
    print(f"Max steps: {agent_profile.max_steps}")
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=agent_profile.max_steps,
        agent_config={
            'model': agent_profile.model_name,
            'temperature': agent_profile.temperature,
        },
    )
    
    # Create runtime spec with agent profile
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
        agent_run=agent_run,
        agent_profile=agent_profile,
    )
    
    print(f"\nRuntime spec includes:")
    print(f"  Tools: {len(runtime_spec.spec_data['available_tools'])}")
    print(f"  Conditions: {len(runtime_spec.spec_data['business_conditions'])}")
    print(f"  Max steps: {runtime_spec.spec_data['execution_constraints']['max_steps']}")
    
    # Get retry policy
    retry_policy = runtime_spec.spec_data['agent_configuration'].get('retry_policy', {})
    if retry_policy:
        print(f"  Retry policy: max {retry_policy.get('max_retries', 0)} retries")
    
    # Run loop
    result = await AgentLoopRunner.start_loop(agent_run)
    
    print(f"\n✅ Loop completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps: {result.steps_executed}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 6: Error handling and retries
# ============================================================================

class ErrorProneNode:
    """Simulate a node that fails sometimes."""
    pass


async def example_error_handling():
    """
    Example: Handle errors and retries.
    
    This demonstrates how the loop handles execution errors.
    """
    print("="*70)
    print("EXAMPLE 6: Error Handling and Retries")
    print("="*70)
    
    from agent_integration.control_plane_models import AgentProfile
    
    # Get pipeline
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found.")
        return
    
    # Get or create agent profile with retry policy
    agent_profile, _ = AgentProfile.objects.get_or_create(
        name="Resilient Agent",
        defaults={
            'description': "Agent with retry policy",
            'status': 'active',
            'max_steps': 100,
            'model_name': 'gpt-4',
            'retry_policy': {
                'max_retries': 3,
                'backoff_multiplier': 2.0,
            },
        },
    )
    
    print(f"\nAgent: {agent_profile.name}")
    print(f"Retry policy: {agent_profile.retry_policy}")
    
    # Create pipeline execution
    pipeline_execution = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
        status='pending',
    )
    
    # Create agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_execution,
        status='initializing',
        max_steps=agent_profile.max_steps,
    )
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
        agent_run=agent_run,
        agent_profile=agent_profile,
    )
    
    print(f"\nRuntime spec max retries: {runtime_spec.spec_data['agent_configuration']['retry_policy']['max_retries']}")
    
    # Run loop
    print("\nRunning loop...")
    result = await AgentLoopRunner.start_loop(agent_run)
    
    print(f"\n✅ Loop completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Success: {result.success}")
    
    if result.error_message:
        print(f"Error: {result.error_message}")
    
    # Show retry attempts
    agent_run.refresh_from_db()
    tool_executions = agent_run.tool_executions.all()
    
    print(f"\nTool execution attempts:")
    for tool_exec in tool_executions:
        print(f"  {tool_exec.tool_name}: {tool_exec.status}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

async def run_all_examples():
    """Run all examples sequentially."""
    print("\n")
    print("*" * 70)
    print("AGENT EXECUTION LOOP - EXAMPLES")
    print("*" * 70)
    print("\n")
    
    # Check if there are pipelines
    from django.db.models import Count
    
    pipeline_count = Pipeline.objects.count()
    if pipeline_count == 0:
        print("⚠️  No pipelines found. Please create a pipeline first.")
        print("   You can create one via the Django admin or Control Plane UI.")
        return
    
    print(f"Found {pipeline_count} pipeline(s)\n")
    
    try:
        await example_basic_loop()
        await example_custom_planner()
        # await example_human_in_the_loop()  # Uncomment if you have pipelines with 3+ nodes
        await example_monitoring()
        await example_with_agent_profile()
        # await example_error_handling()  # Uncomment to test error handling
        
        print("\n")
        print("*" * 70)
        print("ALL EXAMPLES COMPLETED")
        print("*" * 70)
        print("\n")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    # Import required for annotation
    from django.db import models
    
    # Run examples
    asyncio.run(run_all_examples())
