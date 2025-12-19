"""
Pipeline execution engine for running user-defined functions in sequence
"""
import sys
import json
import traceback
from io import StringIO
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
import threading
import time

from .models import Node, PipelineExecution, NodeExecution


class SafeExecutionEnvironment:
    """Provides a safe environment for executing user code"""
    
    # Safe built-ins that users can access
    SAFE_BUILTINS = {
        # Basic data types
        'str': str, 'int': int, 'float': float, 'bool': bool,
        'list': list, 'dict': dict, 'tuple': tuple, 'set': set,
        
        # Iteration and sequence functions
        'range': range, 'enumerate': enumerate, 'zip': zip,
        'len': len, 'sorted': sorted, 'reversed': reversed,
        
        # Math functions
        'abs': abs, 'min': min, 'max': max, 'sum': sum, 'round': round,
        'pow': pow,
        
        # I/O
        'print': print,
        
        # Type checking
        'isinstance': isinstance, 'type': type,
        
        # Utility
        'getattr': getattr, 'setattr': setattr, 'hasattr': hasattr,
        'callable': callable,
    }
    
    def __init__(self):
        self.execution_globals = {
            '__builtins__': self.SAFE_BUILTINS,
            '__name__': '__main__',
        }
    
    def execute_code(self, code, context_vars=None):
        """
        Execute user code in a controlled environment
        
        Args:
            code: Python code string to execute
            context_vars: Dictionary of variables available to the code
            
        Returns:
            Dictionary containing execution results and any new/modified variables
        """
        if context_vars is None:
            context_vars = {}
        
        # Create local execution environment
        exec_locals = context_vars.copy()
        
        # Capture output streams
        stdout_capture = StringIO()
        stderr_capture = StringIO()
        
        result = {
            'success': False,
            'output': '',
            'error': '',
            'variables': {},
            'execution_time': 0,
        }
        
        start_time = time.time()
        
        try:
            with redirect_stdout(stdout_capture), redirect_stderr(stderr_capture):
                # Execute the user code
                exec(code, self.execution_globals, exec_locals)
            
            # Capture any output
            stdout_content = stdout_capture.getvalue()
            stderr_content = stderr_capture.getvalue()
            
            # Calculate execution time
            execution_time = time.time() - start_time
            
            # Extract variables that were created or modified
            new_variables = {}
            for key, value in exec_locals.items():
                if key not in context_vars or context_vars.get(key) != value:
                    # Only include JSON-serializable values
                    try:
                        json.dumps(value)
                        new_variables[key] = value
                    except (TypeError, ValueError):
                        # Convert non-serializable objects to string representation
                        new_variables[key] = str(value)
            
            result.update({
                'success': True,
                'output': stdout_content,
                'error': stderr_content,
                'variables': new_variables,
                'execution_time': execution_time,
            })
            
        except Exception as e:
            execution_time = time.time() - start_time
            error_traceback = traceback.format_exc()
            
            result.update({
                'success': False,
                'output': stdout_capture.getvalue(),
                'error': f"{str(e)}\n\nTraceback:\n{error_traceback}",
                'variables': {},
                'execution_time': execution_time,
            })
        
        return result


