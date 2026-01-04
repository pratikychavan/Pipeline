"""
Tests for LLM Planner

Comprehensive test suite for the LLM-based planner.
"""

from django.test import TestCase
from unittest.mock import Mock, AsyncMock, patch
import asyncio
import json

from agent_integration.llm_planner import (
    LLMPlanner,
    MockLLMClient,
    PromptBuilder,
    OutputParser,
    LLMPlannerFailure,
)
from agent_integration.execution_loop import (
    PlannerDecision,
    PlannerDecisionType,
)


class PromptBuilderTests(TestCase):
    """Tests for PromptBuilder."""
    
    def test_build_system_prompt(self):
        """Test system prompt generation."""
        objective = "Complete data processing pipeline"
        prompt = PromptBuilder.build_system_prompt(objective)
        
        self.assertIn(objective, prompt)
        self.assertIn("JSON", prompt)
        self.assertIn("action", prompt)
        self.assertIn("tool", prompt)
        self.assertIn("final", prompt)
    
    def test_build_tools_section_empty(self):
        """Test tools section with no tools."""
        section = PromptBuilder.build_tools_section([])
        
        self.assertIn("None", section)
    
    def test_build_tools_section_with_tools(self):
        """Test tools section with tools."""
        tools = [
            {
                'tool_name': 'LoadData',
                'tool_id': 'tool-1',
                'description': 'Load data from source',
                'input_variables': ['source'],
            },
            {
                'tool_name': 'ProcessData',
                'tool_id': 'tool-2',
                'description': 'Process loaded data',
                'input_variables': ['data'],
                'agent_constraints': {
                    'is_allowed': True,
                    'max_calls': 1,
                },
            },
        ]
        
        section = PromptBuilder.build_tools_section(tools)
        
        self.assertIn('LoadData', section)
        self.assertIn('ProcessData', section)
        self.assertIn('tool-1', section)
        self.assertIn('max_calls', section)
    
    def test_build_history_section_empty(self):
        """Test history section with no history."""
        section = PromptBuilder.build_history_section([])
        
        self.assertIn("None", section)
        self.assertIn("first decision", section)
    
    def test_build_history_section_with_history(self):
        """Test history section with execution history."""
        history = [
            {
                'tool_name': 'LoadData',
                'success': True,
                'output': 'Loaded 100 records',
            },
            {
                'tool_name': 'ProcessData',
                'success': True,
                'output': 'Processed 100 records successfully',
            },
        ]
        
        section = PromptBuilder.build_history_section(history)
        
        self.assertIn('LoadData', section)
        self.assertIn('ProcessData', section)
        self.assertIn('step', section)
    
    def test_build_state_section(self):
        """Test state section."""
        state = {
            'step': 5,
            'completed_tools': [
                {'tool_name': 'tool-1'},
                {'tool_name': 'tool-2'},
            ],
            'variables': {'data': 'sensitive_value', 'count': 100},
        }
        
        section = PromptBuilder.build_state_section(state)
        
        # Should include step and count
        self.assertIn('5', section)
        self.assertIn('2', section)
        
        # Should include variable names but not values (for safety)
        self.assertIn('data', section)
        self.assertIn('count', section)
        self.assertNotIn('sensitive_value', section)  # Value should not be included
    
    def test_build_user_prompt(self):
        """Test complete user prompt."""
        runtime_spec = {
            'execution_constraints': {'max_steps': 100},
            'agent_config': {},
            'available_tools': [
                {'tool_name': 'TestTool', 'tool_id': 'tool-1', 'agent_constraints': {}},
            ],
        }
        history = []
        state = {'step': 0, 'completed_tools': [], 'variables': {}}
        
        prompt = PromptBuilder.build_user_prompt(runtime_spec, history, state)
        
        self.assertIn('TestTool', prompt)
        self.assertIn('first decision', prompt)
        self.assertIn('JSON', prompt)


