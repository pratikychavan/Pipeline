"""
Example usage of the Pipeline Execution Package
"""

# Example Node 1 Code (Data Generator)
node1_code = """
import pandas as pd

# Create sample data
df = pd.DataFrame({
    'x': [1, 2, 3, 4, 5],
    'y': [10, 20, 30, 40, 50]
})

# Process data
processed_data = df.copy()
processed_data['sum'] = processed_data['x'] + processed_data['y']

# Outputs: df, processed_data (automatically detected)
"""

# Example Node 2 Code (Data Consumer)
node2_code = """
# Get input from previous node (variable name mapping handled automatically)
input_df = wd.get_input('data')  # Maps from node1's 'processed_data' output

# Process the data
result = input_df['sum'].mean()
statistics = {
    'mean': result,
    'count': len(input_df),
    'max': input_df['sum'].max()
}

# Log processing info
wd.log(f"Processed {len(input_df)} rows")

# Outputs: result, statistics (automatically detected)
"""

# Example Node 3 Code (Multiple Inputs)
node3_code = """
# Get multiple inputs
original_df = wd.get_input('original')  # From node1's 'df'
stats = wd.get_input('stats')          # From node2's 'statistics'

# All inputs at once
all_inputs = wd.get_inputs()
wd.log(f"Received inputs: {list(all_inputs.keys())}")

# Create final report
report = {
    'total_rows': len(original_df),
    'mean_sum': stats['mean'],
    'data_summary': original_df.describe().to_dict()
}

# Output: report (automatically detected)
"""

# Configuration Examples

# Local execution (default)
local_config = {
    'PIPELINE_EXECUTION_BACKEND': 'local'
}

# Kubernetes execution
k8s_config = {
    'PIPELINE_EXECUTION_BACKEND': 'kubernetes',
    'PIPELINE_BACKEND_CONFIG': {
        'kubernetes': {
            'namespace': 'ml-pipelines',
            'image': 'pipeline-executor:latest',  # Your custom image with dependencies
        }
    }
}

# AWS Lambda execution (future)
aws_config = {
    'PIPELINE_EXECUTION_BACKEND': 'aws',
    'PIPELINE_BACKEND_CONFIG': {
        'aws': {
            'region': 'us-west-2',
            'lambda_role': 'arn:aws:iam::123456789:role/PipelineLambdaRole',
            'timeout': 300,
            'memory': 512
        }
    }
}