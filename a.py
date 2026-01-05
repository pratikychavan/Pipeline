# Write your planner here
from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)
from typing import Dict, List, Set


class RiskAssessmentPlanner(Planner):
    """
    Intelligent planner for Customer Risk Assessment Pipeline.
    
    Strategy:
    1. Always validate data quality first (CRITICAL - gate for everything)
    2. If validation fails, request human intervention
    3. If validation passes, proceed with risk assessment
    4. Generate recommendations only after risk assessment
    5. Conditionally execute notifications based on risk level
    
    Decision Flow:
    ValidateDataQuality -> [FAIL -> Human Review] OR [PASS -> AssessRiskScore]
    AssessRiskScore -> GenerateRecommendations
    GenerateRecommendations -> [HIGH RISK -> SendNotifications] OR [LOW/MEDIUM -> Complete]
    """
    
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        # Get available tools and execution history
        available_tools = planner_input.get_available_tools()
        executed_tools = set(planner_input.get_executed_tools())  # Returns tool names now
        
        # Get list of available tool names
        available_tool_names = [tool.get('tool_name') for tool in available_tools]
        
        # STRATEGY: Execute tools in order of priority based on what's available
        # Priority order: FetchCustomerData -> ValidateDataQuality -> AssessRiskScore -> GenerateRecommendations -> SendNotifications
        
        # PHASE 1: Fetch Customer Data (must be first if available)
        if 'FetchCustomerData' in available_tool_names and 'FetchCustomerData' not in executed_tools:
            fetch_id = planner_input.get_tool_id_by_name('FetchCustomerData')
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=fetch_id,
                reasoning="Starting pipeline: Fetching customer data as first step",
                confidence=1.0
            )
        
        # PHASE 2: Data Validation (CRITICAL GATE)
        if 'ValidateDataQuality' in available_tool_names and 'ValidateDataQuality' not in executed_tools:
            validate_id = planner_input.get_tool_id_by_name('ValidateDataQuality')
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=validate_id,
                reasoning="CRITICAL STEP: Validating data quality before risk assessment",
                confidence=1.0
            )
        
        # Check validation result - if it failed, request human intervention
        validation_execution = planner_input.get_execution_result('ValidateDataQuality')
        if validation_execution and not validation_execution.get('success', False):
            validate_id = planner_input.get_tool_id_by_name('ValidateDataQuality')
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                tool_id=validate_id,
                human_message=(
                    "Data validation FAILED. Customer data is incomplete or invalid. "
                    "Manual review required before proceeding with risk assessment."
                ),
                reasoning="Cannot proceed with risk assessment on invalid data - human intervention required",
                confidence=1.0
            )
        
        # PHASE 3: Risk Assessment (Only after validation passes)
        if 'AssessRiskScore' in available_tool_names and 'AssessRiskScore' not in executed_tools:
            assess_id = planner_input.get_tool_id_by_name('AssessRiskScore')
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=assess_id,
                reasoning="Data validation passed - proceeding with risk score calculation",
                confidence=0.95
            )
        
        # PHASE 4: Generate Recommendations (Only after risk assessment)
        if 'GenerateRecommendations' in available_tool_names and 'GenerateRecommendations' not in executed_tools:
            recommendations_id = planner_input.get_tool_id_by_name('GenerateRecommendations')
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id=recommendations_id,
                reasoning="Risk assessment complete - generating actionable recommendations",
                confidence=0.9
            )
        
        # PHASE 5: Conditional Notifications (Based on risk level)
        risk_execution = planner_input.get_execution_result('AssessRiskScore')
        
        if risk_execution and 'SendNotifications' in available_tool_names and 'SendNotifications' not in executed_tools:
            # Check if we have risk assessment data
            risk_level = self._extract_risk_level(risk_execution)
            
            if risk_level == 'HIGH':
                notifications_id = planner_input.get_tool_id_by_name('SendNotifications')
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=notifications_id,
                    reasoning=f"HIGH RISK detected - sending notifications to management for review",
                    confidence=0.95
                )
            
            if risk_level == 'MEDIUM':
                notifications_id = planner_input.get_tool_id_by_name('SendNotifications')
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=notifications_id,
                    reasoning=f"MEDIUM RISK - notifying review team for manual approval",
                    confidence=0.85
                )
        
        # PHASE 6: Complete
        # All critical steps done, notifications sent if needed
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning=(
                f"Risk assessment pipeline complete. "
                f"Executed {len(executed_tools)} tools. "
                f"Final decision available in recommendations."
            ),
            confidence=1.0
        )
    
    def _extract_risk_level(self, risk_execution: Dict) -> str:
        """
        Extract risk level from risk assessment execution.
        Returns: 'HIGH', 'MEDIUM', 'LOW', or 'UNKNOWN'
        """
        # Try to get from output_data or result
        output_data = risk_execution.get('output_data', {})
        
        # Check various possible locations for risk level
        if isinstance(output_data, dict):
            # Direct field
            if 'risk_level' in output_data:
                return output_data['risk_level']
            
            # Nested in risk_assessment
            if 'risk_assessment' in output_data:
                risk_assessment = output_data['risk_assessment']
                if isinstance(risk_assessment, dict) and 'risk_level' in risk_assessment:
                    return risk_assessment['risk_level']
            
            # Try risk_score numeric threshold
            if 'risk_score' in output_data:
                score = output_data['risk_score']
                if score >= 80:
                    return 'LOW'
                elif score >= 60:
                    return 'MEDIUM'
                else:
                    return 'HIGH'
        
        return 'UNKNOWN'
