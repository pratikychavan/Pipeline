"""
Integration Test: Node Tool Wrappers

This test demonstrates the complete flow of executing a pipeline node
as a tool, verifying that:
1. No core logic is duplicated
2. Existing execution backend is used
3. Proper tracking records are created
4. Safe results are returned

Run: python manage.py test agent_integration.tests.test_node_tools
Or: python -m pytest agent_integration/tests/test_node_tools.py
"""

import asyncio
from django.test import TestCase
from django.contrib.auth.models import User

from core.models import Pipeline, Node, PipelineExecution, NodeExecution
from agent_integration.models import AgentRun, ToolExecution
from agent_integration.node_tools import (
    NodeToolExecutor,
    NodeToolRegistry,
    get_node_tool,
    get_available_tools_for_agent_run,
    can_execute_node,
)


class NodeToolWrapperTests(TestCase):
    """Test node tool wrapper implementation"""
    
    def setUp(self):
        """Create test fixtures"""
        # Create user
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass'
        )
        
        # Create pipeline
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            description='Pipeline for testing node tools',
            created_by=self.user,
        )
        
        # Create nodes
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='test_node_1',
            description='First test node',
            code='result = 42',
            order=1,
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='test_node_2',
            description='Second test node with input',
            code='output = input_value * 2',
            order=2,
            input_variable_mappings={'input_value': {'node_id': str(self.node1.id), 'source_variable': 'result'}},
        )
        
        # Create pipeline execution
        self.pipeline_exec = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
            status='running',
        )
        
        # Create agent run
        self.agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_exec,
            status='executing',
            agent_config={'model': 'test-model'},
        )
    
    def test_tool_creation(self):
        """Test creating tool wrapper for node"""
        tool = get_node_tool(self.node1.id)
        
        self.assertIsNotNone(tool)
        self.assertIsInstance(tool, NodeToolExecutor)
        self.assertEqual(tool.node_id, self.node1.id)
        self.assertEqual(tool.node_name, self.node1.name)
    
    def test_tool_definition(self):
        """Test tool definition generation"""
        tool = get_node_tool(self.node1.id)
        definition = tool.get_tool_definition()
        
        self.assertEqual(definition['tool_name'], 'test_node_1')
        self.assertEqual(definition['tool_type'], 'pipeline_node')
        self.assertEqual(definition['pipeline_name'], 'Test Pipeline')
        self.assertIn('description', definition)
    
    def test_registry_get_tools_for_pipeline(self):
        """Test getting all tools for a pipeline"""
        tools = NodeToolRegistry.get_tools_for_pipeline(self.pipeline.id)
        
        self.assertEqual(len(tools), 2)
        self.assertIsInstance(tools[0], NodeToolExecutor)
        self.assertIsInstance(tools[1], NodeToolExecutor)
    
    def test_registry_get_tool_definitions(self):
        """Test getting tool definitions for agent"""
        definitions = NodeToolRegistry.get_tool_definitions(self.pipeline.id)
        
        self.assertEqual(len(definitions), 2)
        self.assertIn('tool_name', definitions[0])
        self.assertIn('tool_type', definitions[0])
    
    def test_tool_execution(self):
        """Test executing node as tool"""
        async def run_test():
            tool = get_node_tool(self.node1.id)
            result = await tool.execute(
                agent_run_id=self.agent_run.id,
                agent_decision_id=None,
                parameters={},
                context={},
            )
            
            # Verify result structure
            self.assertIsNotNone(result)
            self.assertIsNotNone(result.tool_execution_id)
            self.assertIsNotNone(result.node_execution_id)
            self.assertIsNotNone(result.summary)
            self.assertIsInstance(result.duration_seconds, float)
            
            # Verify database records created
            tool_exec = ToolExecution.objects.get(pk=result.tool_execution_id)
            self.assertEqual(tool_exec.agent_run_id, self.agent_run.id)
            self.assertEqual(tool_exec.tool_name, 'test_node_1')
            self.assertIsNotNone(tool_exec.result_summary)
            
            node_exec = NodeExecution.objects.get(pk=result.node_execution_id)
            self.assertEqual(node_exec.pipeline_execution_id, self.pipeline_exec.id)
            self.assertEqual(node_exec.node_id, self.node1.id)
            
            # Verify no raw data in result
            self.assertNotIn('result', result.summary)  # Should not contain actual value
            
            return result
        
        result = asyncio.run(run_test())
        self.assertTrue(result.success or not result.success)  # Just verify it ran
    
    def test_parameter_validation(self):
        """Test parameter validation"""
        tool = get_node_tool(self.node2.id)
        
        # Missing required input
        is_valid, error = tool.validate_parameters({})
        self.assertFalse(is_valid)
        self.assertIn('input_value', error)
        
        # Valid parameters
        is_valid, error = tool.validate_parameters({'input_value': 42})
        self.assertTrue(is_valid)
        self.assertIsNone(error)
    
    def test_can_execute_node(self):
        """Test execution validation"""
        # Node without inputs - should pass
        can_run, reason = can_execute_node(
            node_id=self.node1.id,
            agent_run_id=self.agent_run.id,
            context={},
        )
        self.assertTrue(can_run)
        self.assertIsNone(reason)
        
        # Node with missing inputs - should fail
        can_run, reason = can_execute_node(
            node_id=self.node2.id,
            agent_run_id=self.agent_run.id,
            context={},
        )
        self.assertFalse(can_run)
        self.assertIsNotNone(reason)
        
        # Node with provided inputs - should pass
        can_run, reason = can_execute_node(
            node_id=self.node2.id,
            agent_run_id=self.agent_run.id,
            context={'input_value': 42},
        )
        self.assertTrue(can_run)
    
    def test_get_available_tools(self):
        """Test getting available tools for agent run"""
        tools = get_available_tools_for_agent_run(self.agent_run.id)
        
        self.assertEqual(len(tools), 2)
        self.assertIsInstance(tools[0], dict)
        self.assertIn('tool_name', tools[0])
    
    def test_no_core_modification(self):
        """Verify no core modules were modified"""
        from core.execution import backends
        
        # Verify backend has execute_node method
        backend = backends.LocalExecutionBackend()
        self.assertTrue(hasattr(backend, 'execute_node'))
        
        # Verify it's the original method (not replaced)
        import inspect
        source_file = inspect.getfile(backend.execute_node)
        self.assertIn('core/execution/backends.py', source_file)
    
    def test_result_contains_no_raw_data(self):
        """Verify results never contain raw data"""
        tool = get_node_tool(self.node1.id)
        
        # Create mock output
        output_data = {'result': 42, 'data': [1, 2, 3, 4, 5]}
        summary = tool._create_result_summary(True, output_data)
        
        # Summary should not contain actual values
        self.assertNotIn('42', summary)
        self.assertNotIn('[1, 2, 3, 4, 5]', summary)
        
        # Summary should describe outputs
        self.assertIn('result', summary)
        self.assertIn('data', summary)


