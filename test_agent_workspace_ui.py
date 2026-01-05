"""
Test script to verify Agent Workspace UI implementation
"""

# Setup Django environment FIRST
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

from django.contrib.auth.models import User
from core.models import AgentWorkspace, Pipeline
from agent_integration.user_workspace import load_user_workspace
from pathlib import Path
import tempfile

print("=" * 70)
print("AGENT WORKSPACE UI IMPLEMENTATION TEST")
print("=" * 70)

# 1. Test model creation
print("\n1. Testing AgentWorkspace model...")
try:
    user = User.objects.first()
    if not user:
        print("   ❌ No user found - create a user first")
    else:
        print(f"   ✅ User found: {user.username}")
        
        # Create test workspace
        workspace = AgentWorkspace.objects.create(
            name="test_priority_planner",
            description="Test workspace for priority-based planner",
            created_by=user,
            agent_code="""from warpdrive_agent_sdk import (
    Planner,
    PlannerInput,
    PlannerDecision,
    PlannerDecisionType,
)

class PriorityPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        tools = planner_input.get_available_tools()
        executed = set(planner_input.get_executed_tools())
        
        remaining = [
            (tool.get('metadata', {}).get('priority', 100), tool)
            for tool in tools
            if tool['tool_id'] not in executed
        ]
        
        if not remaining:
            return PlannerDecision(
                decision_type=PlannerDecisionType.COMPLETE,
                reasoning="All tools executed"
            )
        
        remaining.sort(key=lambda x: x[0])
        next_tool = remaining[0][1]
        
        return PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=next_tool['tool_id'],
            reasoning=f"Executing {next_tool['name']}"
        )
""",
            agent_config="""name: "Priority Test Agent"
objective: "Execute tools by priority"
description: "Test agent for priority-based execution"
allowed_tools:
  - tool1
  - tool2
config:
  model: "gpt-4o-mini"
  temperature: 0.3
  max_steps: 20
""",
            validation_status='pending'
        )
        print(f"   ✅ Workspace created: {workspace.name}")
        print(f"   ✅ ID: {workspace.id}")
        
        # 2. Test workspace validation
        print("\n2. Testing workspace validation...")
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                workspace_path = Path(temp_dir)
                
                agent_py = workspace_path / 'agent.py'
                agent_py.write_text(workspace.agent_code)
                
                agent_yaml = workspace_path / 'agent.yaml'
                agent_yaml.write_text(workspace.agent_config)
                
                loaded = load_user_workspace(workspace_path)
                
                print(f"   ✅ Validation passed!")
                print(f"   ✅ Planner class: {loaded.planner_class_name}")
                print(f"   ✅ Agent name: {loaded.agent_definition.name}")
                
                workspace.validation_status = 'valid'
                workspace.planner_class_name = loaded.planner_class_name
                workspace.planner_type = 'custom'
                workspace.save()
                
        except Exception as e:
            print(f"   ❌ Validation failed: {e}")
        
        # 3. Test querying workspaces
        print("\n3. Testing workspace queries...")
        workspaces = AgentWorkspace.objects.filter(created_by=user)
        print(f"   ✅ Found {workspaces.count()} workspace(s)")
        
        for ws in workspaces:
            print(f"      - {ws.name}: {ws.get_validation_status_display()}")
        
        # 4. Cleanup
        print("\n4. Cleanup test data...")
        workspace.delete()
        print(f"   ✅ Test workspace deleted")
        
except Exception as e:
    print(f"   ❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 70)
print("TEST COMPLETE")
print("=" * 70)

print("\n📋 Next Steps:")
print("   1. Navigate to http://localhost:8000/agent-workspaces/")
print("   2. Click 'Create Workspace'")
print("   3. Fill in workspace name and description")
print("   4. Click 'Create Workspace'")
print("   5. Edit agent.py and agent.yaml")
print("   6. Click 'Save Changes'")
print("   7. Click 'Validate Agent Code'")
print("   8. Verify validation passes or see errors")
