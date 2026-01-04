"""
Graph-Aware Guardrails

Enforces constraints before and after agent decisions.
Prevents invalid execution flows.
"""

from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass
from core.models import Node


@dataclass
class GuardrailViolation:
    """Represents a guardrail violation."""
    violation_type: str
    severity: str  # 'error', 'warning'
    message: str
    node_id: Optional[str] = None
    suggested_correction: Optional[str] = None
    
    def to_dict(self) -> dict:
        return {
            'violation_type': self.violation_type,
            'severity': self.severity,
            'message': self.message,
            'node_id': self.node_id,
            'suggested_correction': self.suggested_correction
        }


class ExecutionState:
    """
    Tracks current execution state for guardrail checking.
    """
    
    def __init__(self, runtime_spec: Dict[str, Any]):
        self.spec = runtime_spec
        self.executed_nodes: Set[str] = set()
        self.available_nodes: Set[str] = set()
        self.failed_nodes: Set[str] = set()
        self.execution_count: Dict[str, int] = {}
        
        # Build node dependency graph
        self._build_dependency_graph()
    
    def _build_dependency_graph(self):
        """Build dependency graph from constraints."""
        self.dependencies: Dict[str, Set[str]] = {}
        self.dependents: Dict[str, Set[str]] = {}
        
        # Initialize all nodes
        for tool in self.spec['available_tools']:
            tool_id = tool['tool_id']
            self.dependencies[tool_id] = set()
            self.dependents[tool_id] = set()
        
        # Build dependency edges
        for constraint in self.spec['execution_constraints']:
            if constraint['constraint_type'] == 'dependency':
                source = constraint['source_node_id']
                target = constraint['target_node_id']
                
                if source and target:
                    self.dependencies[target].add(source)
                    self.dependents[source].add(target)
    
    def mark_executed(self, node_id: str):
        """Mark node as executed."""
        self.executed_nodes.add(node_id)
        self.execution_count[node_id] = self.execution_count.get(node_id, 0) + 1
    
    def mark_failed(self, node_id: str):
        """Mark node as failed."""
        self.failed_nodes.add(node_id)
    
    def get_available_nodes(self) -> Set[str]:
        """
        Get nodes that can be executed now.
        
        A node is available if all its dependencies have been executed successfully.
        Nodes are NOT available if any of their dependencies failed.
        """
        available = set()
        
        for tool in self.spec['available_tools']:
            tool_id = tool['tool_id']
            
            # Skip already executed
            if tool_id in self.executed_nodes:
                continue
            
            # Skip failed
            if tool_id in self.failed_nodes:
                continue
            
            # Check if all dependencies are satisfied
            deps = self.dependencies.get(tool_id, set())
            
            # Check if any dependency failed - if so, this node cannot execute
            if deps & self.failed_nodes:
                # Mark this node as failed too since its dependencies failed
                self.failed_nodes.add(tool_id)
                continue
            
            # Check if all dependencies have been successfully executed
            if deps.issubset(self.executed_nodes):
                available.add(tool_id)
        
        return available
    
    def is_complete(self) -> bool:
        """Check if all nodes have been executed or failed."""
        all_nodes = {tool['tool_id'] for tool in self.spec['available_tools']}
        return all_nodes.issubset(self.executed_nodes | self.failed_nodes)
    
    def has_deadlock(self) -> bool:
        """
        Check if execution is deadlocked.
        
        Deadlock occurs when:
        - Not all nodes are complete
        - No nodes are available to execute
        """
        if self.is_complete():
            return False
        
        return len(self.get_available_nodes()) == 0


