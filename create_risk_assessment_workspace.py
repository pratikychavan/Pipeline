"""
Create example agent workspace for Customer Risk Assessment Pipeline
"""

# Setup Django environment
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import AgentWorkspace, Pipeline

print("=" * 70)
print("CREATING CUSTOMER RISK ASSESSMENT AGENT WORKSPACE")
print("=" * 70)

# Get admin user
admin = User.objects.filter(is_superuser=True).first()
if not admin:
    print("❌ No admin user found")
    exit(1)

print(f"\n✅ User: {admin.username}")

# Get the risk assessment pipeline
pipeline = Pipeline.objects.filter(name="Customer Onboarding & Risk Assessment").first()
if pipeline:
    print(f"✅ Found pipeline: {pipeline.name}")
else:
    print("⚠️  Pipeline not found - workspace will be created without pipeline link")

# Agent code for risk assessment planner
agent_code = '''from warpdrive_agent_sdk import (
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
        executed_tools = set(planner_input.get_executed_tools())
        execution_history = planner_input.execution_history
        
        # Create tool lookup
        tools_by_id = {tool['tool_id']: tool for tool in available_tools}
        
        # PHASE 1: Data Validation (CRITICAL GATE)
        if 'validate_data_quality' not in executed_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='validate_data_quality',
                reasoning="CRITICAL FIRST STEP: Must validate data quality before any risk assessment",
                confidence=1.0
            )
        
        # Check validation result
        validation_execution = self._get_execution_result(execution_history, 'validate_data_quality')
        
        if validation_execution and not validation_execution.get('success', False):
            return PlannerDecision(
                decision_type=PlannerDecisionType.REQUEST_HUMAN,
                tool_id='validate_data_quality',
                human_message=(
                    "Data validation FAILED. Customer data is incomplete or invalid. "
                    "Manual review required before proceeding with risk assessment."
                ),
                reasoning="Cannot proceed with risk assessment on invalid data - human intervention required",
                confidence=1.0
            )
        
        # PHASE 2: Risk Assessment (Only after validation passes)
        if 'assess_risk_score' not in executed_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='assess_risk_score',
                reasoning="Data validation passed - proceeding with risk score calculation",
                confidence=0.95
            )
        
        # PHASE 3: Generate Recommendations (Only after risk assessment)
        if 'generate_recommendations' not in executed_tools:
            return PlannerDecision(
                decision_type=PlannerDecisionType.EXECUTE_TOOL,
                tool_id='generate_recommendations',
                reasoning="Risk assessment complete - generating actionable recommendations",
                confidence=0.9
            )
        
        # PHASE 4: Conditional Notifications (Based on risk level)
        risk_execution = self._get_execution_result(execution_history, 'assess_risk_score')
        
        if risk_execution:
            # Check if we have risk assessment data
            risk_level = self._extract_risk_level(risk_execution)
            
            if risk_level == 'HIGH' and 'send_notifications' not in executed_tools:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id='send_notifications',
                    reasoning=f"HIGH RISK detected - sending notifications to management for review",
                    confidence=0.95
                )
            
            if risk_level == 'MEDIUM' and 'send_notifications' not in executed_tools:
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id='send_notifications',
                    reasoning=f"MEDIUM RISK - notifying review team for manual approval",
                    confidence=0.85
                )
        
        # PHASE 5: Complete
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
    
    def _get_execution_result(self, history: List[Dict], tool_id: str) -> Dict:
        """Get execution result for a specific tool from history"""
        for execution in history:
            if execution.get('tool_id') == tool_id:
                return execution
        return {}
    
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
'''

# Agent configuration
agent_config = '''name: "Risk Assessment Intelligence Agent"
objective: "Intelligently orchestrate customer risk assessment with conditional logic and human-in-the-loop"
description: |
  A specialized planner for customer onboarding and risk assessment pipelines.
  
  Key Features:
  - Data validation gating (fail-fast on bad data)
  - Risk-based conditional execution
  - Human-in-the-loop for failures and high-risk cases
  - Intelligent notification routing based on risk level
  
  Tool Execution Strategy:
  1. ValidateDataQuality (CRITICAL GATE)
  2. AssessRiskScore (only if validation passes)
  3. GenerateRecommendations (always after risk assessment)
  4. SendNotifications (conditional - only for HIGH/MEDIUM risk)

allowed_tools:
  - fetch_customer_data
  - validate_data_quality
  - assess_risk_score
  - generate_recommendations
  - send_notifications

config:
  model: "gpt-4o-mini"
  temperature: 0.2
  max_steps: 10
  max_execution_time: 180

constraints:
  max_cost_usd: 0.25
  require_approval_for_high_risk: true
  
guardrails:
  - type: "data_validation_required"
    severity: "critical"
    message: "Must validate data before risk assessment"
  
  - type: "human_review_on_failure"
    severity: "high"
    message: "Request human review if validation fails"
'''

