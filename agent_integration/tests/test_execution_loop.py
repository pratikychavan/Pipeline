"""
Tests for Agent Execution Loop

Comprehensive test suite for the agent execution loop.
"""

from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from unittest.mock import Mock, patch, AsyncMock
import asyncio

from core.models import Pipeline, Node, PipelineExecution, NodeExecution
from agent_integration.models import AgentRun, AgentDecision, ToolExecution, RuntimeSpec
from agent_integration.control_plane_models import AgentProfile, BusinessCondition
from agent_integration.runtime_spec_builder import RuntimeSpecService
from agent_integration.execution_loop import (
    AgentExecutionLoop,
    AgentLoopRunner,
    DeterministicPlanner,
    Planner,
    PlannerDecision,
    PlannerDecisionType,
    Guardrails,
    GuardrailViolation,
    ConditionEvaluator,
    LoopTerminationReason,
)
from agent_integration.node_tools import NodeToolResult


class PlannerTests(TestCase):
    """Tests for Planner interface and implementations."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
        )
        
        # Create nodes
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='print("Node 1")',
            order=1,
        )
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 2',
            code='print("Node 2")',
            order=2,
            input_variable_mappings={
                'input1': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'output1',
                }
            }
        )
    
    def test_deterministic_planner_basic(self):
        """Test deterministic planner basic functionality."""
        planner = DeterministicPlanner()
        
        # Create runtime spec
        runtime_spec = {
            'available_tools': [
                {
                    'tool_id': str(self.node1.id),
                    'tool_name': 'Node 1',
                    'agent_constraints': {'is_allowed': True},
                },
                {
                    'tool_id': str(self.node2.id),
                    'tool_name': 'Node 2',
                    'agent_constraints': {'is_allowed': True},
                },
            ],
            'execution_constraints': {
                'dag': {
                    'dependencies': {
                        str(self.node2.id): {
                            'depends_on': [str(self.node1.id)],
                        }
                    }
                }
            }
        }
        
        # Plan with no history - should execute node1
        decision = asyncio.run(planner.plan_next_action(
            runtime_spec=runtime_spec,
            execution_history=[],
            current_state={},
        ))
        
        self.assertEqual(decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(decision.tool_id, str(self.node1.id))
    
    def test_deterministic_planner_respects_dependencies(self):
        """Test that deterministic planner respects dependencies."""
        planner = DeterministicPlanner()
        
        runtime_spec = {
            'available_tools': [
                {
                    'tool_id': str(self.node1.id),
                    'tool_name': 'Node 1',
                    'agent_constraints': {'is_allowed': True},
                },
                {
                    'tool_id': str(self.node2.id),
                    'tool_name': 'Node 2',
                    'agent_constraints': {'is_allowed': True},
                },
            ],
            'execution_constraints': {
                'dag': {
                    'dependencies': {
                        str(self.node2.id): {
                            'depends_on': [str(self.node1.id)],
                        }
                    }
                }
            }
        }
        
        # Plan with node1 completed
        execution_history = [
            {
                'tool_id': str(self.node1.id),
                'success': True,
            }
        ]
        
        decision = asyncio.run(planner.plan_next_action(
            runtime_spec=runtime_spec,
            execution_history=execution_history,
            current_state={},
        ))
        
        # Should now execute node2
        self.assertEqual(decision.decision_type, PlannerDecisionType.EXECUTE_TOOL)
        self.assertEqual(decision.tool_id, str(self.node2.id))
    
    def test_deterministic_planner_completes_when_done(self):
        """Test that planner completes when all tools executed."""
        planner = DeterministicPlanner()
        
        runtime_spec = {
            'available_tools': [
                {
                    'tool_id': str(self.node1.id),
                    'tool_name': 'Node 1',
                    'agent_constraints': {'is_allowed': True},
                },
            ],
            'execution_constraints': {
                'dag': {
                    'dependencies': {}
                }
            }
        }
        
        # All tools executed
        execution_history = [
            {
                'tool_id': str(self.node1.id),
                'success': True,
            }
        ]
        
        decision = asyncio.run(planner.plan_next_action(
            runtime_spec=runtime_spec,
            execution_history=execution_history,
            current_state={},
        ))
        
        self.assertEqual(decision.decision_type, PlannerDecisionType.COMPLETE)


class GuardrailsTests(TestCase):
    """Tests for Guardrails validation."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
        )
        
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='print("Node 1")',
            order=1,
        )
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 2',
            code='print("Node 2")',
            order=2,
            input_variable_mappings={
                'input1': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'output1',
                }
            }
        )
        
        self.runtime_spec = {
            'available_tools': [
                {
                    'tool_id': str(self.node1.id),
                    'tool_name': 'Node 1',
                    'agent_constraints': {
                        'is_allowed': True,
                        'max_calls': 2,
                    },
                },
                {
                    'tool_id': str(self.node2.id),
                    'tool_name': 'Node 2',
                    'agent_constraints': {
                        'is_allowed': False,
                    },
                },
            ],
            'execution_constraints': {
                'dag': {
                    'dependencies': {
                        str(self.node2.id): {
                            'depends_on': [str(self.node1.id)],
                        }
                    }
                }
            }
        }
    
    def test_guardrails_allows_valid_decision(self):
        """Test that guardrails allow valid decisions."""
        guardrails = Guardrails(self.runtime_spec)
        
        decision = PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=str(self.node1.id),
        )
        
        result = asyncio.run(guardrails.validate_decision(
            decision=decision,
            execution_history=[],
            current_state={},
        ))
        
        self.assertTrue(result.is_valid)
        self.assertEqual(len(result.violations), 0)
    
    def test_guardrails_blocks_disallowed_tool(self):
        """Test that guardrails block disallowed tools."""
        guardrails = Guardrails(self.runtime_spec)
        
        decision = PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=str(self.node2.id),
        )
        
        result = asyncio.run(guardrails.validate_decision(
            decision=decision,
            execution_history=[],
            current_state={},
        ))
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any('not allowed' in v.message for v in result.violations))
    
    def test_guardrails_enforces_max_calls(self):
        """Test that guardrails enforce max calls limit."""
        guardrails = Guardrails(self.runtime_spec)
        
        decision = PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=str(self.node1.id),
        )
        
        # Simulate 2 prior executions
        execution_history = [
            {'tool_id': str(self.node1.id), 'success': True},
            {'tool_id': str(self.node1.id), 'success': True},
        ]
        
        result = asyncio.run(guardrails.validate_decision(
            decision=decision,
            execution_history=execution_history,
            current_state={},
        ))
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any('max calls' in v.message.lower() for v in result.violations))
    
    def test_guardrails_checks_dependencies(self):
        """Test that guardrails check dependencies."""
        guardrails = Guardrails(self.runtime_spec)
        
        # Try to execute node2 without node1
        decision = PlannerDecision(
            decision_type=PlannerDecisionType.EXECUTE_TOOL,
            tool_id=str(self.node2.id),
        )
        
        result = asyncio.run(guardrails.validate_decision(
            decision=decision,
            execution_history=[],
            current_state={},
        ))
        
        self.assertFalse(result.is_valid)
        self.assertTrue(any('dependencies' in v.message.lower() for v in result.violations))
    
    def test_guardrails_allows_non_tool_decisions(self):
        """Test that guardrails allow non-tool decisions."""
        guardrails = Guardrails(self.runtime_spec)
        
        decision = PlannerDecision(
            decision_type=PlannerDecisionType.COMPLETE,
        )
        
        result = asyncio.run(guardrails.validate_decision(
            decision=decision,
            execution_history=[],
            current_state={},
        ))
        
        self.assertTrue(result.is_valid)


