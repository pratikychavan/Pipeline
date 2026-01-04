"""
Test suite for agent integration.

Run: python manage.py test agent_integration
"""

from django.test import TestCase
from django.contrib.auth.models import User
from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentRun, AgentDecision, RuntimeSpec
from agent_integration.runtime import RuntimeSpecBuilder, start_agent_execution
from agent_integration.guardrails import GuardrailEngine, ExecutionState
from agent_integration.tools import ToolRegistry, NodeToolWrapper


class RuntimeSpecBuilderTest(TestCase):
    """Test runtime specification building."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            description='Test',
            created_by=self.user,
            global_arguments=['x', 'y']
        )
        
        # Create nodes
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='result = x + 1',
            order=1
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 2',
            code='result = y + 2',
            order=2,
            input_variable_mappings={
                'input_val': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'result'
                }
            }
        )
    
    def test_build_spec(self):
        """Test building runtime spec from pipeline."""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build_spec()
        
        # Verify structure
        self.assertEqual(spec['spec_version'], '1.0')
        self.assertEqual(spec['pipeline_id'], str(self.pipeline.id))
        self.assertEqual(len(spec['available_tools']), 2)
        
        # Verify tools
        tool_names = [t['tool_name'] for t in spec['available_tools']]
        self.assertIn('Node 1', tool_names)
        self.assertIn('Node 2', tool_names)
        
        # Verify constraints
        constraints = spec['execution_constraints']
        self.assertGreater(len(constraints), 0)
        
        # Verify dependency constraint exists
        dep_constraints = [c for c in constraints if c['constraint_type'] == 'dependency']
        self.assertGreater(len(dep_constraints), 0)
    
    def test_spec_checksum(self):
        """Test checksum computation."""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build_spec()
        checksum = builder.compute_checksum(spec)
        
        self.assertEqual(len(checksum), 64)  # SHA256 hex
        
        # Same spec = same checksum
        checksum2 = builder.compute_checksum(spec)
        self.assertEqual(checksum, checksum2)


class GuardrailEngineTest(TestCase):
    """Test guardrail enforcement."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user
        )
        
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='x = 1',
            order=1
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 2',
            code='y = x + 1',
            order=2,
            input_variable_mappings={
                'x': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'x'
                }
            }
        )
        
        # Build spec
        builder = RuntimeSpecBuilder(self.pipeline)
        self.spec = builder.build_spec()
        self.guardrails = GuardrailEngine(self.spec)
    
    def test_available_nodes_initially(self):
        """Test getting available nodes at start."""
        available = self.guardrails.get_safe_choices()
        
        # Only node1 should be available (node2 depends on it)
        self.assertEqual(len(available), 1)
        self.assertEqual(available[0], str(self.node1.id))
    
    def test_dependency_satisfaction(self):
        """Test dependency checking."""
        # Node 2 should not be available initially
        is_valid, violations = self.guardrails.validate_before_execution(
            str(self.node2.id), 0, 0
        )
        
        self.assertFalse(is_valid)
        self.assertGreater(len(violations), 0)
        self.assertTrue(
            any('unsatisfied_dependencies' in v.violation_type for v in violations)
        )
    
    def test_execution_order(self):
        """Test execution order enforcement."""
        # Execute node1
        self.guardrails.record_execution_result(str(self.node1.id), True)
        
        # Now node2 should be available
        available = self.guardrails.get_safe_choices()
        self.assertIn(str(self.node2.id), available)
        
        # And node2 should be valid
        is_valid, violations = self.guardrails.validate_before_execution(
            str(self.node2.id), 1, 0
        )
        self.assertTrue(is_valid)
    
    def test_prevent_duplicate_execution(self):
        """Test that nodes can't be executed twice."""
        # Execute node1
        self.guardrails.record_execution_result(str(self.node1.id), True)
        
        # Try to execute again
        is_valid, violations = self.guardrails.validate_before_execution(
            str(self.node1.id), 1, 0
        )
        
        self.assertFalse(is_valid)
        self.assertTrue(
            any('already_executed' in v.violation_type for v in violations)
        )
    
    def test_max_iterations(self):
        """Test max iteration limit."""
        is_valid, violations = self.guardrails.validate_before_execution(
            str(self.node1.id), 999, 0
        )
        
        self.assertFalse(is_valid)
        self.assertTrue(
            any('max_iterations' in v.violation_type for v in violations)
        )
    
    def test_completion_detection(self):
        """Test completion detection."""
        # Initially not complete
        self.assertFalse(self.guardrails.graph_guardrails.state.is_complete())
        
        # Execute both nodes
        self.guardrails.record_execution_result(str(self.node1.id), True)
        self.guardrails.record_execution_result(str(self.node2.id), True)
        
        # Now complete
        self.assertTrue(self.guardrails.graph_guardrails.state.is_complete())