# Requirements (optional - keep minimal)
requirements = '''# Optional dependencies for risk assessment planner
# Only approved, read-only packages allowed

# No additional packages needed - SDK and stdlib are sufficient
'''

# Create workspace
workspace_name = "risk_assessment_planner"

# Check if already exists
existing = AgentWorkspace.objects.filter(name=workspace_name, created_by=admin).first()
if existing:
    print(f"\n⚠️  Workspace '{workspace_name}' already exists")
    print(f"   Updating existing workspace...")
    workspace = existing
    workspace.agent_code = agent_code
    workspace.agent_config = agent_config
    workspace.requirements = requirements
    workspace.description = "Intelligent planner for customer risk assessment with conditional logic"
    workspace.validation_status = 'pending'
    workspace.save()
    print(f"   ✅ Updated workspace: {workspace.id}")
else:
    workspace = AgentWorkspace.objects.create(
        name=workspace_name,
        description="Intelligent planner for customer risk assessment with conditional logic",
        pipeline=pipeline,
        created_by=admin,
        agent_code=agent_code,
        agent_config=agent_config,
        requirements=requirements,
        validation_status='pending',
        planner_type='custom'
    )
    print(f"\n✅ Created workspace: {workspace.name}")
    print(f"   ID: {workspace.id}")

# Validate the workspace
print(f"\n🔍 Validating workspace...")

from agent_integration.user_workspace import load_user_workspace
from pathlib import Path
import tempfile

try:
    with tempfile.TemporaryDirectory() as temp_dir:
        workspace_path = Path(temp_dir)
        
        # Write files
        (workspace_path / 'agent.py').write_text(workspace.agent_code)
        (workspace_path / 'agent.yaml').write_text(workspace.agent_config)
        if workspace.requirements:
            (workspace_path / 'requirements.txt').write_text(workspace.requirements)
        
        # Validate
        loaded = load_user_workspace(workspace_path)
        
        # Update workspace
        workspace.validation_status = 'valid'
        workspace.validation_errors = []
        workspace.planner_class_name = loaded.planner_class_name
        workspace.planner_type = 'custom'
        workspace.save()
        
        print(f"   ✅ Validation PASSED")
        print(f"   ✅ Planner Class: {loaded.planner_class_name}")
        print(f"   ✅ Agent Name: {loaded.agent_definition.name}")
        print(f"   ✅ Allowed Tools: {', '.join(loaded.agent_definition.allowed_tools)}")

except Exception as e:
    print(f"   ❌ Validation FAILED: {e}")
    workspace.validation_status = 'invalid'
    workspace.validation_errors = [str(e)]
    workspace.save()

print("\n" + "=" * 70)
print("WORKSPACE READY")
print("=" * 70)

print(f"""
📋 Next Steps:

1. View workspace in UI:
   http://localhost:8000/agent-workspaces/{workspace.id}/

2. Test the planner logic:
   - Validates data quality first (GATE)
   - Fails fast on bad data -> requests human review
   - Assesses risk only after validation passes
   - Conditionally sends notifications for HIGH/MEDIUM risk
   - Completes after all necessary steps

3. Key Features:
   ✅ Data validation gating
   ✅ Risk-based conditional execution
   ✅ Human-in-the-loop for failures
   ✅ Smart notification routing
   ✅ Clear reasoning for each decision

4. Integrate with Control Plane:
   - Use this planner for risk assessment pipelines
   - Platform will execute tools based on planner decisions
   - Planner provides intelligent orchestration

5. Customize:
   - Adjust risk thresholds in _extract_risk_level()
   - Add more conditional logic in plan_next_action()
   - Modify notification conditions
   - Add guardrail checks
""")
