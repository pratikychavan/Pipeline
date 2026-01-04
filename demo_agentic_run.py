#!/usr/bin/env python
"""
Demo: Complete Agentic Pipeline Execution with OpenAI

This demo showcases the full agent system with:
- Real OpenAI LLM integration
- Multi-node pipeline with decision points
- Business conditions and guardrails
- Tool constraints and dependencies
- Complete execution loop with monitoring

Run: python demo_agentic_run.py
"""

import os
import sys
import django
import asyncio
from datetime import datetime

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentRun, AgentDecision, ToolExecution
from agent_integration.control_plane_models import (
    AgentProfile,
    ToolDefinition,
    AgentToolMapping,
    BusinessCondition,
    AgentConditionBinding,
)
from agent_integration.execution_loop import AgentLoopRunner
from agent_integration.llm_planner import LLMPlanner
from agent_integration.runtime_spec_builder import RuntimeSpecService


# ============================================================================
# REAL OPENAI CLIENT
# ============================================================================

class RealOpenAIClient:
    """
    Production-ready OpenAI client.
    
    Uses the official OpenAI Python library.
    """
    
    def __init__(self, api_key: str):
        """Initialize with OpenAI API key."""
        try:
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=api_key)
        except ImportError:
            print("❌ OpenAI library not installed. Installing...")
            os.system("pip install openai")
            from openai import AsyncOpenAI
            self.client = AsyncOpenAI(api_key=api_key)
    
    async def create_completion(
        self,
        messages,
        model,
        max_tokens,
        temperature,
        timeout,
    ):
        """Create completion using OpenAI API."""
        try:
            response = await self.client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
            )
            
            return {
                'content': response.choices[0].message.content,
                'usage': {
                    'total_tokens': response.usage.total_tokens,
                    'prompt_tokens': response.usage.prompt_tokens,
                    'completion_tokens': response.usage.completion_tokens,
                },
            }
        except Exception as e:
            raise Exception(f"OpenAI API error: {str(e)}")


# ============================================================================
# DEMO DATA SETUP
# ============================================================================

