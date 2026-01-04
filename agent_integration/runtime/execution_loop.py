"""
Agent Execution Loop

Coordinates LLM-based execution flow with guardrails.
This is the main orchestration engine.
"""

from typing import Dict, Any, Optional, List
import json
from django.utils import timezone
from core.models import PipelineExecution
from ..models import AgentRun, AgentDecision, RuntimeSpec
from ..runtime.spec_builder import RuntimeSpecBuilder, SpecValidator
from ..guardrails import GuardrailEngine, GuardrailViolation
from ..tools import ToolRegistry, NodeToolWrapper


class AgentExecutionLoop:
    """
    Main execution loop for agent-driven pipeline execution.
    
    Flow:
    1. Initialize runtime spec
    2. Loop:
        a. Get available choices from guardrails
        b. Call planner (LLM) for decision
        c. Validate decision with guardrails
        d. Execute tool (node) via existing backend
        e. Record result
        f. Check completion
    3. Finalize execution
    
    CRITICAL: The LLM is a CONTROLLER, not a processor.
    It decides what to execute, but does not execute directly.
    """
    
    def __init__(
        self,
        pipeline_execution: PipelineExecution,
        agent_config: Optional[Dict[str, Any]] = None
    ):
        self.pipeline_execution = pipeline_execution
        
        # Merge provided config with defaults
        default_config = self._default_config()
        if agent_config:
            default_config.update(agent_config)
        self.agent_config = default_config
        
        # Extract guardrail config early (needed for guardrail engine initialization)
        self.guardrail_config = agent_config.get('guardrail_config', {}) if agent_config else {}
        
        # Execution state
        self.current_step = 0
        self.consecutive_failures = 0
        self.execution_context = {}
        self.execution_start_time = None
        self.total_cost_usd = 0.0
        
        # Initialize agent run
        self.agent_run = self._initialize_agent_run()
        
        # Build runtime spec
        self.runtime_spec = self._build_runtime_spec()
        
        # Initialize guardrails
        self.guardrails = GuardrailEngine(
            self.runtime_spec.spec_data,
            guardrail_config=self.guardrail_config
        )
        
        # Initialize tool registry
        self.tool_registry = ToolRegistry(pipeline_execution.pipeline)
    
    def _default_config(self) -> Dict[str, Any]:
        """Default agent configuration."""
        return {
            'model': 'gpt-4o-mini',
            'temperature': 0.3,
            'max_tokens': 2000,
            'enable_human_intervention': True,
            'max_steps': 100,
            'fail_on_node_failure': True,  # Stop execution if any node fails
        }
    
    def _initialize_agent_run(self) -> AgentRun:
        """Create AgentRun record."""
        from ..models import AgentRun
        
        agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_execution,
            status='initializing',
            agent_config=self.agent_config,
            max_steps=self.agent_config.get('max_steps', 100)
        )
        
        return agent_run
    
    def _build_runtime_spec(self) -> RuntimeSpec:
        """Build and save runtime specification."""
        builder = RuntimeSpecBuilder(self.pipeline_execution.pipeline)
        runtime_spec = builder.materialize_and_save(self.agent_run)
        
        # Validate spec
        is_valid, errors = SpecValidator.validate_spec(runtime_spec.spec_data)
        if not is_valid:
            raise ValueError(f"Invalid runtime spec: {errors}")
        
        return runtime_spec
    
    def execute(self) -> Dict[str, Any]:
        """
        Main execution loop.
        
        Returns:
            Execution summary
        """
        try:
            # Update status
            self.agent_run.status = 'planning'
            self.agent_run.save()
            
            # Track execution start time
            from django.utils import timezone
            self.execution_start_time = timezone.now()
            
            # Initialize context with pipeline arguments
            self._initialize_execution_context()
            
            # Main loop
            while not self._is_complete():
                self.current_step += 1
                
                # Check guardrail limits
                self._check_guardrail_limits()
                
                # Check iteration limit
                if self.current_step > self.agent_run.max_steps:
                    raise RuntimeError(f"Maximum steps ({self.agent_run.max_steps}) exceeded")
                
                # Execute one step
                step_result = self._execute_step()
                
                # Check for human intervention request
                if step_result.get('human_intervention_required'):
                    self._request_human_intervention(
                        step_result.get('reason', 'Agent requested human input')
                    )
                    break
                
                # Check for errors
                if step_result.get('status') == 'failed':
                    self.consecutive_failures += 1
                    
                    # Check if should fail immediately on any node failure
                    if self.agent_config.get('fail_on_node_failure', True):
                        raise RuntimeError(f"Node execution failed: {step_result.get('error', 'Unknown error')}")
                    
                    # Check if too many consecutive failures
                    if self.consecutive_failures >= 3:
                        raise RuntimeError("Too many consecutive failures")
                else:
                    self.consecutive_failures = 0
            
            # Finalize
            if not self.agent_run.human_intervention_required:
                self._finalize_execution()
            
            return {
                'agent_run_id': str(self.agent_run.id),
                'status': self.agent_run.status,
                'steps_executed': self.current_step,
                'summary': self._generate_summary()
            }
            
        except Exception as e:
            self._handle_failure(str(e))
            raise
    
    def _execute_step(self) -> Dict[str, Any]:
        """
        Execute one step of the agent loop.
        
        Returns:
            Step execution result
        """
        # Get available choices from guardrails
        available_nodes = self.guardrails.get_safe_choices()
        
        if not available_nodes:
            # Check if complete or deadlocked
            if self.guardrails.graph_guardrails.state.is_complete():
                return {'status': 'complete'}
            else:
                return {
                    'status': 'failed',
                    'error': 'No available nodes (possible deadlock)',
                    'human_intervention_required': True,
                    'reason': 'Execution deadlocked - no nodes available to execute'
                }
        
        # Call planner to select next node
        selected_node_id, reasoning = self._call_planner(available_nodes)
        
        # Validate selection with guardrails
        is_valid, violations = self.guardrails.validate_before_execution(
            selected_node_id,
            self.current_step,
            self.consecutive_failures
        )
        
        # Record decision
        decision = self._record_decision(
            decision_type='select_node',
            selected_node_id=selected_node_id,
            reasoning=reasoning,
            violations=violations
        )
        
        if not is_valid:
            # Guardrail violation - record and potentially request human intervention
            error_msg = '; '.join(v.message for v in violations)
            
            return {
                'status': 'failed',
                'error': f"Guardrail violations: {error_msg}",
                'human_intervention_required': True,
                'reason': f"Agent selected invalid node: {error_msg}"
            }
        
        # Execute tool (node)
        tool = self.tool_registry.get_tool(selected_node_id)
        if not tool:
            return {
                'status': 'failed',
                'error': f"Tool {selected_node_id} not found"
            }
        
        # Check if high-risk approval is required
        if self.guardrail_config.get('require_approval_for_high_risk', False):
            # Check if this is a high-risk node
            if self._is_high_risk_node(selected_node_id):
                return {
                    'status': 'failed',
                    'error': 'High-risk operation requires human approval',
                    'human_intervention_required': True,
                    'reason': f'Node {selected_node_id} requires approval before execution'
                }
        
        # Update status
        self.agent_run.status = 'executing'
        self.agent_run.current_step = self.current_step
        self.agent_run.save()
        
        # Execute
        result = tool.execute(
            agent_run=self.agent_run,
            context=self.execution_context,
            agent_decision=decision
        )
        
        # Update guardrails state
        success = result['status'] == 'completed'
        self.guardrails.record_execution_result(selected_node_id, success)
        
        # Update execution context with outputs
        if success:
            self._update_context_with_outputs(result)
        
        return {
            'status': result['status'],
            'tool_execution_id': result.get('tool_execution_id'),
            'summary': result.get('summary')
        }
    
    def _call_planner(self, available_nodes: List[str]) -> tuple[str, str]:
        """
        Call LLM planner to select next node.
        
        Args:
            available_nodes: List of node IDs that can be executed
            
        Returns:
            (selected_node_id, reasoning)
        """
        # Check if we should use real LLM or fallback
        model = self.agent_config.get('model', 'gpt-4')
        
        # If model is specified and not fallback, use LLM planner
        if model and model != 'fallback-ordering':
            try:
                from ..llm_planner import LLMPlanner
                import os
                
                # Check for OpenAI API key
                if not os.environ.get('OPENAI_API_KEY'):
                    import logging
                    logger = logging.getLogger(__name__)
                    logger.warning("No OPENAI_API_KEY found, using fallback planner")
                else:
                    
                    # Create OpenAI client
                    from openai import AsyncOpenAI
                    
                    class OpenAIClientWrapper:
                        """Wrapper for OpenAI client to match LLMClient protocol."""
                        def __init__(self, api_key: str):
                            self.client = AsyncOpenAI(api_key=api_key)
                        
                        async def create_completion(self, messages, model, max_tokens, temperature, timeout):
                            """Create completion using OpenAI API."""
                            response = await self.client.chat.completions.create(
                                model=model,
                                messages=messages,
                                max_tokens=max_tokens,
                                temperature=temperature,
                                timeout=timeout
                            )
                            return {
                                'id': response.id,
                                'model': response.model,
                                'content': response.choices[0].message.content,
                                'usage': {
                                    'prompt_tokens': response.usage.prompt_tokens,
                                    'completion_tokens': response.usage.completion_tokens,
                                    'total_tokens': response.usage.total_tokens,
                                },
                                'finish_reason': response.choices[0].finish_reason,
                            }
                    
                    llm_client = OpenAIClientWrapper(api_key=os.environ['OPENAI_API_KEY'])
                    
                    # Use real LLM planner
                    planner = LLMPlanner(
                        llm_client=llm_client,
                        model=model,
                        temperature=self.agent_config.get('temperature', 0.3),
                        max_tokens=self.agent_config.get('max_tokens', 2000)
                    )
                    
                    # Build prompt context
                    from core.models import Node
                    nodes_info = []
                    for node_id in available_nodes:
                        node = Node.objects.get(id=node_id)
                        nodes_info.append({
                            'id': str(node.id),
                            'name': node.name,
                            'description': node.description or '',
                            'order': node.order
                        })
                    
                    # Get completed tools
                    completed_tools = []
                    from ..models import ToolExecution
                    completed = ToolExecution.objects.filter(
                        agent_run=self.agent_run,
                        status='completed'
                    ).select_related('node_execution__node')
                    
                    for tool_exec in completed:
                        if tool_exec.node_execution and tool_exec.node_execution.node:
                            completed_tools.append({
                                'tool_name': tool_exec.node_execution.node.name,
                                'tool_id': str(tool_exec.node_execution.node.id)
                            })
                    
                    # Build runtime spec format - available_tools should be a list
                    tools_list = []
                    for node in nodes_info:
                        tools_list.append({
                            'tool_id': node['id'],
                            'tool_name': node['name'],
                            'description': node['description'],
                            'execution_order': node['order'],
                            'input_variables': [],
                            'agent_constraints': {
                                'is_allowed': True,
                                'max_calls': 1,
                                'dependencies': []
                            }
                        })
                    
                    runtime_spec = {
                        'available_tools': tools_list
                    }
                    
                    # Build execution history
                    execution_history = [
                        {
                            'tool_id': tool['tool_id'],
                            'tool_name': tool['tool_name'],
                            'status': 'completed'
                        } for tool in completed_tools
                    ]
                    
                    # Build current state
                    current_state = {
                        'execution_context': self.execution_context,
                        'current_step': self.current_step,
                        'max_steps': self.agent_run.max_steps
                    }
                    
                    # Make decision (async call)
                    import asyncio
                    decision = asyncio.run(planner.plan_next_action(
                        runtime_spec=runtime_spec,
                        execution_history=execution_history,
                        current_state=current_state
                    ))
                    
                    # Track LLM cost (approximate using token counts)
                    if hasattr(decision, 'usage') and decision.usage:
                        # Rough estimate: gpt-4o-mini pricing
                        # Input: $0.150 / 1M tokens, Output: $0.600 / 1M tokens
                        prompt_tokens = decision.usage.get('prompt_tokens', 0)
                        completion_tokens = decision.usage.get('completion_tokens', 0)
                        cost = (prompt_tokens * 0.150 / 1_000_000) + (completion_tokens * 0.600 / 1_000_000)
                        self.total_cost_usd += cost
                    
                    # Convert decision type to action
                    from ..llm_planner import PlannerDecisionType
                    if decision.decision_type == PlannerDecisionType.EXECUTE_TOOL:
                        if decision.tool_id:
                            return (decision.tool_id, decision.reasoning)
                    elif decision.decision_type == PlannerDecisionType.COMPLETE:
                        # Signal completion
                        return (None, decision.reasoning)
                    elif decision.decision_type == PlannerDecisionType.REQUEST_HUMAN:
                        # Request human intervention
                        return (None, decision.reasoning)
                    
            except Exception as e:
                import traceback
                import logging
                logger = logging.getLogger(__name__)
                logger.error(f"LLM planner error: {e}")
                logger.debug(traceback.format_exc())
        
        # Fallback: use simple ordering-based selection
        suggested = self.guardrails.graph_guardrails.suggest_next_node()
        fallback_reasoning = "Selected based on execution order (fallback planner)"
        return (suggested, fallback_reasoning)
    
    def _record_decision(
        self,
        decision_type: str,
        selected_node_id: str,
        reasoning: str,
        violations: List[GuardrailViolation]
    ) -> AgentDecision:
        """Record agent decision in database."""
        decision = AgentDecision.objects.create(
            agent_run=self.agent_run,
            step_number=self.current_step,
            decision_type=decision_type,
            prompt=self._build_prompt(selected_node_id),
            llm_response=reasoning,  # TODO: Store actual LLM response
            parsed_decision={
                'selected_node_id': selected_node_id,
                'reasoning': reasoning
            },
            guardrail_violations=[v.to_dict() for v in violations],
            guardrail_corrections=[],
            reasoning=reasoning
        )
        
        return decision
    
    def _build_prompt(self, context: str) -> str:
        """Build prompt for LLM (placeholder)."""
        # TODO: Implement proper prompt engineering
        return f"Context: {context}"
    
    def _check_guardrail_limits(self):
        """Check if any guardrail limits have been exceeded."""
        from django.utils import timezone
        
        # Check execution time limit
        max_time = self.guardrail_config.get('max_execution_time_seconds')
        if max_time and self.execution_start_time:
            elapsed = (timezone.now() - self.execution_start_time).total_seconds()
            if elapsed > max_time:
                raise RuntimeError(
                    f"Maximum execution time exceeded: {elapsed:.1f}s > {max_time}s"
                )
        
        # Check cost limit
        max_cost = self.guardrail_config.get('max_cost_usd')
        if max_cost and self.total_cost_usd > max_cost:
            raise RuntimeError(
                f"Maximum cost exceeded: ${self.total_cost_usd:.4f} > ${max_cost:.4f}"
            )
    
    def _is_complete(self) -> bool:
        """Check if execution is complete."""
        return self.guardrails.graph_guardrails.state.is_complete()
    
    def _is_high_risk_node(self, node_id: str) -> bool:
        """Determine if a node is considered high-risk."""
        from core.models import Node
        try:
            node = Node.objects.get(id=node_id)
            # Check if node description or name contains high-risk keywords
            high_risk_keywords = ['delete', 'drop', 'remove', 'destroy', 'payment', 'transfer', 'charge']
            node_text = f"{node.name} {node.description or ''}".lower()
            return any(keyword in node_text for keyword in high_risk_keywords)
        except Node.DoesNotExist:
            return False
    
    def _initialize_execution_context(self):
        """Initialize execution context with pipeline arguments."""
        # Get initial data from pipeline execution
        initial_data = self.pipeline_execution.context_data or {}
        self.execution_context = initial_data.copy()
    
    def _update_context_with_outputs(self, execution_result: Dict[str, Any]):
        """Update execution context with node outputs."""
        # Outputs are stored in NodeExecution, retrieve them
        tool_execution_id = execution_result.get('tool_execution_id')
        
        if tool_execution_id:
            from ..models import ToolExecution
            tool_exec = ToolExecution.objects.get(id=tool_execution_id)
            node_exec = tool_exec.node_execution
            
            # Merge outputs into context
            if node_exec.output_data:
                self.execution_context.update(node_exec.output_data)
    
    def _request_human_intervention(self, reason: str):
        """Request human intervention and pause execution."""
        self.agent_run.status = 'waiting_for_human'
        self.agent_run.human_intervention_required = True
        self.agent_run.human_intervention_reason = reason
        self.agent_run.save()
    
    def _finalize_execution(self):
        """Finalize successful execution."""
        self.agent_run.status = 'completed'
        self.agent_run.completed_at = timezone.now()
        self.agent_run.save()
        
        self.pipeline_execution.status = 'completed'
        self.pipeline_execution.completed_at = timezone.now()
        self.pipeline_execution.save()
    
    def _handle_failure(self, error_message: str):
        """Handle execution failure."""
        self.agent_run.status = 'failed'
        self.agent_run.completed_at = timezone.now()
        self.agent_run.save()
        
        self.pipeline_execution.status = 'failed'
        self.pipeline_execution.error_message = error_message
        self.pipeline_execution.completed_at = timezone.now()
        self.pipeline_execution.save()
    
    def _generate_summary(self) -> str:
        """Generate execution summary."""
        decisions = AgentDecision.objects.filter(agent_run=self.agent_run).count()
        tools = self.agent_run.tool_executions.count()
        
        summary_parts = [f"Executed {tools} tools across {decisions} agent decisions in {self.current_step} steps"]
        
        if self.total_cost_usd > 0:
            summary_parts.append(f"Total LLM cost: ${self.total_cost_usd:.4f}")
        
        if self.execution_start_time:
            from django.utils import timezone
            elapsed = (timezone.now() - self.execution_start_time).total_seconds()
            summary_parts.append(f"Execution time: {elapsed:.1f}s")
        
        return " | ".join(summary_parts)
    
    def resume_from_human_intervention(self, human_response: Dict[str, Any]):
        """
        Resume execution after human intervention.
        
        Args:
            human_response: Human's response/decision
        """
        if not self.agent_run.human_intervention_required:
            raise ValueError("No human intervention pending")
        
        # Record human response
        self.agent_run.human_intervention_response = human_response
        self.agent_run.human_intervention_required = False
        self.agent_run.status = 'executing'
        self.agent_run.save()
        
        # Continue execution
        return self.execute()


def start_agent_execution(
    pipeline_execution: PipelineExecution,
    agent_config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Start agent-driven execution of a pipeline.
    
    This is the main entry point for agent execution.
    
    Args:
        pipeline_execution: PipelineExecution instance
        agent_config: Optional agent configuration
        
    Returns:
        Execution result
    """
    loop = AgentExecutionLoop(pipeline_execution, agent_config)
    return loop.execute()
