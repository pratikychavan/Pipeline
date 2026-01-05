"""
LLM Planner Example

This example shows how to use the LLMPlanner with different LLM providers.
"""

import asyncio
from typing import Dict, Any, List
from warpdrive_agent_sdk import LLMPlanner, LLMClient, PlannerInput


# ============================================================================
# EXAMPLE LLM CLIENTS
# ============================================================================

class OpenAIClientExample:
    """
    Example OpenAI client implementation.
    
    This shows how to integrate OpenAI's API with the LLMPlanner.
    """
    
    def __init__(self, api_key: str):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key
        """
        self.api_key = api_key
        # In real usage: from openai import AsyncOpenAI
        # self.client = AsyncOpenAI(api_key=api_key)
    
    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Dict[str, Any]:
        """
        Create completion using OpenAI API.
        
        In real usage, this would call OpenAI's API.
        """
        # Real implementation:
        # response = await self.client.chat.completions.create(
        #     model=model,
        #     messages=messages,
        #     max_tokens=max_tokens,
        #     temperature=temperature,
        #     timeout=timeout
        # )
        # return {'content': response.choices[0].message.content}
        
        # Mock response for example
        return {
            'content': '''{
                "decision_type": "execute_tool",
                "tool_id": "validate_data",
                "reasoning": "Starting with data validation",
                "confidence": 0.95
            }'''
        }


class AnthropicClientExample:
    """
    Example Anthropic (Claude) client implementation.
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        # In real usage: import anthropic
        # self.client = anthropic.AsyncAnthropic(api_key=api_key)
    
    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Dict[str, Any]:
        """
        Create completion using Anthropic API.
        """
        # Real implementation:
        # message = await self.client.messages.create(
        #     model=model,
        #     max_tokens=max_tokens,
        #     temperature=temperature,
        #     messages=messages,
        #     timeout=timeout
        # )
        # return {'content': message.content[0].text}
        
        # Mock response
        return {
            'content': '''{
                "decision_type": "execute_tool",
                "tool_id": "validate_data",
                "reasoning": "Starting with data validation",
                "confidence": 0.95
            }'''
        }


class MockLLMClient:
    """
    Mock LLM client for testing without API calls.
    """
    
    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Dict[str, Any]:
        """Return a mock decision."""
        return {
            'content': '''{
                "decision_type": "execute_tool",
                "tool_id": "test_tool",
                "reasoning": "Mock decision for testing",
                "confidence": 1.0
            }'''
        }


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

async def example_openai_planner():
    """
    Example: Using LLMPlanner with OpenAI.
    """
    # Create OpenAI client
    client = OpenAIClientExample(api_key='your-api-key')
    
    # Create planner
    planner = LLMPlanner(
        llm_client=client,
        model='gpt-4o-mini',
        temperature=0.3,
        max_tokens=2000,
        timeout=30.0
    )
    
    # Create mock planner input
    planner_input = PlannerInput(
        runtime_spec={
            'available_tools': [
                {
                    'tool_id': 'validate_data',
                    'name': 'Data Validation',
                    'description': 'Validate incoming data'
                },
                {
                    'tool_id': 'process_data',
                    'name': 'Data Processing',
                    'description': 'Process validated data'
                }
            ],
            'execution_constraints': []
        },
        execution_history=[],
        current_state={},
        step_number=0
    )
    
    # Get decision
    decision = await planner.plan_next_action(planner_input)
    
    print("OpenAI Planner Decision:")
    print(f"  Type: {decision.decision_type.value}")
    print(f"  Tool: {decision.tool_id}")
    print(f"  Reasoning: {decision.reasoning}")
    print(f"  Confidence: {decision.confidence}")
    
    return decision


async def example_anthropic_planner():
    """
    Example: Using LLMPlanner with Anthropic Claude.
    """
    client = AnthropicClientExample(api_key='your-api-key')
    
    planner = LLMPlanner(
        llm_client=client,
        model='claude-3-opus-20240229',
        temperature=0.2,
        max_tokens=1500
    )
    
    # Mock input
    planner_input = PlannerInput(
        runtime_spec={'available_tools': []},
        execution_history=[],
        current_state={},
        step_number=0
    )
    
    decision = await planner.plan_next_action(planner_input)
    
    print("\nAnthropic Planner Decision:")
    print(f"  Type: {decision.decision_type.value}")
    print(f"  Tool: {decision.tool_id}")
    
    return decision


async def example_custom_system_prompt():
    """
    Example: Using custom system prompt for domain-specific planning.
    """
    client = MockLLMClient()
    
    custom_prompt = """You are a financial transaction planner. Your job is to:
1. Always validate transactions first
2. Check for fraud risk
3. Only process if validation and fraud checks pass
4. Never skip security checks

Return decisions in JSON format as specified."""
    
    planner = LLMPlanner(
        llm_client=client,
        model='gpt-4o-mini',
        temperature=0.1,  # Very low for financial operations
        system_prompt=custom_prompt
    )
    
    planner_input = PlannerInput(
        runtime_spec={
            'available_tools': [
                {'tool_id': 'validate_transaction', 'name': 'Validate'},
                {'tool_id': 'check_fraud', 'name': 'Fraud Check'},
                {'tool_id': 'process_payment', 'name': 'Process'}
            ]
        },
        execution_history=[],
        current_state={},
        step_number=0
    )
    
    decision = await planner.plan_next_action(planner_input)
    
    print("\nCustom Prompt Planner Decision:")
    print(f"  Type: {decision.decision_type.value}")
    print(f"  Tool: {decision.tool_id}")
    
    return decision


async def example_error_handling():
    """
    Example: Handling LLM errors gracefully.
    """
    class FailingClient:
        """Client that simulates failures."""
        async def create_completion(self, *args, **kwargs):
            raise TimeoutError("LLM call timed out")
    
    planner = LLMPlanner(
        llm_client=FailingClient(),
        model='gpt-4o-mini',
        timeout=5.0
    )
    
    planner_input = PlannerInput(
        runtime_spec={'available_tools': []},
        execution_history=[],
        current_state={},
        step_number=0
    )
    
    # Planner will return a FAIL decision instead of raising exception
    decision = await planner.plan_next_action(planner_input)
    
    print("\nError Handling Example:")
    print(f"  Type: {decision.decision_type.value}")
    print(f"  Reasoning: {decision.reasoning}")
    
    return decision


async def main():
    """
    Run all examples.
    """
    print("=" * 60)
    print("LLM Planner Examples")
    print("=" * 60)
    
    await example_openai_planner()
    await example_anthropic_planner()
    await example_custom_system_prompt()
    await example_error_handling()
    
    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == '__main__':
    asyncio.run(main())