def setup_demo_pipeline():
    """
    Create a realistic multi-node pipeline for customer data processing.
    
    Pipeline: Customer Onboarding & Risk Assessment
    - Fetch customer data
    - Validate data quality
    - Assess risk score
    - Generate recommendations
    - Send notifications
    """
    print("🔧 Setting up demo pipeline...")
    
    # Get admin user
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        print("❌ No admin user found. Run: python manage.py createsuperuser")
        sys.exit(1)
    
    # Create pipeline
    pipeline, created = Pipeline.objects.get_or_create(
        name="Customer Onboarding & Risk Assessment",
        defaults={
            'description': "Automated customer onboarding with intelligent risk assessment",
            'created_by': admin,
            'global_arguments': []
        }
    )
    
    if created:
        print(f"   ✓ Created pipeline: {pipeline.name}")
    else:
        print(f"   ✓ Using existing pipeline: {pipeline.name}")
    
    # Node 1: Fetch Customer Data
    node1, _ = Node.objects.get_or_create(
        pipeline=pipeline,
        name="FetchCustomerData",
        defaults={
            'description': "Retrieve customer information from database",
            'order': 1,
            'position_x': 100,
            'position_y': 100,
            'code': """# Fetch Customer Data
from core.execution.warpdrive import WarpDrive
import json

wd = WarpDrive()
wd.log("Fetching customer data...", "INFO")

# Simulate fetching customer data
customer_data = {
    "customer_id": "CUST-12345",
    "name": "Acme Corporation",
    "industry": "Technology",
    "annual_revenue": 5000000,
    "employees": 50,
    "years_in_business": 3,
    "credit_score": 720,
    "previous_defaults": 0,
    "requested_credit_limit": 100000,
}

wd.log(f"Fetched data for: {customer_data['name']}", "INFO")
wd.save_artifact('customer_data', customer_data, json.dumps)
wd.log("Customer data fetch complete", "INFO")
""",
            'input_variable_mappings': {}
        }
    )
    
    # Node 2: Validate Data Quality
    node2, _ = Node.objects.get_or_create(
        pipeline=pipeline,
        name="ValidateDataQuality",
        defaults={
            'description': "Validate completeness and quality of customer data",
            'order': 2,
            'position_x': 300,
            'position_y': 100,
            'code': """# Validate Data Quality
from core.execution.warpdrive import WarpDrive
import json

wd = WarpDrive()
wd.log("Validating data quality...", "INFO")

# Get customer data from previous node
customer_data = wd.get_arg('customer_data', json.loads)

# Validation checks
required_fields = ['customer_id', 'name', 'industry', 'annual_revenue', 'credit_score']
missing_fields = [field for field in required_fields if not customer_data.get(field)]

validation_result = {
    "is_valid": len(missing_fields) == 0,
    "missing_fields": missing_fields,
    "completeness_score": 1.0 - (len(missing_fields) / len(required_fields)),
    "quality_checks": {
        "has_revenue": customer_data.get('annual_revenue', 0) > 0,
        "has_credit_score": customer_data.get('credit_score', 0) > 0,
        "business_age_valid": customer_data.get('years_in_business', 0) >= 0,
    }
}

wd.log(f"Validation complete: {'PASSED' if validation_result['is_valid'] else 'FAILED'}", 
       "INFO" if validation_result['is_valid'] else "WARNING")

wd.save_artifact('validation_result', validation_result, json.dumps)
wd.save_artifact('customer_data', customer_data, json.dumps)  # Pass through
wd.log("Data quality validation complete", "INFO")
""",
            'input_variable_mappings': {}
        }
    )
    
    # Node 3: Assess Risk Score
    node3, _ = Node.objects.get_or_create(
        pipeline=pipeline,
        name="AssessRiskScore",
        defaults={
            'description': "Calculate comprehensive risk score based on multiple factors",
            'order': 3,
            'position_x': 500,
            'position_y': 100,
            'code': """# Assess Risk Score
from core.execution.warpdrive import WarpDrive
import json

wd = WarpDrive()
wd.log("Calculating risk score...", "INFO")

# Get data from previous nodes
customer_data = wd.get_arg('customer_data', json.loads)
validation_result = wd.get_arg('validation_result', json.loads)

# Risk scoring algorithm
def calculate_risk_score(data):
    score = 100  # Start at 100 (perfect score)
    
    # Credit score factor (40% weight)
    credit_score = data.get('credit_score', 0)
    if credit_score < 600:
        score -= 40
    elif credit_score < 700:
        score -= 20
    elif credit_score < 750:
        score -= 10
    
    # Business age factor (20% weight)
    years = data.get('years_in_business', 0)
    if years < 1:
        score -= 20
    elif years < 3:
        score -= 10
    elif years < 5:
        score -= 5
    
    # Revenue factor (20% weight)
    revenue = data.get('annual_revenue', 0)
    credit_limit = data.get('requested_credit_limit', 0)
    if credit_limit > revenue * 0.2:  # Requesting > 20% of revenue
        score -= 20
    elif credit_limit > revenue * 0.1:
        score -= 10
    
    # Default history (20% weight)
    defaults = data.get('previous_defaults', 0)
    score -= defaults * 20
    
    return max(0, min(100, score))

risk_score = calculate_risk_score(customer_data)

# Risk categorization
if risk_score >= 80:
    risk_level = "LOW"
    decision = "APPROVED"
elif risk_score >= 60:
    risk_level = "MEDIUM"
    decision = "REVIEW_REQUIRED"
else:
    risk_level = "HIGH"
    decision = "REJECTED"

risk_assessment = {
    "risk_score": risk_score,
    "risk_level": risk_level,
    "decision": decision,
    "factors": {
        "credit_score": customer_data.get('credit_score'),
        "years_in_business": customer_data.get('years_in_business'),
        "revenue_ratio": customer_data.get('requested_credit_limit', 0) / max(customer_data.get('annual_revenue', 1), 1),
        "previous_defaults": customer_data.get('previous_defaults'),
    }
}

wd.log(f"Risk Assessment: {risk_level} (Score: {risk_score}/100) - {decision}", 
       "INFO" if risk_level == "LOW" else "WARNING")

wd.save_artifact('risk_assessment', risk_assessment, json.dumps)
wd.save_artifact('customer_data', customer_data, json.dumps)  # Pass through
wd.log("Risk assessment complete", "INFO")
""",
            'input_variable_mappings': {}
        }
    )
    
    # Node 4: Generate Recommendations
    node4, _ = Node.objects.get_or_create(
        pipeline=pipeline,
        name="GenerateRecommendations",
        defaults={
            'description': "Generate actionable recommendations based on risk assessment",
            'order': 4,
            'position_x': 700,
            'position_y': 100,
            'code': """# Generate Recommendations
from core.execution.warpdrive import WarpDrive
import json

wd = WarpDrive()
wd.log("Generating recommendations...", "INFO")

# Get risk assessment
risk_assessment = wd.get_arg('risk_assessment', json.loads)
customer_data = wd.get_arg('customer_data', json.loads)

risk_score = risk_assessment['risk_score']
decision = risk_assessment['decision']

# Generate recommendations
recommendations = {
    "decision": decision,
    "approved_credit_limit": 0,
    "conditions": [],
    "next_steps": [],
    "rationale": []
}

if decision == "APPROVED":
    recommendations['approved_credit_limit'] = customer_data['requested_credit_limit']
    recommendations['conditions'] = [
        "Standard payment terms: Net 30",
        "Monthly credit review for first 6 months"
    ]
    recommendations['next_steps'] = [
        "Send approval letter to customer",
        "Setup credit account in system",
        "Schedule first review date"
    ]
    recommendations['rationale'] = [
        f"Strong credit score: {customer_data['credit_score']}",
        f"Risk score: {risk_score}/100 (Low risk)",
        "No previous defaults"
    ]

elif decision == "REVIEW_REQUIRED":
    # Approve reduced amount
    reduced_limit = int(customer_data['requested_credit_limit'] * 0.5)
    recommendations['approved_credit_limit'] = reduced_limit
    recommendations['conditions'] = [
        f"Reduced credit limit: ${reduced_limit:,} (50% of requested)",
        "Require personal guarantee",
        "Bi-weekly credit review for first 3 months"
    ]
    recommendations['next_steps'] = [
        "Schedule call with credit manager",
        "Request additional financial documents",
        "Obtain personal guarantee"
    ]
    recommendations['rationale'] = [
        f"Moderate risk score: {risk_score}/100",
        "Limited business history or revenue concerns",
        "Requires additional oversight"
    ]

else:  # REJECTED
    recommendations['conditions'] = [
        "Application declined at this time"
    ]
    recommendations['next_steps'] = [
        "Send rejection letter with explanation",
        "Provide guidance for reapplication",
        "Suggest alternative financing options"
    ]
    recommendations['rationale'] = [
        f"High risk score: {risk_score}/100",
        "Credit score below threshold" if customer_data['credit_score'] < 600 else "Risk factors exceed threshold",
        "Recommend reapply after 6 months with improved metrics"
    ]

wd.log(f"Generated recommendations: {decision}", "INFO")
wd.save_artifact('recommendations', recommendations, json.dumps)
wd.log("Recommendations generation complete", "INFO")
""",
            'input_variable_mappings': {}
        }
    )
    
    # Node 5: Send Notifications
    node5, _ = Node.objects.get_or_create(
        pipeline=pipeline,
        name="SendNotifications",
        defaults={
            'description': "Send notifications to stakeholders about the decision",
            'order': 5,
            'position_x': 900,
            'position_y': 100,
            'code': """# Send Notifications
from core.execution.warpdrive import WarpDrive
import json

wd = WarpDrive()
wd.log("Sending notifications...", "INFO")

# Get final recommendations
recommendations = wd.get_arg('recommendations', json.loads)
customer_data = wd.get_arg('customer_data', json.loads)
risk_assessment = wd.get_arg('risk_assessment', json.loads)

# Simulate sending notifications
notifications_sent = {
    "customer_notification": {
        "recipient": customer_data['name'],
        "subject": f"Credit Application {recommendations['decision']}",
        "sent": True,
        "timestamp": "2026-01-04T10:30:00Z"
    },
    "internal_notification": {
        "recipients": ["credit_manager@company.com", "sales_team@company.com"],
        "subject": f"New Credit Decision: {customer_data['name']}",
        "sent": True,
        "timestamp": "2026-01-04T10:30:01Z"
    },
    "summary": {
        "customer": customer_data['name'],
        "decision": recommendations['decision'],
        "risk_score": risk_assessment['risk_score'],
        "approved_amount": recommendations['approved_credit_limit']
    }
}

wd.log(f"Notifications sent to customer and internal teams", "INFO")
wd.save_artifact('notifications', notifications_sent, json.dumps)
wd.log("Pipeline execution complete!", "INFO")
""",
            'input_variable_mappings': {}
        }
    )
    
    print(f"   ✓ Created 5 nodes with dependencies")
    
    return pipeline, [node1, node2, node3, node4, node5], admin


