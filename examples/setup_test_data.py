#!/usr/bin/env python
"""
Setup test data for UI testing of LLM planner system.
Run with: python setup_test_data.py

This creates a single-node pipeline to test the agent system.
Nodes use WarpDrive for I/O, not functional programming.
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentProfile, AgentRun
from agent_integration.control_plane_models import ToolDefinition, AgentToolMapping

def setup():
    print("🚀 Setting up test data for LLM planner...")
    print()
    
    # Get admin user
    admin = User.objects.filter(is_superuser=True).first()
    if not admin:
        print("❌ No admin user found. Create one with: python manage.py createsuperuser")
        return
    
    print(f"✓ Using admin user: {admin.username}")
    
    # Create pipeline
    pipeline, p_created = Pipeline.objects.get_or_create(
        name="Simple Test Pipeline",
        defaults={
            'description': "Single node pipeline for testing LLM planner",
            'created_by': admin,
            'global_arguments': []
        }
    )
    print(f"{'✓ Created' if p_created else '✓ Using existing'} pipeline: {pipeline.name} (ID: {pipeline.id})")
    
    # Create a single node with WarpDrive usage
    # This node uses WarpDrive to handle all I/O (not functional style)
    node1, n_created = Node.objects.get_or_create(
        pipeline=pipeline,
        name="ProcessData",
        defaults={
            'description': "Process data using WarpDrive",
            'code': """# Import WarpDrive for I/O
from core.execution import WarpDrive

# Create WarpDrive instance
wd = WarpDrive()

# Log execution
wd.log("Starting data processing...", "INFO")

# For testing, create some simple data
test_data = {
    "message": "Hello from LLM Planner!",
    "timestamp": "2026-01-04",
    "processed": True
}

# Log the result
wd.log(f"Processed: {test_data}", "INFO")

# Save artifact (this is how WarpDrive handles outputs)
wd.save_artifact('result', test_data)

# WarpDrive will automatically track this as output
wd.log("Processing complete!", "INFO")
""",
            'order': 1,
            'position_x': 100,
            'position_y': 100,
            'input_variable_mappings': {}
        }
    )
    print(f"{'✓ Created' if n_created else '✓ Using existing'} node: {node1.name} (ID: {node1.id})")
    print(f"  Note: Node uses WarpDrive for I/O")
    
    # Create agent profile
    agent, a_created = AgentProfile.objects.get_or_create(
        name="LLM Test Agent",
        defaults={
            'description': "Agent using LLM for planning (or deterministic fallback)",
            'created_by': admin,
            'status': 'active',
            'max_steps': 10,  # Only need a few steps for single node
            'llm_config': {
                'provider': 'openai',
                'model': 'gpt-4',
                'temperature': 0.3,
                'max_tokens': 1000,
                'timeout_seconds': 30
            },
            'retry_policy': {'max_retries': 0},
            'guardrail_config': {
                'max_execution_time_seconds': 300,
                'max_cost_usd': 5.0
            }
        }
    )
    print(f"{'✓ Created' if a_created else '✓ Using existing'} agent: {agent.name} (ID: {agent.id})")
    
    # Create tool for the node
    tool, t_created = ToolDefinition.objects.get_or_create(
        name=node1.name,
        defaults={
            'description': f"Execute {node1.name} - {node1.description}",
            'executor_type': 'node',  # Valid choice: 'node', 'function', or 'external'
            'pipeline': pipeline,
            'node_name': node1.name,
            'input_schema': {'type': 'object'},
            'output_schema': {'type': 'object'},
            'is_enabled': True
        }
    )
    print(f"{'✓ Created' if t_created else '✓ Using existing'} tool: {tool.name} (ID: {tool.id})")
    
    # Map tool to agent
    mapping, m_created = AgentToolMapping.objects.get_or_create(
        agent=agent,
        tool=tool,
        defaults={
            'is_allowed': True,
            'max_calls': 1,
            'priority': 1,
            'prerequisites': []
        }
    )
    print(f"  {'└─ Mapped' if m_created else '└─ Already mapped'} to agent")
    
    print()
    print("=" * 80)
    print("✅ SETUP COMPLETE!")
    print("=" * 80)
    print()
    print("📊 Summary:")
    print(f"   Pipeline: {pipeline.name}")
    print(f"   Pipeline ID: {pipeline.id}")
    print(f"   Nodes: 1 (ProcessData with WarpDrive)")
    print(f"   Agent: {agent.name}")
    print(f"   Agent ID: {agent.id}")
    print(f"   Tools: 1")
    print(f"   Tool Mappings: 1")
    print()
    print("🌐 Next Steps:")
    print()
    print("1. Start the dev server:")
    print("   python manage.py runserver")
    print()
    print("2. Access Django Admin:")
    print("   http://localhost:8000/admin/")
    print()
    print("3. View your data:")
    print(f"   - Core → Pipelines → {pipeline.name}")
    print(f"   - Core → Nodes → {node1.name}")
    print(f"   - Agent Integration → Agent Profiles → {agent.name}")
    print(f"   - Control Plane → Tool Definitions → {tool.name}")
    print(f"   - Control Plane → Agent Tool Mappings (1 mapping)")
    print()
    print("4. Create a Pipeline Execution (via admin UI):")
    print("   - Core → Pipeline Executions → Add")
    print(f"   - Pipeline: {pipeline.name}")
    print("   - Status: pending")
    print("   - Started by: admin")
    print("   - Save and note the ID")
    print()
    print("5. Create an Agent Run (via admin UI):")
    print("   - Agent Integration → Agent Runs → Add")
    print("   - Pipeline execution: [select the one you created]")
    print(f"   - Agent profile: {agent.name}")
    print("   - Status: initializing")
    print("   - Max steps: 10")
    print("   - Save and note the ID")
    print()
    print("6. Execute via Django shell:")
    print("   python manage.py shell")
    print()
    print("   Then run:")
    print("   >>> import asyncio")
    print("   >>> from agent_integration.models import AgentRun")
    print("   >>> from agent_integration.execution_loop import AgentLoopRunner, DeterministicPlanner")
    print("   >>> ")
    print("   >>> # Get your agent run")
    print("   >>> agent_run = AgentRun.objects.last()")
    print("   >>> ")
    print("   >>> # Use DeterministicPlanner (no OpenAI needed)")
    print("   >>> planner = DeterministicPlanner()")
    print("   >>> ")
    print("   >>> # Run it")
    print("   >>> result = asyncio.run(AgentLoopRunner.start_loop(agent_run, planner=planner))")
    print("   >>> ")
    print("   >>> # View results")
    print("   >>> print(f'Status: {result.termination_reason.value}')")
    print("   >>> print(f'Steps: {result.steps_executed}')")
    print("   >>> print(f'Success: {result.success}')")
    print()
    print("7. View results in admin:")
    print("   - Agent Run → Check status (should be 'completed')")
    print("   - Agent Decisions → See decisions made")
    print("   - Tool Executions → See tool executed")
    print("   - Core → Node Executions → See node execution details")
    print()
    print("💡 Notes:")
    print("   - This is a SINGLE NODE pipeline for simple testing")
    print("   - The node uses WarpDrive for I/O (not functional style)")
    print("   - Use DeterministicPlanner to test without OpenAI")
    print("   - For LLM testing, you'll need to implement OpenAI client")
    print("   - Check NodeToolExecutor wraps existing execution logic")
    print()
    print("=" * 80)

if __name__ == '__main__':
    setup()
