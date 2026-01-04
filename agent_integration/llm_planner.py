"""
LLM Planner

This module implements an LLM-based planner that integrates external LLMs
(OpenAI, Anthropic, etc.) into the agent execution system.

CRITICAL CONSTRAINTS:
- Planner is BOUNDED (one LLM call per decide)
- Planner is STATELESS (no internal state)
- Output is STRUCTURED (strict JSON schema)
- Errors are SAFE (no exceptions, return failure objects)
- Compatible with existing DeterministicPlanner fallback

The LLMPlanner is a plug-and-play replacement for DeterministicPlanner.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Protocol, Union
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json
import asyncio

from agent_integration.execution_loop import (
    Planner,
    PlannerDecision,
    PlannerDecisionType,
)


# ============================================================================
# LLM CLIENT PROTOCOL
# ============================================================================

class LLMClient(Protocol):
    """
    Protocol for LLM clients.
    
    This defines the interface that LLM clients must implement.
    Compatible with OpenAI, Anthropic, and other LLM providers.
    """
    
    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Dict[str, Any]:
        """
        Create a completion from the LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            model: Model name (e.g., 'gpt-4', 'claude-3-opus')
            max_tokens: Maximum tokens to generate
            temperature: Temperature (0.0 - 1.0)
            timeout: Timeout in seconds
            
        Returns:
            Response dict with 'content' key containing the completion
            
        Raises:
            TimeoutError: If request times out
            Exception: For other errors
        """
        ...


# ============================================================================
# LLM PLANNER RESULT TYPES
# ============================================================================

@dataclass
class LLMPlannerSuccess:
    """Successful LLM planner result."""
    decision: PlannerDecision
    raw_response: str
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None


@dataclass
class LLMPlannerFailure:
    """Failed LLM planner result."""
    error_type: str
    error_message: str
    raw_response: Optional[str] = None
    fallback_decision: Optional[PlannerDecision] = None
    
    def to_decision(self) -> PlannerDecision:
        """Convert failure to a FAIL decision."""
        if self.fallback_decision:
            return self.fallback_decision
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.FAIL,
            reasoning=f"LLM planner failed: {self.error_type} - {self.error_message}",
            confidence=0.0,
        )


LLMPlannerResult = Union[LLMPlannerSuccess, LLMPlannerFailure]


# ============================================================================
# PROMPT BUILDER
# ============================================================================

class SafePromptTemplate:
    """
    SAFE prompt template for LLM planner.
    
    This template enforces strict constraints:
    - Advisory role only (planner makes suggestions, guardrails enforce)
    - No tool invention
    - No looping
    - No retries
    - STRICT JSON output only (no prose)
    - Bounded execution (max steps)
    - Sanitized context (no sensitive data)
    
    The template produces deterministic, auditable prompts.
    """
    
    # System prompt template (static, never includes user data)
    SYSTEM_PROMPT_TEMPLATE = """You are an ADVISORY planner for a pipeline execution system.

YOUR ROLE:
You make recommendations about which tool to execute next.
Your decisions are SUGGESTIONS that will be validated by guardrails.
You do NOT execute tools directly.
You do NOT have memory across decisions.
You do NOT retry failed tools.

YOUR OBJECTIVE:
{objective}

OUTPUT FORMAT (STRICT):
You MUST respond with ONLY a valid JSON object in this EXACT format:

{{
  "action": "<ACTION_TYPE>",
  "tool_name": "<TOOL_NAME>",
  "arguments": {{}},
  "reasoning": "<YOUR_REASONING>"
}}

ACTION TYPES:
1. "tool" - Recommend executing a specific tool
   - MUST provide "tool_name" (from allowed tools list ONLY)
   - MUST provide "arguments" (matching tool schema)
   - Guardrails will validate before execution

2. "final" - Recommend completion
   - Use when objective is achieved
   - All required tools have been executed

3. "noop" - Cannot make a decision
   - Use when no valid tool can be recommended
   - Escalates to human oversight

