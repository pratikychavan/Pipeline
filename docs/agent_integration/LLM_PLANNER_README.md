# LLM Planner

## Overview

The LLM Planner is a **bounded, stateless, plug-and-play** component that integrates Large Language Models (LLMs) into the agent execution system. It makes intelligent decisions about which tools to execute based on the current state and execution history.

## Key Features

✅ **Bounded**: Exactly ONE LLM call per decision - prevents runaway costs  
✅ **Stateless**: No internal state - pure function behavior  
✅ **Structured**: JSON output enforced via system prompt - prevents hallucination  
✅ **Safe**: Never raises exceptions - returns failure objects instead  
✅ **Observable**: Tracks tokens and latency for cost/performance monitoring  
✅ **Compatible**: Implements existing `Planner` interface - drop-in replacement for `DeterministicPlanner`  
✅ **Secure**: State sanitization (keys only, no values) prevents data leakage  
✅ **Efficient**: History truncation (200 chars/item) prevents context overflow  

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         LLM Planner                              │
│                                                                  │
│  ┌────────────────┐    ┌──────────────┐    ┌────────────────┐  │
│  │ PromptBuilder  │───▶│  LLMClient   │───▶│ OutputParser   │  │
│  │                │    │              │    │                │  │
│  │ • System       │    │ • OpenAI     │    │ • JSON Parse   │  │
│  │ • Tools        │    │ • Anthropic  │    │ • Validate     │  │
│  │ • History      │    │ • Custom     │    │ • Convert      │  │
│  │ • State        │    │              │    │                │  │
│  └────────────────┘    └──────────────┘    └────────────────┘  │
│                              │                      │           │
│                              ▼                      ▼           │
│                        LLM Response         PlannerDecision     │
└─────────────────────────────────────────────────────────────────┘
```

## Files

- **`agent_integration/llm_planner.py`** (650+ lines)
  - `LLMClient` protocol: Interface for LLM providers
  - `PromptBuilder`: Structured prompt generation
  - `OutputParser`: JSON parsing and schema validation
  - `LLMPlanner`: Main planner implementation
  - `MockLLMClient`: Testing implementation
  - `OpenAIClient`: OpenAI API adapter (stub)
  - `AnthropicClient`: Anthropic API adapter (stub)

- **`agent_integration/tests/test_llm_planner.py`** (500+ lines)
  - 33 comprehensive test cases
  - Mock-based testing (no real API calls required)
  - Covers all components and error scenarios

- **`agent_integration/llm_planner_examples.py`**
  - 5 complete usage examples
  - Demonstrates integration, error handling, fallback strategies

- **`agent_integration/LLM_PLANNER_README.md`**
  - This file

## Quick Start

### 1. Using Mock Client (Testing)

```python
from agent_integration.llm_planner import LLMPlanner, MockLLMClient
from agent_integration.execution_loop import AgentLoopRunner

# Create mock client with predefined responses
mock_responses = [
    '{"action": "tool", "tool_name": "ValidateInput", "arguments": {}, "reasoning": "First validate"}',
    '{"action": "tool", "tool_name": "ProcessData", "arguments": {}, "reasoning": "Then process"}',
    '{"action": "final", "reasoning": "Work complete"}',
]
client = MockLLMClient(mock_responses)

# Create planner
planner = LLMPlanner(client, model='mock-gpt-4')

# Run agent loop
result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
```

### 2. Using OpenAI (Production)

```python
from agent_integration.llm_planner import LLMPlanner, OpenAIClient

# Create OpenAI client
client = OpenAIClient(api_key='sk-...')

# Create planner
planner = LLMPlanner(
    llm_client=client,
    model='gpt-4',
    objective='Complete the data processing pipeline',
    max_tokens=1000,
    temperature=0.3,
    timeout_seconds=30.0,
)

# Run agent loop
result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
```

### 3. Using Anthropic (Production)

```python
from agent_integration.llm_planner import LLMPlanner, AnthropicClient

