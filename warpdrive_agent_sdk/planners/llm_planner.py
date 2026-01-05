"""
LLM Planner

LLM-based intelligent planner using external language models.

This planner uses LLMs (OpenAI, Anthropic, etc.) to make intelligent
decisions about which tools to execute next.

CRITICAL CONSTRAINTS:
- ONE LLM call per decision (no loops)
- STATELESS (no memory between calls)
- STRUCTURED output (strict JSON schema)
- SAFE errors (no exceptions, return failures)
"""

from typing import Dict, Any, List, Optional, Protocol
from dataclasses import dataclass
import json
import asyncio

from ..interfaces.planner import (
    Planner,
    PlannerDecision,
    PlannerDecisionType,
    PlannerInput,
    PlannerFailure,
)


# ============================================================================
# LLM CLIENT PROTOCOL
# ============================================================================

class LLMClient(Protocol):
    """
    Protocol for LLM clients.
    
    Implement this interface to integrate different LLM providers.
    Compatible with OpenAI, Anthropic, and other providers.
    
    Example:
        >>> class OpenAIClient:
        ...     async def create_completion(self, messages, model, max_tokens, temperature, timeout):
        ...         # Call OpenAI API
        ...         response = await openai.chat.completions.create(...)
        ...         return {'content': response.choices[0].message.content}
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
            model: Model name (e.g., 'gpt-4o-mini', 'claude-3-opus')
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
# LLM PLANNER
# ============================================================================

class LLMPlanner(Planner):
    """
    LLM-based intelligent planner.
    
    This planner uses a language model to analyze the current state
    and make intelligent decisions about which tools to execute next.
    
    Usage:
        >>> llm_client = MyLLMClient()  # Implement LLMClient protocol
        >>> planner = LLMPlanner(
        ...     llm_client=llm_client,
        ...     model='gpt-4o-mini',
        ...     temperature=0.3
        ... )
        >>> decision = await planner.plan_next_action(planner_input)
    
    CONSTRAINTS:
    - ONE call per decision (no loops)
    - Returns structured PlannerDecision
    - Handles errors gracefully (no exceptions)
    - Does NOT execute tools
    - Does NOT access platform internals
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        model: str = 'gpt-4o-mini',
        temperature: float = 0.3,
        max_tokens: int = 2000,
        timeout: float = 30.0,
        system_prompt: Optional[str] = None,
    ):
        """
        Initialize LLM planner.
        
        Args:
            llm_client: Client implementing LLMClient protocol
            model: LLM model name
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens for response
            timeout: Timeout in seconds
            system_prompt: Custom system prompt (optional)
        """
        self.llm_client = llm_client
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.system_prompt = system_prompt or self._default_system_prompt()
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan next action using LLM.
        
        This method:
        1. Builds prompt from current state
        2. Calls LLM
        3. Parses response into PlannerDecision
        4. Returns decision (or failure)
        
        Args:
            planner_input: Current execution state
            
        Returns:
            PlannerDecision for next action
        """
        try:
            # Build prompt
            messages = self._build_messages(planner_input)
            
            # Call LLM
            response = await self.llm_client.create_completion(
                messages=messages,
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                timeout=self.timeout,
            )
            
            # Parse response
            content = response.get('content', '')
            decision = self._parse_response(content)
            
            return decision
            
        except TimeoutError as e:
            # Return failure on timeout
            failure = PlannerFailure(
                error_type='timeout',
                error_message=f'LLM call timed out after {self.timeout}s',
            )
            return failure.to_decision()
            
        except Exception as e:
            # Return failure on any other error
            failure = PlannerFailure(
                error_type='llm_error',
                error_message=str(e),
            )
            return failure.to_decision()
    
    def _default_system_prompt(self) -> str:
        """
        Default system prompt for LLM.
        
        This prompt guides the LLM to:
        - Analyze available tools
        - Consider execution history
        - Make structured decisions
        - Return valid JSON
        """
        return """You are an intelligent agent planner. Your job is to analyze the current state and decide which tool to execute next.

You will receive:
- Available tools with descriptions and parameters
- Execution history (what's been done)
- Current state (variables, outputs)

You must return a JSON decision with this structure:
{
  "decision_type": "execute_tool" | "complete" | "request_human" | "fail",
  "tool_id": "tool_to_execute",  // required for execute_tool
  "tool_parameters": {},  // parameters for the tool
  "reasoning": "why you made this decision",
  "confidence": 0.0-1.0
}

RULES:
1. Execute tools in logical order based on dependencies
2. Only execute tools that are available
3. Provide clear reasoning for each decision
4. Return "complete" when all necessary work is done
5. Return "request_human" if you need human input
6. Return "fail" if you cannot proceed

Return ONLY valid JSON, no other text."""
    
    def _build_messages(self, planner_input: PlannerInput) -> List[Dict[str, str]]:
        """
        Build messages for LLM call.
        
        Args:
            planner_input: Current execution state
            
        Returns:
            List of message dicts for LLM
        """
        # System message
        messages = [
            {'role': 'system', 'content': self.system_prompt}
        ]
        
        # User message with current state
        user_content = self._format_state(planner_input)
        messages.append({'role': 'user', 'content': user_content})
        
        return messages
    
    def _format_state(self, planner_input: PlannerInput) -> str:
        """
        Format current state for LLM.
        
        Args:
            planner_input: Current execution state
            
        Returns:
            Formatted string for LLM
        """
        parts = []
        
        # Available tools
        tools = planner_input.get_available_tools()
        parts.append(f"Available tools ({len(tools)}):")
        for tool in tools:
            tool_str = f"- {tool.get('tool_id')}: {tool.get('name', 'N/A')}"
            if tool.get('description'):
                tool_str += f" - {tool.get('description')}"
            parts.append(tool_str)
        
        # Execution history
        executed = planner_input.get_executed_tools()
        parts.append(f"\nAlready executed ({len(executed)}): {', '.join(executed)}")
        
        # Current step
        parts.append(f"\nCurrent step: {planner_input.step_number}")
        
        # Constraints
        constraints = planner_input.get_execution_constraints()
        if constraints:
            parts.append(f"\nExecution constraints: {len(constraints)} constraints")
        
        return '\n'.join(parts)
    
    def _parse_response(self, content: str) -> PlannerDecision:
        """
        Parse LLM response into PlannerDecision.
        
        Args:
            content: Response content from LLM
            
        Returns:
            PlannerDecision
            
        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Try to extract JSON from response
            data = json.loads(content)
            
            # Parse decision type
            decision_type_str = data.get('decision_type', '').lower()
            decision_type = {
                'execute_tool': PlannerDecisionType.EXECUTE_TOOL,
                'complete': PlannerDecisionType.COMPLETE,
                'request_human': PlannerDecisionType.REQUEST_HUMAN,
                'fail': PlannerDecisionType.FAIL,
            }.get(decision_type_str)
            
            if not decision_type:
                raise ValueError(f"Invalid decision_type: {decision_type_str}")
            
            # Build decision
            decision = PlannerDecision(
                decision_type=decision_type,
                tool_id=data.get('tool_id'),
                tool_parameters=data.get('tool_parameters', {}),
                reasoning=data.get('reasoning', ''),
                confidence=data.get('confidence', 1.0),
                human_message=data.get('human_message'),
            )
            
            # Validate
            decision.validate()
            
            return decision
            
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON response: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse decision: {e}")