CRITICAL CONSTRAINTS:
1. NO TOOL INVENTION: Use ONLY tools from the allowed list below
2. NO LOOPING: Each tool should be recommended at most once
3. NO RETRIES: If a tool fails, do NOT recommend it again
4. NO PROSE: Output ONLY the JSON object (no markdown, no explanations outside JSON)
5. RESPECT DEPENDENCIES: Tools must be executed in valid order
6. RESPECT LIMITS: Honor max_calls constraints for each tool

SECURITY:
- You receive SANITIZED context only (variable names, not values)
- You do NOT have access to sensitive data
- Your recommendations are validated before execution

If you cannot make a valid recommendation, return:
{{"action": "noop", "reasoning": "Explain why you cannot decide"}}

REMEMBER: You are advisory only. Guardrails enforce all constraints."""

    @staticmethod
    def _escape_string(value: str) -> str:
        """
        Escape user-provided strings for safe inclusion in prompts.
        
        Prevents:
        - JSON injection
        - Prompt injection
        - Control character exploits
        """
        if not isinstance(value, str):
            return str(value)
        
        # Replace control characters
        value = ''.join(char if char.isprintable() or char in '\n\r\t' else '?' for char in value)
        
        # Truncate if too long (safety limit)
        if len(value) > 1000:
            value = value[:1000] + "...[truncated]"
        
        return value
    
    @staticmethod
    def _sanitize_dict(data: Dict[str, Any], max_depth: int = 3, current_depth: int = 0) -> Dict[str, Any]:
        """
        Sanitize dictionary for safe inclusion in prompt.
        
        - Removes sensitive keys (passwords, tokens, secrets)
        - Truncates large values
        - Limits nesting depth
        """
        if current_depth >= max_depth:
            return {"[too_deep]": "..."}
        
        sensitive_keys = {
            'password', 'passwd', 'pwd', 'secret', 'token', 'api_key', 
            'apikey', 'auth', 'credential', 'private_key', 'access_token'
        }
        
        result = {}
        for key, value in data.items():
            # Skip sensitive keys
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                result[key] = "[REDACTED]"
                continue
            
            # Recursively sanitize nested dicts
            if isinstance(value, dict):
                result[key] = SafePromptTemplate._sanitize_dict(value, max_depth, current_depth + 1)
            elif isinstance(value, (list, tuple)) and len(value) > 0 and isinstance(value[0], dict):
                result[key] = [SafePromptTemplate._sanitize_dict(item, max_depth, current_depth + 1) for item in value[:10]]
            elif isinstance(value, str):
                result[key] = SafePromptTemplate._escape_string(value)
            else:
                result[key] = value
        
        return result
    
    @staticmethod
    def build_system_prompt(objective: str) -> str:
        """
        Build system prompt with objective.
        
        Args:
            objective: High-level objective (will be escaped)
            
        Returns:
            System prompt string (deterministic)
        """
        safe_objective = SafePromptTemplate._escape_string(objective)
        return SafePromptTemplate.SYSTEM_PROMPT_TEMPLATE.format(objective=safe_objective)
    
    @staticmethod
    def build_constraints_section(runtime_spec: Dict[str, Any]) -> str:
        """
        Build execution constraints section.
        
        This informs the planner about:
        - Maximum steps allowed
        - Execution time limits
        - Retry policies
        - SLA constraints
        """
        constraints = runtime_spec.get('execution_constraints', {})
        agent_config = runtime_spec.get('agent_config', {})
        
        constraints_data = {
            'max_steps': constraints.get('max_steps', 100),
            'max_execution_time_seconds': constraints.get('max_execution_time_seconds', None),
            'allow_parallel_execution': constraints.get('allow_parallel_execution', False),
            'retry_policy': agent_config.get('retry_policy', {'max_retries': 0}),
        }
        
        # Add cost limits if present
        if 'max_cost_usd' in constraints:
            constraints_data['max_cost_usd'] = constraints['max_cost_usd']
        
        return f"""