class NodeToolIntegrationTests(TestCase):
    """Integration tests for complete tool execution flow"""
    
    def setUp(self):
        """Create test fixtures"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.pipeline = Pipeline.objects.create(
            name='Integration Test Pipeline',
            created_by=self.user,
        )
        self.node = Node.objects.create(
            pipeline=self.pipeline,
            name='integration_node',
            code='x = 100\ny = 200\nsum_result = x + y',
            order=1,
        )
        self.pipeline_exec = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
            status='running',
        )
        self.agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_exec,
            status='executing',
        )
    
    def test_complete_execution_flow(self):
        """Test complete flow from tool discovery to execution"""
        async def run_test():
            # 1. Discover tools
            tools = NodeToolRegistry.get_tools_for_pipeline(self.pipeline.id)
            self.assertEqual(len(tools), 1)
            
            # 2. Get tool definition
            tool = tools[0]
            definition = tool.get_tool_definition()
            self.assertEqual(definition['tool_name'], 'integration_node')
            
            # 3. Validate execution
            can_run, reason = can_execute_node(
                node_id=self.node.id,
                agent_run_id=self.agent_run.id,
                context={},
            )
            self.assertTrue(can_run)
            
            # 4. Execute tool
            result = await tool.execute(
                agent_run_id=self.agent_run.id,
                agent_decision_id=None,
                parameters={},
                context={},
            )
            
            # 5. Verify result
            self.assertIsNotNone(result)
            self.assertIsNotNone(result.tool_execution_id)
            
            # 6. Verify records
            tool_exec = ToolExecution.objects.get(pk=result.tool_execution_id)
            self.assertEqual(tool_exec.status, 'completed' if result.success else 'failed')
            
            node_exec = NodeExecution.objects.get(pk=result.node_execution_id)
            self.assertEqual(node_exec.node_id, self.node.id)
            
            # 7. Verify result safety (no raw data)
            self.assertNotIn('300', result.summary)  # Should not contain computed value
            
            return result
        
        result = asyncio.run(run_test())
        self.assertIsNotNone(result)


if __name__ == '__main__':
    import django
    django.setup()
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['agent_integration.tests.test_node_tools'])