class OutputParserTests(TestCase):
    """Tests for OutputParser."""
    
    def test_parse_valid_json(self):
        """Test parsing valid JSON response."""
        response = '{"action": "tool", "tool_name": "LoadData", "arguments": {}, "reasoning": "Start loading"}'
        
        result = OutputParser.parse_response(response)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['action'], 'tool')
        self.assertEqual(result['tool_name'], 'LoadData')
    
    def test_parse_json_with_markdown(self):
        """Test parsing JSON wrapped in markdown code blocks."""
        response = '''```json
{
  "action": "tool",
  "tool_name": "LoadData",
  "arguments": {},
  "reasoning": "Start loading"
}
```'''
        
        result = OutputParser.parse_response(response)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result['action'], 'tool')
    
    def test_parse_invalid_json(self):
        """Test parsing invalid JSON."""
        response = 'This is not JSON'
        
        result = OutputParser.parse_response(response)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'invalid_json')
    
    def test_parse_empty_response(self):
        """Test parsing empty response."""
        result = OutputParser.parse_response('')
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'empty_response')
    
    def test_validate_schema_valid(self):
        """Test schema validation with valid data."""
        data = {
            'action': 'tool',
            'tool_name': 'LoadData',
            'arguments': {},
            'reasoning': 'Test',
        }
        
        result = OutputParser.validate_schema(data)
        
        self.assertIsInstance(result, dict)
        self.assertEqual(result, data)
    
    def test_validate_schema_missing_action(self):
        """Test schema validation with missing action."""
        data = {
            'tool_name': 'LoadData',
        }
        
        result = OutputParser.validate_schema(data)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'missing_field')
    
    def test_validate_schema_invalid_action(self):
        """Test schema validation with invalid action."""
        data = {
            'action': 'invalid',
        }
        
        result = OutputParser.validate_schema(data)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'invalid_action')
    
    def test_validate_schema_tool_without_name(self):
        """Test schema validation for tool action without tool_name."""
        data = {
            'action': 'tool',
            'arguments': {},
        }
        
        result = OutputParser.validate_schema(data)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'missing_tool_name')
    
    def test_validate_schema_invalid_arguments(self):
        """Test schema validation with invalid arguments type."""
        data = {
            'action': 'tool',
            'tool_name': 'LoadData',
            'arguments': 'not a dict',
        }
        
        result = OutputParser.validate_schema(data)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'invalid_arguments')
    
    def test_to_planner_decision_final(self):
        """Test converting 'final' action to PlannerDecision."""
        data = {
            'action': 'final',
            'reasoning': 'All work complete',
        }
        
        decision = OutputParser.to_planner_decision(data, [])
        
        self.assertIsInstance(decision, PlannerDecision)
        self.assertEqual(decision.decision_type, PlannerDecisionType.COMPLETE)
    
    def test_to_planner_decision_noop(self):
        """Test converting 'noop' action to PlannerDecision."""
        data = {
            'action': 'noop',
            'reasoning': 'Cannot proceed',
        }
        
        decision = OutputParser.to_planner_decision(data, [])
        
        self.assertIsInstance(decision, PlannerDecision)
        self.assertEqual(decision.decision_type, PlannerDecisionType.REQUEST_HUMAN)
    
    def test_to_planner_decision_tool(self):
        """Test converting 'tool' action to PlannerDecision."""
        data = {
            'action': 'tool',
            'tool_name': 'LoadData',
            'arguments': {'source': 'db'},
            'reasoning': 'Load from database',
        }
        
        available_tools = [
            {
                'tool_name': 'LoadData',
                'tool_id': 'tool-1',
            },
        ]
        
        decision = OutputParser.to_planner_decision(data, available_tools)
        
        self.assertIsInstance(decision, PlannerDecision)
        self.assertEqual(decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(decision.tool_id, 'tool-1')
        self.assertEqual(decision.tool_parameters, {'source': 'db'})
    
    def test_to_planner_decision_unknown_tool(self):
        """Test converting tool action with unknown tool."""
        data = {
            'action': 'tool',
            'tool_name': 'UnknownTool',
            'arguments': {},
            'reasoning': 'Try unknown tool',
        }
        
        available_tools = [
            {
                'tool_name': 'LoadData',
                'tool_id': 'tool-1',
            },
        ]
        
        result = OutputParser.to_planner_decision(data, available_tools)
        
        self.assertIsInstance(result, LLMPlannerFailure)
        self.assertEqual(result.error_type, 'tool_not_found')
        
        # Should have fallback decision
        self.assertIsNotNone(result.fallback_decision)
        self.assertEqual(result.fallback_decision.decision_type, PlannerDecisionType.REQUEST_HUMAN)


class MockLLMClientTests(TestCase):
    """Tests for MockLLMClient."""
    
    def test_mock_client_cycles_responses(self):
        """Test that mock client cycles through responses."""
        responses = [
            '{"action": "tool", "tool_name": "Tool1", "arguments": {}, "reasoning": "First"}',
            '{"action": "tool", "tool_name": "Tool2", "arguments": {}, "reasoning": "Second"}',
        ]
        
        client = MockLLMClient(responses)
        
        # First call
        result1 = asyncio.run(client.create_completion([], 'mock', 100, 0.3, 30))
        self.assertIn('Tool1', result1['content'])
        
        # Second call
        result2 = asyncio.run(client.create_completion([], 'mock', 100, 0.3, 30))
        self.assertIn('Tool2', result2['content'])
        
        # Third call (cycles back to first)
        result3 = asyncio.run(client.create_completion([], 'mock', 100, 0.3, 30))
        self.assertIn('Tool1', result3['content'])


class LLMPlannerTests(TestCase):
    """Tests for LLMPlanner."""
    
    def setUp(self):
        """Set up test data."""
        self.runtime_spec = {
            'available_tools': [
                {
                    'tool_name': 'LoadData',
                    'tool_id': 'tool-1',
                    'description': 'Load data',
                    'input_variables': [],
                    'agent_constraints': {'is_allowed': True},
                },
                {
                    'tool_name': 'ProcessData',
                    'tool_id': 'tool-2',
                    'description': 'Process data',
                    'input_variables': ['data'],
                    'agent_constraints': {'is_allowed': True},
                },
            ],
            'execution_constraints': {
                'dag': {
                    'dependencies': {
                        'tool-2': {'depends_on': ['tool-1']},
                    },
                },
            },
        }
        
        self.execution_history = []
        self.current_state = {'step': 0, 'completed_tools': [], 'variables': {}}
    
    def test_planner_with_mock_client(self):
        """Test planner with mock client."""
        client = MockLLMClient([
            '{"action": "tool", "tool_name": "LoadData", "arguments": {}, "reasoning": "Start loading"}',
        ])
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        self.assertIsInstance(decision, PlannerDecision)
        self.assertEqual(decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(decision.tool_id, 'tool-1')
    
    def test_planner_with_final_action(self):
        """Test planner returning final action."""
        client = MockLLMClient([
            '{"action": "final", "reasoning": "All work complete"}',
        ])
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        self.assertEqual(decision.decision_type, PlannerDecisionType.COMPLETE)
    
    def test_planner_with_invalid_json(self):
        """Test planner handling invalid JSON response."""
        client = MockLLMClient([
            'This is not valid JSON',
        ])
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        # Should return FAIL decision
        self.assertEqual(decision.decision_type, PlannerDecisionType.FAIL)
        self.assertIn('JSON', decision.reasoning)
    
    def test_planner_with_unknown_tool(self):
        """Test planner requesting unknown tool."""
        client = MockLLMClient([
            '{"action": "tool", "tool_name": "UnknownTool", "arguments": {}, "reasoning": "Try unknown"}',
        ])
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        # Should request human intervention
        self.assertEqual(decision.decision_type, PlannerDecisionType.REQUEST_HUMAN)
        self.assertIn('unknown', decision.reasoning.lower())
    
    def test_planner_timeout(self):
        """Test planner handling timeout."""
        # Create mock client that delays response
        async def slow_completion(*args, **kwargs):
            await asyncio.sleep(2.0)  # Longer than timeout
            return {'content': '{"action": "final"}'}
        
        client = Mock()
        client.create_completion = slow_completion
        
        planner = LLMPlanner(client, model='mock', timeout_seconds=0.1)
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        # Should return FAIL decision
        self.assertEqual(decision.decision_type, PlannerDecisionType.FAIL)
        self.assertIn('timed out', decision.reasoning.lower())
    
    def test_planner_exception_handling(self):
        """Test planner handling exceptions."""
        async def failing_completion(*args, **kwargs):
            raise Exception("API error")
        
        client = Mock()
        client.create_completion = failing_completion
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            self.execution_history,
            self.current_state,
        ))
        
        # Should return FAIL decision
        self.assertEqual(decision.decision_type, PlannerDecisionType.FAIL)
        self.assertIn('failed', decision.reasoning.lower())
    
    def test_planner_with_execution_history(self):
        """Test planner with execution history."""
        history = [
            {
                'tool_name': 'LoadData',
                'tool_id': 'tool-1',
                'success': True,
                'output': 'Loaded 100 records',
            },
        ]
        
        client = MockLLMClient([
            '{"action": "tool", "tool_name": "ProcessData", "arguments": {}, "reasoning": "Process loaded data"}',
        ])
        
        planner = LLMPlanner(client, model='mock')
        
        decision = asyncio.run(planner.plan_next_action(
            self.runtime_spec,
            history,
            self.current_state,
        ))
        
        self.assertEqual(decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(decision.tool_id, 'tool-2')
    
    def test_planner_parameters(self):
        """Test planner initialization parameters."""
        client = MockLLMClient()
        
        planner = LLMPlanner(
            llm_client=client,
            model='gpt-4-turbo',
            objective='Complete data pipeline',
            max_tokens=2000,
            temperature=0.5,
            timeout_seconds=60.0,
        )
        
        self.assertEqual(planner.model, 'gpt-4-turbo')
        self.assertEqual(planner.objective, 'Complete data pipeline')
        self.assertEqual(planner.max_tokens, 2000)
        self.assertEqual(planner.temperature, 0.5)
        self.assertEqual(planner.timeout_seconds, 60.0)


class IntegrationTests(TestCase):
    """Integration tests for LLM planner with execution loop."""
    
    def test_planner_swap_compatibility(self):
        """Test that LLMPlanner can swap with DeterministicPlanner."""
        from agent_integration.execution_loop import DeterministicPlanner
        
        runtime_spec = {
            'available_tools': [
                {
                    'tool_name': 'Tool1',
                    'tool_id': 'tool-1',
                    'agent_constraints': {'is_allowed': True},
                },
            ],
            'execution_constraints': {'dag': {'dependencies': {}}},
        }
        
        # Test with DeterministicPlanner
        det_planner = DeterministicPlanner()
        det_decision = asyncio.run(det_planner.plan_next_action(
            runtime_spec, [], {'step': 0},
        ))
        
        # Test with LLMPlanner
        llm_client = MockLLMClient([
            '{"action": "tool", "tool_name": "Tool1", "arguments": {}, "reasoning": "Execute"}',
        ])
        llm_planner = LLMPlanner(llm_client)
        llm_decision = asyncio.run(llm_planner.plan_next_action(
            runtime_spec, [], {'step': 0},
        ))
        
        # Both should return valid PlannerDecision
        self.assertIsInstance(det_decision, PlannerDecision)
        self.assertIsInstance(llm_decision, PlannerDecision)
        
        # Both should decide to execute the tool
        self.assertEqual(det_decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(llm_decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
    
    def test_planner_failure_fallback(self):
        """Test that planner failures are safe and recoverable."""
        # Create planner that always fails
        client = MockLLMClient(['invalid json'])
        planner = LLMPlanner(client)
        
        runtime_spec = {'available_tools': []}
        
        decision = asyncio.run(planner.plan_next_action(
            runtime_spec, [], {'step': 0},
        ))
        
        # Should return safe FAIL decision
        self.assertIsInstance(decision, PlannerDecision)
        self.assertEqual(decision.decision_type, PlannerDecisionType.FAIL)
        
        # Should not raise exception
        # (test passes if we get here)


class LLMPlannerFailureTests(TestCase):
    """Tests for LLMPlannerFailure."""
    
    def test_failure_to_decision_without_fallback(self):
        """Test converting failure to decision without fallback."""
        failure = LLMPlannerFailure(
            error_type='test_error',
            error_message='Test failure',
        )
        
        decision = failure.to_decision()
        
        self.assertEqual(decision.decision_type, PlannerDecisionType.FAIL)
        self.assertIn('test_error', decision.reasoning)
        self.assertIn('Test failure', decision.reasoning)
    
    def test_failure_to_decision_with_fallback(self):
        """Test converting failure to decision with fallback."""
        fallback = PlannerDecision(
            decision_type=PlannerDecisionType.REQUEST_HUMAN,
            reasoning='Fallback decision',
        )
        
        failure = LLMPlannerFailure(
            error_type='test_error',
            error_message='Test failure',
            fallback_decision=fallback,
        )
        
        decision = failure.to_decision()
        
        self.assertEqual(decision, fallback)
