"""
Example: Using Node Tool Wrappers

This script demonstrates how to use node tool wrappers
to execute pipeline nodes as tools for agent orchestration.

Run: python manage.py shell < node_tools_example.py
"""

import asyncio
import uuid
from datetime import datetime, timezone

# Django setup
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentRun
from agent_integration.node_tools import (
    NodeToolRegistry,
    get_node_tool,
    get_available_tools_for_agent_run,
    get_executed_tools,
    can_execute_node,
    format_tool_result_for_agent,
)


async def example_1_basic_tool_execution():
    """Example 1: Execute a single node as a tool"""
    print("\n" + "="*60)
    print("Example 1: Basic Tool Execution")
    print("="*60)
    
    # Get first pipeline and node
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found. Create a pipeline first.")
        return
    
    node = Node.objects.filter(pipeline=pipeline).first()
    if not node:
        print("❌ No nodes found. Add nodes to the pipeline first.")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    print(f"🔧 Node: {node.name}")
    
    # Create a pipeline execution for testing
    user = User.objects.first()
    pipeline_exec = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=user,
        status='running',
        context_data={'test': 'data'},
    )
    
    # Create an agent run
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_exec,
        status='executing',
        agent_config={'model': 'gpt-4', 'temperature': 0.7},
    )
    
    print(f"\n🤖 Created AgentRun: {agent_run.id}")
    
    # Get tool wrapper
    tool = get_node_tool(node.id)
    print(f"\n🔧 Tool: {tool.node_name}")
    print(f"   ID: {tool.node_id}")
    
    # Get tool definition
    tool_def = tool.get_tool_definition()
    print(f"\n📋 Tool Definition:")
    for key, value in tool_def.items():
        print(f"   {key}: {value}")
    
    # Execute the tool
    print(f"\n▶️  Executing tool...")
    try:
        result = await tool.execute(
            agent_run_id=agent_run.id,
            agent_decision_id=None,
            parameters={},  # Empty parameters for this example
            context={'test_context': 'value'},
        )
        
        print(f"\n✅ Execution Result:")
        print(format_tool_result_for_agent(result))
        print(f"\n📊 Details:")
        print(f"   Tool Execution ID: {result.tool_execution_id}")
        print(f"   Node Execution ID: {result.node_execution_id}")
        print(f"   Duration: {result.duration_seconds:.3f}s")
        
    except Exception as e:
        print(f"\n❌ Execution failed: {e}")


async def example_2_pipeline_tools():
    """Example 2: Get all tools for a pipeline"""
    print("\n" + "="*60)
    print("Example 2: Pipeline Tools Discovery")
    print("="*60)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    
    # Get all tools for pipeline
    tools = NodeToolRegistry.get_tools_for_pipeline(pipeline.id)
    print(f"\n🔧 Available Tools: {len(tools)}")
    
    for i, tool in enumerate(tools, 1):
        print(f"\n{i}. {tool.node_name}")
        tool_def = tool.get_tool_definition()
        print(f"   Pipeline: {tool_def['pipeline_name']}")
        print(f"   Description: {tool_def['description']}")
        if tool_def.get('input_variables'):
            print(f"   Inputs: {', '.join(tool_def['input_variables'])}")
    
    # Get tool definitions (for agent context)
    tool_defs = NodeToolRegistry.get_tool_definitions(pipeline.id)
    print(f"\n📋 Tool Definitions for Agent: {len(tool_defs)}")


async def example_3_execution_history():
    """Example 3: Check execution history"""
    print("\n" + "="*60)
    print("Example 3: Execution History")
    print("="*60)
    
    # Get most recent agent run
    agent_run = AgentRun.objects.order_by('-created_at').first()
    if not agent_run:
        print("❌ No agent runs found")
        return
    
    print(f"\n🤖 Agent Run: {agent_run.id}")
    print(f"   Status: {agent_run.status}")
    print(f"   Created: {agent_run.created_at}")
    
    # Get executed tools
    executed = get_executed_tools(agent_run.id)
    print(f"\n📊 Executed Tools: {len(executed)}")
    
    for i, exec_info in enumerate(executed, 1):
        print(f"\n{i}. {exec_info['tool_name']}")
        print(f"   Status: {exec_info['status']}")
        print(f"   Summary: {exec_info['result_summary']}")
        if exec_info['artifact_references']:
            print(f"   Artifacts: {len(exec_info['artifact_references'])}")


async def example_4_validation():
    """Example 4: Validate node execution"""
    print("\n" + "="*60)
    print("Example 4: Execution Validation")
    print("="*60)
    
    # Get node and agent run
    node = Node.objects.first()
    agent_run = AgentRun.objects.order_by('-created_at').first()
    
    if not node or not agent_run:
        print("❌ Missing node or agent run")
        return
    
    print(f"\n🔧 Node: {node.name}")
    print(f"🤖 Agent Run: {agent_run.id}")
    
    # Check if node can be executed
    can_run, reason = can_execute_node(
        node_id=node.id,
        agent_run_id=agent_run.id,
        context={},  # Empty context
    )
    
    if can_run:
        print(f"\n✅ Node can be executed")
    else:
        print(f"\n❌ Cannot execute node")
        print(f"   Reason: {reason}")
    
    # Check with missing inputs
    if node.input_variable_mappings:
        print(f"\n📋 Required Inputs: {list(node.input_variable_mappings.keys())}")
        can_run, reason = can_execute_node(
            node_id=node.id,
            agent_run_id=agent_run.id,
            context={},  # Still empty - should fail
        )
        print(f"   Can execute without inputs? {can_run}")
        if not can_run:
            print(f"   Reason: {reason}")


async def example_5_available_tools():
    """Example 5: Get available tools for agent run"""
    print("\n" + "="*60)
    print("Example 5: Available Tools for Agent")
    print("="*60)
    
    agent_run = AgentRun.objects.order_by('-created_at').first()
    if not agent_run:
        print("❌ No agent runs found")
        return
    
    print(f"\n🤖 Agent Run: {agent_run.id}")
    
    # Get available tools
    tools = get_available_tools_for_agent_run(agent_run.id)
    print(f"\n🔧 Available Tools: {len(tools)}")
    
    for i, tool_def in enumerate(tools, 1):
        print(f"\n{i}. {tool_def['tool_name']}")
        print(f"   Type: {tool_def['tool_type']}")
        print(f"   Pipeline: {tool_def.get('pipeline_name', 'N/A')}")


async def main():
    """Run all examples"""
    print("\n" + "="*60)
    print("NODE TOOL WRAPPERS - EXAMPLES")
    print("="*60)
    
    try:
        await example_1_basic_tool_execution()
    except Exception as e:
        print(f"\n❌ Example 1 failed: {e}")
    
    try:
        await example_2_pipeline_tools()
    except Exception as e:
        print(f"\n❌ Example 2 failed: {e}")
    
    try:
        await example_3_execution_history()
    except Exception as e:
        print(f"\n❌ Example 3 failed: {e}")
    
    try:
        await example_4_validation()
    except Exception as e:
        print(f"\n❌ Example 4 failed: {e}")
    
    try:
        await example_5_available_tools()
    except Exception as e:
        print(f"\n❌ Example 5 failed: {e}")
    
    print("\n" + "="*60)
    print("Examples Complete!")
    print("="*60)


if __name__ == '__main__':
    asyncio.run(main())