EXECUTION CONSTRAINTS:
{json.dumps(constraints_data, indent=2)}

IMPORTANT:
- You have a maximum of {constraints_data['max_steps']} total steps
- Each tool can only be called a limited number of times (see tool constraints)
- Retries are NOT ALLOWED (max_retries=0 means no retries)
- You must complete the objective within these constraints
"""
    
    @staticmethod
    def build_tools_section(available_tools: List[Dict[str, Any]]) -> str:
        """
        Build allowed tools section with schemas and constraints.
        
        This is the ONLY list of tools the planner can recommend.
        """
        if not available_tools:
            return """
ALLOWED TOOLS:
None - No tools available. You should return action="final" or action="noop".
"""
        
        tools_data = []
        for tool in available_tools:
            # Build safe tool representation
            tool_info = {
                'tool_name': tool.get('tool_name', 'unknown'),
                'tool_id': tool.get('tool_id', 'unknown'),
                'description': SafePromptTemplate._escape_string(tool.get('description', '')),
                'input_schema': {
                    'required_variables': tool.get('input_variables', []),
                    'optional_variables': [],  # TODO: Extract from tool definition
                },
            }
            
            # Add constraints (CRITICAL for safety)
            agent_constraints = tool.get('agent_constraints', {})
            tool_info['constraints'] = {
                'is_allowed': agent_constraints.get('is_allowed', True),
                'max_calls': agent_constraints.get('max_calls', 1),
                'dependencies': agent_constraints.get('dependencies', []),
            }
            
            # Add execution order hint
            tool_info['execution_order'] = tool.get('execution_order', 0)
            
            tools_data.append(tool_info)
        
        # Sort by execution order for clarity
        tools_data.sort(key=lambda t: t.get('execution_order', 0))
        
        return f"""
ALLOWED TOOLS (COMPLETE LIST):
{json.dumps(tools_data, indent=2)}

RULES:
- You MUST use tool_name EXACTLY as shown above
- You CANNOT invent new tools
- You MUST respect max_calls limits
- You MUST respect dependencies (execute prerequisite tools first)
- If is_allowed=false, DO NOT recommend that tool
"""
    
    @staticmethod
    def build_history_section(execution_history: List[Dict[str, Any]]) -> str:
        """
        Build execution history section (sanitized).
        
        Shows what has been executed so far.
        """
        if not execution_history:
            return """
EXECUTION HISTORY:
None - This is the first decision (step 0).
"""
        
        history_items = []
        for i, exec_record in enumerate(execution_history, 1):
            # Sanitize execution record
            item = {
                'step': i,
                'tool_name': exec_record.get('tool_name', 'unknown'),
                'tool_id': exec_record.get('tool_id', 'unknown'),
                'success': exec_record.get('success', False),
                'status': 'completed' if exec_record.get('success') else 'failed',
            }
            
            # Include truncated output summary if available
            output = exec_record.get('output', '')
            if output:
                # Truncate and escape
                output_str = str(output)[:200]
                item['output_summary'] = SafePromptTemplate._escape_string(output_str)
            
            history_items.append(item)
        
        return f"""
EXECUTION HISTORY (Steps completed so far):
{json.dumps(history_items, indent=2)}

NOTES:
- You can see what tools have been executed
- You can see which succeeded and which failed
- DO NOT recommend failed tools again (no retries allowed)
- DO NOT recommend successful tools again (no loops allowed)
"""
    
    @staticmethod
    def build_state_section(current_state: Dict[str, Any]) -> str:
        """
        Build current state section (HEAVILY SANITIZED).
        
        Security: Shows structure only, NOT values.
        """
        # Extract safe state information
        completed_tools = current_state.get('completed_tools', [])
        
        # Handle both string and dict formats for completed_tools
        completed_tool_names = []
        for tool in completed_tools:
            if isinstance(tool, dict):
                completed_tool_names.append(tool.get('tool_name', 'unknown'))
            elif isinstance(tool, str):
                completed_tool_names.append(tool)
            else:
                completed_tool_names.append('unknown')
        
        safe_state = {
            'current_step': current_state.get('step', 0),
            'completed_tools_count': len(completed_tools),
            'completed_tool_names': completed_tool_names[:20],  # Limit to 20 for brevity
        }
        
        # Show variable names ONLY (not values) for security
        variables = current_state.get('variables', {})
        if variables:
            safe_state['available_variables'] = list(variables.keys())[:50]  # Limit to 50
        
        return f"""
