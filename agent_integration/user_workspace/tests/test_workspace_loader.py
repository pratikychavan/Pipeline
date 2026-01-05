"""
Tests for User Workspace Loader

Tests security validation, planner validation, and workspace loading.
"""

import pytest
import tempfile
from pathlib import Path
from agent_integration.user_workspace import (
    load_user_workspace,
    WorkspaceValidationError,
    SecurityViolation,
    InvalidPlannerError,
    InvalidConfigError,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

@pytest.fixture
def temp_workspace():
    """Create temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def valid_agent_py():
    """Valid agent.py content."""
    return """
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision, PlannerDecisionType

class TestPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="Test planner"
        )
"""


@pytest.fixture
def valid_agent_yaml():
    """Valid agent.yaml content."""
    return """
name: "Test Agent"
objective: "Test agent for unit tests"
description: "Test description"

allowed_tools:
  - test_tool

config:
  model: "gpt-4o-mini"
  temperature: 0.3
  max_steps: 10
"""


# ============================================================================
# SECURITY VALIDATION TESTS
# ============================================================================

class TestSecurityValidation:
    """Test security validations."""
    
    def test_forbidden_import_os(self, temp_workspace, valid_agent_yaml):
        """Test that os import is rejected."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
import os
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision

class TestPlanner(Planner):
    async def plan_next_action(self, planner_input):
        return PlannerDecision()
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(SecurityViolation) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'Forbidden import' in str(exc_info.value)
        assert 'os' in str(exc_info.value)
    
    def test_forbidden_import_subprocess(self, temp_workspace, valid_agent_yaml):
        """Test that subprocess import is rejected."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
import subprocess
from warpdrive_agent_sdk import Planner

class TestPlanner(Planner):
    async def plan_next_action(self, planner_input):
        pass
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(SecurityViolation) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'subprocess' in str(exc_info.value)
    
    def test_forbidden_builtin_eval(self, temp_workspace, valid_agent_yaml):
        """Test that eval() is rejected."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision

class TestPlanner(Planner):
    async def plan_next_action(self, planner_input):
        eval("print('test')")
        return PlannerDecision()
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(SecurityViolation) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'eval' in str(exc_info.value)
    
    def test_allowed_imports(self, temp_workspace, valid_agent_yaml):
        """Test that allowed imports work."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
import json
import math
from typing import Dict
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision, PlannerDecisionType

class TestPlanner(Planner):
    async def plan_next_action(self, planner_input: PlannerInput) -> PlannerDecision:
        return PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
            reasoning="Test"
        )
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        # Should not raise
        workspace = load_user_workspace(temp_workspace)
        assert workspace.planner_class_name == 'TestPlanner'


# ============================================================================
# PLANNER VALIDATION TESTS
# ============================================================================

class TestPlannerValidation:
    """Test planner validation."""
    
    def test_no_planner_class(self, temp_workspace, valid_agent_yaml):
        """Test error when no Planner subclass exists."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
from warpdrive_agent_sdk import Planner

