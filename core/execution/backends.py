"""
Execution backends for different deployment environments.
"""

import json
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from django.conf import settings
from ..models import Node, PipelineExecution, NodeExecution


class ExecutionBackend(ABC):
    """Base class for execution backends."""
    
    @abstractmethod
    def execute_node(self, node: Node, context: Dict[str, Any], 
                    execution: PipelineExecution) -> Dict[str, Any]:
        """
        Execute a node and return its outputs.
        
        Args:
            node: Node to execute
            context: Execution context with input variables
            execution: Pipeline execution instance
            
        Returns:
            Dictionary of output variables
        """
        pass


class LocalExecutionBackend(ExecutionBackend):
    """Execute nodes locally in the same process."""
    
    def execute_node(self, node: Node, context: Dict[str, Any], 
                    execution: PipelineExecution) -> Dict[str, Any]:
        """Execute node locally using the existing execution logic."""
        from .warpdrive import NodeExecutionContext
        from ..views import execute_node_code
        
        # Execute with context
        node_context = context.copy()
        
        # Handle input variable mappings from the node's configuration
        if node.input_variable_mappings:
            for var_name, mapping in node.input_variable_mappings.items():
                source_var = mapping.get('source_variable')
                
                if source_var and source_var in context:
                    node_context[var_name] = context[source_var]
        
        # Add execution metadata for WarpDrive initialization
        # Note: We no longer pass connections, WarpDrive will use context_data directly
        node_context['__warpdrive_context__'] = {
            'node_id': str(node.id),
            'execution_id': str(execution.id),
            'context_data': node_context,  # Pass the mapped context
            'input_variable_mappings': node.input_variable_mappings or {}
        }
        
        # Also set environment variables for container-based execution
        import os
        os.environ['WARPDRIVE_NODE_ID'] = str(node.id)
        os.environ['WARPDRIVE_EXECUTION_ID'] = str(execution.id)
        
        # Execute the code directly (user creates WarpDrive if needed)
        outputs = execute_node_code(node.code, node_context)
        
        return outputs


