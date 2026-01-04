"""
LLM Planner - Usage Examples

This file demonstrates how to use the LLM planner.
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

import asyncio

from agent_integration.llm_planner import (
    LLMPlanner,
    MockLLMClient,
    OpenAIClient,
    AnthropicClient,
)
from agent_integration.execution_loop import (
    AgentLoopRunner,
    DeterministicPlanner,
)
from core.models import Pipeline, PipelineExecution
from agent_integration.models import AgentRun
from agent_integration.runtime_spec_builder import RuntimeSpecService


# ============================================================================
# EXAMPLE 1: Basic LLM Planner with Mock Client
# ============================================================================

async def example_basic_llm_planner():
    """
    Basic example: Use LLM planner with mock client.
    
    This demonstrates the simplest way to use the LLM planner.
    """
    print("="*70)
    print("EXAMPLE 1: Basic LLM Planner with Mock Client")
    print("="*70)
    
    # Get pipeline
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
        max_steps=20,
    )
    
    # Create runtime spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
    
    print(f"Tools available: {len(runtime_spec.spec_data['available_tools'])}")
    
    # Create mock LLM client with predefined responses
    # In production, you would use OpenAIClient or AnthropicClient
    mock_responses = []
    
    # Generate responses for each tool
    for tool in runtime_spec.spec_data['available_tools']:
        response = {
            'action': 'tool',
            'tool_name': tool['tool_name'],
            'arguments': {},
            'reasoning': f"Execute {tool['tool_name']} as next step",
        }
        mock_responses.append(json.dumps(response))
    
    # Add final response
    mock_responses.append('{"action": "final", "reasoning": "All tools executed successfully"}')
    
    llm_client = MockLLMClient(mock_responses)
    
    # Create LLM planner
    llm_planner = LLMPlanner(
        llm_client=llm_client,
        model='mock-gpt-4',
        objective='Complete the pipeline execution successfully',
        max_tokens=1000,
        temperature=0.3,
    )
    
    print("\nUsing LLM planner (mock)")
    
    # Run loop with LLM planner
    result = await AgentLoopRunner.start_loop(agent_run, planner=llm_planner)
    
    print(f"\n✅ Loop completed")
    print(f"Termination: {result.termination_reason.value}")
    print(f"Steps: {result.steps_executed}")
    print(f"Success: {result.success}")
    
    # Review decisions
    agent_run.refresh_from_db()
    print(f"\nDecisions made: {agent_run.decisions.count()}")
    
    for decision in agent_run.decisions.all()[:5]:
        print(f"  Step {decision.step_number}: {decision.decision_type} - {decision.reasoning[:50]}...")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 2: LLM Planner vs Deterministic Planner
# ============================================================================

async def example_planner_comparison():
    """
    Compare LLM planner with deterministic planner.
    """
    print("="*70)
    print("EXAMPLE 2: LLM Planner vs Deterministic Planner")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    
    # Test with deterministic planner
    print("\n--- Test 1: Deterministic Planner ---")
    
    pe1 = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
    )
    ar1 = AgentRun.objects.create(pipeline_execution=pe1, max_steps=20)
    RuntimeSpecService.create_spec_for_agent_run(ar1)
    
    det_planner = DeterministicPlanner()
    result1 = await AgentLoopRunner.start_loop(ar1, planner=det_planner)
    
    print(f"Result: {result1.termination_reason.value}")
    print(f"Steps: {result1.steps_executed}")
    
    # Test with LLM planner
    print("\n--- Test 2: LLM Planner (Mock) ---")
    
    pe2 = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=pipeline.created_by,
    )
    ar2 = AgentRun.objects.create(pipeline_execution=pe2, max_steps=20)
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(ar2)
    
    # Create mock responses
    import json
    responses = []
    for tool in runtime_spec.spec_data['available_tools']:
        responses.append(json.dumps({
            'action': 'tool',
            'tool_name': tool['tool_name'],
            'arguments': {},
            'reasoning': f"LLM decides to execute {tool['tool_name']}",
        }))
    responses.append('{"action": "final", "reasoning": "LLM decides work is complete"}')
    
    llm_client = MockLLMClient(responses)
    llm_planner = LLMPlanner(llm_client, model='mock')
    
    result2 = await AgentLoopRunner.start_loop(ar2, planner=llm_planner)
    
    print(f"Result: {result2.termination_reason.value}")
    print(f"Steps: {result2.steps_executed}")
    
    # Compare
    print("\n--- Comparison ---")
    print(f"Deterministic: {result1.steps_executed} steps")
    print(f"LLM: {result2.steps_executed} steps")
    print(f"Both completed successfully: {result1.success and result2.success}")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 3: LLM Planner Error Handling
# ============================================================================

async def example_error_handling():
    """
    Demonstrate LLM planner error handling.
    """
    print("="*70)
    print("EXAMPLE 3: LLM Planner Error Handling")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found.")
        return
    
    # Test 1: Invalid JSON response
    print("\n--- Test 1: Invalid JSON ---")
    
    pe1 = PipelineExecution.objects.create(pipeline=pipeline, started_by=pipeline.created_by)
    ar1 = AgentRun.objects.create(pipeline_execution=pe1, max_steps=5)
    RuntimeSpecService.create_spec_for_agent_run(ar1)
    
    invalid_client = MockLLMClient(['This is not valid JSON'])
    invalid_planner = LLMPlanner(invalid_client)
    
    result1 = await AgentLoopRunner.start_loop(ar1, planner=invalid_planner)
    
    print(f"Result: {result1.termination_reason.value}")
    print(f"Error handled safely: {not result1.success}")
    
    ar1.refresh_from_db()
    last_decision = ar1.decisions.last()
    if last_decision:
        print(f"Decision: {last_decision.decision_type}")
        print(f"Reasoning: {last_decision.reasoning[:100]}...")
    
    # Test 2: Unknown tool
    print("\n--- Test 2: Unknown Tool ---")
    
    pe2 = PipelineExecution.objects.create(pipeline=pipeline, started_by=pipeline.created_by)
    ar2 = AgentRun.objects.create(pipeline_execution=pe2, max_steps=5)
    RuntimeSpecService.create_spec_for_agent_run(ar2)
    
    import json
    unknown_tool_response = json.dumps({
        'action': 'tool',
        'tool_name': 'NonExistentTool',
        'arguments': {},
        'reasoning': 'Try to use unknown tool',
    })
    
    unknown_client = MockLLMClient([unknown_tool_response])
    unknown_planner = LLMPlanner(unknown_client)
    
    result2 = await AgentLoopRunner.start_loop(ar2, planner=unknown_planner)
    
    print(f"Result: {result2.termination_reason.value}")
    
    ar2.refresh_from_db()
    last_decision = ar2.decisions.last()
    if last_decision:
        print(f"Decision: {last_decision.decision_type}")
        print(f"Reasoning: {last_decision.reasoning[:100]}...")
    
    # Test 3: Timeout
    print("\n--- Test 3: Timeout ---")
    
    from unittest.mock import Mock
    
    async def slow_completion(*args, **kwargs):
        await asyncio.sleep(2.0)
        return {'content': '{"action": "final"}'}
    
    timeout_client = Mock()
    timeout_client.create_completion = slow_completion
    
    pe3 = PipelineExecution.objects.create(pipeline=pipeline, started_by=pipeline.created_by)
    ar3 = AgentRun.objects.create(pipeline_execution=pe3, max_steps=5)
    RuntimeSpecService.create_spec_for_agent_run(ar3)
    
    timeout_planner = LLMPlanner(timeout_client, timeout_seconds=0.1)
    
    result3 = await AgentLoopRunner.start_loop(ar3, planner=timeout_planner)
    
    print(f"Result: {result3.termination_reason.value}")
    
    ar3.refresh_from_db()
    last_decision = ar3.decisions.last()
    if last_decision:
        print(f"Decision: {last_decision.decision_type}")
        print(f"Reasoning: {last_decision.reasoning[:100]}...")
    
    print("\n✅ All errors handled safely without crashes")
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 4: Custom LLM Client (Stub for OpenAI)
# ============================================================================

async def example_openai_client_stub():
    """
    Demonstrate how to use OpenAI client (stub).
    
    This shows the interface for real LLM integration.
    """
    print("="*70)
    print("EXAMPLE 4: OpenAI Client Interface (Stub)")
    print("="*70)
    
    print("\nTo use OpenAI client:")
    print("1. Install: pip install openai")
    print("2. Set API key: export OPENAI_API_KEY='sk-...'")
    print("3. Create client:")
    print()
    print("   from agent_integration.llm_planner import OpenAIClient, LLMPlanner")
    print()
    print("   client = OpenAIClient(api_key='sk-...')")
    print("   planner = LLMPlanner(")
    print("       llm_client=client,")
    print("       model='gpt-4',")
    print("       objective='Complete pipeline execution',")
    print("       max_tokens=1000,")
    print("       temperature=0.3,")
    print("       timeout_seconds=30.0,")
    print("   )")
    print()
    print("   result = await AgentLoopRunner.start_loop(agent_run, planner=planner)")
    print()
    print("Note: OpenAIClient requires 'openai' library (not installed by default)")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# EXAMPLE 5: Fallback from LLM to Deterministic
# ============================================================================

async def example_fallback_strategy():
    """
    Demonstrate fallback from LLM to deterministic planner.
    """
    print("="*70)
    print("EXAMPLE 5: Fallback Strategy")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("No pipeline found.")
        return
    
    print(f"\nPipeline: {pipeline.name}")
    
    # Try LLM planner first
    print("\n--- Attempt 1: LLM Planner ---")
    
    pe1 = PipelineExecution.objects.create(pipeline=pipeline, started_by=pipeline.created_by)
    ar1 = AgentRun.objects.create(pipeline_execution=pe1, max_steps=20)
    RuntimeSpecService.create_spec_for_agent_run(ar1)
    
    # Simulate LLM failure
    failing_client = MockLLMClient(['invalid json that will fail'])
    llm_planner = LLMPlanner(failing_client)
    
    result1 = await AgentLoopRunner.start_loop(ar1, planner=llm_planner)
    
    print(f"Result: {result1.termination_reason.value}")
    print(f"Success: {result1.success}")
    
    if not result1.success:
        print("\n--- Attempt 2: Fallback to Deterministic Planner ---")
        
        pe2 = PipelineExecution.objects.create(pipeline=pipeline, started_by=pipeline.created_by)
        ar2 = AgentRun.objects.create(pipeline_execution=pe2, max_steps=20)
        RuntimeSpecService.create_spec_for_agent_run(ar2)
        
        det_planner = DeterministicPlanner()
        result2 = await AgentLoopRunner.start_loop(ar2, planner=det_planner)
        
        print(f"Result: {result2.termination_reason.value}")
        print(f"Success: {result2.success}")
        
        print("\n✅ Successfully fell back to deterministic planner")
    
    print("\n" + "="*70 + "\n")


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

async def run_all_examples():
    """Run all examples sequentially."""
    import json
    
    print("\n")
    print("*" * 70)
    print("LLM PLANNER - USAGE EXAMPLES")
    print("*" * 70)
    print("\n")
    
    # Check if there are pipelines
    pipeline_count = Pipeline.objects.count()
    if pipeline_count == 0:
        print("⚠️  No pipelines found. Please create a pipeline first.")
        return
    
    print(f"Found {pipeline_count} pipeline(s)\n")
    
    try:
        await example_basic_llm_planner()
        await example_planner_comparison()
        await example_error_handling()
        await example_openai_client_stub()
        await example_fallback_strategy()
        
        print("\n")
        print("*" * 70)
        print("ALL EXAMPLES COMPLETED")
        print("*" * 70)
        print("\n")
        print("Key Takeaways:")
        print("1. LLMPlanner is plug-and-play with execution loop")
        print("2. Errors are handled safely (no crashes)")
        print("3. Falls back to deterministic planner if needed")
        print("4. Supports OpenAI, Anthropic, and custom clients")
        print("5. All decisions are observable and auditable")
        print("\n")
        
    except Exception as e:
        print(f"\n❌ Error running examples: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(run_all_examples())