# No planner class defined
def some_function():
    pass
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(InvalidPlannerError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'No Planner subclass found' in str(exc_info.value)
    
    def test_multiple_planner_classes(self, temp_workspace, valid_agent_yaml):
        """Test error when multiple Planner subclasses exist."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
from warpdrive_agent_sdk import Planner, PlannerInput, PlannerDecision

class Planner1(Planner):
    async def plan_next_action(self, planner_input):
        return PlannerDecision()

class Planner2(Planner):
    async def plan_next_action(self, planner_input):
        return PlannerDecision()
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(InvalidPlannerError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'Multiple Planner subclasses' in str(exc_info.value)
    
    def test_missing_plan_next_action(self, temp_workspace, valid_agent_yaml):
        """Test error when plan_next_action not implemented."""
        agent_py = temp_workspace / 'agent.py'
        agent_py.write_text("""
from warpdrive_agent_sdk import Planner

class TestPlanner(Planner):
    def some_other_method(self):
        pass
""")
        
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(InvalidPlannerError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'plan_next_action' in str(exc_info.value)


# ============================================================================
# CONFIG VALIDATION TESTS
# ============================================================================

class TestConfigValidation:
    """Test agent.yaml validation."""
    
    def test_missing_name(self, temp_workspace, valid_agent_py):
        """Test error when name missing from agent.yaml."""
        agent_yaml = temp_workspace / 'agent.yaml'
        agent_yaml.write_text("""
objective: "Test objective"
""")
        
        (temp_workspace / 'agent.py').write_text(valid_agent_py)
        
        with pytest.raises(InvalidConfigError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'name' in str(exc_info.value)
    
    def test_missing_objective(self, temp_workspace, valid_agent_py):
        """Test error when objective missing from agent.yaml."""
        agent_yaml = temp_workspace / 'agent.yaml'
        agent_yaml.write_text("""
name: "Test Agent"
""")
        
        (temp_workspace / 'agent.py').write_text(valid_agent_py)
        
        with pytest.raises(InvalidConfigError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'objective' in str(exc_info.value)
    
    def test_invalid_temperature(self, temp_workspace, valid_agent_py):
        """Test error when temperature out of range."""
        agent_yaml = temp_workspace / 'agent.yaml'
        agent_yaml.write_text("""
name: "Test Agent"
objective: "Test"

config:
  temperature: 2.0  # Invalid - must be 0.0-1.0
""")
        
        (temp_workspace / 'agent.py').write_text(valid_agent_py)
        
        with pytest.raises(InvalidConfigError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'temperature' in str(exc_info.value)


# ============================================================================
# WORKSPACE LOADING TESTS
# ============================================================================

class TestWorkspaceLoading:
    """Test complete workspace loading."""
    
    def test_load_valid_workspace(self, temp_workspace, valid_agent_py, valid_agent_yaml):
        """Test loading a valid workspace."""
        (temp_workspace / 'agent.py').write_text(valid_agent_py)
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        workspace = load_user_workspace(temp_workspace)
        
        assert workspace.planner_class_name == 'TestPlanner'
        assert workspace.agent_definition.name == 'Test Agent'
        assert workspace.agent_definition.objective == 'Test agent for unit tests'
        assert workspace.agent_config.model == 'gpt-4o-mini'
        assert workspace.agent_config.temperature == 0.3
        assert workspace.agent_config.max_steps == 10
    
    def test_missing_agent_py(self, temp_workspace, valid_agent_yaml):
        """Test error when agent.py missing."""
        (temp_workspace / 'agent.yaml').write_text(valid_agent_yaml)
        
        with pytest.raises(WorkspaceValidationError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'agent.py' in str(exc_info.value)
    
    def test_missing_agent_yaml(self, temp_workspace, valid_agent_py):
        """Test error when agent.yaml missing."""
        (temp_workspace / 'agent.py').write_text(valid_agent_py)
        
        with pytest.raises(WorkspaceValidationError) as exc_info:
            load_user_workspace(temp_workspace)
        
        assert 'agent.yaml' in str(exc_info.value)
    
    def test_nonexistent_workspace(self):
        """Test error when workspace doesn't exist."""
        with pytest.raises(WorkspaceValidationError) as exc_info:
            load_user_workspace('/nonexistent/path')
        
        assert 'not found' in str(exc_info.value)


# ============================================================================
# INTEGRATION TESTS
# ============================================================================

class TestIntegration:
    """Integration tests using example workspaces."""
    
    def test_load_priority_planner_example(self):
        """Test loading the priority planner example."""
        example_path = Path(__file__).parent.parent / 'examples' / 'priority_planner'
        
        if not example_path.exists():
            pytest.skip("Example workspace not found")
        
        workspace = load_user_workspace(example_path)
        
        assert workspace.planner_class_name == 'PriorityPlanner'
        assert 'Priority' in workspace.agent_definition.name
        assert len(workspace.agent_definition.allowed_tools) > 0
    
    def test_load_conditional_planner_example(self):
        """Test loading the conditional planner example."""
        example_path = Path(__file__).parent.parent / 'examples' / 'conditional_planner'
        
        if not example_path.exists():
            pytest.skip("Example workspace not found")
        
        workspace = load_user_workspace(example_path)
        
        assert workspace.planner_class_name == 'ConditionalPlanner'
        assert 'Conditional' in workspace.agent_definition.name
    
    def test_reject_invalid_security_example(self):
        """Test that invalid security example is rejected."""
        example_path = Path(__file__).parent.parent / 'examples' / 'invalid_security'
        
        if not example_path.exists():
            pytest.skip("Example workspace not found")
        
        with pytest.raises(SecurityViolation):
            load_user_workspace(example_path)