class DockerExecutionBackend(ExecutionBackend):
    """Execute nodes in Docker containers with shared volume for artifacts."""
    
    def __init__(self, image: str = 'python:3.11-slim', 
                 volume_path: str = None):
        self.image = image
        # Use Django MEDIA_ROOT or fallback to /tmp
        try:
            from django.conf import settings
            self.volume_path = volume_path or settings.MEDIA_ROOT
        except:
            self.volume_path = volume_path or '/tmp/pipeline-artifacts'
    
    def execute_node(self, node: Node, context: Dict[str, Any], 
                    execution: PipelineExecution) -> Dict[str, Any]:
        """Execute node in a Docker container."""
        import subprocess
        import tempfile
        
        # Get connections for this node
        from ..models import NodeConnection
        connections = list(NodeConnection.objects.filter(
            from_node__pipeline=node.pipeline
        ))
        
        # Prepare execution script with WarpDrive support
        script = self._prepare_container_script(node, context, execution, connections)
        
        # Create temporary file for the script
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(script)
            script_file = f.name
        
        try:
            # Run Docker container with mounted volumes
            container_name = f"pipeline-{execution.id}-{node.id}"[:63]
            
            cmd = [
                'docker', 'run',
                '--rm',
                '--name', container_name,
                '-v', f'{script_file}:/app/node_code.py',
                '-v', f'{self.volume_path}:/artifacts',
                '-e', f'WARPDRIVE_NODE_ID={node.id}',
                '-e', f'WARPDRIVE_EXECUTION_ID={execution.id}',
                self.image,
                'python', '/app/node_code.py'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                raise Exception(f"Container execution failed: {result.stderr}")
            
            # Parse outputs from stdout (JSON)
            import json
            outputs = json.loads(result.stdout)
            return outputs
            
        finally:
            os.unlink(script_file)
    
    def _prepare_container_script(self, node: Node, context: Dict[str, Any],
                                 execution: PipelineExecution, 
                                 connections: list) -> str:
        """Prepare Python script to run in container."""
        
        # Serialize connections and context
        connections_data = []
        for conn in connections:
            connections_data.append({
                'from_node_id': str(conn.from_node.id),
                'to_node_id': str(conn.to_node.id),
                'from_output': conn.from_output,
                'to_input': conn.to_input
            })
        
        script = f'''
import os
import sys
import json
import pickle
import base64
from typing import Dict, Any, Optional, List

# Minimal WarpDrive implementation for container execution
class WarpDrive:
    def __init__(self, node_id=None, execution_id=None):
        self.node_id = node_id or os.environ.get('WARPDRIVE_NODE_ID')
        self.execution_id = execution_id or os.environ.get('WARPDRIVE_EXECUTION_ID')
        self.context_data = {json.dumps(context)}
        self.connections = {json.dumps(connections_data)}
        self.artifact_storage_dir = f'/artifacts/{{self.execution_id}}'
        os.makedirs(self.artifact_storage_dir, exist_ok=True)
        self.caller_globals = globals()
        self.initial_vars = set(self.caller_globals.keys())
        self.loaded_vars = set()
        
    def get_arg(self, variable_name):
        """Get input variable through connections."""
        # Find connection
        for conn in self.connections:
            if conn['to_node_id'] == self.node_id and conn['to_input'] == variable_name:
                source_var = conn['from_output']
                if source_var in self.context_data:
                    value = self.context_data[source_var]
                    
                    # Load artifact if needed
                    if isinstance(value, dict) and value.get('_artifact'):
                        file_path = value.get('_file')
                        if file_path:
                            value = self._load_artifact(file_path)
                    
                    self.loaded_vars.add(variable_name)
                    return value
        
        raise ValueError(f"Input variable '{{variable_name}}' not found")
    
    def _load_artifact(self, file_path):
        """Load artifact from file."""
        full_path = f'/artifacts/{{self.execution_id}}/{{os.path.basename(file_path)}}'
        with open(full_path, 'rb') as f:
            return pickle.load(f)
    
    def get_outputs(self):
        """Collect outputs (simplified for container)."""
        outputs = {{}}
        current_vars = set(self.caller_globals.keys())
        new_vars = current_vars - self.initial_vars - self.loaded_vars
        
        for var_name in new_vars:
            if var_name.startswith('_') or var_name in ['wd', 'WarpDrive']:
                continue
            
            value = self.caller_globals[var_name]
            
            try:
                json.dumps(value)
                outputs[var_name] = value
            except (TypeError, ValueError):
                # Non-serializable - save as artifact
                artifact_file = f'{{var_name}}.pkl'
                file_path = os.path.join(self.artifact_storage_dir, artifact_file)
                with open(file_path, 'wb') as f:
                    pickle.dump(value, f)
                outputs[var_name] = {{
                    '_artifact': True,
                    '_type': type(value).__name__,
                    '_file': artifact_file
                }}
        
        return outputs

# Make WarpDrive available
globals()['WarpDrive'] = WarpDrive

# Execute user code
{node.code}

# Collect and output results
if 'wd' in globals():
    outputs = wd.get_outputs()
else:
    # Fallback: collect all new variables
    outputs = {{}}
    for name, value in globals().items():
        if not name.startswith('_') and name not in ['WarpDrive', 'os', 'sys', 'json', 'pickle']:
            try:
                json.dumps(value)
                outputs[name] = value
            except:
                pass

print(json.dumps(outputs))
'''
        return script


class KubernetesExecutionBackend(ExecutionBackend):
    """Execute nodes as Kubernetes jobs."""
    
    def __init__(self, namespace: str = 'default', 
                 image: str = 'python:3.11-slim'):
        self.namespace = namespace
        self.image = image
    
    def execute_node(self, node: Node, context: Dict[str, Any], 
                    execution: PipelineExecution) -> Dict[str, Any]:
        """Execute node as a Kubernetes job."""
        
        # Create job manifest
        job_manifest = self._create_job_manifest(node, context, execution)
        
        # Submit job
        job_name = self._submit_job(job_manifest)
        
        # Wait for completion and get outputs
        outputs = self._wait_for_job_completion(job_name)
        
        return outputs
    
    def _create_job_manifest(self, node: Node, context: Dict[str, Any], 
                           execution: PipelineExecution) -> Dict[str, Any]:
        """Create Kubernetes job manifest."""
        
        job_name = f"pipeline-{execution.id}-node-{node.id}".lower()
        
        # Prepare the execution script
        script = self._prepare_kubernetes_script(node, context, execution)
        
        manifest = {
            'apiVersion': 'batch/v1',
            'kind': 'Job',
            'metadata': {
                'name': job_name,
                'namespace': self.namespace,
                'labels': {
                    'pipeline-id': str(execution.pipeline.id),
                    'execution-id': str(execution.id),
                    'node-id': str(node.id),
                    'app': 'pipeline-executor'
                }
            },
            'spec': {
                'template': {
                    'spec': {
                        'restartPolicy': 'Never',
                        'containers': [{
                            'name': 'node-executor',
                            'image': self.image,
                            'command': ['python', '-c'],
                            'args': [script],
                            'env': [
                                {
                                    'name': 'NODE_ID',
                                    'value': str(node.id)
                                },
                                {
                                    'name': 'EXECUTION_ID',
                                    'value': str(execution.id)
                                },
                                {
                                    'name': 'CONTEXT_DATA',
                                    'value': json.dumps(context)
                                }
                            ],
                            'volumeMounts': [{
                                'name': 'output-volume',
                                'mountPath': '/outputs'
                            }]
                        }],
                        'volumes': [{
                            'name': 'output-volume',
                            'emptyDir': {}
                        }]
                    }
                }
            }
        }
        
        return manifest
    
    def _prepare_kubernetes_script(self, node: Node, context: Dict[str, Any], 
                                 execution: PipelineExecution) -> str:
        """Prepare the script to run in Kubernetes."""
        
        script = f'''
import os
import json
import sys

# Add the pipeline package to sys.path (in real deployment, use proper package)
sys.path.append('/app')

# Load context
context_data = json.loads(os.environ.get('CONTEXT_DATA', '{{}}'))
node_id = os.environ.get('NODE_ID')
execution_id = os.environ.get('EXECUTION_ID')

# Setup WarpDrive with Kubernetes backend
class KubernetesWarpDrive:
    def __init__(self):
        self.context_data = context_data
        self.node_id = node_id
        self.execution_id = execution_id
    
    def get_input(self, var_name):
        return self.context_data.get(var_name)
    
    def get_inputs(self):
        return self.context_data
    
    def log(self, message, level='INFO'):
        print(f"[{{level}}] {{message}}")

# Create WarpDrive instance
wd = KubernetesWarpDrive()

# Execute user code
{node.code}

# Save outputs to mounted volume
import pickle
outputs = {{}}
for name, value in locals().items():
    if not name.startswith('_') and name not in ['wd', 'os', 'json', 'sys']:
        try:
            json.dumps(value, default=str)
            outputs[name] = value
        except:
            outputs[name] = str(value)

with open('/outputs/results.json', 'w') as f:
    json.dump(outputs, f)
'''
        
        return script
    
    def _submit_job(self, manifest: Dict[str, Any]) -> str:
        """Submit job to Kubernetes."""
        
        # Write manifest to temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', 
                                       delete=False) as f:
            import yaml
            yaml.dump(manifest, f)
            manifest_file = f.name
        
        try:
            # Apply the job
            result = subprocess.run([
                'kubectl', 'apply', '-f', manifest_file
            ], capture_output=True, text=True, check=True)
            
            job_name = manifest['metadata']['name']
            print(f"Kubernetes job {job_name} submitted successfully")
            return job_name
            
        except subprocess.CalledProcessError as e:
            raise Exception(f"Failed to submit Kubernetes job: {e.stderr}")
        finally:
            os.unlink(manifest_file)
    
    def _wait_for_job_completion(self, job_name: str) -> Dict[str, Any]:
        """Wait for job completion and retrieve outputs."""
        
        import time
        timeout = 300  # 5 minutes
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            # Check job status
            result = subprocess.run([
                'kubectl', 'get', 'job', job_name, 
                '-o', 'jsonpath={.status.conditions[0].type}'
            ], capture_output=True, text=True)
            
            if result.stdout.strip() == 'Complete':
                # Get pod name
                pod_result = subprocess.run([
                    'kubectl', 'get', 'pods',
                    '--selector', f'job-name={job_name}',
                    '-o', 'jsonpath={.items[0].metadata.name}'
                ], capture_output=True, text=True)
                
                pod_name = pod_result.stdout.strip()
                
                # Copy outputs from pod
                output_result = subprocess.run([
                    'kubectl', 'cp', 
                    f'{pod_name}:/outputs/results.json',
                    '/tmp/results.json'
                ], capture_output=True, text=True)
                
                # Read outputs
                try:
                    with open('/tmp/results.json', 'r') as f:
                        outputs = json.load(f)
                    os.unlink('/tmp/results.json')
                    return outputs
                except Exception as e:
                    raise Exception(f"Failed to read job outputs: {e}")
            
            elif result.stdout.strip() == 'Failed':
                raise Exception(f"Kubernetes job {job_name} failed")
            
            time.sleep(5)
        
        raise Exception(f"Kubernetes job {job_name} timed out")


