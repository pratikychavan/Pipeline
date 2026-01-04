#!/usr/bin/env python
"""
Create example Control Plane data for UI testing.
Run: python manage.py shell < create_control_plane_examples.py
Or: python create_control_plane_examples.py
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from agent_integration.control_plane_models import (
    AgentProfile, ToolDefinition, AgentToolMapping,
    BusinessCondition, AgentConditionBinding
)
from core.models import Pipeline, Node

def create_examples():
    print("Creating Control Plane example data...")
    
    # 1. Create example tools
    print("\n1. Creating Tools...")
    
    tool_data_validator = ToolDefinition.objects.create(
        name="data_validator",
        description="Validates input data against schema constraints",
        executor_type="function",
        is_enabled=True,
        input_schema={
            "type": "object",
            "properties": {
                "data": {"type": "object"},
                "schema": {"type": "object"}
            },
            "required": ["data", "schema"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "valid": {"type": "boolean"},
                "errors": {"type": "array", "items": {"type": "string"}}
            }
        }
    )
    print(f"   ✓ Created tool: {tool_data_validator.name}")
    
    tool_api_caller = ToolDefinition.objects.create(
        name="external_api_caller",
        description="Makes HTTP requests to external APIs with retry logic",
        executor_type="external",
        is_enabled=True,
        input_schema={
            "type": "object",
            "properties": {
                "url": {"type": "string"},
                "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE"]},
                "headers": {"type": "object"},
                "body": {"type": "object"}
            },
            "required": ["url", "method"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "status_code": {"type": "integer"},
                "response": {"type": "object"}
            }
        }
    )
    print(f"   ✓ Created tool: {tool_api_caller.name}")
    
    tool_db_query = ToolDefinition.objects.create(
        name="database_query_executor",
        description="Executes read-only database queries with safety checks",
        executor_type="function",
        is_enabled=False,  # Disabled for safety
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "params": {"type": "array"}
            },
            "required": ["query"]
        },
        output_schema={
            "type": "object",
            "properties": {
                "rows": {"type": "array"},
                "count": {"type": "integer"}
            }
        }
    )
    print(f"   ✓ Created tool: {tool_db_query.name} (disabled)")
    
    # Try to link a tool to a pipeline node if available
    pipeline = Pipeline.objects.first()
    if pipeline:
        node = pipeline.nodes.first()
        if node:
            tool_pipeline_node = ToolDefinition.objects.create(
                name="transform_data",
                description="Pipeline node for data transformation",
                executor_type="node",
                pipeline=pipeline,
                node_name=node.name,
                is_enabled=True,
                input_schema={"type": "object"},
                output_schema={"type": "object"}
            )
            print(f"   ✓ Created tool: {tool_pipeline_node.name} (backed by pipeline node)")
    
    # 2. Create business conditions
    print("\n2. Creating Business Conditions...")
    
    condition_budget = BusinessCondition.objects.create(
        name="budget_check",
        description="Ensures operation cost stays within budget limits",
        condition_type="threshold",
        version="1.0",
        is_active=True,
        condition_config={
            "metric": "estimated_cost",
            "operator": "<=",
            "threshold": 100.0,
            "currency": "USD"
        },
        test_cases=[
            {"input": {"estimated_cost": 50}, "expected": True},
            {"input": {"estimated_cost": 150}, "expected": False}
        ]
    )
    print(f"   ✓ Created condition: {condition_budget.name}")
    
    condition_quality = BusinessCondition.objects.create(
        name="data_quality_gate",
        description="Validates data quality metrics meet minimum standards",
        condition_type="composite",
        version="1.0",
        is_active=True,
        condition_config={
            "rules": [
                {"metric": "completeness", "min": 0.95},
                {"metric": "accuracy", "min": 0.90},
                {"metric": "null_rate", "max": 0.05}
            ],
            "operator": "all"
        },
        test_cases=[
            {
                "input": {"completeness": 0.98, "accuracy": 0.92, "null_rate": 0.02},
                "expected": True
            },
            {
                "input": {"completeness": 0.98, "accuracy": 0.85, "null_rate": 0.02},
                "expected": False
            }
        ]
    )
    print(f"   ✓ Created condition: {condition_quality.name}")
    
    condition_retry = BusinessCondition.objects.create(
        name="retry_eligibility",
        description="Determines if a failed operation should be retried",
        condition_type="rule",
        version="1.0",
        is_active=True,
        condition_config={
            "error_types_allowed": ["timeout", "rate_limit", "temporary_failure"],
            "max_attempts": 3,
            "backoff_strategy": "exponential"
        },
        test_cases=[
            {"input": {"error_type": "timeout", "attempt": 1}, "expected": True},
            {"input": {"error_type": "validation_error", "attempt": 1}, "expected": False}
        ]
    )
    print(f"   ✓ Created condition: {condition_retry.name}")
    
    # 3. Create agent profiles
    print("\n3. Creating Agent Profiles...")
    
    agent_analyst = AgentProfile.objects.create(
        name="Data Analyst Agent",
        description="Analyzes datasets and generates insights with visualization recommendations",
        status="active",
        max_steps=20,
        retry_policy={
            "max_retries": 3,
            "backoff_multiplier": 2,
            "initial_delay_seconds": 1
        },
        guardrail_config={
            "max_cost_usd": 50.0,
            "max_execution_time_seconds": 300,
            "require_human_approval_for": ["external_api_calls", "data_modifications"]
        },
        llm_config={
            "model": "gpt-4",
            "temperature": 0.7,
            "max_tokens": 2000,
            "system_prompt": "You are a data analyst assistant. Focus on accuracy and clarity."
        }
    )
    print(f"   ✓ Created agent: {agent_analyst.name}")
    
    agent_validator = AgentProfile.objects.create(
        name="Validation Agent",
        description="Validates data quality and compliance before processing",
        status="active",
        max_steps=10,
        retry_policy={
            "max_retries": 2,
            "backoff_multiplier": 1.5,
            "initial_delay_seconds": 0.5
        },
        guardrail_config={
            "max_cost_usd": 10.0,
            "max_execution_time_seconds": 60,
            "require_human_approval_for": []
        },
        llm_config={
            "model": "gpt-3.5-turbo",
            "temperature": 0.3,
            "max_tokens": 1000,
            "system_prompt": "You are a validation specialist. Be thorough and conservative."
        }
    )
    print(f"   ✓ Created agent: {agent_validator.name}")
    
    agent_orchestrator = AgentProfile.objects.create(
        name="Pipeline Orchestrator",
        description="Coordinates multi-step workflows and delegates to specialized agents",
        status="draft",
        max_steps=50,
        retry_policy={
            "max_retries": 5,
            "backoff_multiplier": 2,
            "initial_delay_seconds": 2
        },
        guardrail_config={
            "max_cost_usd": 200.0,
            "max_execution_time_seconds": 1800,
            "require_human_approval_for": ["high_cost_operations"]
        },
        llm_config={
            "model": "gpt-4",
            "temperature": 0.5,
            "max_tokens": 4000,
            "system_prompt": "You are an orchestrator. Plan carefully and coordinate efficiently."
        }
    )
    print(f"   ✓ Created agent: {agent_orchestrator.name} (draft)")
    
    # 4. Create agent-tool mappings
    print("\n4. Creating Agent-Tool Mappings...")
    
    AgentToolMapping.objects.create(
        agent=agent_analyst,
        tool=tool_data_validator,
        is_allowed=True,
        max_calls=100,
        priority=10,
        prerequisites=["data_loaded"],
        notes="High priority for data validation before analysis"
    )
    print(f"   ✓ Mapped: {agent_analyst.name} → {tool_data_validator.name}")
    
    AgentToolMapping.objects.create(
        agent=agent_analyst,
        tool=tool_api_caller,
        is_allowed=True,
        max_calls=50,
        priority=5,
        prerequisites=["api_credentials_configured"],
        notes="Limited API calls to control costs"
    )
    print(f"   ✓ Mapped: {agent_analyst.name} → {tool_api_caller.name}")
    
    AgentToolMapping.objects.create(
        agent=agent_validator,
        tool=tool_data_validator,
        is_allowed=True,
        max_calls=200,
        priority=20,
        prerequisites=[],
        notes="Primary tool for validation agent"
    )
    print(f"   ✓ Mapped: {agent_validator.name} → {tool_data_validator.name}")
    
    AgentToolMapping.objects.create(
        agent=agent_validator,
        tool=tool_db_query,
        is_allowed=False,  # Explicitly blocked
        max_calls=0,
        priority=0,
        prerequisites=[],
        notes="Database access blocked for security"
    )
    print(f"   ✓ Mapped: {agent_validator.name} → {tool_db_query.name} (BLOCKED)")
    
    # 5. Create agent-condition bindings
    print("\n5. Creating Agent-Condition Bindings...")
    
    AgentConditionBinding.objects.create(
        agent=agent_analyst,
        condition=condition_budget,
        evaluation_point="before_execution",
        on_true_action="proceed",
        on_false_action="abort",
        priority=100,
        is_enabled=True,
        parameters={"cost_estimation_method": "token_based"},
        max_evaluations=1
    )
    print(f"   ✓ Bound: {agent_analyst.name} → {condition_budget.name}")
    
    AgentConditionBinding.objects.create(
        agent=agent_analyst,
        condition=condition_quality,
        evaluation_point="after_tool_execution",
        on_true_action="proceed",
        on_false_action="retry",
        priority=50,
        is_enabled=True,
        parameters={"quality_threshold": "strict"},
        max_evaluations=3
    )
    print(f"   ✓ Bound: {agent_analyst.name} → {condition_quality.name}")
    
    AgentConditionBinding.objects.create(
        agent=agent_validator,
        condition=condition_quality,
        evaluation_point="before_completion",
        on_true_action="proceed",
        on_false_action="abort",
        priority=100,
        is_enabled=True,
        parameters={"quality_threshold": "maximum"},
        max_evaluations=1
    )
    print(f"   ✓ Bound: {agent_validator.name} → {condition_quality.name}")
    
    AgentConditionBinding.objects.create(
        agent=agent_orchestrator,
        condition=condition_retry,
        evaluation_point="on_error",
        on_true_action="retry",
        on_false_action="abort",
        priority=75,
        is_enabled=True,
        parameters={"retry_delay_seconds": 5},
        max_evaluations=5
    )
    print(f"   ✓ Bound: {agent_orchestrator.name} → {condition_retry.name}")
    
    print("\n✅ Example data created successfully!")
    print("\n📊 Summary:")
    print(f"   - {ToolDefinition.objects.count()} tools")
    print(f"   - {BusinessCondition.objects.count()} conditions")
    print(f"   - {AgentProfile.objects.count()} agents")
    print(f"   - {AgentToolMapping.objects.count()} tool mappings")
    print(f"   - {AgentConditionBinding.objects.count()} condition bindings")
    print("\n🌐 Access Control Plane at: http://localhost:8000/control-plane/")

if __name__ == "__main__":
    create_examples()
