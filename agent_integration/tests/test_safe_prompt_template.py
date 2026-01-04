"""
Tests for SafePromptTemplate

Tests the SAFE prompt template system including:
- String escaping
- Dictionary sanitization
- Constraint rendering
- Deterministic output
- Security features
"""

import json
from django.test import TestCase

from agent_integration.llm_planner import (
    SafePromptTemplate,
    render_prompt,
)


class SafePromptTemplateSecurityTests(TestCase):
    """Test security features of SafePromptTemplate."""
    
    def test_escape_string_removes_control_characters(self):
        """Test that control characters are removed."""
        unsafe_string = "Hello\x00World\x01Test\x02"
        safe_string = SafePromptTemplate._escape_string(unsafe_string)
        
        # Control characters should be replaced with ?
        self.assertNotIn('\x00', safe_string)
        self.assertNotIn('\x01', safe_string)
        self.assertNotIn('\x02', safe_string)
    
    def test_escape_string_truncates_long_strings(self):
        """Test that long strings are truncated."""
        long_string = "a" * 2000
        safe_string = SafePromptTemplate._escape_string(long_string)
        
        # Should be truncated to 1000 chars + "[truncated]"
        self.assertLess(len(safe_string), 1020)
        self.assertIn("[truncated]", safe_string)
    
    def test_escape_string_handles_non_string(self):
        """Test that non-strings are converted."""
        result = SafePromptTemplate._escape_string(12345)
        self.assertEqual(result, "12345")
    
    def test_sanitize_dict_redacts_sensitive_keys(self):
        """Test that sensitive keys are redacted."""
        unsafe_dict = {
            'username': 'alice',
            'password': 'secret123',
            'api_key': 'sk-1234',
            'token': 'bearer xyz',
            'safe_data': 'visible',
        }
        
        safe_dict = SafePromptTemplate._sanitize_dict(unsafe_dict)
        
        # Sensitive keys should be redacted
        self.assertEqual(safe_dict['password'], '[REDACTED]')
        self.assertEqual(safe_dict['api_key'], '[REDACTED]')
        self.assertEqual(safe_dict['token'], '[REDACTED]')
        
        # Safe data should be visible
        self.assertEqual(safe_dict['safe_data'], 'visible')
    
    def test_sanitize_dict_limits_depth(self):
        """Test that nested dicts are limited in depth."""
        deep_dict = {
            'level1': {
                'level2': {
                    'level3': {
                        'level4': {
                            'level5': 'too deep'
                        }
                    }
                }
            }
        }
        
        safe_dict = SafePromptTemplate._sanitize_dict(deep_dict, max_depth=3)
        
        # Should not reach level 5
        level3 = safe_dict['level1']['level2']['level3']
        self.assertIn('[too_deep]', level3)
    
    def test_sanitize_dict_escapes_strings(self):
        """Test that strings in dict are escaped."""
        unsafe_dict = {
            'message': 'Hello\x00World',
        }
        
        safe_dict = SafePromptTemplate._sanitize_dict(unsafe_dict)
        
        # String should be escaped
        self.assertNotIn('\x00', safe_dict['message'])
    
    def test_sanitize_dict_handles_lists(self):
        """Test that lists of dicts are sanitized."""
        unsafe_dict = {
            'users': [
                {'name': 'Alice', 'password': 'secret1'},
                {'name': 'Bob', 'password': 'secret2'},
            ]
        }
        
        safe_dict = SafePromptTemplate._sanitize_dict(unsafe_dict)
        
        # Passwords in list should be redacted
        self.assertEqual(safe_dict['users'][0]['password'], '[REDACTED]')
        self.assertEqual(safe_dict['users'][1]['password'], '[REDACTED]')
        
        # Names should be visible
        self.assertEqual(safe_dict['users'][0]['name'], 'Alice')
        self.assertEqual(safe_dict['users'][1]['name'], 'Bob')


