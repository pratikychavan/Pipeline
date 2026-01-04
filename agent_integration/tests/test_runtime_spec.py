"""
Tests for Runtime Spec Builder

Tests the materialization of pipelines into immutable runtime specs.
"""

import json
from django.test import TestCase
from django.contrib.auth.models import User

from core.models import Pipeline, Node, PipelineExecution
from agent_integration.models import AgentRun, RuntimeSpec
from agent_integration.control_plane_models import (
    AgentProfile,
    BusinessCondition,
    AgentConditionBinding,
)
from agent_integration.runtime_spec_builder import (
    RuntimeSpecBuilder,
    RuntimeSpecService,
)


class RuntimeSpecBuilderTests(TestCase):
    """Test RuntimeSpecBuilder"""
    
    def setUp(self):
        """Create test fixtures"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        
        # Create pipeline
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            description='Test pipeline for spec building',
            created_by=self.user,
            global_arguments=['input_file', 'output_dir'],
        )
        
        # Create nodes
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='load_data',
            description='Load input data',
            code='# Load data',
            order=1,
            position_x=100,
            position_y=100,
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='process_data',
            description='Process loaded data',
            code='# Process data',
            order=2,
            position_x=300,
            position_y=100,
            input_variable_mappings={
                'input_data': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'data',
                }
            },
        )
        
        # Create agent profile
        self.agent_profile = AgentProfile.objects.create(
            name='Test Agent',
            description='Test agent profile',
            status='active',
            max_steps=50,
            retry_policy={'max_retries': 3, 'backoff_multiplier': 2},
            guardrail_config={'max_cost_usd': 10.0, 'max_execution_time_seconds': 300},
            llm_config={'model': 'gpt-4', 'temperature': 0.7},
        )
    
    def test_build_basic_spec(self):
        """Test building basic runtime spec without agent profile"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        # Verify structure
        self.assertIn('version', spec)
        self.assertIn('pipeline', spec)
        self.assertIn('available_tools', spec)
        self.assertIn('execution_constraints', spec)
        self.assertIn('business_conditions', spec)
        self.assertIn('agent_configuration', spec)
        self.assertIn('global_context', spec)
        
        # Verify pipeline metadata
        self.assertEqual(spec['pipeline']['name'], 'Test Pipeline')
        self.assertEqual(spec['pipeline']['global_arguments'], ['input_file', 'output_dir'])
        
        # Verify tools
        self.assertEqual(len(spec['available_tools']), 2)
        tool1 = spec['available_tools'][0]
        self.assertEqual(tool1['tool_name'], 'load_data')
        self.assertEqual(tool1['tool_type'], 'pipeline_node')
        
        # Verify no executable code in spec
        spec_json = json.dumps(spec)
        self.assertNotIn('# Load data', spec_json)
        self.assertNotIn('code', spec_json)
    
    def test_build_spec_with_agent_profile(self):
        """Test building spec with agent profile"""
        builder = RuntimeSpecBuilder(self.pipeline, self.agent_profile)
        spec = builder.build()
        
        # Verify agent config included
        agent_config = spec['agent_configuration']
        self.assertEqual(agent_config['agent_name'], 'Test Agent')
        self.assertEqual(agent_config['max_steps'], 50)
        self.assertIn('retry_policy', agent_config)
        self.assertIn('guardrails', agent_config)
        
        # Verify LLM config NOT included
        self.assertNotIn('llm_config', agent_config)
        self.assertNotIn('model', json.dumps(agent_config))
        self.assertNotIn('temperature', json.dumps(agent_config))
    
    def test_build_tools(self):
        """Test tool building from nodes"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        tools = spec['available_tools']
        self.assertEqual(len(tools), 2)
        
        # Check first tool
        tool1 = tools[0]
        self.assertEqual(tool1['tool_name'], 'load_data')
        self.assertEqual(tool1['order'], 1)
        self.assertEqual(tool1['input_variables'], [])
        self.assertIn('position', tool1)
        
        # Check second tool
        tool2 = tools[1]
        self.assertEqual(tool2['tool_name'], 'process_data')
        self.assertEqual(tool2['order'], 2)
        self.assertIn('input_data', tool2['input_variables'])
        self.assertIn('input_mappings', tool2)
    
    def test_build_constraints(self):
        """Test execution constraints building"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        constraints = spec['execution_constraints']
        
        # Check DAG structure
        self.assertIn('dag', constraints)
        dag = constraints['dag']
        self.assertIn('nodes', dag)
        self.assertIn('dependencies', dag)
        
        # Check dependencies
        dependencies = dag['dependencies']
        self.assertEqual(len(dependencies), 2)
        
        # node2 should depend on node1
        node2_deps = dependencies[str(self.node2.id)]
        self.assertIn(str(self.node1.id), node2_deps['depends_on'])
        
        # node1 should be required for node2
        node1_deps = dependencies[str(self.node1.id)]
        self.assertIn(str(self.node2.id), node1_deps['required_for'])
    
    def test_build_conditions(self):
        """Test business conditions building"""
        # Create condition
        condition = BusinessCondition.objects.create(
            name='test_condition',
            description='Test condition',
            condition_type='threshold',
            version='1.0',
            is_active=True,
            condition_config={'threshold': 100},
        )
        
        # Bind to agent
        AgentConditionBinding.objects.create(
            agent=self.agent_profile,
            condition=condition,
            evaluation_point='before_execution',
            on_true_action='proceed',
            on_false_action='abort',
            priority=100,
            is_enabled=True,
            parameters={'strict': True},
        )
        
        # Build spec
        builder = RuntimeSpecBuilder(self.pipeline, self.agent_profile)
        spec = builder.build()
        
        # Verify conditions included
        conditions = spec['business_conditions']
        self.assertEqual(len(conditions), 1)
        
        cond = conditions[0]
        self.assertEqual(cond['condition_name'], 'test_condition')
        self.assertEqual(cond['condition_type'], 'threshold')
        self.assertEqual(cond['evaluation_point'], 'before_execution')
        self.assertEqual(cond['on_true_action'], 'proceed')
        self.assertEqual(cond['config']['threshold'], 100)
    
    def test_compute_checksum(self):
        """Test checksum computation"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        checksum1 = builder.compute_checksum(spec)
        self.assertEqual(len(checksum1), 64)  # SHA256 hex length
        
        # Same spec should produce same checksum
        checksum2 = builder.compute_checksum(spec)
        self.assertEqual(checksum1, checksum2)
        
        # Modified spec should produce different checksum
        spec_modified = spec.copy()
        spec_modified['pipeline']['name'] = 'Modified'
        checksum3 = builder.compute_checksum(spec_modified)
        self.assertNotEqual(checksum1, checksum3)
    
    def test_validate_spec(self):
        """Test spec validation"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        # Valid spec
        is_valid, error = builder.validate_spec(spec)
        self.assertTrue(is_valid)
        self.assertIsNone(error)
        
        # Missing required key
        invalid_spec = spec.copy()
        del invalid_spec['pipeline']
        is_valid, error = builder.validate_spec(invalid_spec)
        self.assertFalse(is_valid)
        self.assertIn('pipeline', error)
        
        # Invalid tools type
        invalid_spec = spec.copy()
        invalid_spec['available_tools'] = "not a list"
        is_valid, error = builder.validate_spec(invalid_spec)
        self.assertFalse(is_valid)
        self.assertIn('list', error)
    
    def test_spec_contains_no_code(self):
        """Test that spec contains no executable code"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        spec_json = json.dumps(spec)
        
        # Should not contain node code
        self.assertNotIn('# Load data', spec_json)
        self.assertNotIn('# Process data', spec_json)
        
        # Should not contain dangerous patterns
        self.assertNotIn('exec(', spec_json)
        self.assertNotIn('eval(', spec_json)
        self.assertNotIn('__import__', spec_json)
    
    def test_to_json(self):
        """Test JSON serialization"""
        builder = RuntimeSpecBuilder(self.pipeline)
        json_str = builder.to_json()
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertIn('version', parsed)
        self.assertIn('pipeline', parsed)
        
        # Should be pretty-printed
        self.assertIn('\n', json_str)
        self.assertIn('  ', json_str)


class RuntimeSpecServiceTests(TestCase):
    """Test RuntimeSpecService"""
    
    def setUp(self):
        """Create test fixtures"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        
        self.pipeline = Pipeline.objects.create(
            name='Service Test Pipeline',
            created_by=self.user,
        )
        
        self.node = Node.objects.create(
            pipeline=self.pipeline,
            name='test_node',
            code='# Test',
            order=1,
        )
        
        self.pipeline_exec = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
            status='running',
        )
        
        self.agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_exec,
            status='initializing',
        )
    
    def test_create_spec_for_agent_run(self):
        """Test creating and storing spec for agent run"""
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(self.agent_run)
        
        # Verify created
        self.assertIsNotNone(runtime_spec)
        self.assertEqual(runtime_spec.agent_run, self.agent_run)
        self.assertEqual(runtime_spec.spec_version, RuntimeSpecBuilder.SPEC_VERSION)
        self.assertIsNotNone(runtime_spec.spec_checksum)
        
        # Verify spec data
        spec_data = runtime_spec.spec_data
        self.assertIn('version', spec_data)
        self.assertIn('pipeline', spec_data)
        self.assertEqual(spec_data['pipeline']['name'], 'Service Test Pipeline')
    
    def test_get_spec_for_agent_run(self):
        """Test retrieving spec for agent run"""
        # Create spec
        created_spec = RuntimeSpecService.create_spec_for_agent_run(self.agent_run)
        
        # Retrieve it
        retrieved_spec = RuntimeSpecService.get_spec_for_agent_run(self.agent_run.id)
        
        self.assertIsNotNone(retrieved_spec)
        self.assertEqual(retrieved_spec.id, created_spec.id)
        self.assertEqual(retrieved_spec.spec_checksum, created_spec.spec_checksum)
    
    def test_verify_spec_integrity(self):
        """Test spec integrity verification"""
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(self.agent_run)
        
        # Should be valid
        is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
        self.assertTrue(is_valid)
        
        # Tamper with spec
        runtime_spec.spec_data['pipeline']['name'] = 'Tampered'
        runtime_spec.save()
        
        # Should now be invalid
        is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
        self.assertFalse(is_valid)
    
    def test_export_spec_to_json(self):
        """Test exporting spec to JSON"""
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(self.agent_run)
        
        json_str = RuntimeSpecService.export_spec_to_json(runtime_spec)
        
        # Should be valid JSON
        parsed = json.loads(json_str)
        self.assertEqual(parsed['pipeline']['name'], 'Service Test Pipeline')
    
    def test_preview_spec_for_pipeline(self):
        """Test previewing spec without creating AgentRun"""
        spec = RuntimeSpecService.preview_spec_for_pipeline(self.pipeline)
        
        # Should have spec structure
        self.assertIn('version', spec)
        self.assertIn('pipeline', spec)
        self.assertIn('available_tools', spec)
        
        # Should match pipeline
        self.assertEqual(spec['pipeline']['name'], 'Service Test Pipeline')
        self.assertEqual(len(spec['available_tools']), 1)