class CloudFunctionBackend(ExecutionBackend):
    """Execute nodes as cloud functions (AWS Lambda, Google Cloud Functions, etc.)."""
    
    def __init__(self, provider: str = 'aws', **config):
        self.provider = provider
        self.config = config
    
    def execute_node(self, node: Node, context: Dict[str, Any], 
                    execution: PipelineExecution) -> Dict[str, Any]:
        """Execute node as a cloud function."""
        
        if self.provider == 'aws':
            return self._execute_aws_lambda(node, context, execution)
        elif self.provider == 'gcp':
            return self._execute_gcp_function(node, context, execution)
        else:
            raise ValueError(f"Unsupported cloud provider: {self.provider}")
    
    def _execute_aws_lambda(self, node: Node, context: Dict[str, Any], 
                          execution: PipelineExecution) -> Dict[str, Any]:
        """Execute on AWS Lambda."""
        # Implementation for AWS Lambda execution
        # This would involve creating a Lambda function payload and invoking it
        raise NotImplementedError("AWS Lambda backend not yet implemented")
    
    def _execute_gcp_function(self, node: Node, context: Dict[str, Any], 
                            execution: PipelineExecution) -> Dict[str, Any]:
        """Execute on Google Cloud Functions."""
        # Implementation for GCP Cloud Functions execution
        raise NotImplementedError("GCP Cloud Functions backend not yet implemented")