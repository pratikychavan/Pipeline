# Pipeline Execution Package

This package provides a clean, POC-inspired interface for executing pipeline nodes with support for different execution backends.

## Usage in Node Code

### Basic Usage (Auto-injected WarpDrive)

```python
# WarpDrive is automatically available as 'wd'
# Get input from connected nodes
df = wd.get_input('input_data')

# Process data
processed_df = df * 2
result_data = processed_df.sum()

# Outputs are automatically detected and saved
# No need to explicitly declare outputs
```

### Explicit WarpDrive Usage

```python
from core.execution import WarpDrive

wd = WarpDrive()

# Get specific input
data = wd.get_input('my_input')

# Get all available inputs
inputs = wd.get_inputs()

# Process and create outputs
output_data = process(data)

# Explicit output setting (optional)
wd.set_output('result', output_data)

# Logging
wd.log('Processing completed', 'INFO')
```

### Node Information

```python
# Get information about current node
node_info = wd.get_node_info()
print(f"Executing node: {node_info['name']}")

# Get execution information
exec_info = wd.get_execution_info()
print(f"Pipeline: {exec_info['pipeline_name']}")
```

## Execution Backends

### Local Execution (Default)

Executes nodes in the same Django process.

```python
# settings.py
PIPELINE_EXECUTION_BACKEND = 'local'
```

### Kubernetes Execution

Executes each node as a separate Kubernetes Job.

```python
# settings.py
PIPELINE_EXECUTION_BACKEND = 'kubernetes'
PIPELINE_BACKEND_CONFIG = {
    'kubernetes': {
        'namespace': 'pipeline-execution',
        'image': 'python:3.11-slim',
    }
}
```

### Cloud Function Execution (Future)

Execute nodes as serverless functions.

```python
# settings.py
PIPELINE_EXECUTION_BACKEND = 'aws'
PIPELINE_BACKEND_CONFIG = {
    'aws': {
        'region': 'us-west-2',
        'lambda_role': 'arn:aws:iam::account:role/pipeline-lambda-role',
    }
}
```

## Custom Backend Development

Create custom execution backends by extending `ExecutionBackend`:

```python
from core.execution.backends import ExecutionBackend
from core.execution import ExecutionRegistry

class MyCustomBackend(ExecutionBackend):
    def execute_node(self, node, context, execution):
        # Your custom execution logic
        return outputs

# Register the backend
ExecutionRegistry.register_backend('custom', MyCustomBackend)

# Use in settings
PIPELINE_EXECUTION_BACKEND = 'custom'
```

## Migration from POC

The interface is designed to be familiar to POC users:

### POC Style:
```python
import os
from warpdrive import WarpDrive

os.environ['UDF_NAME'] = 'step2'
wd = WarpDrive()
df = wd.get_args('df')
```

### Django Package Style:
```python
# No environment variables needed
# wd is auto-injected or imported
df = wd.get_input('df')
```

## Benefits

1. **Clean Interface**: Simple, POC-inspired API
2. **Backend Abstraction**: Switch between local, Kubernetes, cloud functions
3. **Automatic Output Detection**: No manual output declaration needed
4. **Cloud Ready**: Built for cloud-native deployments
5. **Scalable**: Easy to add new execution backends
6. **Compatible**: Works with existing Django workflow system