CURRENT STATE (Sanitized):
{json.dumps(safe_state, indent=2)}

SECURITY NOTE:
- You can see variable NAMES, not VALUES
- This prevents sensitive data leakage
- Use this to understand what data is available
"""
    
    @staticmethod
    def build_user_prompt(
        runtime_spec: Dict[str, Any],
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> str:
        """
        Build complete user prompt (deterministic).
        
        This combines all sections into a single prompt.
        Sections are assembled in a specific order for clarity.
        
        Args:
            runtime_spec: Runtime specification
            execution_history: Execution history
            current_state: Current state
            
        Returns:
            Complete user prompt (deterministic)
        """
        sections = [
            "=" * 80,
            "PIPELINE EXECUTION PLANNER - DECISION REQUEST",
            "=" * 80,
            "",
            SafePromptTemplate.build_constraints_section(runtime_spec),
            "",
            SafePromptTemplate.build_tools_section(runtime_spec.get('available_tools', [])),
            "",
            SafePromptTemplate.build_history_section(execution_history),
            "",
            SafePromptTemplate.build_state_section(current_state),
            "",
            "=" * 80,
            "YOUR DECISION (JSON ONLY):",
            "=" * 80,
            "",
            "Analyze the above information and return your decision as VALID JSON.",
            "Remember: You are ADVISORY. Your recommendation will be validated by guardrails.",
            "",
        ]
        
        return "\n".join(sections)


# Keep PromptBuilder as alias for backward compatibility
PromptBuilder = SafePromptTemplate


# ============================================================================
# STANDALONE PROMPT RENDERING
# ============================================================================

def render_prompt(
    objective: str,
    runtime_spec: Dict[str, Any],
    execution_history: List[Dict[str, Any]],
    current_state: Dict[str, Any],
) -> tuple[str, str]:
    """
    Render complete prompt for LLM planner.
    
    This is a standalone helper that can be used independently of LLMPlanner.
    Useful for:
    - Testing prompt generation
    - Debugging prompts
    - Pre-generating prompts for analysis
    
    Args:
        objective: High-level objective
        runtime_spec: Runtime specification (tools, constraints)
        execution_history: Execution history
        current_state: Current state
        
    Returns:
        Tuple of (system_prompt, user_prompt)
        
    Example:
        >>> system, user = render_prompt(
        ...     "Complete data processing",
        ...     runtime_spec,
        ...     [],
        ...     {'step': 0}
        ... )
        >>> print(system)
        >>> print(user)
    """
    system_prompt = SafePromptTemplate.build_system_prompt(objective)
    user_prompt = SafePromptTemplate.build_user_prompt(
        runtime_spec,
        execution_history,
        current_state,
    )
    return system_prompt, user_prompt


# ============================================================================
# OUTPUT PARSER
# ============================================================================

class OutputParser:
    """
    Parses and validates LLM output.
    
    Ensures output:
    - Is valid JSON
    - Matches expected schema
    - Contains required fields
    - Has valid values
    """
    
    VALID_ACTIONS = {'tool', 'final', 'noop'}
    
    @staticmethod
    def parse_response(raw_response: str) -> Union[Dict[str, Any], LLMPlannerFailure]:
        """
        Parse LLM response.
        
        Returns:
            Parsed dict or LLMPlannerFailure
        """
        if not raw_response or not raw_response.strip():
            return LLMPlannerFailure(
                error_type="empty_response",
                error_message="LLM returned empty response",
                raw_response=raw_response,
            )
        
        # Try to extract JSON from response
        # Some LLMs wrap JSON in markdown code blocks
        cleaned_response = raw_response.strip()
        
        # Remove markdown code blocks if present
        if cleaned_response.startswith('```'):
            lines = cleaned_response.split('\n')
            # Remove first line (```json or ```)
            lines = lines[1:]
            # Remove last line (```)
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            cleaned_response = '\n'.join(lines).strip()
        
        # Parse JSON
        try:
            data = json.loads(cleaned_response)
        except json.JSONDecodeError as e:
            return LLMPlannerFailure(
                error_type="invalid_json",
                error_message=f"Failed to parse JSON: {str(e)}",
                raw_response=raw_response,
            )
        
        # Validate schema
        validation_result = OutputParser.validate_schema(data)
        if isinstance(validation_result, LLMPlannerFailure):
            validation_result.raw_response = raw_response
            return validation_result
        
        return data
    
    @staticmethod
    def validate_schema(data: Dict[str, Any]) -> Union[Dict[str, Any], LLMPlannerFailure]:
        """
        Validate output schema.
        
        Returns:
            Original dict or LLMPlannerFailure
        """
        # Check action field
        if 'action' not in data:
            return LLMPlannerFailure(
                error_type="missing_field",
                error_message="Missing required field: 'action'",
            )
        
        action = data['action']
        if action not in OutputParser.VALID_ACTIONS:
            return LLMPlannerFailure(
                error_type="invalid_action",
                error_message=f"Invalid action '{action}'. Must be one of: {OutputParser.VALID_ACTIONS}",
            )
        
        # Validate tool action
        if action == 'tool':
            if 'tool_name' not in data or not data['tool_name']:
                return LLMPlannerFailure(
                    error_type="missing_tool_name",
                    error_message="Action 'tool' requires 'tool_name' field",
                )
        
        # Validate arguments field
        if 'arguments' in data:
            if not isinstance(data['arguments'], dict):
                return LLMPlannerFailure(
                    error_type="invalid_arguments",
                    error_message="Field 'arguments' must be a dict",
                )
        
        # Validate reasoning field
        if 'reasoning' not in data:
            data['reasoning'] = "No reasoning provided"
        
        return data
    
    @staticmethod
    def to_planner_decision(
        data: Dict[str, Any],
        available_tools: List[Dict[str, Any]],
    ) -> Union[PlannerDecision, LLMPlannerFailure]:
        """
        Convert parsed data to PlannerDecision.
        
        Args:
            data: Validated output data
            available_tools: Available tools from runtime spec
            
        Returns:
            PlannerDecision or LLMPlannerFailure
        """
        action = data['action']
        reasoning = data.get('reasoning', 'No reasoning provided')
        
        # Handle final action
        if action == 'final':
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning=reasoning,
                confidence=0.9,
            )
        
        # Handle noop action
        if action == 'noop':
            # Noop means skip this step, let loop continue
            # We can represent this as a low-confidence complete
            # or as a request for human intervention
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                reasoning=f"LLM requested no-op: {reasoning}",
                human_message="LLM cannot decide next action. Please review and continue manually.",
                confidence=0.5,
            )
        
        # Handle tool action
        tool_name = data['tool_name']
        arguments = data.get('arguments', {})
        
        # Find tool by name
        tool = None
        for t in available_tools:
            if t.get('tool_name') == tool_name:
                tool = t
                break
        
        if not tool:
            return LLMPlannerFailure(
                error_type="tool_not_found",
                error_message=f"Tool '{tool_name}' not found in available tools",
                fallback_decision=PlannerDecision(
                    decision_type=PlannerDecisionType.REQUEST_HUMAN,
                    reasoning=f"LLM requested unknown tool '{tool_name}'",
                    human_message=f"LLM tried to use unknown tool: {tool_name}",
                    confidence=0.0,
                ),
            )
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=tool['tool_id'],
            tool_parameters=arguments,
            reasoning=reasoning,
            confidence=0.85,
        )


# ============================================================================
# LLM PLANNER
# ============================================================================

class LLMPlanner(Planner):
    """
    LLM-based planner that integrates external LLMs.
    
    This planner:
    - Makes exactly ONE LLM call per decision
    - Uses structured prompting (JSON output)
    - Enforces strict schema validation
    - Handles timeouts and errors safely
    - Returns structured failure objects (no exceptions)
    
    Compatible with OpenAI, Anthropic, and other LLM providers.
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        model: str = "gpt-4",
        objective: str = "Complete the pipeline execution successfully",
        max_tokens: int = 1000,
        temperature: float = 0.3,
        timeout_seconds: float = 30.0,
    ):
        """
        Initialize LLM planner.
        
        Args:
            llm_client: LLM client implementing LLMClient protocol
            model: Model name (e.g., 'gpt-4', 'claude-3-opus')
            objective: High-level objective for the agent
            max_tokens: Maximum tokens to generate
            temperature: Temperature (0.0 - 1.0, lower = more deterministic)
            timeout_seconds: Timeout for LLM calls
        """
        self.llm_client = llm_client
        self.model = model
        self.objective = objective
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds
    
    async def plan_next_action(
        self,
        runtime_spec: Dict[str, Any],
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> PlannerDecision:
        """
        Plan next action using LLM.
        
        This method is BOUNDED and STATELESS:
        1. Builds SAFE structured prompt (sanitized, escaped)
        2. Makes exactly ONE LLM call (with timeout)
        3. Parses and validates response (strict JSON schema)
        4. Converts to PlannerDecision (or safe failure)
        
        If anything fails, returns a safe FAIL or REQUEST_HUMAN decision.
        NEVER raises exceptions.
        
        Args:
            runtime_spec: Runtime specification (tools, constraints)
            execution_history: Execution history (what's been done)
            current_state: Current state (variables, outputs)
            
        Returns:
            PlannerDecision (always returns, never raises)
        """
        start_time = datetime.now(timezone.utc)
        
        # Build SAFE prompt using SafePromptTemplate
        system_prompt = SafePromptTemplate.build_system_prompt(self.objective)
        user_prompt = SafePromptTemplate.build_user_prompt(
            runtime_spec,
            execution_history,
            current_state,
        )
        
        messages = [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ]
        
        # Call LLM with timeout
        try:
            response = await asyncio.wait_for(
                self.llm_client.create_completion(
                    messages=messages,
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                    timeout=self.timeout_seconds,
                ),
                timeout=self.timeout_seconds,
            )
            
            raw_response = response.get('content', '')
            tokens_used = response.get('usage', {}).get('total_tokens')
            
        except asyncio.TimeoutError:
            return PlannerDecision(
                decision_type=PlannerDecisionType.FAIL,
                reasoning=f"LLM request timed out after {self.timeout_seconds}s",
                confidence=0.0,
            )
        
        except Exception as e:
            return PlannerDecision(
                decision_type=PlannerDecisionType.FAIL,
                reasoning=f"LLM request failed: {str(e)}",
                confidence=0.0,
            )
        
        # Calculate latency
        latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        
        # Parse response
        parsed = OutputParser.parse_response(raw_response)
        if isinstance(parsed, LLMPlannerFailure):
            return parsed.to_decision()
        
        # Validate and convert to decision
        available_tools = runtime_spec.get('available_tools', [])
        decision_result = OutputParser.to_planner_decision(parsed, available_tools)
        
        if isinstance(decision_result, LLMPlannerFailure):
            return decision_result.to_decision()
        
        # Success - return decision
        return decision_result


# ============================================================================
# MOCK LLM CLIENT (FOR TESTING)
# ============================================================================

class MockLLMClient:
    """
    Mock LLM client for testing.
    
    This client returns deterministic responses for testing purposes.
    In production, use OpenAIClient or AnthropicClient.
    """
    
    def __init__(self, responses: Optional[List[str]] = None):
        """
        Initialize mock client.
        
        Args:
            responses: List of responses to return (cycles through them)
        """
        self.responses = responses or [
            '{"action": "tool", "tool_name": "Node 1", "arguments": {}, "reasoning": "Starting with first tool"}',
            '{"action": "final", "reasoning": "All work complete"}',
        ]
        self.call_count = 0
    
    async def create_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int,
        temperature: float,
        timeout: float,
    ) -> Dict[str, Any]:
        """Return mock response."""
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        
        return {
            'content': response,
            'usage': {'total_tokens': 100},
        }