class SafePromptTemplateConstraintsTests(TestCase):
    """Test constraint rendering."""
    
    def test_build_constraints_section_includes_max_steps(self):
        """Test that max_steps is included."""
        runtime_spec = {
            'execution_constraints': {
                'max_steps': 50,
            },
            'agent_config': {},
        }
        
        section = SafePromptTemplate.build_constraints_section(runtime_spec)
        
        self.assertIn('50', section)
        self.assertIn('max_steps', section)
    
    def test_build_constraints_section_includes_timeout(self):
        """Test that timeout is included."""
        runtime_spec = {
            'execution_constraints': {
                'max_steps': 100,
                'max_execution_time_seconds': 300,
            },
            'agent_config': {},
        }
        
        section = SafePromptTemplate.build_constraints_section(runtime_spec)
        
        self.assertIn('300', section)
        self.assertIn('max_execution_time_seconds', section)
    
    def test_build_constraints_section_includes_retry_policy(self):
        """Test that retry policy is included."""
        runtime_spec = {
            'execution_constraints': {
                'max_steps': 100,
            },
            'agent_config': {
                'retry_policy': {
                    'max_retries': 0,  # No retries allowed
                },
            },
        }
        
        section = SafePromptTemplate.build_constraints_section(runtime_spec)
        
        self.assertIn('retry_policy', section)
        self.assertIn('NO', section.upper())  # Should mention no retries
    
    def test_build_constraints_section_includes_cost_limit(self):
        """Test that cost limit is included if present."""
        runtime_spec = {
            'execution_constraints': {
                'max_steps': 100,
                'max_cost_usd': 10.0,
            },
            'agent_config': {},
        }
        
        section = SafePromptTemplate.build_constraints_section(runtime_spec)
        
        self.assertIn('10.0', section)
        self.assertIn('max_cost_usd', section)


class SafePromptTemplateToolsTests(TestCase):
    """Test tools section rendering."""
    
    def test_build_tools_section_empty(self):
        """Test tools section with no tools."""
        section = SafePromptTemplate.build_tools_section([])
        
        self.assertIn('None', section)
        self.assertIn('ALLOWED TOOLS', section)
    
    def test_build_tools_section_includes_tool_names(self):
        """Test that tool names are included."""
        tools = [
            {
                'tool_name': 'ValidateInput',
                'tool_id': 'tool-1',
                'description': 'Validates input data',
                'input_variables': ['data'],
                'agent_constraints': {
                    'is_allowed': True,
                    'max_calls': 1,
                },
            },
        ]
        
        section = SafePromptTemplate.build_tools_section(tools)
        
        self.assertIn('ValidateInput', section)
        self.assertIn('tool-1', section)
    
    def test_build_tools_section_escapes_descriptions(self):
        """Test that tool descriptions are escaped."""
        tools = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'description': 'Test\x00Description',
                'input_variables': [],
                'agent_constraints': {},
            },
        ]
        
        section = SafePromptTemplate.build_tools_section(tools)
        
        # Control character should not be present
        self.assertNotIn('\x00', section)
    
    def test_build_tools_section_includes_constraints(self):
        """Test that tool constraints are included."""
        tools = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'description': 'Test',
                'input_variables': [],
                'agent_constraints': {
                    'is_allowed': False,
                    'max_calls': 2,
                    'dependencies': ['tool-0'],
                },
            },
        ]
        
        section = SafePromptTemplate.build_tools_section(tools)
        
        self.assertIn('is_allowed', section)
        self.assertIn('false', section.lower())
        self.assertIn('max_calls', section)
        self.assertIn('2', section)
    
    def test_build_tools_section_sorts_by_execution_order(self):
        """Test that tools are sorted by execution order."""
        tools = [
            {'tool_name': 'Tool3', 'tool_id': 'c', 'execution_order': 3, 'agent_constraints': {}},
            {'tool_name': 'Tool1', 'tool_id': 'a', 'execution_order': 1, 'agent_constraints': {}},
            {'tool_name': 'Tool2', 'tool_id': 'b', 'execution_order': 2, 'agent_constraints': {}},
        ]
        
        section = SafePromptTemplate.build_tools_section(tools)
        
        # Tool1 should appear before Tool2, which should appear before Tool3
        tool1_pos = section.find('Tool1')
        tool2_pos = section.find('Tool2')
        tool3_pos = section.find('Tool3')
        
        self.assertLess(tool1_pos, tool2_pos)
        self.assertLess(tool2_pos, tool3_pos)