class ConditionEvaluatorTests(TestCase):
    """Tests for ConditionEvaluator."""
    
    def test_evaluator_filters_by_evaluation_point(self):
        """Test that evaluator filters conditions by evaluation point."""
        runtime_spec = {
            'business_conditions': [
                {
                    'condition_id': '1',
                    'condition_name': 'Condition 1',
                    'condition_type': 'always_true',
                    'evaluation_point': 'before_execution',
                },
                {
                    'condition_id': '2',
                    'condition_name': 'Condition 2',
                    'condition_type': 'always_true',
                    'evaluation_point': 'after_tool_execution',
                },
            ]
        }
        
        evaluator = ConditionEvaluator(runtime_spec)
        
        results = asyncio.run(evaluator.evaluate_conditions(
            evaluation_point='before_execution',
            current_state={},
        ))
        
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['condition_id'], '1')
    
    def test_evaluator_evaluates_always_true(self):
        """Test evaluation of always_true condition."""
        runtime_spec = {
            'business_conditions': [
                {
                    'condition_id': '1',
                    'condition_name': 'Always True',
                    'condition_type': 'always_true',
                    'evaluation_point': 'before_execution',
                },
            ]
        }
        
        evaluator = ConditionEvaluator(runtime_spec)
        
        results = asyncio.run(evaluator.evaluate_conditions(
            evaluation_point='before_execution',
            current_state={},
        ))
        
        self.assertTrue(results[0]['is_true'])
    
    def test_evaluator_evaluates_variable_equals(self):
        """Test evaluation of variable_equals condition."""
        runtime_spec = {
            'business_conditions': [
                {
                    'condition_id': '1',
                    'condition_name': 'Check Variable',
                    'condition_type': 'variable_equals',
                    'config': {
                        'variable': 'status',
                        'value': 'active',
                    },
                    'evaluation_point': 'before_execution',
                },
            ]
        }
        
        evaluator = ConditionEvaluator(runtime_spec)
        
        # Test with matching value
        results = asyncio.run(evaluator.evaluate_conditions(
            evaluation_point='before_execution',
            current_state={'variables': {'status': 'active'}},
        ))
        
        self.assertTrue(results[0]['is_true'])
        
        # Test with non-matching value
        results = asyncio.run(evaluator.evaluate_conditions(
            evaluation_point='before_execution',
            current_state={'variables': {'status': 'inactive'}},
        ))
        
        self.assertFalse(results[0]['is_true'])