class GraphGuardrails:
    """
    Enforces graph-based constraints on execution flow.
    
    CRITICAL: These guardrails prevent:
    - Execution of nodes with unsatisfied dependencies
    - Skipping mandatory nodes
    - Infinite loops
    - Deadlocks
    """
    
    def __init__(self, runtime_spec: Dict[str, Any]):
        self.spec = runtime_spec
        self.state = ExecutionState(runtime_spec)
    
    def validate_node_selection(
        self,
        selected_node_id: str,
        reasoning: Optional[str] = None
    ) -> tuple[bool, List[GuardrailViolation]]:
        """
        Validate agent's node selection before execution.
        
        Returns:
            (is_valid, list_of_violations)
        """
        violations = []
        
        # Check if node exists
        if not self._node_exists(selected_node_id):
            violations.append(GuardrailViolation(
                violation_type='invalid_node',
                severity='error',
                message=f"Node {selected_node_id} does not exist in pipeline",
                node_id=selected_node_id
            ))
            return (False, violations)
        
        # Check if already executed
        if selected_node_id in self.state.executed_nodes:
            violations.append(GuardrailViolation(
                violation_type='already_executed',
                severity='error',
                message=f"Node {selected_node_id} has already been executed",
                node_id=selected_node_id,
                suggested_correction="Select a different node"
            ))
            return (False, violations)
        
        # Check if dependencies are satisfied
        deps = self.state.dependencies.get(selected_node_id, set())
        unsatisfied = deps - self.state.executed_nodes
        
        if unsatisfied:
            violations.append(GuardrailViolation(
                violation_type='unsatisfied_dependencies',
                severity='error',
                message=f"Node {selected_node_id} has unsatisfied dependencies: {unsatisfied}",
                node_id=selected_node_id,
                suggested_correction=f"Execute dependencies first: {unsatisfied}"
            ))
            return (False, violations)
        
        # Check for infinite loop (same node executed too many times)
        max_executions = 1  # Each node should execute exactly once
        current_count = self.state.execution_count.get(selected_node_id, 0)
        
        if current_count >= max_executions:
            violations.append(GuardrailViolation(
                violation_type='infinite_loop',
                severity='error',
                message=f"Node {selected_node_id} has already been executed {current_count} times",
                node_id=selected_node_id
            ))
            return (False, violations)
        
        # Check if node is in failed state
        if selected_node_id in self.state.failed_nodes:
            violations.append(GuardrailViolation(
                violation_type='failed_node',
                severity='error',
                message=f"Node {selected_node_id} previously failed and cannot be re-executed",
                node_id=selected_node_id,
                suggested_correction="Handle failure or select different node"
            ))
            return (False, violations)
        
        # All checks passed
        return (True, violations)
    
    def validate_execution_complete(self) -> tuple[bool, List[GuardrailViolation]]:
        """
        Validate that execution can be completed.
        
        Checks for mandatory nodes that haven't been executed.
        """
        violations = []
        
        # Get all mandatory nodes
        all_nodes = {tool['tool_id'] for tool in self.spec['available_tools']}
        unexecuted = all_nodes - self.state.executed_nodes - self.state.failed_nodes
        
        if unexecuted:
            violations.append(GuardrailViolation(
                violation_type='incomplete_execution',
                severity='error',
                message=f"Cannot complete: {len(unexecuted)} nodes not executed: {unexecuted}",
                suggested_correction="Execute all mandatory nodes before completing"
            ))
            return (False, violations)
        
        return (True, violations)
    
    def detect_deadlock(self) -> Optional[GuardrailViolation]:
        """
        Detect if execution is deadlocked.
        
        Returns violation if deadlocked, None otherwise.
        """
        if self.state.has_deadlock():
            available_nodes = self.state.get_available_nodes()
            unexecuted = set()
            for tool in self.spec['available_tools']:
                tool_id = tool['tool_id']
                if tool_id not in self.state.executed_nodes:
                    unexecuted.add(tool_id)
            
            return GuardrailViolation(
                violation_type='deadlock',
                severity='error',
                message=f"Execution deadlocked. Unexecuted nodes: {unexecuted}, but none are available",
                suggested_correction="Check for circular dependencies or failed prerequisite nodes"
            )
        
        return None
    
    def get_next_available_nodes(self) -> List[str]:
        """
        Get list of nodes that can be executed next.
        
        This is the safe set of choices for the agent.
        """
        return list(self.state.get_available_nodes())
    
    def suggest_next_node(self) -> Optional[str]:
        """
        Suggest next node to execute based on ordering.
        
        Returns the lowest-order available node.
        """
        available = self.get_next_available_nodes()
        
        if not available:
            return None
        
        # Find node with lowest order
        min_order = float('inf')
        suggested = None
        
        for tool in self.spec['available_tools']:
            if tool['tool_id'] in available:
                order = tool['constraints'].get('execution_order', float('inf'))
                if order < min_order:
                    min_order = order
                    suggested = tool['tool_id']
        
        return suggested
    
    def _node_exists(self, node_id: str) -> bool:
        """Check if node exists in spec."""
        return any(
            tool['tool_id'] == node_id
            for tool in self.spec['available_tools']
        )
    
    def record_execution(self, node_id: str, success: bool):
        """
        Record node execution result.
        
        Updates state for future guardrail checks.
        """
        if success:
            self.state.mark_executed(node_id)
        else:
            self.state.mark_failed(node_id)


