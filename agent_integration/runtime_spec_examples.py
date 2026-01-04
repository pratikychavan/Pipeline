"""
Runtime Spec Examples

This script demonstrates how to materialize pipelines into runtime specs.

Run: python manage.py shell < runtime_spec_examples.py
"""

import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'pipeline.settings')
django.setup()

import json
from django.contrib.auth.models import User
from core.models import Pipeline, PipelineExecution
from agent_integration.models import AgentRun
from agent_integration.control_plane_models import AgentProfile
from agent_integration.runtime_spec_builder import (
    RuntimeSpecBuilder,
    RuntimeSpecService,
)


def example_1_basic_spec():
    """Example 1: Build basic runtime spec from pipeline"""
    print("\n" + "="*70)
    print("Example 1: Basic Runtime Spec")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    print(f"   Nodes: {pipeline.nodes.count()}")
    
    # Build spec
    builder = RuntimeSpecBuilder(pipeline)
    spec = builder.build()
    
    print(f"\n📋 Runtime Spec Generated:")
    print(f"   Version: {spec['version']}")
    print(f"   Tools: {len(spec['available_tools'])}")
    print(f"   Conditions: {len(spec['business_conditions'])}")
    print(f"   Max Steps: {spec['agent_configuration']['max_steps']}")
    
    # Show tools
    print(f"\n🔧 Available Tools:")
    for tool in spec['available_tools']:
        print(f"   - {tool['tool_name']} (order: {tool['order']})")
        if tool['input_variables']:
            print(f"     Inputs: {', '.join(tool['input_variables'])}")
    
    # Show constraints
    print(f"\n🔒 Execution Constraints:")
    dag = spec['execution_constraints']['dag']
    print(f"   Nodes: {len(dag['nodes'])}")
    print(f"   Dependencies: {len(dag['dependencies'])}")
    
    # Compute checksum
    checksum = builder.compute_checksum(spec)
    print(f"\n✅ Checksum: {checksum[:16]}...")


def example_2_spec_with_agent_profile():
    """Example 2: Build spec with agent profile configuration"""
    print("\n" + "="*70)
    print("Example 2: Spec with Agent Profile")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    agent_profile = AgentProfile.objects.filter(status='active').first()
    
    if not pipeline or not agent_profile:
        print("❌ Missing pipeline or agent profile")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    print(f"🤖 Agent Profile: {agent_profile.name}")
    
    # Build spec with agent configuration
    builder = RuntimeSpecBuilder(pipeline, agent_profile)
    spec = builder.build()
    
    print(f"\n📋 Runtime Spec:")
    print(f"   Max Steps: {spec['agent_configuration']['max_steps']}")
    
    # Show retry policy
    retry_policy = spec['agent_configuration']['retry_policy']
    if retry_policy:
        print(f"\n🔄 Retry Policy:")
        for key, value in retry_policy.items():
            print(f"   {key}: {value}")
    
    # Show guardrails
    guardrails = spec['agent_configuration']['guardrails']
    if guardrails:
        print(f"\n🛡️  Guardrails:")
        for key, value in guardrails.items():
            print(f"   {key}: {value}")
    
    # Show business conditions
    print(f"\n📊 Business Conditions: {len(spec['business_conditions'])}")
    for cond in spec['business_conditions']:
        print(f"   - {cond['condition_name']} ({cond['condition_type']})")
        print(f"     Evaluation: {cond['evaluation_point']}")
        print(f"     Actions: true={cond['on_true_action']}, false={cond['on_false_action']}")


def example_3_create_and_store():
    """Example 3: Create and store runtime spec"""
    print("\n" + "="*70)
    print("Example 3: Create and Store Spec")
    print("="*70)
    
    # Get or create test data
    pipeline = Pipeline.objects.first()
    user = User.objects.first()
    
    if not pipeline or not user:
        print("❌ Missing pipeline or user")
        return
    
    # Create pipeline execution and agent run
    pipeline_exec = PipelineExecution.objects.create(
        pipeline=pipeline,
        started_by=user,
        status='running',
    )
    
    agent_run = AgentRun.objects.create(
        pipeline_execution=pipeline_exec,
        status='initializing',
    )
    
    print(f"\n🤖 Agent Run: {agent_run.id}")
    print(f"📦 Pipeline: {pipeline.name}")
    
    # Create and store spec
    runtime_spec = RuntimeSpecService.create_spec_for_agent_run(agent_run)
    
    print(f"\n✅ Runtime Spec Created:")
    print(f"   ID: {runtime_spec.id}")
    print(f"   Version: {runtime_spec.spec_version}")
    print(f"   Checksum: {runtime_spec.spec_checksum[:16]}...")
    
    # Verify integrity
    is_valid = RuntimeSpecService.verify_spec_integrity(runtime_spec)
    print(f"   Integrity: {'✅ Valid' if is_valid else '❌ Invalid'}")
    
    # Show spec summary
    spec = runtime_spec.spec_data
    print(f"\n📋 Spec Summary:")
    print(f"   Tools: {len(spec['available_tools'])}")
    print(f"   Conditions: {len(spec['business_conditions'])}")
    print(f"   Max Steps: {spec['agent_configuration']['max_steps']}")