class SafePromptTemplateHistoryTests(TestCase):
    """Test history section rendering."""
    
    def test_build_history_section_empty(self):
        """Test history section with no history."""
        section = SafePromptTemplate.build_history_section([])
        
        self.assertIn('None', section)
        self.assertIn('first decision', section)
    
    def test_build_history_section_includes_steps(self):
        """Test that execution steps are included."""
        history = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'success': True,
                'output': 'Result 1',
            },
            {
                'tool_name': 'Tool2',
                'tool_id': 'tool-2',
                'success': False,
                'output': 'Error occurred',
            },
        ]
        
        section = SafePromptTemplate.build_history_section(history)
        
        self.assertIn('Tool1', section)
        self.assertIn('Tool2', section)
        self.assertIn('completed', section)
        self.assertIn('failed', section)
    
    def test_build_history_section_truncates_output(self):
        """Test that output is truncated."""
        long_output = "a" * 500
        history = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'success': True,
                'output': long_output,
            },
        ]
        
        section = SafePromptTemplate.build_history_section(history)
        
        # Output should be truncated to 200 chars
        self.assertLess(section.count('a'), 250)
    
    def test_build_history_section_escapes_output(self):
        """Test that output is escaped."""
        history = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'success': True,
                'output': 'Result\x00Data',
            },
        ]
        
        section = SafePromptTemplate.build_history_section(history)
        
        # Control character should not be present
        self.assertNotIn('\x00', section)
    
    def test_build_history_section_mentions_no_retries(self):
        """Test that section mentions no retries allowed."""
        history = [
            {
                'tool_name': 'Tool1',
                'tool_id': 'tool-1',
                'success': False,
            },
        ]
        
        section = SafePromptTemplate.build_history_section(history)
        
        self.assertIn('retries', section.lower())
        self.assertIn('NOT', section)


class SafePromptTemplateStateTests(TestCase):
    """Test state section rendering."""
    
    def test_build_state_section_shows_step_number(self):
        """Test that current step is shown."""
        state = {
            'step': 5,
            'completed_tools': [],
            'variables': {},
        }
        
        section = SafePromptTemplate.build_state_section(state)
        
        self.assertIn('5', section)
        self.assertIn('current_step', section)
    
    def test_build_state_section_shows_variable_names_only(self):
        """Test that only variable names are shown, not values."""
        state = {
            'step': 1,
            'completed_tools': [],
            'variables': {
                'password': 'secret123',
                'api_key': 'sk-1234',
                'user_data': 'sensitive_value',
            },
        }
        
        section = SafePromptTemplate.build_state_section(state)
        
        # Variable names should be present
        self.assertIn('password', section)
        self.assertIn('api_key', section)
        self.assertIn('user_data', section)
        
        # Values should NOT be present
        self.assertNotIn('secret123', section)
        self.assertNotIn('sk-1234', section)
        self.assertNotIn('sensitive_value', section)
    
    def test_build_state_section_limits_variables(self):
        """Test that variable list is limited."""
        # Create 100 variables
        variables = {f'var_{i}': f'value_{i}' for i in range(100)}
        state = {
            'step': 1,
            'completed_tools': [],
            'variables': variables,
        }
        
        section = SafePromptTemplate.build_state_section(state)
        
        # Should be limited to 50 variables
        # Count how many var_ appear (rough check)
        var_count = section.count('var_')
        self.assertLessEqual(var_count, 55)  # Allow some buffer
    
    def test_build_state_section_mentions_security(self):
        """Test that section mentions security."""
        state = {'step': 1, 'completed_tools': [], 'variables': {}}
        section = SafePromptTemplate.build_state_section(state)
        
        self.assertIn('SECURITY', section)
        self.assertIn('NAMES', section)
        self.assertIn('VALUES', section)