class ExecutionLoopTests(TransactionTestCase):
    """Tests for AgentExecutionLoop."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
        )
        
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='print("Node 1")',
            order=1,
        )
        
        self.pipeline_execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
        )
        
        self.agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_execution,
            max_steps=10,
        )
        
        # Create runtime spec
        self.runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
            agent_run=self.agent_run,
        )
    
    def test_loop_initialization(self):
        """Test loop initialization."""
        loop = AgentExecutionLoop(self.agent_run)
        
        asyncio.run(loop.initialize())
        
        self.assertIsNotNone(loop.runtime_spec)
        self.assertIsNotNone(loop.guardrails)
        self.assertIsNotNone(loop.condition_evaluator)
    
    def test_loop_requires_runtime_spec(self):
        """Test that loop requires runtime spec."""
        # Create agent run without runtime spec
        pipeline_execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
        )
        
        agent_run = AgentRun.objects.create(
            pipeline_execution=pipeline_execution,
        )
        
        loop = AgentExecutionLoop(agent_run)
        
        with self.assertRaises(ValueError):
            asyncio.run(loop.initialize())
    
    @patch('agent_integration.node_tools.executor.NodeToolExecutor.execute')
    def test_loop_executes_tools(self, mock_execute):
        """Test that loop executes tools."""
        # Mock tool execution
        mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
            success=True,
            duration=1.0,
            summary="Tool executed successfully",
        ))()
        
        loop = AgentExecutionLoop(self.agent_run, planner=DeterministicPlanner())
        
        result = asyncio.run(loop.run())
        
        self.assertTrue(result.success)
        self.assertIn(result.termination_reason, [
            LoopTerminationReason.COMPLETED,
            LoopTerminationReason.MAX_STEPS_REACHED,
        ])
    
    def test_loop_respects_max_steps(self):
        """Test that loop respects max steps."""
        # Create agent run with low max steps
        pipeline_execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
        )
        
        agent_run = AgentRun.objects.create(
            pipeline_execution=pipeline_execution,
            max_steps=1,
        )
        
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
        
        # Create planner that never completes
        class NeverCompletePlanner(Planner):
            async def plan_next_action(self, runtime_spec, execution_history, current_state):
                return PlannerDecision(
                    decision_type=PlannerDecisionType.EXECUTE_TOOL,
                    tool_id=str(self.node1.id),
                )
        
        loop = AgentExecutionLoop(agent_run, planner=NeverCompletePlanner())
        
        result = asyncio.run(loop.run())
        
        self.assertFalse(result.success)
        self.assertEqual(result.termination_reason, LoopTerminationReason.MAX_STEPS_REACHED)
    
    def test_loop_handles_human_intervention(self):
        """Test that loop handles human intervention requests."""
        class HumanRequestPlanner(Planner):
            async def plan_next_action(self, runtime_spec, execution_history, current_state):
                return PlannerDecision(
                    decision_type=PlannerDecisionType.REQUEST_HUMAN,
                    human_message="Please approve",
                )
        
        loop = AgentExecutionLoop(self.agent_run, planner=HumanRequestPlanner())
        
        result = asyncio.run(loop.run())
        
        self.assertTrue(result.success)
        self.assertEqual(result.termination_reason, LoopTerminationReason.HUMAN_INTERVENTION_REQUIRED)
        
        # Check agent run
        self.agent_run.refresh_from_db()
        self.assertTrue(self.agent_run.human_intervention_required)
        self.assertEqual(self.agent_run.status, 'waiting_for_human')
    
    def test_loop_records_decisions(self):
        """Test that loop records all decisions."""
        loop = AgentExecutionLoop(self.agent_run, planner=DeterministicPlanner())
        
        with patch('agent_integration.node_tools.executor.NodeToolExecutor.execute') as mock_execute:
            mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
                success=True,
                duration=1.0,
                summary="Success",
            ))()
            
            result = asyncio.run(loop.run())
        
        # Check decisions recorded
        self.agent_run.refresh_from_db()
        decisions = self.agent_run.decisions.all()
        
        self.assertGreater(decisions.count(), 0)
        
        for decision in decisions:
            self.assertIsNotNone(decision.decision_type)
            self.assertIsNotNone(decision.step_number)


class LoopRunnerTests(TransactionTestCase):
    """Tests for AgentLoopRunner service."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
        )
        
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Node 1',
            code='print("Node 1")',
            order=1,
        )
        
        self.pipeline_execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
        )
        
        self.agent_run = AgentRun.objects.create(
            pipeline_execution=self.pipeline_execution,
            max_steps=10,
        )
        
        # Create runtime spec
        self.runtime_spec = RuntimeSpecService.create_spec_for_agent_run(
            agent_run=self.agent_run,
        )
    
    @patch('agent_integration.node_tools.executor.NodeToolExecutor.execute')
    def test_runner_starts_loop(self, mock_execute):
        """Test that runner starts loop."""
        mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
            success=True,
            duration=1.0,
            summary="Success",
        ))()
        
        result = asyncio.run(AgentLoopRunner.start_loop(self.agent_run))
        
        self.assertIsNotNone(result)
        self.assertIsNotNone(result.termination_reason)
    
    @patch('agent_integration.node_tools.executor.NodeToolExecutor.execute')
    def test_runner_resumes_loop(self, mock_execute):
        """Test that runner resumes loop after human intervention."""
        mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
            success=True,
            duration=1.0,
            summary="Success",
        ))()
        
        # Set up human intervention
        self.agent_run.status = 'waiting_for_human'
        self.agent_run.human_intervention_required = True
        self.agent_run.human_intervention_reason = "Approval needed"
        self.agent_run.save()
        
        # Resume
        result = asyncio.run(AgentLoopRunner.resume_loop(self.agent_run))
        
        # Check flags cleared
        self.agent_run.refresh_from_db()
        self.assertFalse(self.agent_run.human_intervention_required)


