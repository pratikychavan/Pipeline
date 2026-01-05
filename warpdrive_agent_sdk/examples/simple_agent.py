"""
Simple Agent Example

This example shows how to define a basic agent.
"""

from warpdrive_agent_sdk import AgentDefinition, AgentConfig, GuardrailConfig


def create_data_validation_agent() -> AgentDefinition:
    """
    Create a simple data validation agent.
    
    This agent validates incoming data against a schema,
    checks data quality, and performs basic cleaning.
    """
    return AgentDefinition(
        name="Data Validation Agent",
        objective="Validate and clean incoming data to ensure quality",
        description="""
        This agent performs three main tasks:
        1. Validates data against expected schema
        2. Checks data quality metrics (completeness, accuracy)
        3. Performs basic data cleaning (remove duplicates, fix formats)
        """,
        allowed_tools=[
            "validate_schema",
            "check_data_quality",
            "clean_data",
        ],
        config=AgentConfig(
            model='gpt-4o-mini',
            temperature=0.2,  # Low temperature for deterministic validation
            max_steps=10,  # Simple workflow, few steps needed
            enable_human_intervention=True,
            fail_on_node_failure=True,  # Stop if validation fails
        ),
        constraints={
            'min_quality_score': 0.8,  # Data must be 80% quality
            'max_errors_allowed': 5,  # Maximum 5 validation errors
        },
        metadata={
            'version': '1.0',
            'category': 'data_validation',
            'author': 'platform_team',
        }
    )


def create_agent_with_guardrails() -> tuple[AgentDefinition, GuardrailConfig]:
    """
    Create an agent with safety guardrails.
    
    This example shows how to configure guardrails to ensure
    the agent operates within safe limits.
    """
    agent = AgentDefinition(
        name="Payment Processing Agent",
        objective="Process payment transactions safely",
        description="Validates and processes payment transactions with approval gates",
        allowed_tools=[
            "validate_payment",
            "check_fraud_risk",
            "process_payment",
            "send_receipt",
        ],
        config=AgentConfig(
            model='gpt-4o-mini',
            temperature=0.1,  # Very low temperature for financial operations
            max_steps=20,
            enable_human_intervention=True,
        ),
    )
    
    guardrails = GuardrailConfig(
        max_execution_time_seconds=60,  # 1 minute max
        max_cost_usd=0.10,  # 10 cents max LLM cost
        require_approval_for_high_risk=True,  # Require approval for risky operations
        forbidden_tool_patterns=[
            '.*delete.*',  # No deletion operations
            '.*refund.*',  # Refunds require separate workflow
        ],
        max_retries_per_tool=2,  # Only 2 retries for financial ops
        fail_on_guardrail_violation=True,  # Stop immediately on violation
    )
    
    return agent, guardrails


if __name__ == '__main__':
    # Create and validate agent
    agent = create_data_validation_agent()
    agent.validate()
    
    print("✅ Agent definition is valid!")
    print(f"Name: {agent.name}")
    print(f"Objective: {agent.objective}")
    print(f"Tools: {', '.join(agent.allowed_tools)}")
    print(f"Max steps: {agent.config.max_steps}")
    
    # Create agent with guardrails
    agent2, guardrails = create_agent_with_guardrails()
    agent2.validate()
    guardrails.validate()
    
    print(f"\n✅ Agent with guardrails is valid!")
    print(f"Name: {agent2.name}")
    print(f"Max execution time: {guardrails.max_execution_time_seconds}s")
    print(f"Max cost: ${guardrails.max_cost_usd}")