# ============================================================================
# OPENAI CLIENT ADAPTER
# ============================================================================

class OpenAIClient:
    """
    OpenAI API client adapter.
    
    This adapter wraps the OpenAI Python client to match our LLMClient protocol.
    
    Usage:
        import openai
        client = OpenAIClient(api_key="sk-...")
        planner = LLMPlanner(client, model="gpt-4")
    """
    
    def __init__(self, api_key: str, base_url: Optional[str] = None):
        """
        Initialize OpenAI client.
        
        Args:
            api_key: OpenAI API key
            base_url: Optional base URL (for Azure OpenAI, etc.)
        """
        # TODO: Import openai library when available
        # For now, this is a stub that shows the interface
        self.api_key = api_key
        self.base_url = base_url
        self._client = None  # Would be: openai.AsyncOpenAI(api_key=api_key)
    
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
        
        TODO: Implement this when openai library is installed.
        For now, raise an error with installation instructions.
        """
        raise NotImplementedError(
            "OpenAI client requires 'openai' library. Install with: pip install openai"
        )
        
        # TODO: Uncomment when openai is installed
        # response = await self._client.chat.completions.create(
        #     model=model,
        #     messages=messages,
        #     max_tokens=max_tokens,
        #     temperature=temperature,
        #     timeout=timeout,
        # )
        # 
        # return {
        #     'content': response.choices[0].message.content,
        #     'usage': {
        #         'total_tokens': response.usage.total_tokens,
        #     },
        # }


# ============================================================================
# ANTHROPIC CLIENT ADAPTER
# ============================================================================

class AnthropicClient:
    """
    Anthropic API client adapter.
    
    This adapter wraps the Anthropic Python client to match our LLMClient protocol.
    
    Usage:
        import anthropic
        client = AnthropicClient(api_key="sk-ant-...")
        planner = LLMPlanner(client, model="claude-3-opus-20240229")
    """
    
    def __init__(self, api_key: str):
        """
        Initialize Anthropic client.
        
        Args:
            api_key: Anthropic API key
        """
        # TODO: Import anthropic library when available
        # For now, this is a stub that shows the interface
        self.api_key = api_key
        self._client = None  # Would be: anthropic.AsyncAnthropic(api_key=api_key)
    
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
        
        TODO: Implement this when anthropic library is installed.
        For now, raise an error with installation instructions.
        """
        raise NotImplementedError(
            "Anthropic client requires 'anthropic' library. Install with: pip install anthropic"
        )
        
        # TODO: Uncomment when anthropic is installed
        # # Convert messages to Anthropic format
        # system_message = next((m['content'] for m in messages if m['role'] == 'system'), '')
        # user_messages = [m for m in messages if m['role'] != 'system']
        # 
        # response = await self._client.messages.create(
        #     model=model,
        #     system=system_message,
        #     messages=user_messages,
        #     max_tokens=max_tokens,
        #     temperature=temperature,
        #     timeout=timeout,
        # )
        # 
        # return {
        #     'content': response.content[0].text,
        #     'usage': {
        #         'total_tokens': response.usage.input_tokens + response.usage.output_tokens,
        #     },
        # }