def setup_agent_system(pipeline, nodes, admin):
    """
    Create agent profile, tools, and mappings with guardrails.
    """
    print("\n🤖 Setting up agent system...")
    
    # Create Agent Profile with real OpenAI config
    agent, created = AgentProfile.objects.get_or_create(
        name="Credit Risk Agent",
        defaults={
            'description': "AI agent for automated credit risk assessment and decision making",
            'created_by': admin,
            'status': 'active',
            'max_steps': 20,
            'llm_config': {
                'provider': 'openai',
                'model': 'gpt-4o-mini',  # Cost-effective for demo
                'temperature': 0.3,  # Lower for more consistent decisions
                'max_tokens': 1500,
                'timeout_seconds': 30
            },
            'retry_policy': {
                'max_retries': 1,
                'retry_delay_seconds': 2
            },
            'guardrail_config': {
                'max_execution_time_seconds': 300,  # 5 minutes max
                'max_cost_usd': 1.0,  # Max $1 per execution
                'require_approval_for_high_risk': True
            }
        }
    )
    
    action = "Created" if created else "Using existing"
    print(f"   ✓ {action} agent: {agent.name}")
    
    # Create Business Condition: High Risk Approval Required
    condition1, _ = BusinessCondition.objects.get_or_create(
        name="HighRiskRequiresApproval",
        defaults={
            'description': "High-risk decisions require human approval",
            'version': '1.0',
            'condition_type': 'value_comparison',
            'condition_config': {
                'field': 'risk_assessment.risk_level',
                'operator': 'equals',
                'value': 'HIGH'
            },
            'test_cases': [
                {
                    'input': {'risk_assessment': {'risk_level': 'HIGH'}},
                    'expected': True
                },
                {
                    'input': {'risk_assessment': {'risk_level': 'LOW'}},
                    'expected': False
                }
            ]
        }
    )
    print(f"   ✓ Created business condition: {condition1.name}")
    
    # Create tools for each node
    tools_created = []
    for i, node in enumerate(nodes, 1):
        tool, tool_created = ToolDefinition.objects.get_or_create(
            name=node.name,
            defaults={
                'description': node.description,
                'executor_type': 'node',
                'pipeline': pipeline,
                'node_name': node.name,
                'input_schema': {
                    'type': 'object',
                    'properties': {},
                    'required': []
                },
                'output_schema': {
                    'type': 'object',
                    'properties': {}
                },
                'is_enabled': True,
                'estimated_duration_seconds': 10,
                'cost_estimate': 0.01
            }
        )
        
        # Map tool to agent with constraints
        mapping, mapping_created = AgentToolMapping.objects.get_or_create(
            agent=agent,
            tool=tool,
            defaults={
                'is_allowed': True,
                'max_calls': 1,  # Each tool should run once
                'priority': node.order,  # Priority based on node order
                'prerequisites': [] if i == 1 else [nodes[i-2].name]  # Depends on previous node
            }
        )
        
        tools_created.append(tool)
        
        action = "Created" if tool_created else "Using"
        print(f"   ✓ {action} tool: {tool.name} (priority: {node.order})")
    
    # Bind high-risk condition to agent (not to specific tool)
    risk_tool = next((t for t in tools_created if t.name == "AssessRiskScore"), None)
    if risk_tool:
        binding, _ = AgentConditionBinding.objects.get_or_create(
            condition=condition1,
            agent=agent,
            evaluation_point='after_tool',
            defaults={
                'on_true_action': 'pause',  # Pause for human if high risk
                'on_false_action': 'continue',
                'priority': 10,
                'parameters': {'check_after_tool': 'AssessRiskScore'}
            }
        )
        print(f"   ✓ Bound condition to agent at evaluation point: {binding.evaluation_point}")
    
    return agent