class ToolRegistryTest(TestCase):
    """Test tool registry."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user
        )
        
        self.node = Node.objects.create(
            pipeline=self.pipeline,
            name='Test Node',
            description='Test Description',
            code='x = 1 + 1',
            order=1
        )
    
    def test_registry_initialization(self):
        """Test registry loads all nodes."""
        registry = ToolRegistry(self.pipeline)
        tools = registry.get_all_tools()
        
        self.assertEqual(len(tools), 1)
        self.assertIsInstance(tools[0], NodeToolWrapper)
    
    def test_tool_definition(self):
        """Test tool definition conversion."""
        registry = ToolRegistry(self.pipeline)
        definitions = registry.get_tool_definitions()
        
        self.assertEqual(len(definitions), 1)
        definition = definitions[0]
        
        self.assertEqual(definition.tool_id, str(self.node.id))
        self.assertEqual(definition.tool_name, 'Test Node')
        self.assertEqual(definition.description, 'Test Description')
    
    def test_tool_lookup(self):
        """Test tool lookup by ID."""
        registry = ToolRegistry(self.pipeline)
        
        tool = registry.get_tool(str(self.node.id))
        self.assertIsNotNone(tool)
        
        invalid = registry.get_tool('invalid-id')
        self.assertIsNone(invalid)


class AgentExecutionTest(TestCase):
    """Test full agent execution flow."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
            global_arguments=['input_value']
        )
        
        # Simple linear pipeline
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Add One',
            code='''
# Simple node that adds 1
result = input_value + 1
''',
            order=1,
            input_variable_mappings={
                'input_value': {
                    'node_id': '__pipeline__',
                    'source_variable': 'input_value'
                }
            }
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Multiply Two',
            code='''
# Simple node that multiplies by 2
result = prev_result * 2
''',
            order=2,
            input_variable_mappings={
                'prev_result': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'result'
                }
            }
        )
    
    def test_agent_execution(self):
        """Test complete agent-driven execution."""
        # Create execution
        execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
            context_data={'input_value': 10}
        )
        
        # Start agent
        result = start_agent_execution(execution)
        
        # Verify completion
        self.assertEqual(result['status'], 'completed')
        
        # Verify agent run created
        agent_run = AgentRun.objects.get(pipeline_execution=execution)
        self.assertEqual(agent_run.status, 'completed')
        
        # Verify decisions recorded
        decisions = AgentDecision.objects.filter(agent_run=agent_run)
        self.assertGreater(decisions.count(), 0)
        
        # Verify both nodes executed
        from agent_integration.models import ToolExecution
        tool_executions = ToolExecution.objects.filter(agent_run=agent_run)
        self.assertEqual(tool_executions.count(), 2)


class HumanInterventionTest(TestCase):
    """Test human-in-the-loop functionality."""
    
    def setUp(self):
        self.user = User.objects.create_user('testuser', 'test@test.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user
        )
    
    def test_intervention_request(self):
        """Test requesting human intervention."""
        execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user
        )
        
        agent_run = AgentRun.objects.create(
            pipeline_execution=execution,
            status='waiting_for_human',
            human_intervention_required=True,
            human_intervention_reason='Test reason'
        )
        
        self.assertTrue(agent_run.human_intervention_required)
        self.assertEqual(agent_run.status, 'waiting_for_human')
    
    def test_intervention_response(self):
        """Test responding to intervention."""
        execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user
        )
        
        agent_run = AgentRun.objects.create(
            pipeline_execution=execution,
            status='waiting_for_human',
            human_intervention_required=True
        )
        
        # Record response
        agent_run.human_intervention_response = {'action': 'continue'}
        agent_run.human_intervention_required = False
        agent_run.status = 'executing'
        agent_run.save()
        
        self.assertFalse(agent_run.human_intervention_required)
        self.assertEqual(agent_run.status, 'executing')
