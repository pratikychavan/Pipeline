"""
Example User Agent - Conditional Planner

This planner makes decisions based on execution results.
"""

from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)


class ConditionalPlanner(Planner):
    """
    Conditional planner that branches based on results.
    
    Workflow:
    1. Run validation tool first
    2. If validation passes, run processing
    3. If validation fails, request human intervention
    4. After processing, generate reports
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        """Plan next action based on execution history."""
        executed = set(planner_input.get_executed_tools())
        history = planner_input.execution_history
        
        # Step 1: Always start with validation
        if 'validate_input' not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='validate_input',
                reasoning="Starting with input validation"
            )
        
        # Step 2: Check validation result
        validation_result = self._get_execution_result('validate_input', history)
        
        if validation_result and not validation_result.get('success'):
            # Validation failed - request human intervention
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                human_message="Input validation failed. Please review the data.",
                reasoning="Validation errors detected, requiring human review"
            )
        
        # Step 3: Process data (validation passed)
        if 'process_data' not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='process_data',
                reasoning="Validation passed, proceeding with data processing"
            )
        
        # Step 4: Check processing result
        processing_result = self._get_execution_result('process_data', history)
        
        if processing_result and not processing_result.get('success'):
            return PlannerDecision(
                decision_type=PlannerDecisionType.FAIL,
                reasoning="Data processing failed"
            )
        
        # Step 5: Generate reports
        if 'generate_report' not in executed:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='generate_report',
                reasoning="Processing complete, generating report"
            )
        
        # All done
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="All steps completed successfully"
        )
    
    def _get_execution_result(self, tool_id: str, history: list) -> dict:
        """Get execution result for a specific tool."""
        for execution in history:
            if execution.get('tool_id') == tool_id:
                return execution
        return {}