# Create Anthropic client
client = AnthropicClient(api_key='sk-ant-...')

# Create planner
planner = LLMPlanner(
    llm_client=client,
    model='claude-3-opus-20240229',
    objective='Execute the pipeline efficiently',
    max_tokens=1000,
    temperature=0.3,
)

# Run agent loop
result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
```

### 4. Fallback Strategy

```python
from agent_integration.llm_planner import LLMPlanner, OpenAIClient
from agent_integration.execution_loop import DeterministicPlanner, AgentLoopRunner

# Try LLM planner first
try:
    client = OpenAIClient(api_key='sk-...')
    planner = LLMPlanner(client, model='gpt-4')
    result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
    
    if not result.success:
        # Fall back to deterministic planner
        fallback_planner = DeterministicPlanner()
        result = await AgentLoopRunner.start_loop(agent_run, planner=fallback_planner)
except Exception:
    # Always fall back to deterministic planner
    fallback_planner = DeterministicPlanner()
    result = await AgentLoopRunner.start_loop(agent_run, planner=fallback_planner)
```

## LLM Client Protocol

All LLM clients must implement the `LLMClient` protocol:

```python
from typing import Protocol, Dict, Any

class LLMClient(Protocol):
    """Protocol for LLM clients."""
    
    async def create_completion(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> Dict[str, Any]:
        """
        Create a completion request.
        
        Returns:
            Dict with keys:
            - 'content': str (the generated text)
            - 'usage': dict with 'total_tokens' (optional)
        """
        ...
```

## Decision Types

The planner returns one of three decision types:

1. **`EXECUTE_TOOL`**: Execute a specific tool
   ```json
   {
     "action": "tool",
     "tool_name": "ValidateInput",
     "arguments": {"key": "value"},
     "reasoning": "Need to validate input data"
   }
   ```

2. **`COMPLETE`**: Work is done
   ```json
   {
     "action": "final",
     "reasoning": "All tasks completed successfully"
   }
   ```

3. **`REQUEST_HUMAN`**: Need human intervention (fallback for unknown tools or errors)
   ```json
   {
     "action": "noop",
     "reasoning": "Unable to proceed, need human guidance"
   }
   ```

## Prompt Structure

The planner builds structured prompts with 4 sections:

### 1. System Prompt
- Role definition (autonomous agent)
- JSON schema for output
- Decision type explanations
- Constraints (one tool at a time, no retries)

### 2. Tools Section
- Available tools with descriptions
- Constraints for each tool
- Execution context

### 3. History Section (Optional)
- Previous decisions and outcomes
- Truncated to 200 chars per entry
- Helps LLM understand context

### 4. State Section (Sanitized)
- Current state keys (no values for security)
- Shows what data is available
- Prevents data leakage

Example prompt:
```
You are an autonomous agent that controls a data pipeline.

Available tools:
- ValidateInput: Validate input data (no constraints)
- ProcessData: Process data (requires: ValidateInput)

Execution history:
Step 1: EXECUTE_TOOL ValidateInput - Success

Current state (keys only):
- input_data
- validation_result

What is the next action?
```

## Error Handling

The planner **never raises exceptions**. All errors are converted to safe decisions:

| Error Type | Result | Decision Type | Example |
|------------|--------|---------------|---------|
| Invalid JSON | Failure | `REQUEST_HUMAN` | "Could not parse LLM response" |
| Missing fields | Failure | `REQUEST_HUMAN` | "Response missing 'action' field" |
| Unknown tool | Failure | `REQUEST_HUMAN` | "Tool 'Unknown' not available" |
| Timeout | Failure | `FAIL` | "LLM request timed out after 30s" |
| API Error | Failure | `FAIL` | "LLM client error: API error" |

## Result Types

### LLMPlannerSuccess

```python
@dataclass
class LLMPlannerSuccess:
    decision: PlannerDecision
    raw_response: str
    tokens_used: Optional[int]
    latency_ms: float
    
    def to_decision(self) -> PlannerDecision:
        return self.decision
```

### LLMPlannerFailure

```python
@dataclass
class LLMPlannerFailure:
    error_type: str
    error_message: str
    raw_response: Optional[str]
    fallback_decision: Optional[PlannerDecision]
    
    def to_decision(self) -> PlannerDecision:
        return self.fallback_decision or PlannerDecision(
            decision_type=PlannerDecisionType.FAIL,
            reasoning=f"{self.error_type}: {self.error_message}",
        )
```

## Configuration

### LLMPlanner Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `llm_client` | `LLMClient` | Required | LLM client instance |
| `model` | `str` | `"gpt-4"` | Model name |
| `objective` | `str` | `"Complete..."` | High-level objective |
| `max_tokens` | `int` | `1000` | Max tokens to generate |
| `temperature` | `float` | `0.3` | Sampling temperature (0.0-1.0) |
| `timeout_seconds` | `float` | `30.0` | Request timeout |

### Recommended Settings

**For Production:**
```python
planner = LLMPlanner(
    llm_client=client,
    model='gpt-4',
    temperature=0.3,  # Low temperature for consistency
    max_tokens=1000,
    timeout_seconds=30.0,
)
```

**For Testing:**
```python
planner = LLMPlanner(
    llm_client=client,
    model='gpt-3.5-turbo',
    temperature=0.0,  # Deterministic
    max_tokens=500,
    timeout_seconds=10.0,
)
```

**For Creativity:**
```python
planner = LLMPlanner(
    llm_client=client,
    model='gpt-4',
    temperature=0.7,  # Higher temperature
    max_tokens=1500,
    timeout_seconds=45.0,
)
```

## Testing

### Run All Tests

```bash
python manage.py test agent_integration.tests.test_llm_planner
```

### Run Specific Test Class

```bash
python manage.py test agent_integration.tests.test_llm_planner.LLMPlannerTests
```

### Run Single Test

```bash
python manage.py test agent_integration.tests.test_llm_planner.LLMPlannerTests.test_planner_with_mock_client
```

### Test Coverage

- **PromptBuilderTests**: 7 tests
- **OutputParserTests**: 11 tests
- **MockLLMClientTests**: 1 test
- **LLMPlannerTests**: 9 tests
- **IntegrationTests**: 3 tests
- **LLMPlannerFailureTests**: 2 tests

**Total: 33 tests** ✅

## Examples

Run the examples file:

```bash
python agent_integration/llm_planner_examples.py
```

This will run 5 examples:
1. Basic LLM planner with mock client
2. LLM planner vs deterministic planner comparison
3. Error handling demonstrations
4. OpenAI client interface (stub)
5. Fallback strategy

## Integration with Existing System

### Compatible with AgentExecutionLoop

The LLM planner implements the same `Planner` interface as `DeterministicPlanner`:

```python
class Planner(ABC):
    @abstractmethod
    def decide(self, planner_input: PlannerInput) -> PlannerDecision:
        """Make a decision about the next action."""
        pass
```

### Swap Planners Without Code Changes

```python
from agent_integration.execution_loop import AgentLoopRunner, DeterministicPlanner
from agent_integration.llm_planner import LLMPlanner, OpenAIClient

# Use deterministic planner
det_planner = DeterministicPlanner()
result1 = await AgentLoopRunner.start_loop(agent_run, planner=det_planner)

# Use LLM planner
client = OpenAIClient(api_key='sk-...')
llm_planner = LLMPlanner(client, model='gpt-4')
result2 = await AgentLoopRunner.start_loop(agent_run, planner=llm_planner)
```

## Security Considerations

### State Sanitization

The planner **never sends state values** to the LLM:

```python
# State section shows only keys
"Current state (keys only):"
"- input_data"
"- validation_result"
```

This prevents:
- Sensitive data leakage
- PII exposure
- API key exposure
- Database credentials exposure

### History Truncation

Execution history is truncated to 200 characters per entry:

```python
reasoning = reasoning[:200] + "..." if len(reasoning) > 200 else reasoning
```

This prevents:
- Context overflow
- Token limit exceeded
- Cost explosion

## Cost Monitoring

The planner tracks tokens and latency for every decision:

```python
result = await planner.plan_next_action(...)

if isinstance(result, LLMPlannerSuccess):
    print(f"Tokens used: {result.tokens_used}")
    print(f"Latency: {result.latency_ms}ms")
    print(f"Cost estimate: {result.tokens_used * 0.00003}")  # $0.03 per 1K tokens for GPT-4
```

## Troubleshooting

### Issue: "openai module not found"

**Solution**: Install OpenAI library
```bash
pip install openai
```

### Issue: "anthropic module not found"

**Solution**: Install Anthropic library
```bash
pip install anthropic
```

### Issue: "LLM request timed out"

**Solution**: Increase timeout
```python
planner = LLMPlanner(client, timeout_seconds=60.0)
```

### Issue: "Invalid JSON response"

**Solution**: Use lower temperature for consistency
```python
planner = LLMPlanner(client, temperature=0.0)
```

### Issue: "Unknown tool requested"

**Solution**: This is expected - planner falls back to `REQUEST_HUMAN` automatically

### Issue: High costs

**Solution**: 
1. Use `gpt-3.5-turbo` instead of `gpt-4`
2. Reduce `max_tokens`
3. Implement caching for repeated decisions
4. Use deterministic planner for simple pipelines

## Performance

### Benchmarks (Mock Client)

| Test | Time | Result |
|------|------|--------|
| Single decision | ~0.001s | ✅ Pass |
| 10 decisions | ~0.010s | ✅ Pass |
| Timeout handling | ~0.110s | ✅ Pass |
| Error handling | ~0.001s | ✅ Pass |

### Real LLM Performance (Expected)

| Provider | Model | Avg Latency | Tokens/Decision |
|----------|-------|-------------|-----------------|
| OpenAI | GPT-4 | 2-5s | 200-500 |
| OpenAI | GPT-3.5 | 1-2s | 150-300 |
| Anthropic | Claude-3 | 2-4s | 200-400 |

## Future Enhancements

- [ ] Implement OpenAIClient (requires `openai` library)
- [ ] Implement AnthropicClient (requires `anthropic` library)
- [ ] Add prompt templates system
- [ ] Add decision caching
- [ ] Add cost tracking to database
- [ ] Add LLM configuration UI
- [ ] Add streaming support for long responses
- [ ] Add multi-model ensemble voting
- [ ] Add prompt optimization based on success rate

## FAQ

**Q: Does the planner make multiple LLM calls per decision?**  
A: No. Exactly ONE call per `plan_next_action()`. This is a core design principle.

**Q: What happens if the LLM returns invalid JSON?**  
A: The planner returns a failure decision with `REQUEST_HUMAN` type. No exceptions raised.

**Q: Can I use multiple LLM providers?**  
A: Yes. Implement the `LLMClient` protocol for any provider.

**Q: Does this work with local LLMs (Ollama, LM Studio)?**  
A: Yes. Create a custom client implementing `LLMClient` protocol.

**Q: How do I debug what the LLM is seeing?**  
A: Check `LLMPlannerSuccess.raw_response` or enable logging in your client.

**Q: Can I use this with streaming responses?**  
A: Not currently. The planner expects a complete response. Future enhancement planned.

**Q: Is the planner thread-safe?**  
A: Yes. It's stateless and uses `asyncio` for concurrency.

**Q: Can I retry failed decisions?**  
A: The planner doesn't retry internally. Implement retry logic at the loop level if needed.

## License

Same as parent project.

## Contributors

- Agent Integration Team
- LLM Planning System

## Support

For issues or questions:
1. Check this README
2. Review the examples file
3. Check test cases for usage patterns
4. Open an issue in the project repository
