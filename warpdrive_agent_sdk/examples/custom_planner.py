"""
Custom Planner Example

This example shows how to implement a custom planner.
"""

from warpdrive_agent_sdk import (
    Planner,
    PlannerDecision,
    PlannerDecisionType,
    PlannerInput,
)


class PriorityBasedPlanner(Planner):
    """
    A custom planner that executes tools based on priority.
    
    Tools with higher priority (lower priority number) are executed first.
    Priority is determined by tool metadata.
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan next action based on tool priorities.
        
        Algorithm:
        1. Get available tools
        2. Filter out executed tools
        3. Sort by priority (from tool metadata)
        4. Execute highest priority tool with satisfied dependencies
        5. Complete when no more tools
        """
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
        
        # Find executable tools (dependencies satisfied)
        executable_tools = []
        for tool in tools:
            tool_id = tool.get('tool_id')
            
            # Skip executed
            if tool_id in executed:
                continue
            
            # Check dependencies
            deps = dependencies.get(tool_id, set())
            if deps.issubset(executed):
                # Get priority from metadata (default 100)
                priority = tool.get('metadata', {}).get('priority', 100)
                executable_tools.append((priority, tool))
        
        # No more executable tools
        if not executable_tools:
            # Check if all tools executed
            if len(executed) == len(tools):
                return PlannerDecision(
                    decision_type=PlannerDecisionType.COMPLETE,
                    reasoning=f"All {len(tools)} tools executed successfully"
                )
            else:
                # Some tools have unsatisfied dependencies
                remaining = len(tools) - len(executed)
                return PlannerDecision(
                    decision_type=PlannerDecisionType.FAIL,
                    reasoning=f"{remaining} tools remaining but dependencies not satisfied"
                )
        
        # Sort by priority (lowest number = highest priority)
        executable_tools.sort(key=lambda x: x[0])
        priority, next_tool = executable_tools[0]
        
        # Execute highest priority tool
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=next_tool['tool_id'],
            reasoning=f"Executing {next_tool.get('name')} (priority {priority})",
            confidence=0.9
        )
    
    def _build_dependencies(self, planner_input: PlannerInput) -> dict:
        """Build dependency map from constraints."""
        dependencies = {}
        
        # Initialize all tools
        for tool in planner_input.get_available_tools():
            tool_id = tool.get('tool_id')
            dependencies[tool_id] = set()
        
        # Build dependencies from constraints
        for constraint in planner_input.get_execution_constraints():
            if constraint.get('constraint_type') == 'dependency':
                source = constraint.get('source_node_id')
                target = constraint.get('target_node_id')
                if source and target:
                    if target not in dependencies:
                        dependencies[target] = set()
                    dependencies[target].add(source)
        
        return dependencies


class ConditionalPlanner(Planner):
    """
    A planner that makes decisions based on execution results.
    
    This planner checks the results of previous executions and
    makes conditional decisions (e.g., if validation failed, skip processing).
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan next action based on execution history.
        """
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        history = planner_input.execution_history
        
        # Check if validation tool was executed
        validation_tool_id = 'validate_data'
        if validation_tool_id not in executed:
            # Start with validation
            for tool in tools:
                if tool.get('tool_id') == validation_tool_id:
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.EXECUTE_TOOL,
                        tool_id=validation_tool_id,
                        reasoning="Starting with data validation"
                    )
        
        # Check validation result
        for execution in history:
            if execution.get('tool_id') == validation_tool_id:
                if not execution.get('success'):
                    # Validation failed, don't proceed
                    return PlannerDecision(
                        decision_type=PlannerDecisionType.FAIL,
                        reasoning="Data validation failed, cannot proceed"
                    )
                break
        
        # Validation passed, continue with processing
        processing_tool_id = 'process_data'
        if processing_tool_id not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=processing_tool_id,
                reasoning="Validation passed, proceeding with processing"
            )
        
        # All done
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="Validation and processing complete"
        )


class HumanInTheLoopPlanner(Planner):
    """
    A planner that requests human intervention for critical decisions.
    
    This planner automatically pauses execution at certain points
    to get human approval before proceeding.
    """
    
    def __init__(self, approval_required_tools: list[str]):
        """
        Initialize planner.
        
        Args:
            approval_required_tools: List of tool IDs that require human approval
        """
        self.approval_required_tools = set(approval_required_tools)
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """
        Plan next action with human approval gates.
        """
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        
        # Find next tool to execute
        for tool in tools:
            tool_id = tool.get('tool_id')
            
            if tool_id in executed:
                continue
            
            # Check if this tool requires approval
            if tool_id in self.approval_required_tools:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.REQUEST_HUMAN,
                    tool_id=tool_id,
                    human_message=f"Approval required to execute: {tool.get('name')}",
                    reasoning=f"Tool {tool_id} requires human approval"
                )
            
            # Execute tool without approval
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=tool_id,
                reasoning=f"Executing {tool.get('name')}"
            )
        
        # All done
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All tools executed"
        )


if __name__ == '__main__':
    # Example: Priority-based planning
    print("Example: Priority-based planning")
    print("Tools are executed based on priority metadata")
    print("Lower priority number = higher priority\n")
    
    # Example: Conditional planning
    print("Example: Conditional planning")
    print("Decisions based on execution results")
    print("If validation fails, processing is skipped\n")
    
    # Example: Human-in-the-loop
    print("Example: Human-in-the-loop planning")
    print("Critical tools require human approval")
    print("Agent pauses and waits for approval")
