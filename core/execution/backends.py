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
        
        # Get connections for this node
        from ..models import NodeConnection
        connections = list(NodeConnection.objects.filter(
            from_node__pipeline=node.pipeline
        ))
        
        # Create execution context
        with NodeExecutionContext(node, execution, context, connections) as wd:
            # Prepare the code with WarpDrive injection
            enhanced_code = self._prepare_code_with_warpdrive(node.code)
            
            # Execute with context
            node_context = context.copy()
            
            # Add connected inputs
            for connection in connections:
                if connection.to_node == node:
                    source_var = connection.from_output
                    target_var = connection.to_input
                    
                    if source_var in context:
                        node_context[target_var] = context[source_var]
            
            # Add WarpDrive to execution context
            node_context['wd'] = wd
            node_context['WarpDrive'] = type(wd)
            
            # Execute the enhanced code
            outputs = execute_node_code(enhanced_code, node_context)
            
            return outputs
    
    def _prepare_code_with_warpdrive(self, code: str) -> str:
        """Prepare code by injecting WarpDrive if needed."""
        # Check if code already imports or uses WarpDrive
        if 'WarpDrive' in code or 'wd =' in code:
            return code
        
        # Auto-inject WarpDrive for convenience
        enhanced_code = f"""
# Auto-injected WarpDrive instance
# wd = WarpDrive() - already provided in context

{code}
"""
        return enhanced_code


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