class RuntimeSpecImmutabilityTests(TestCase):
    """Test spec immutability guarantees"""
    
    def setUp(self):
        """Create test fixtures"""
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.pipeline = Pipeline.objects.create(
            name='Immutable Test',
            created_by=self.user,
        )
        Node.objects.create(
            pipeline=self.pipeline,
            name='node1',
            code='# Code',
            order=1,
        )
    
    def test_spec_is_json_serializable(self):
        """Test that spec is fully JSON-serializable"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        # Should serialize without error
        json_str = json.dumps(spec)
        
        # Should deserialize to equivalent structure
        parsed = json.loads(json_str)
        self.assertEqual(parsed['version'], spec['version'])
        self.assertEqual(parsed['pipeline']['name'], spec['pipeline']['name'])
    
    def test_spec_contains_no_runtime_state(self):
        """Test that spec contains no runtime state"""
        builder = RuntimeSpecBuilder(self.pipeline)
        spec = builder.build()
        
        spec_json = json.dumps(spec)
        
        # Should not contain runtime state keywords
        runtime_keywords = ['status', 'current_step', 'execution_id']
        for keyword in runtime_keywords:
            # These keywords might appear in descriptions, but not as keys
            self.assertNotIn(f'"{keyword}":', spec_json)
    
    def test_spec_checksum_stable(self):
        """Test that checksum is stable for identical specs"""
        builder1 = RuntimeSpecBuilder(self.pipeline)
        spec1 = builder1.build()
        checksum1 = builder1.compute_checksum(spec1)
        
        # Build again
        builder2 = RuntimeSpecBuilder(self.pipeline)
        spec2 = builder2.build()
        checksum2 = builder2.compute_checksum(spec2)
        
        # Checksums should match
        self.assertEqual(checksum1, checksum2)
    
    def test_spec_immutable_after_creation(self):
        """Test that stored spec can be verified for tampering"""
        pipeline_exec = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
            status='running',
        )
        agent_run = AgentRun.objects.create(
            pipeline_execution=pipeline_exec,
            status='initializing',
        )
        
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
        original_checksum = runtime_spec.spec_checksum
        
        # Verify it's valid
        self.assertTrue(RuntimeSpecService.verify_spec_integrity(runtime_spec))
        
        # Modify spec data
        runtime_spec.spec_data['pipeline']['name'] = 'Modified'
        
        # Checksum should not match anymore
        self.assertFalse(RuntimeSpecService.verify_spec_integrity(runtime_spec))
        
        # Original checksum unchanged
        self.assertEqual(runtime_spec.spec_checksum, original_checksum)


if __name__ == '__main__':
    import django
    django.setup()
    from django.test.utils import get_runner
    from django.conf import settings
    
    TestRunner = get_runner(settings)
    test_runner = TestRunner()
    failures = test_runner.run_tests(['agent_integration.tests.test_runtime_spec'])