class SafePromptTemplateIntegrationTests(TestCase):
    """Test complete prompt generation."""
    
    def test_build_user_prompt_is_deterministic(self):
        """Test that prompt generation is deterministic."""
        runtime_spec = {
            'execution_constraints': {'max_steps': 10},
            'agent_config': {},
            'available_tools': [],
        }
        history = []
        state = {'step': 0, 'completed_tools': [], 'variables': {}}
        
        # Generate twice
        prompt1 = SafePromptTemplate.build_user_prompt(runtime_spec, history, state)
        prompt2 = SafePromptTemplate.build_user_prompt(runtime_spec, history, state)
        
        # Should be identical
        self.assertEqual(prompt1, prompt2)
    
    def test_build_user_prompt_includes_all_sections(self):
        """Test that all sections are included."""
        runtime_spec = {
            'execution_constraints': {'max_steps': 10},
            'agent_config': {},
            'available_tools': [
                {
                    'tool_name': 'Tool1',
                    'tool_id': 'tool-1',
                    'description': 'Test tool',
                    'input_variables': [],
                    'agent_constraints': {},
                },
            ],
        }
        history = []
        state = {'step': 0, 'completed_tools': [], 'variables': {}}
        
        prompt = SafePromptTemplate.build_user_prompt(runtime_spec, history, state)
        
        # Check for section headers
        self.assertIn('EXECUTION CONSTRAINTS', prompt)
        self.assertIn('ALLOWED TOOLS', prompt)
        self.assertIn('EXECUTION HISTORY', prompt)
        self.assertIn('CURRENT STATE', prompt)
        self.assertIn('YOUR DECISION', prompt)
    
    def test_render_prompt_helper(self):
        """Test standalone render_prompt helper."""
        objective = "Complete the task"
        runtime_spec = {
            'execution_constraints': {'max_steps': 10},
            'agent_config': {},
            'available_tools': [],
        }
        history = []
        state = {'step': 0, 'completed_tools': [], 'variables': {}}
        
        system_prompt, user_prompt = render_prompt(
            objective,
            runtime_spec,
            history,
            state,
        )
        
        # Check system prompt
        self.assertIn(objective, system_prompt)
        self.assertIn('ADVISORY', system_prompt)
        
        # Check user prompt
        self.assertIn('EXECUTION CONSTRAINTS', user_prompt)
    
    def test_system_prompt_emphasizes_advisory_role(self):
        """Test that system prompt emphasizes advisory role."""
        prompt = SafePromptTemplate.build_system_prompt("Test objective")
        
        self.assertIn('ADVISORY', prompt)
        self.assertIn('SUGGESTIONS', prompt)
        self.assertIn('validated by guardrails', prompt)
        self.assertIn('do not execute', prompt.lower())
    
    def test_system_prompt_forbids_tool_invention(self):
        """Test that system prompt forbids tool invention."""
        prompt = SafePromptTemplate.build_system_prompt("Test objective")
        
        self.assertIn('NO TOOL INVENTION', prompt)
        self.assertIn('ONLY tools from the allowed list', prompt)
    
    def test_system_prompt_forbids_looping(self):
        """Test that system prompt forbids looping."""
        prompt = SafePromptTemplate.build_system_prompt("Test objective")
        
        self.assertIn('NO LOOPING', prompt)
        self.assertIn('at most once', prompt)
    
    def test_system_prompt_forbids_retries(self):
        """Test that system prompt forbids retries."""
        prompt = SafePromptTemplate.build_system_prompt("Test objective")
        
        self.assertIn('NO RETRIES', prompt)
        self.assertIn('do NOT recommend it again', prompt)
    
    def test_system_prompt_requires_json_only(self):
        """Test that system prompt requires JSON only."""
        prompt = SafePromptTemplate.build_system_prompt("Test objective")
        
        self.assertIn('ONLY a valid JSON object', prompt)
        self.assertIn('NO PROSE', prompt)
        self.assertIn('no markdown', prompt)
