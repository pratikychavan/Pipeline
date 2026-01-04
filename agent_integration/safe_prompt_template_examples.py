"""
SAFE Prompt Template - Usage Examples

Demonstrates the SAFE prompt template system with security features.
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')

import django
django.setup()

from agent_integration.llm_planner import SafePromptTemplate, render_prompt


# ============================================================================
# EXAMPLE 1: Security Features
# ============================================================================

def example_security_features():
    """Demonstrate security features of SafePromptTemplate."""
    print("="*80)
    print("EXAMPLE 1: Security Features")
    print("="*80)
    
    # Test string escaping
    print("\n1. String Escaping (removes control characters):")
    unsafe_string = "Hello\x00World\x01Test"
    safe_string = SafePromptTemplate._escape_string(unsafe_string)
    print(f"  Unsafe: {repr(unsafe_string)}")
    print(f"  Safe:   {repr(safe_string)}")
    
    # Test string truncation
    print("\n2. String Truncation (limits length):")
    long_string = "a" * 2000
    safe_long = SafePromptTemplate._escape_string(long_string)
    print(f"  Original length: {len(long_string)}")
    print(f"  Safe length: {len(safe_long)}")
    print(f"  Truncated: {'[truncated]' in safe_long}")
    
    # Test dictionary sanitization
    print("\n3. Dictionary Sanitization (redacts sensitive keys):")
    unsafe_dict = {
        'username': 'alice',
        'password': 'secret123',
        'api_key': 'sk-1234',
        'token': 'bearer xyz',
        'safe_data': 'visible',
    }
    safe_dict = SafePromptTemplate._sanitize_dict(unsafe_dict)
    print(f"  Original: {unsafe_dict}")
    print(f"  Sanitized: {safe_dict}")
    print(f"  Password redacted: {safe_dict['password'] == '[REDACTED]'}")
    print(f"  API key redacted: {safe_dict['api_key'] == '[REDACTED]'}")
    print(f"  Safe data visible: {safe_dict['safe_data'] == 'visible'}")
    
    # Test depth limiting
    print("\n4. Depth Limiting (prevents deep nesting):")
    deep_dict = {
        'level1': {
            'level2': {
                'level3': {
                    'level4': 'too deep'
                }
            }
        }
    }
    safe_deep = SafePromptTemplate._sanitize_dict(deep_dict, max_depth=3)
    print(f"  Original depth: 4 levels")
    print(f"  Max allowed: 3 levels")
    print(f"  Result: {safe_deep}")
    print(f"  Level 4 blocked: {'[too_deep]' in str(safe_deep)}")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE 2: Constraint Rendering
# ============================================================================

def example_constraint_rendering():
    """Demonstrate constraint rendering."""
    print("="*80)
    print("EXAMPLE 2: Constraint Rendering")
    print("="*80)
    
    runtime_spec = {
        'execution_constraints': {
            'max_steps': 50,
            'max_execution_time_seconds': 300,
            'max_cost_usd': 10.0,
        },
        'agent_config': {
            'retry_policy': {
                'max_retries': 0,
            },
        },
    }
    
    constraints_section = SafePromptTemplate.build_constraints_section(runtime_spec)
    
    print("\nGenerated Constraints Section:")
    print("-" * 80)
    print(constraints_section)
    print("-" * 80)
    
    print("\nKey Features:")
    print(f"  ✓ Max steps mentioned: {'max_steps' in constraints_section}")
    print(f"  ✓ Timeout mentioned: {'max_execution_time_seconds' in constraints_section}")
    print(f"  ✓ Cost limit mentioned: {'max_cost_usd' in constraints_section}")
    print(f"  ✓ No retries emphasized: {'NOT ALLOWED' in constraints_section}")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE 3: Tools Section with Constraints
# ============================================================================

def example_tools_rendering():
    """Demonstrate tools section rendering."""
    print("="*80)
    print("EXAMPLE 3: Tools Section with Constraints")
    print("="*80)
    
    tools = [
        {
            'tool_name': 'ValidateInput',
            'tool_id': 'tool-1',
            'description': 'Validates input data for correctness',
            'input_variables': ['data'],
            'agent_constraints': {
                'is_allowed': True,
                'max_calls': 1,
                'dependencies': [],
            },
            'execution_order': 1,
        },
        {
            'tool_name': 'ProcessData',
            'tool_id': 'tool-2',
            'description': 'Processes validated data',
            'input_variables': ['validated_data'],
            'agent_constraints': {
                'is_allowed': True,
                'max_calls': 1,
                'dependencies': ['tool-1'],
            },
            'execution_order': 2,
        },
        {
            'tool_name': 'GenerateReport',
            'tool_id': 'tool-3',
            'description': 'Generates final report',
            'input_variables': ['processed_data'],
            'agent_constraints': {
                'is_allowed': False,  # Not allowed
                'max_calls': 0,
                'dependencies': ['tool-2'],
            },
            'execution_order': 3,
        },
    ]
    
    tools_section = SafePromptTemplate.build_tools_section(tools)
    
    print("\nGenerated Tools Section:")
    print("-" * 80)
    print(tools_section)
    print("-" * 80)
    
    print("\nKey Features:")
    print(f"  ✓ All 3 tools listed: {tools_section.count('tool_name') == 3}")
    print(f"  ✓ Sorted by execution order: {'ValidateInput' in tools_section.split('ProcessData')[0]}")
    print(f"  ✓ Constraints included: {'max_calls' in tools_section}")
    print(f"  ✓ Dependencies shown: {'dependencies' in tools_section}")
    print(f"  ✓ Forbidden tool marked: {'false' in tools_section.lower()}")
    print(f"  ✓ Rules emphasized: {'CANNOT invent new tools' in tools_section}")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE 4: State Sanitization (Variable Names Only)
# ============================================================================

def example_state_sanitization():
    """Demonstrate state sanitization."""
    print("="*80)
    print("EXAMPLE 4: State Sanitization (Security)")
    print("="*80)
    
    current_state = {
        'step': 5,
        'completed_tools': [
            {'tool_name': 'ValidateInput'},
            {'tool_name': 'ProcessData'},
        ],
        'variables': {
            'password': 'secret123',
            'api_key': 'sk-1234567890',
            'user_data': 'sensitive information',
            'count': 100,
        },
    }
    
    state_section = SafePromptTemplate.build_state_section(current_state)
    
    print("\nOriginal State:")
    print(f"  Variables with values: {current_state['variables']}")
    
    print("\nGenerated State Section (Sanitized):")
    print("-" * 80)
    print(state_section)
    print("-" * 80)
    
    print("\nSecurity Verification:")
    print(f"  ✓ Step number shown: {str(current_state['step']) in state_section}")
    print(f"  ✓ Variable names shown: {'password' in state_section and 'api_key' in state_section}")
    print(f"  ✗ Password VALUE hidden: {'secret123' not in state_section}")
    print(f"  ✗ API key VALUE hidden: {'sk-1234567890' not in state_section}")
    print(f"  ✗ Sensitive data VALUE hidden: {'sensitive information' not in state_section}")
    print(f"  ✓ Security note included: {'SECURITY NOTE' in state_section}")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE 5: Complete Prompt Generation
# ============================================================================

def example_complete_prompt():
    """Demonstrate complete prompt generation."""
    print("="*80)
    print("EXAMPLE 5: Complete Prompt Generation")
    print("="*80)
    
    objective = "Complete the data processing pipeline successfully"
    
    runtime_spec = {
        'execution_constraints': {
            'max_steps': 20,
            'max_execution_time_seconds': 600,
        },
        'agent_config': {
            'retry_policy': {'max_retries': 0},
        },
        'available_tools': [
            {
                'tool_name': 'ValidateInput',
                'tool_id': 'tool-1',
                'description': 'Validates input',
                'input_variables': ['data'],
                'agent_constraints': {
                    'is_allowed': True,
                    'max_calls': 1,
                    'dependencies': [],
                },
                'execution_order': 1,
            },
        ],
    }
    
    execution_history = [
        {
            'tool_name': 'ValidateInput',
            'tool_id': 'tool-1',
            'success': True,
            'output': 'Input validated successfully',
        },
    ]
    
    current_state = {
        'step': 1,
        'completed_tools': [{'tool_name': 'ValidateInput'}],
        'variables': {'validated_data': 'hidden_value'},
    }
    
    # Use standalone helper
    system_prompt, user_prompt = render_prompt(
        objective,
        runtime_spec,
        execution_history,
        current_state,
    )
    
    print("\nSystem Prompt (excerpt):")
    print("-" * 80)
    print(system_prompt[:500] + "...")
    print("-" * 80)
    
    print("\nUser Prompt (excerpt):")
    print("-" * 80)
    print(user_prompt[:800] + "...")
    print("-" * 80)
    
    print("\nPrompt Features:")
    print(f"  ✓ Advisory role emphasized: {'ADVISORY' in system_prompt}")
    print(f"  ✓ No tool invention: {'NO TOOL INVENTION' in system_prompt}")
    print(f"  ✓ No looping: {'NO LOOPING' in system_prompt}")
    print(f"  ✓ No retries: {'NO RETRIES' in system_prompt}")
    print(f"  ✓ JSON only: {'ONLY' in system_prompt and 'JSON' in system_prompt}")
    print(f"  ✓ Constraints section: {'EXECUTION CONSTRAINTS' in user_prompt}")
    print(f"  ✓ Tools section: {'ALLOWED TOOLS' in user_prompt}")
    print(f"  ✓ History section: {'EXECUTION HISTORY' in user_prompt}")
    print(f"  ✓ State section: {'CURRENT STATE' in user_prompt}")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# EXAMPLE 6: Deterministic Output
# ============================================================================

def example_deterministic_output():
    """Demonstrate deterministic prompt generation."""
    print("="*80)
    print("EXAMPLE 6: Deterministic Output")
    print("="*80)
    
    runtime_spec = {
        'execution_constraints': {'max_steps': 10},
        'agent_config': {},
        'available_tools': [],
    }
    history = []
    state = {'step': 0, 'completed_tools': [], 'variables': {}}
    
    # Generate twice
    system1, user1 = render_prompt("Test", runtime_spec, history, state)
    system2, user2 = render_prompt("Test", runtime_spec, history, state)
    
    print("\nGenerating prompt twice with identical inputs...")
    print(f"  System prompt 1 length: {len(system1)}")
    print(f"  System prompt 2 length: {len(system2)}")
    print(f"  User prompt 1 length: {len(user1)}")
    print(f"  User prompt 2 length: {len(user2)}")
    
    print("\nDeterministic Check:")
    print(f"  ✓ System prompts identical: {system1 == system2}")
    print(f"  ✓ User prompts identical: {user1 == user2}")
    print(f"  ✓ Output is deterministic: {system1 == system2 and user1 == user2}")
    
    print("\n✅ Prompts are deterministic (reproducible, auditable)")
    
    print("\n" + "="*80 + "\n")


# ============================================================================
# RUN ALL EXAMPLES
# ============================================================================

if __name__ == "__main__":
    print("\n")
    print("*" * 80)
    print("SAFE PROMPT TEMPLATE - USAGE EXAMPLES")
    print("*" * 80)
    print("\n")
    
    example_security_features()
    example_constraint_rendering()
    example_tools_rendering()
    example_state_sanitization()
    example_complete_prompt()
    example_deterministic_output()
    
    print("\n")
    print("*" * 80)
    print("ALL EXAMPLES COMPLETED")
    print("*" * 80)
    print("\n")
    print("Key Takeaways:")
    print("1. All sensitive data is sanitized before sending to LLM")
    print("2. Constraints are explicitly stated in prompts")
    print("3. Advisory role is emphasized (planner suggests, guardrails enforce)")
    print("4. Tool invention, looping, and retries are forbidden")
    print("5. Variable values are hidden (names only shown)")
    print("6. Output is deterministic and auditable")
    print("7. All sections are clearly separated and documented")
    print("\n")