class IntegrationTests(TransactionTestCase):
    """Integration tests for full execution flow."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        self.pipeline = Pipeline.objects.create(
            name='Test Pipeline',
            created_by=self.user,
        )
        
        # Create multi-node pipeline
        self.node1 = Node.objects.create(
            pipeline=self.pipeline,
            name='Load Data',
            code='data = {"value": 42}',
            order=1,
        )
        
        self.node2 = Node.objects.create(
            pipeline=self.pipeline,
            name='Process Data',
            code='result = data["value"] * 2',
            order=2,
            input_variable_mappings={
                'data': {
                    'node_id': str(self.node1.id),
                    'source_variable': 'data',
                }
            }
        )
        
        self.node3 = Node.objects.create(
            pipeline=self.pipeline,
            name='Save Result',
            code='print(f"Result: {result}")',
            order=3,
            input_variable_mappings={
                'result': {
                    'node_id': str(self.node2.id),
                    'source_variable': 'result',
                }
            }
        )
    
    @patch('agent_integration.node_tools.executor.NodeToolExecutor.execute')
    def test_full_pipeline_execution(self, mock_execute):
        """Test full pipeline execution through agent loop."""
        # Mock successful executions
        mock_execute.return_value = AsyncMock(return_value=NodeToolResult(
            success=True,
            duration=1.0,
            summary="Success",
        ))()
        
        # Create pipeline execution
        pipeline_execution = PipelineExecution.objects.create(
            pipeline=self.pipeline,
            started_by=self.user,
        )
        
        # Create agent run
        agent_run = AgentRun.objects.create(
            pipeline_execution=pipeline_execution,
            max_steps=100,
        )
        
        # Create runtime spec
        runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
        
        # Run loop
        result = asyncio.run(AgentLoopRunner.start_loop(agent_run))
        
        # Verify execution
        self.assertTrue(result.success)
        self.assertEqual(result.termination_reason, LoopTerminationReason.COMPLETED)
        
        # Verify decisions recorded
        agent_run.refresh_from_db()
        self.assertGreater(agent_run.decisions.count(), 0)
        
        # Verify nodes executed in order (via mocks)
        self.assertGreaterEqual(mock_execute.call_count, 3)
