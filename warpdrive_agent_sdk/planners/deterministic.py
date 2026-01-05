"""
Deterministic Planner

A simple rule-based planner that executes tools in DAG order.

This planner follows deterministic rules:
1. Execute tools in dependency order
2. Execute each tool once
3. Complete when all tools done
4. No LLM calls, no intelligence

Use this as a fallback or for simple linear workflows.
"""

from typing import Dict, Any, List
from ..interfaces.planner import Planner, PlannerDecision, PlannerDecisionType, PlannerInput


class DeterministicPlanner(Planner):
    """
    Deterministic rule-based planner.
    
    This planner executes tools in a deterministic order based on
    dependencies. It does NOT use any intelligence or LLM calls.
    
    Usage:
        >>> planner = DeterministicPlanner()
        >>> decision = await planner.plan_next_action(planner_input)
    
    NOTE: This is provided as a fallback. For intelligent planning,
    use LLMPlanner or implement your own custom planner.
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan next action using deterministic rules.
        
        Algorithm:
        1. Get all available tools
        2. Filter out already-executed tools
        3. Find first tool with satisfied dependencies
        4. Return EXECUTE_TOOL decision
        5. If no tools left, return COMPLETE
        
        Args:
            planner_input: Current execution state
            
        Returns:
            PlannerDecision for next action
        """
        # Get available tools
        available_tools = planner_input.get_available_tools()
        if not available_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="No tools available in spec",
            )
        
        # Get already executed tools
        executed_tools = set(planner_input.get_executed_tools())
        
        # Build dependency map
        dependencies = self._build_dependency_map(planner_input)
        
        # Find next executable tool
        for tool in available_tools:
            tool_id = tool.get('tool_id')
            
            # Skip already executed
            if tool_id in executed_tools:
                continue
            
            # Check if dependencies are satisfied
            tool_deps = dependencies.get(tool_id, set())
            if tool_deps.issubset(executed_tools):
                # All dependencies satisfied, execute this tool
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=tool_id,
                    reasoning=f"Executing {tool.get('name', tool_id)} - dependencies satisfied",
                )
        
        # No more tools to execute
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed or no executable tools remaining",
        )
    
    def _build_dependency_map(self, planner_input: PlannerInput) -> Dict[str, set]:
        """
        Build map of tool_id -> set of dependency tool_ids.
        
        Args:
            planner_input: Planner input with runtime spec
            
        Returns:
            Dictionary mapping tool IDs to their dependency sets
        """
        dependencies = {}
        
        # Initialize all tools with empty dependencies
        for tool in planner_input.get_available_tools():
            tool_id = tool.get('tool_id')
            dependencies[tool_id] = set()
        
        # Build dependencies from constraints
        constraints = planner_input.get_execution_constraints()
        for constraint in constraints:
            if constraint.get('constraint_type') == 'dependency':
                source = constraint.get('source_node_id')
                target = constraint.get('target_node_id')
                
                if source and target:
                    if target not in dependencies:
                        dependencies[target] = set()
                    dependencies[target].add(source)
        
        return dependencies
