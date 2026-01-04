"""
Agent Execution Loop

This module implements the agent execution loop for pipeline control.

CRITICAL CONSTRAINTS:
- Loop controls pipeline flow (does NOT execute nodes directly)
- Planner is bounded and always terminates
- Graph constraints are enforced
- Human-in-the-loop pauses are supported
- Termination is explicit and auditable

Architecture:
    AgentExecutionLoop
        ↓
    Load RuntimeSpec (immutable)
        ↓
    Loop (bounded, max_steps):
        1. Call Planner (LLM or deterministic)
        2. Validate with Guardrails
        3. Execute via NodeToolExecutor
        4. Observe outcome
        5. Evaluate conditions
        6. Check termination
        ↓
    Finalize (explicit completion)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import json

from django.db import transaction
from django.utils import timezone as django_timezone
from asgiref.sync import sync_to_async

from core.models import Pipeline, Node, PipelineExecution, NodeExecution
from agent_integration.models import (
    AgentRun,
    AgentDecision,
    ToolExecution,
    RuntimeSpec,
)
from agent_integration.runtime_spec_builder import RuntimeSpecService
from agent_integration.node_tools import NodeToolExecutor, NodeToolResult


# ============================================================================
# PLANNER INTERFACE
# ============================================================================

class PlannerDecisionType(Enum):
    """Types of planner decisions."""
    EXECUTE_TOOL = "execute_tool"
    REQUEST_HUMAN = "request_human"
    COMPLETE = "complete"
    FAIL = "fail"


@dataclass
class PlannerDecision:
    """
    Structured output from planner.
    
    This is what the planner returns after analyzing state.
    """
    decision_type: PlannerDecisionType
    tool_id: Optional[str] = None
    tool_parameters: Dict[str, Any] = field(default_factory=dict)
    reasoning: str = ""
    confidence: float = 1.0
    human_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'decision_type': self.decision_type.value,
            'tool_id': self.tool_id,
            'tool_parameters': self.tool_parameters,
            'reasoning': self.reasoning,
            'confidence': self.confidence,
            'human_message': self.human_message,
        }


class Planner(ABC):
    """
    Abstract planner interface.
    
    Planner decides WHICH tool to execute next based on:
    - Runtime spec (available tools, constraints)
    - Execution history (what's been done)
    - Current state (variables, outputs)
    
    Planner does NOT execute tools directly.
    """
    
    @abstractmethod
    async def plan_next_action(
        self,
        runtime_spec: Dict[str, Any],
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> PlannerDecision:
        """
        Plan the next action.
        
        Args:
            runtime_spec: Runtime specification from RuntimeSpecBuilder
            execution_history: List of completed tool executions
            current_state: Current execution state (variables, etc.)
            
        Returns:
            PlannerDecision with next action
        """
        pass


class DeterministicPlanner(Planner):
    """
    Deterministic rule-based planner (fallback).
    
    This planner follows simple rules:
    1. Execute tools in DAG order
    2. Respect dependencies
    3. Execute each tool once
    4. Complete when all tools done
    
    This is NOT an LLM - it's a simple fallback.
    """
    
    async def plan_next_action(
        self,
        runtime_spec: Dict[str, Any],
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> PlannerDecision:
        """Plan next action using deterministic rules."""
        
        # Get available tools from spec
        available_tools = runtime_spec.get('available_tools', [])
        if not available_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="No tools available in spec",
            )
        
        # Get execution constraints
        constraints = runtime_spec.get('execution_constraints', {})
        dag = constraints.get('dag', {})
        dependencies = dag.get('dependencies', {})
        
        # Build set of executed tool IDs
        executed_tool_ids = {
            exec_record['tool_id']
            for exec_record in execution_history
            if exec_record.get('success', False)
        }
        
        # Find next tool to execute
        for tool in available_tools:
            tool_id = tool['tool_id']
            
            # Skip if already executed
            if tool_id in executed_tool_ids:
                continue
            
            # Check if agent is allowed to use this tool
            agent_constraints = tool.get('agent_constraints', {})
            if not agent_constraints.get('is_allowed', True):
                continue
            
            # Check dependencies
            tool_deps = dependencies.get(tool_id, {}).get('depends_on', [])
            if all(dep_id in executed_tool_ids for dep_id in tool_deps):
                # All dependencies satisfied, execute this tool
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=tool_id,
                    tool_parameters={},
                    reasoning=f"Execute tool '{tool['tool_name']}' (dependencies satisfied)",
                    confidence=1.0,
                )
        
        # No more tools to execute
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed successfully",
        )


# ============================================================================
# GUARDRAILS
# ============================================================================

@dataclass
class GuardrailViolation:
    """Represents a guardrail violation."""
    rule_name: str
    severity: str  # 'warning', 'error', 'critical'
    message: str
    suggested_correction: Optional[str] = None


@dataclass
class GuardrailResult:
    """Result of guardrail validation."""
    is_valid: bool
    violations: List[GuardrailViolation] = field(default_factory=list)
    corrected_decision: Optional[PlannerDecision] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'is_valid': self.is_valid,
            'violations': [
                {
                    'rule_name': v.rule_name,
                    'severity': v.severity,
                    'message': v.message,
                    'suggested_correction': v.suggested_correction,
                }
                for v in self.violations
            ],
            'corrected_decision': self.corrected_decision.to_dict() if self.corrected_decision else None,
        }


class Guardrails:
    """
    Validates planner decisions before execution.
    
    Guardrails enforce:
    - Graph constraints (DAG structure)
    - Tool call limits
    - Business rules
    - Safety policies
    """
    
    def __init__(self, runtime_spec: Dict[str, Any]):
        """Initialize guardrails with runtime spec."""
        self.runtime_spec = runtime_spec
    
    async def validate_decision(
        self,
        decision: PlannerDecision,
        execution_history: List[Dict[str, Any]],
        current_state: Dict[str, Any],
    ) -> GuardrailResult:
        """
        Validate planner decision.
        
        Args:
            decision: Planner decision to validate
            execution_history: Execution history
            current_state: Current state
            
        Returns:
            GuardrailResult with validation outcome
        """
        violations = []
        
        # If decision is not tool execution, allow it
        if decision.decision_type != PlannerDecisionType.EXECUTE_TOOL:
            return GuardrailResult(is_valid=True)
        
        tool_id = decision.tool_id
        if not tool_id:
            violations.append(GuardrailViolation(
                rule_name="tool_id_required",
                severity="critical",
                message="Tool ID is required for EXECUTE_TOOL decision",
            ))
            return GuardrailResult(is_valid=False, violations=violations)
        
        # Find tool in spec
        available_tools = self.runtime_spec.get('available_tools', [])
        tool = next((t for t in available_tools if t['tool_id'] == tool_id), None)
        
        if not tool:
            violations.append(GuardrailViolation(
                rule_name="tool_not_found",
                severity="critical",
                message=f"Tool {tool_id} not found in runtime spec",
            ))
            return GuardrailResult(is_valid=False, violations=violations)
        
        # Check agent constraints
        agent_constraints = tool.get('agent_constraints', {})
        if not agent_constraints.get('is_allowed', True):
            violations.append(GuardrailViolation(
                rule_name="tool_not_allowed",
                severity="error",
                message=f"Tool '{tool['tool_name']}' is not allowed by agent constraints",
            ))
        
        # Check max calls
        max_calls = agent_constraints.get('max_calls', float('inf'))
        tool_call_count = sum(
            1 for exec_record in execution_history
            if exec_record.get('tool_id') == tool_id
        )
        if tool_call_count >= max_calls:
            violations.append(GuardrailViolation(
                rule_name="max_calls_exceeded",
                severity="error",
                message=f"Tool '{tool['tool_name']}' has exceeded max calls ({max_calls})",
            ))
        
        # Check dependencies
        constraints = self.runtime_spec.get('execution_constraints', {})
        dag = constraints.get('dag', {})
        dependencies = dag.get('dependencies', {})
        
        tool_deps = dependencies.get(tool_id, {}).get('depends_on', [])
        executed_tool_ids = {
            exec_record['tool_id']
            for exec_record in execution_history
            if exec_record.get('success', False)
        }
        
        missing_deps = [dep for dep in tool_deps if dep not in executed_tool_ids]
        if missing_deps:
            violations.append(GuardrailViolation(
                rule_name="missing_dependencies",
                severity="error",
                message=f"Tool '{tool['tool_name']}' has unsatisfied dependencies: {missing_deps}",
            ))
        
        # Return result
        is_valid = all(v.severity != 'critical' and v.severity != 'error' for v in violations)
        return GuardrailResult(is_valid=is_valid, violations=violations)


# ============================================================================
# CONDITION EVALUATOR
# ============================================================================

class ConditionEvaluator:
    """
    Evaluates business conditions at runtime.
    
    Conditions are defined in runtime spec and evaluated at:
    - before_execution
    - after_tool_execution
    - on_error
    - before_completion
    """
    
    def __init__(self, runtime_spec: Dict[str, Any]):
        """Initialize evaluator with runtime spec."""
        self.runtime_spec = runtime_spec
    
    async def evaluate_conditions(
        self,
        evaluation_point: str,
        current_state: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Evaluate conditions at given evaluation point.
        
        Args:
            evaluation_point: When to evaluate (before_execution, after_tool_execution, etc.)
            current_state: Current execution state
            
        Returns:
            List of condition evaluation results
        """
        results = []
        
        conditions = self.runtime_spec.get('business_conditions', [])
        for condition in conditions:
            if condition.get('evaluation_point') != evaluation_point:
                continue
            
            # Evaluate condition (simplified - real implementation would be more complex)
            result = await self._evaluate_single_condition(condition, current_state)
            results.append(result)
        
        return results
    
    async def _evaluate_single_condition(
        self,
        condition: Dict[str, Any],
        current_state: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Evaluate a single condition.
        
        This is a simplified implementation.
        Real implementation would support complex condition logic.
        """
        condition_type = condition.get('condition_type', 'always_true')
        condition_config = condition.get('config', {})
        
        # Simplified evaluation logic
        if condition_type == 'always_true':
            is_true = True
        elif condition_type == 'variable_equals':
            var_name = condition_config.get('variable')
            expected_value = condition_config.get('value')
            actual_value = current_state.get('variables', {}).get(var_name)
            is_true = actual_value == expected_value
        else:
            # Unknown condition type - default to false
            is_true = False
        
        return {
            'condition_id': condition.get('condition_id'),
            'condition_name': condition.get('condition_name'),
            'is_true': is_true,
            'on_true_action': condition.get('on_true_action') if is_true else None,
            'on_false_action': condition.get('on_false_action') if not is_true else None,
            'evaluated_at': datetime.now(timezone.utc).isoformat(),
        }


# ============================================================================
# AGENT EXECUTION LOOP
# ============================================================================

class LoopTerminationReason(Enum):
    """Reasons for loop termination."""
    COMPLETED = "completed"
    MAX_STEPS_REACHED = "max_steps_reached"
    HUMAN_INTERVENTION_REQUIRED = "human_intervention_required"
    ERROR = "error"
    CANCELLED = "cancelled"


@dataclass
class LoopResult:
    """Result of execution loop."""
    success: bool
    termination_reason: LoopTerminationReason
    steps_executed: int
    final_state: Dict[str, Any]
    error_message: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'success': self.success,
            'termination_reason': self.termination_reason.value,
            'steps_executed': self.steps_executed,
            'final_state': self.final_state,
            'error_message': self.error_message,
        }


class AgentExecutionLoop:
    """
    Main execution loop for agent-controlled pipeline flow.
    
    This loop:
    1. Loads runtime spec (immutable)
    2. Iterates (bounded by max_steps)
    3. Calls planner for next action
    4. Validates with guardrails
    5. Executes tool via NodeToolExecutor
    6. Observes outcome
    7. Evaluates conditions
    8. Checks termination
    
    Loop NEVER:
    - Executes nodes directly (uses NodeToolExecutor)
    - Bypasses graph constraints
    - Runs infinitely (bounded by max_steps)
    - Mutates pipeline definitions
    """
    
    def __init__(
        self,
        agent_run: AgentRun,
        planner: Optional[Planner] = None,
    ):
        """
        Initialize execution loop.
        
        Args:
            agent_run: AgentRun instance
            planner: Planner implementation (defaults to DeterministicPlanner)
        """
        self.agent_run = agent_run
        self.planner = planner or DeterministicPlanner()
        self.runtime_spec = None
        self.guardrails = None
        self.condition_evaluator = None
    
    async def initialize(self):
        """
        Initialize loop components.
        
        Must be called before run().
        """
        # Load runtime spec
        runtime_spec_model = await sync_to_async(
            RuntimeSpecService.get_spec_for_agent_run
        )(self.agent_run.id)
        
        if not runtime_spec_model:
            raise ValueError(f"No runtime spec found for agent run {self.agent_run.id}")
        
        # Verify integrity
        is_valid = await sync_to_async(
            RuntimeSpecService.verify_spec_integrity
        )(runtime_spec_model)
        
        if not is_valid:
            raise ValueError("Runtime spec integrity check failed")
        
        self.runtime_spec = runtime_spec_model.spec_data
        self.guardrails = Guardrails(self.runtime_spec)
        self.condition_evaluator = ConditionEvaluator(self.runtime_spec)
    
    async def run(self) -> LoopResult:
        """
        Run the execution loop.
        
        Returns:
            LoopResult with execution outcome
        """
        if not self.runtime_spec:
            await self.initialize()
        
        # Update agent run status
        await self._update_agent_run_status('planning')
        
        # Get max steps from runtime spec
        max_steps = self.runtime_spec.get('execution_constraints', {}).get('max_steps', 100)
        
        # Initialize state
        current_state = {
            'variables': {},
            'completed_tools': [],
            'step': 0,
        }
        
        # Evaluate pre-execution conditions
        await self._evaluate_conditions_at_point('before_execution', current_state)
        
        # Main execution loop
        for step in range(max_steps):
            current_state['step'] = step
            
            # Update agent run step
            await self._update_agent_run_step(step)
            
            # Get execution history
            execution_history = await self._get_execution_history()
            
            # Plan next action
            decision = await self.planner.plan_next_action(
                runtime_spec=self.runtime_spec,
                execution_history=execution_history,
                current_state=current_state,
            )
            
            # Record decision
            await self._record_decision(step, decision)
            
            # Check for completion or human intervention
            if decision.decision_type == PlannerDecisionType.COMPLETE:
                # Evaluate completion conditions
                await self._evaluate_conditions_at_point('before_completion', current_state)
                
                await self._update_agent_run_status('completed')
                return LoopResult(
                    success=True,
                    termination_reason=LoopTerminationReason.COMPLETED,
                    steps_executed=step + 1,
                    final_state=current_state,
                )
            
            if decision.decision_type == PlannerDecisionType.REQUEST_HUMAN:
                await self._request_human_intervention(decision)
                await self._update_agent_run_status('waiting_for_human')
                return LoopResult(
                    success=True,
                    termination_reason=LoopTerminationReason.HUMAN_INTERVENTION_REQUIRED,
                    steps_executed=step + 1,
                    final_state=current_state,
                )
            
            if decision.decision_type == PlannerDecisionType.FAIL:
                await self._update_agent_run_status('failed')
                return LoopResult(
                    success=False,
                    termination_reason=LoopTerminationReason.ERROR,
                    steps_executed=step + 1,
                    final_state=current_state,
                    error_message=decision.reasoning,
                )
            
            # Validate decision with guardrails
            guardrail_result = await self.guardrails.validate_decision(
                decision,
                execution_history,
                current_state,
            )
            
            if not guardrail_result.is_valid:
                # Record guardrail violations
                await self._record_guardrail_violations(step, guardrail_result)
                
                # Check if we should fail or continue
                has_critical = any(
                    v.severity == 'critical'
                    for v in guardrail_result.violations
                )
                
                if has_critical:
                    await self._update_agent_run_status('failed')
                    return LoopResult(
                        success=False,
                        termination_reason=LoopTerminationReason.ERROR,
                        steps_executed=step + 1,
                        final_state=current_state,
                        error_message="Critical guardrail violation",
                    )
                
                # Skip this step and continue
                continue
            
            # Execute tool
            tool_result = await self._execute_tool(decision)
            
            # Evaluate post-execution conditions
            await self._evaluate_conditions_at_point('after_tool_execution', current_state)
            
            # Update state
            if tool_result.success:
                current_state['completed_tools'].append(decision.tool_id)
            else:
                # Handle error
                retry_result = await self._handle_execution_error(decision, tool_result)
                if not retry_result:
                    # No retry, fail
                    await self._update_agent_run_status('failed')
                    return LoopResult(
                        success=False,
                        termination_reason=LoopTerminationReason.ERROR,
                        steps_executed=step + 1,
                        final_state=current_state,
                        error_message=tool_result.error_message,
                    )
        
        # Max steps reached
        await self._update_agent_run_status('failed')
        return LoopResult(
            success=False,
            termination_reason=LoopTerminationReason.MAX_STEPS_REACHED,
            steps_executed=max_steps,
            final_state=current_state,
            error_message=f"Maximum steps ({max_steps}) reached",
        )
    
    # ------------------------------------------------------------------------
    # Helper methods
    # ------------------------------------------------------------------------
    
    async def _update_agent_run_status(self, status: str):
        """Update agent run status."""
        def _update():
            self.agent_run.status = status
            self.agent_run.save(update_fields=['status', 'updated_at'])
        
        await sync_to_async(_update)()
    
    async def _update_agent_run_step(self, step: int):
        """Update agent run current step."""
        def _update():
            self.agent_run.current_step = step
            self.agent_run.save(update_fields=['current_step', 'updated_at'])
        
        await sync_to_async(_update)()
    
    async def _get_execution_history(self) -> List[Dict[str, Any]]:
        """Get execution history."""
        def _get_history():
            tool_executions = ToolExecution.objects.filter(
                agent_run=self.agent_run
            ).select_related('node_execution').order_by('queued_at')
            
            history = []
            for tool_exec in tool_executions:
                node_exec = tool_exec.node_execution
                history.append({
                    'tool_id': str(node_exec.node_id),
                    'tool_name': tool_exec.tool_name,
                    'success': node_exec.status == 'completed',
                    'output': tool_exec.result_summary,
                    'completed_at': tool_exec.completed_at.isoformat() if tool_exec.completed_at else None,
                })
            
            return history
        
        return await sync_to_async(_get_history)()
    
    async def _record_decision(self, step: int, decision: PlannerDecision):
        """Record agent decision."""
        def _record():
            AgentDecision.objects.create(
                agent_run=self.agent_run,
                step_number=step,
                decision_type=decision.decision_type.value,
                prompt="",  # Populated by LLM planner
                llm_response="",  # Populated by LLM planner
                parsed_decision=decision.to_dict(),
                reasoning=decision.reasoning,
                confidence=decision.confidence,
            )
        
        await sync_to_async(_record)()
    
    async def _record_guardrail_violations(self, step: int, guardrail_result: GuardrailResult):
        """Record guardrail violations."""
        def _record():
            # Find the decision for this step
            decision = AgentDecision.objects.filter(
                agent_run=self.agent_run,
                step_number=step,
            ).order_by('-timestamp').first()
            
            if decision:
                decision.guardrail_violations = [
                    {
                        'rule_name': v.rule_name,
                        'severity': v.severity,
                        'message': v.message,
                    }
                    for v in guardrail_result.violations
                ]
                decision.save(update_fields=['guardrail_violations'])
        
        await sync_to_async(_record)()
    
    async def _execute_tool(self, decision: PlannerDecision) -> NodeToolResult:
        """Execute tool via NodeToolExecutor."""
        # Get node
        def _get_node():
            return Node.objects.get(id=decision.tool_id)
        
        node = await sync_to_async(_get_node)()
        
        # Build execution context from previous node outputs
        def _build_context():
            from core.models import NodeExecution
            context = {}
            
            # Get all completed node executions in this pipeline execution
            node_executions = NodeExecution.objects.filter(
                pipeline_execution=self.agent_run.pipeline_execution,
                status='completed'
            ).select_related('node').order_by('started_at')
            
            # Add outputs from each completed node to context
            for node_exec in node_executions:
                if node_exec.output_data:
                    # Add with node name prefix (e.g., FetchCustomerData.customer_data)
                    for key, value in node_exec.output_data.items():
                        if not key.startswith('__'):  # Skip internal keys
                            context[f"{node_exec.node.name}.{key}"] = value
                            # Also add without prefix for direct access
                            context[key] = value
            
            return context
        
        execution_context = await sync_to_async(_build_context)()
        
        # Create tool executor with correct parameters
        executor = NodeToolExecutor(
            node_id=node.id,
            node_name=node.name,
            node=node  # Pass the node to avoid re-fetching
        )
        
        # Execute tool with context from previous nodes
        result = await executor.execute(
            agent_run_id=self.agent_run.id,
            agent_decision_id=None,  # Will be set by executor if needed
            parameters=decision.tool_parameters,
            context=execution_context,  # Pass outputs from previous nodes
        )
        
        return result
    
    async def _evaluate_conditions_at_point(self, evaluation_point: str, current_state: Dict[str, Any]):
        """Evaluate conditions at given point."""
        results = await self.condition_evaluator.evaluate_conditions(
            evaluation_point,
            current_state,
        )
        
        # Process condition results (simplified)
        for result in results:
            if result.get('on_true_action') == 'pause':
                # Pause execution - would trigger human intervention
                pass
            elif result.get('on_false_action') == 'fail':
                # Fail execution
                pass
    
    async def _request_human_intervention(self, decision: PlannerDecision):
        """Request human intervention."""
        def _request():
            self.agent_run.human_intervention_required = True
            self.agent_run.human_intervention_reason = decision.human_message or decision.reasoning
            self.agent_run.save(update_fields=[
                'human_intervention_required',
                'human_intervention_reason',
                'updated_at',
            ])
        
        await sync_to_async(_request)()
    
    async def _handle_execution_error(
        self,
        decision: PlannerDecision,
        tool_result: NodeToolResult,
    ) -> bool:
        """
        Handle execution error with retry logic.
        
        Returns:
            True if retry should be attempted, False otherwise
        """
        # Get retry policy from agent config
        agent_config = self.runtime_spec.get('agent_configuration', {})
        retry_policy = agent_config.get('retry_policy', {})
        
        max_retries = retry_policy.get('max_retries', 0)
        if max_retries == 0:
            return False
        
        # Check how many times this tool has been attempted
        def _get_retry_count():
            return ToolExecution.objects.filter(
                agent_run=self.agent_run,
                node_execution__node_id=decision.tool_id,
            ).count()
        
        retry_count = await sync_to_async(_get_retry_count)()
        
        if retry_count < max_retries:
            # Allow retry
            return True
        
        return False


# ============================================================================
# LOOP RUNNER SERVICE
# ============================================================================

class AgentLoopRunner:
    """
    Service for running agent execution loops.
    
    This provides a high-level interface for starting/resuming loops.
    """
    
    @staticmethod
    async def start_loop(agent_run: AgentRun, planner: Optional[Planner] = None) -> LoopResult:
        """
        Start execution loop for agent run.
        
        Args:
            agent_run: AgentRun instance
            planner: Optional planner (defaults to DeterministicPlanner)
            
        Returns:
            LoopResult with execution outcome
        """
        loop = AgentExecutionLoop(agent_run, planner)
        await loop.initialize()
        result = await loop.run()
        return result
    
    @staticmethod
    async def resume_loop(agent_run: AgentRun) -> LoopResult:
        """
        Resume execution loop after human intervention.
        
        Args:
            agent_run: AgentRun instance
            
        Returns:
            LoopResult with execution outcome
        """
        # Clear human intervention flags
        def _clear_flags():
            agent_run.human_intervention_required = False
            agent_run.status = 'executing'
            agent_run.save(update_fields=[
                'human_intervention_required',
                'status',
                'updated_at',
            ])
        
        await sync_to_async(_clear_flags)()
        
        # Resume loop
        loop = AgentExecutionLoop(agent_run)
        await loop.initialize()
        result = await loop.run()
        return result