def example_4_validate_spec():
    """Example 4: Validate runtime spec"""
    print("\n" + "="*70)
    print("Example 4: Spec Validation")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    
    # Build spec
    builder = RuntimeSpecBuilder(pipeline)
    spec = builder.build()
    
    # Validate
    is_valid, error = builder.validate_spec(spec)
    
    if is_valid:
        print(f"\n✅ Spec is valid")
        print(f"   Version: {spec['version']}")
        print(f"   Tools: {len(spec['available_tools'])}")
    else:
        print(f"\n❌ Spec is invalid: {error}")
    
    # Try to validate invalid spec
    print(f"\n🧪 Testing with invalid spec...")
    invalid_spec = spec.copy()
    del invalid_spec['pipeline']
    
    is_valid, error = builder.validate_spec(invalid_spec)
    print(f"   Result: {'Valid' if is_valid else f'Invalid - {error}'}")


def example_5_export_spec():
    """Example 5: Export spec to JSON"""
    print("\n" + "="*70)
    print("Example 5: Export Spec to JSON")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    
    # Preview spec
    spec = RuntimeSpecService.preview_spec_for_pipeline(pipeline)
    
    print(f"\n📋 Preview Runtime Spec:")
    print(f"   Tools: {len(spec['available_tools'])}")
    
    # Export to JSON
    builder = RuntimeSpecBuilder(pipeline)
    json_str = builder.to_json()
    
    print(f"\n📄 JSON Export (first 500 chars):")
    print(json_str[:500] + "...")
    
    # Show it's serializable
    parsed = json.loads(json_str)
    print(f"\n✅ JSON is valid and parseable")
    print(f"   Keys: {list(parsed.keys())}")


def example_6_dependencies():
    """Example 6: Show dependency graph"""
    print("\n" + "="*70)
    print("Example 6: Dependency Graph")
    print("="*70)
    
    pipeline = Pipeline.objects.first()
    if not pipeline:
        print("❌ No pipelines found")
        return
    
    print(f"\n📦 Pipeline: {pipeline.name}")
    
    # Build spec
    builder = RuntimeSpecBuilder(pipeline)
    spec = builder.build()
    
    # Extract dependencies
    dependencies = spec['execution_constraints']['dag']['dependencies']
    
    print(f"\n🔗 Dependency Graph:")
    for node_id, dep_info in dependencies.items():
        # Find node name
        node_name = "unknown"
        for tool in spec['available_tools']:
            if tool['tool_id'] == node_id:
                node_name = tool['tool_name']
                break
        
        print(f"\n   {node_name}:")
        
        if dep_info['depends_on']:
            dep_names = []
            for dep_id in dep_info['depends_on']:
                for tool in spec['available_tools']:
                    if tool['tool_id'] == dep_id:
                        dep_names.append(tool['tool_name'])
            print(f"      Depends on: {', '.join(dep_names)}")
        else:
            print(f"      Depends on: (none)")
        
        if dep_info['required_for']:
            req_names = []
            for req_id in dep_info['required_for']:
                for tool in spec['available_tools']:
                    if tool['tool_id'] == req_id:
                        req_names.append(tool['tool_name'])
            print(f"      Required for: {', '.join(req_names)}")


def main():
    """Run all examples"""
    print("\n" + "="*70)
    print("RUNTIME SPEC BUILDER - EXAMPLES")
    print("="*70)
    
    try:
        example_1_basic_spec()
    except Exception as e:
        print(f"\n❌ Example 1 failed: {e}")
    
    try:
        example_2_spec_with_agent_profile()
    except Exception as e:
        print(f"\n❌ Example 2 failed: {e}")
    
    try:
        example_3_create_and_store()
    except Exception as e:
        print(f"\n❌ Example 3 failed: {e}")
    
    try:
        example_4_validate_spec()
    except Exception as e:
        print(f"\n❌ Example 4 failed: {e}")
    
    try:
        example_5_export_spec()
    except Exception as e:
        print(f"\n❌ Example 5 failed: {e}")
    
    try:
        example_6_dependencies()
    except Exception as e:
        print(f"\n❌ Example 6 failed: {e}")
    
    print("\n" + "="*70)
    print("Examples Complete!")
    print("="*70)


if __name__ == '__main__':
    main()