class PipelineExecutor:
    """Manages pipeline execution workflow"""
    
    def __init__(self, pipeline_execution_id):
        self.pipeline_execution_id = pipeline_execution_id
        self.execution_env = SafeExecutionEnvironment()
    
    def execute(self):
        """Execute the entire pipeline"""
        try:
            # Get pipeline execution record
            execution = PipelineExecution.objects.get(pk=self.pipeline_execution_id)
            execution.status = 'running'
            execution.save()
            
            pipeline = execution.pipeline
            nodes = Node.objects.filter(pipeline=pipeline).order_by('order')
            
            # Initialize execution context with initial data
            context = execution.context_data.copy()
            
            success = True
            for node in nodes:
                if not self._execute_node(execution, node, context):
                    success = False
                    break
            
            # Update final execution status
            if success:
                execution.status = 'completed'
                execution.completed_at = datetime.now(timezone.utc)
                execution.context_data = context  # Store final context
            else:
                execution.status = 'failed'
                execution.completed_at = datetime.now(timezone.utc)
            
            execution.save()
            
        except Exception as e:
            # Handle execution-level errors
            try:
                execution = PipelineExecution.objects.get(pk=self.pipeline_execution_id)
                execution.status = 'failed'
                execution.error_message = f"Pipeline execution error: {str(e)}"
                execution.completed_at = datetime.now(timezone.utc)
                execution.save()
            except:
                pass  # If we can't save the error state, we're in deep trouble
    
    def _execute_node(self, execution, node, context):
        """Execute a single node and update context"""
        # Create node execution record
        node_execution = NodeExecution.objects.create(
            pipeline_execution=execution,
            node=node,
            status='running',
            started_at=datetime.now(timezone.utc),
            input_data=self._extract_node_inputs(node, context)
        )
        
        try:
            # Execute node code
            result = self.execution_env.execute_code(node.code, context)
            
            if result['success']:
                # Update context with node outputs
                for var_name in node.output_variables:
                    if var_name in result['variables']:
                        context[var_name] = result['variables'][var_name]
                
                # Update node execution record
                node_execution.status = 'completed'
                node_execution.output_data = result['variables']
                node_execution.output_logs = result['output']
                
                # Update node status
                node.status = 'completed'
                node.save()
                
                success = True
            else:
                # Handle execution failure
                node_execution.status = 'failed'
                node_execution.error_message = result['error']
                node_execution.output_logs = result['output']
                
                # Update node status
                node.status = 'failed'
                node.save()
                
                # Update pipeline execution with error
                execution.status = 'failed'
                execution.error_message = f"Node '{node.name}' failed: {result['error']}"
                execution.completed_at = datetime.now(timezone.utc)
                execution.save()
                
                success = False
            
            node_execution.completed_at = datetime.now(timezone.utc)
            node_execution.save()
            
            return success
            
        except Exception as e:
            # Handle unexpected errors during node execution
            error_msg = f"Unexpected error in node '{node.name}': {str(e)}"
            
            node_execution.status = 'failed'
            node_execution.error_message = error_msg
            node_execution.completed_at = datetime.now(timezone.utc)
            node_execution.save()
            
            # Update node status
            node.status = 'failed'
            node.save()
            
            # Update pipeline execution
            execution.status = 'failed'
            execution.error_message = error_msg
            execution.completed_at = datetime.now(timezone.utc)
            execution.save()
            
            return False
    
    def _extract_node_inputs(self, node, context):
        """Extract input variables for a node from the execution context"""
        inputs = {}
        for var_name in node.input_variables:
            if var_name in context:
                inputs[var_name] = context[var_name]
        return inputs


def execute_pipeline_async(pipeline_execution_id):
    """
    Asynchronous pipeline execution entry point
    This function is called in a separate thread
    """
    executor = PipelineExecutor(pipeline_execution_id)
    executor.execute()


class CodeValidator:
    """Validates user code for security and syntax issues"""
    
    # Dangerous keywords and modules that should be restricted
    RESTRICTED_KEYWORDS = [
        'import', 'exec', 'eval', 'compile', '__import__',
        'open', 'file', 'input', 'raw_input',
        'globals', 'locals', 'vars', 'dir',
    ]
    
    RESTRICTED_ATTRIBUTES = [
        '__class__', '__bases__', '__subclasses__',
        '__dict__', '__code__', '__globals__',
    ]
    
    @classmethod
    def validate_code(cls, code):
        """
        Validate user code for security issues
        
        Returns:
            tuple: (is_valid, error_message)
        """
        if not code or not code.strip():
            return False, "Code cannot be empty"
        
        # Check for restricted keywords
        for keyword in cls.RESTRICTED_KEYWORDS:
            if keyword in code:
                return False, f"Restricted keyword '{keyword}' found in code"
        
        # Check for restricted attributes
        for attr in cls.RESTRICTED_ATTRIBUTES:
            if attr in code:
                return False, f"Restricted attribute '{attr}' found in code"
        
        # Check for basic syntax errors
        try:
            compile(code, '<user_code>', 'exec')
        except SyntaxError as e:
            return False, f"Syntax error: {str(e)}"
        except Exception as e:
            return False, f"Code validation error: {str(e)}"
        
        return True, ""
    
    @classmethod
    def get_code_suggestions(cls, code):
        """Provide suggestions for improving user code"""
        suggestions = []
        
        if 'print(' not in code and 'return' not in code:
            suggestions.append("Consider adding print statements or return values to see output")
        
        if len(code.split('\n')) > 50:
            suggestions.append("Consider breaking large code blocks into smaller functions")
        
        return suggestions