class PolicyGuardrails:
    """
    Enforces policy-based constraints.
    
    These are softer constraints than graph guardrails.
    """
    
    def __init__(self, runtime_spec: Dict[str, Any]):
        self.spec = runtime_spec
        self.policies = runtime_spec.get('execution_policies', {})
    
    def check_max_iterations(self, current_iteration: int) -> Optional[GuardrailViolation]:
        """Check if max iterations exceeded."""
        max_iter = self.policies.get('max_iterations', 100)
        
        if current_iteration >= max_iter:
            return GuardrailViolation(
                violation_type='max_iterations',
                severity='error',
                message=f"Maximum iterations ({max_iter}) exceeded",
                suggested_correction="Stop execution"
            )
        
        return None
    
    def check_consecutive_failures(
        self,
        failure_count: int
    ) -> Optional[GuardrailViolation]:
        """Check for too many consecutive failures."""
        max_failures = self.policies.get('safety', {}).get('max_consecutive_failures', 3)
        
        if failure_count >= max_failures:
            return GuardrailViolation(
                violation_type='consecutive_failures',
                severity='error',
                message=f"Too many consecutive failures ({failure_count})",
                suggested_correction="Request human intervention"
            )
        
        return None


class GuardrailEngine:
    """
    Main guardrail engine coordinating all checks.
    """
    
    def __init__(self, runtime_spec: Dict[str, Any], guardrail_config: Optional[Dict[str, Any]] = None):
        self.graph_guardrails = GraphGuardrails(runtime_spec)
        self.policy_guardrails = PolicyGuardrails(runtime_spec)
        self.guardrail_config = guardrail_config or {}
    
    def validate_before_execution(
        self,
        selected_node_id: str,
        current_iteration: int,
        consecutive_failures: int
    ) -> tuple[bool, List[GuardrailViolation]]:
        """
        Run all guardrail checks before executing a node.
        
        Returns:
            (is_safe, list_of_violations)
        """
        violations = []
        
        # Graph checks
        valid, graph_violations = self.graph_guardrails.validate_node_selection(selected_node_id)
        violations.extend(graph_violations)
        
        # Policy checks
        iter_violation = self.policy_guardrails.check_max_iterations(current_iteration)
        if iter_violation:
            violations.append(iter_violation)
        
        failure_violation = self.policy_guardrails.check_consecutive_failures(consecutive_failures)
        if failure_violation:
            violations.append(failure_violation)
        
        # Check for deadlock
        deadlock = self.graph_guardrails.detect_deadlock()
        if deadlock:
            violations.append(deadlock)
        
        # Any error-level violation means not safe
        has_errors = any(v.severity == 'error' for v in violations)
        
        return (not has_errors, violations)
    
    def get_safe_choices(self) -> List[str]:
        """Get list of safe node choices for agent."""
        return self.graph_guardrails.get_next_available_nodes()
    
    def record_execution_result(self, node_id: str, success: bool):
        """Record execution result for state tracking."""
        self.graph_guardrails.record_execution(node_id, success)
