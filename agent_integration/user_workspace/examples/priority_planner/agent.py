"""
Example User Agent - Priority-Based Planner

This is an example of user-written agent code that uses the SDK.
"""

from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)


class PriorityPlanner(Planner):
    """
    Priority-based planner that executes tools based on priority metadata.
    
    This planner:
    1. Looks at tool metadata for 'priority' field
    2. Executes highest priority (lowest number) first
    3. Respects dependencies
    4. Completes when all tools executed
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """Plan next action based on tool priorities."""
        # Get available tools
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        
        if not tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="No tools available"
            )
        
        # Build dependency map
        dependencies = self._build_dependencies(planner_input)
        
        # Find executable tools (with satisfied dependencies)
        executable = []
        for tool in tools:
            tool_id = tool.get('tool_id')
            
            # Skip if already executed
            if tool_id in executed:
                continue
            
            # Check if dependencies satisfied
            deps = dependencies.get(tool_id, set())
            if not deps.issubset(executed):
                continue  # Dependencies not satisfied
            
            # Get priority from metadata (default 100)
            priority = tool.get('metadata', {}).get('priority', 100)
            executable.append((priority, tool))
        
        # Check if any tools executable
        if not executable:
            if len(executed) == len(tools):
                return PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    reasoning=f"All {len(tools)} tools executed successfully"
                )
            else:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.FAIL,
                    reasoning="Some tools have unsatisfied dependencies"
                )
        
        # Sort by priority (lowest number = highest priority)
        executable.sort(key=lambda x: x[0])
        priority, next_tool = executable[0]
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=next_tool['tool_id'],
            reasoning=f"Executing {next_tool.get('name')} (priority {priority})",
            confidence=0.9
        )
    
    def _build_dependencies(self, planner_input: PlannerInput) -> dict:
        """Build dependency map from execution constraints."""
        dependencies = {}
        
        # Initialize all tools
        for tool in planner_input.get_available_tools():
            tool_id = tool.get('tool_id')
            dependencies[tool_id] = set()
        
        # Build dependency edges
        for constraint in planner_input.get_execution_constraints():
            if constraint.get('constraint_type') == 'dependency':
                source = constraint.get('source_node_id')
                target = constraint.get('target_node_id')
                if source and target:
                    if target not in dependencies:
                        dependencies[target] = set()
                    dependencies[target].add(source)
        
        return dependencies