async def run_demo_execution(pipeline, agent):
    """
    Execute the pipeline with LLM agent.
    """
    from asgiref.sync import sync_to_async
    
    print("\n" + "="*80)
    print("🚀 STARTING AGENTIC EXECUTION")
    print("="*80)
    
    # Check for OpenAI API key
    api_key = os.environ.get('OPENAI_API_KEY')
    if not api_key:
        print("\n❌ ERROR: OPENAI_API_KEY environment variable not set!")
        print("\nTo run this demo:")
        print("  1. Get your API key from: https://platform.openai.com/api-keys")
        print("  2. Export it: export OPENAI_API_KEY='sk-...'")
        print("  3. Run this script again")
        sys.exit(1)
    
    print(f"\n✓ Found OpenAI API key: {api_key[:10]}...")
    
    # Create pipeline execution (async)
    @sync_to_async
    def create_execution():
        admin = User.objects.filter(is_superuser=True).first()
        return PipelineExecution.objects.create(
            pipeline=pipeline,
            started_by=admin,
            status='pending',
            context_data={'demo_run': True, 'timestamp': str(datetime.now())}
        )
    
    pipeline_execution = await create_execution()
    print(f"\n📋 Created Pipeline Execution: {pipeline_execution.id}")
    
    # Create agent run (async)
    @sync_to_async
    def create_agent_run():
        return AgentRun.objects.create(
            pipeline_execution=pipeline_execution,
            status='initializing',
            max_steps=20,
            agent_config={
                'profile_id': str(agent.id),
                'profile_name': agent.name,
                'llm_config': agent.llm_config,
                'objective': 'Complete customer onboarding and risk assessment'
            }
        )
    
    agent_run = await create_agent_run()
    print(f"🤖 Created Agent Run: {agent_run.id}")
    
    # Create runtime spec (async)
    print("\n📊 Building runtime specification...")
    
    @sync_to_async
    def build_spec():
        return RuntimeSpecService.create_spec_for_agent_run(agent_run, agent_profile=agent)
    
    runtime_spec = await build_spec()
    print(f"   ✓ Available tools: {len(runtime_spec.spec_data['available_tools'])}")
    
    # Initialize OpenAI client
    print("\n🔌 Connecting to OpenAI...")
    llm_client = RealOpenAIClient(api_key=api_key)
    
    # Create LLM planner
    llm_config = agent.llm_config
    planner = LLMPlanner(
        llm_client=llm_client,
        model=llm_config['model'],
        objective="Complete the customer onboarding and risk assessment pipeline by executing tools in the correct order",
        max_tokens=llm_config['max_tokens'],
        temperature=llm_config['temperature'],
        timeout_seconds=llm_config['timeout_seconds']
    )
    
    print(f"   ✓ Using model: {llm_config['model']}")
    print(f"   ✓ Temperature: {llm_config['temperature']}")
    print(f"   ✓ Max tokens: {llm_config['max_tokens']}")
    
    # Run the execution loop
    print("\n" + "="*80)
    print("⚡ EXECUTING WITH LLM PLANNER")
    print("="*80)
    print("\nThe LLM will decide which tools to execute and in what order...")
    print("Watch as it makes intelligent decisions!\n")
    
    try:
        result = await AgentLoopRunner.start_loop(agent_run, planner=planner)
        
        # Display results
        print("\n" + "="*80)
        print("✅ EXECUTION COMPLETE")
        print("="*80)
        
        print(f"\n📊 Execution Summary:")
        print(f"   Status: {result.termination_reason.value}")
        print(f"   Steps Executed: {result.steps_executed}")
        print(f"   Success: {result.success}")
        if result.error_message:
            print(f"   Error: {result.error_message}")
        
        # Show decisions made (async)
        @sync_to_async
        def get_decisions():
            return list(AgentDecision.objects.filter(agent_run=agent_run).order_by('step_number'))
        
        decisions = await get_decisions()
        print(f"\n🧠 Agent Decisions Made ({len(decisions)} decisions):")
        for decision in decisions:
            icon = "✓" if decision.decision_type == 'execute_tool' else "ℹ"
            print(f"   {icon} Step {decision.step_number}: {decision.decision_type}")
            if decision.reasoning:
                print(f"      Reasoning: {decision.reasoning[:100]}...")
        
        # Show tool executions (async)
        @sync_to_async
        def get_executions():
            return list(ToolExecution.objects.filter(agent_decision__agent_run=agent_run).order_by('started_at'))
        
        executions = await get_executions()
        print(f"\n🔧 Tools Executed:")
        for execution in executions:
            status_icon = "✅" if execution.status == 'completed' else "❌"
            print(f"   {status_icon} {execution.tool.name}")
            print(f"      Status: {execution.status}")
            if execution.execution_time_seconds:
                print(f"      Duration: {execution.execution_time_seconds:.2f}s")
        
        # Show final output
        print(f"\n📤 Final State:")
        if result.final_state:
            import json
            print(json.dumps(result.final_state, indent=2)[:500])  # Limit output
        
        print(f"\n💰 Cost Estimate:")
        total_cost = sum(e.cost_usd or 0 for e in executions)
        print(f"   Total: ${total_cost:.4f}")
        
        print("\n" + "="*80)
        print("🎉 DEMO COMPLETE!")
        print("="*80)
        print(f"\nView full details in Django admin:")
        print(f"   http://localhost:8000/admin/agent_integration/agentrun/{agent_run.id}/change/")
        
        return result
        
    except Exception as e:
        print(f"\n❌ ERROR during execution: {str(e)}")
        import traceback
        traceback.print_exc()
        raise


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Main demo function."""
    print("\n" + "="*80)
    print("🎯 AGENTIC PIPELINE DEMO - Customer Risk Assessment")
    print("="*80)
    print("\nThis demo shows:")
    print("  ✓ Real OpenAI LLM integration")
    print("  ✓ Multi-node pipeline with dependencies")
    print("  ✓ Agent making intelligent decisions")
    print("  ✓ Business conditions and guardrails")
    print("  ✓ Complete execution monitoring")
    print("\n" + "="*80)
    
    # Setup
    pipeline, nodes, admin = setup_demo_pipeline()
    agent = setup_agent_system(pipeline, nodes, admin)
    
    print("\n✅ Setup complete!\n")
    
    # Ask user to confirm
    print("Ready to run the agentic execution?")
    print("This will use your OpenAI API key (estimated cost: $0.01-0.05)")
    
    response = input("\nContinue? [Y/n]: ").strip().lower()
    if response and response != 'y':
        print("\n👋 Demo cancelled.")
        return
    
    # Run execution
    asyncio.run(run_demo_execution(pipeline, agent))


if __name__ == '__main__':
    main()
