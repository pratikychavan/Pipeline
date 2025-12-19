"""
WarpDrive - Pipeline execution interface for Django

This class provides a clean interface for pipeline node execution,
handling data flow, variable mapping, and backend abstraction.
"""

import os
import json
import inspect
from typing import Dict, Any, Optional, List
from django.conf import settings
from ..models import Node, NodeConnection, PipelineExecution, NodeExecution


class WarpDrive:
    """
    Main pipeline execution interface with explicit artifact save/load system.
    
    Basic Usage:
        wd = WarpDrive()
        
        # Save artifacts with custom serialization
        import pandas as pd
        df = pd.DataFrame({'x': [1, 2, 3]})
        wd.save_artifact('df', df, serialization_func=df.to_parquet)
        
        # In next node - load artifacts with custom deserialization
        df = wd.get_arg('df', deserialization_func=pd.read_parquet)
        result = df.shape
    
    This supports cloud storage and container-based execution since artifacts
    are saved to files that can be shared across containers or uploaded to S3/GCS.
    """
    
    def __init__(self, execution_context: Optional[Dict[str, Any]] = None, 
                 node_id: Optional[str] = None, 
                 execution_id: Optional[str] = None):
        """
        Initialize WarpDrive with execution context.
        
        Args:
            execution_context: Dictionary containing execution metadata (for local execution)
            node_id: Node ID (for remote/container execution)
            execution_id: Execution ID (for remote/container execution)
        """
        # Get caller's frame to extract execution context if not provided
        caller_frame = inspect.currentframe().f_back
        caller_locals = caller_frame.f_locals if caller_frame else {}
        
        # Priority: explicit context > caller locals > node_id/execution_id
        if execution_context is None:
            execution_context = caller_locals.get('__warpdrive_context__', {})
        
        # If still no context and node_id/execution_id provided, load from environment or DB
        if not execution_context and (node_id or execution_id):
            node_id = node_id or os.environ.get('WARPDRIVE_NODE_ID')
            execution_id = execution_id or os.environ.get('WARPDRIVE_EXECUTION_ID')
            
            if node_id and execution_id:
                execution_context = self._load_context_from_storage(node_id, execution_id)
        
        self.execution_context = execution_context or {}
        self.node_id = self.execution_context.get('node_id') or node_id
        self.execution_id = self.execution_context.get('execution_id') or execution_id
        self.context_data = self.execution_context.get('context_data', {})
        self.connections = self.execution_context.get('connections', [])
        
        # Get caller's locals for automatic output detection
        self.caller_globals = caller_locals
        
        # Track initial variables to detect outputs later
        self.initial_vars = set(self.caller_globals.keys())
        
        # Artifact registry for complex objects
        self.artifacts = {}  # {var_name: {'data': obj, 'serializer': func, 'deserializer': func}}
        self.serializers = {}  # {type_name: {'serialize': func, 'deserialize': func}}
        
        # Track variables loaded via get_arg() to exclude from outputs
        self.loaded_vars = set()
        
        # Track actual data objects loaded via get_arg() by id()
        self.loaded_data_ids = set()
        
        # Set up artifact storage directory
        self.artifact_storage_dir = os.path.join(
            settings.MEDIA_ROOT, 
            'artifacts', 
            str(self.execution_id) if self.execution_id else 'temp'
        )
        os.makedirs(self.artifact_storage_dir, exist_ok=True)
        
        # Register built-in serializers
        self._register_builtin_serializers()
        
        # Load artifacts from context data if available
        self._load_artifacts_from_context()
        
    def save_artifact(self, name: str, data: Any, serialization_func=None):
        """
        Save an artifact with custom serialization function.
        
        Args:
            name: Artifact variable name
            data: Data to save
            serialization_func: Function to serialize the data (e.g., df.to_parquet)
                              If None, uses pickle
        
        Example:
            wd.save_artifact('df', df, serialization_func=df.to_parquet)
        """
        import pickle
        
        # Create safe filename
        safe_name = name.replace('/', '_').replace('\\', '_')
        
        if serialization_func:
            # Use custom serialization - determine file extension from function name
            func_name = getattr(serialization_func, '__name__', 'data')
            if 'parquet' in func_name.lower():
                ext = 'parquet'
            elif 'csv' in func_name.lower():
                ext = 'csv'
            elif 'json' in func_name.lower():
                ext = 'json'
            else:
                ext = 'dat'
            
            file_name = f"{safe_name}.{ext}"
            file_path = os.path.join(self.artifact_storage_dir, file_name)
            
            # Call serialization function
            try:
                serialization_func(file_path)
            except TypeError:
                # Function might need the data as first argument
                serialization_func(data, file_path)
        else:
            # Use pickle as fallback
            file_name = f"{safe_name}.pkl"
            file_path = os.path.join(self.artifact_storage_dir, file_name)
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
        
        # Store metadata for this artifact
        self.artifacts[name] = {
            'file': file_name,
            'type': type(data).__name__,
            'serialization_func': serialization_func
        }
        
        # Update caller_globals with artifact reference
        self.caller_globals[name] = {
            '_artifact': True,
            '_type': type(data).__name__,
            '_file': file_name
        }
        
        self.log(f"Saved artifact '{name}' to {file_name}")
    
    def get_arg(self, variable_name: str, deserialization_func=None) -> Any:
        """
        Get input variable from connected nodes, loaded artifacts, or context data.
        
        Args:
            variable_name: The input variable name expected by current node
            
        Returns:
            The value from the connected output variable or loaded artifact
            
        Raises:
            ValueError: If the input variable is not connected or available
        """
        if not self.node_id:
            raise ValueError("WarpDrive not properly initialized with node context")
            
        # First check if this variable is available as a loaded artifact
        if variable_name in self.artifacts:
            return self.artifacts[variable_name]['data']
            
        # Then find connection that provides this input
        for connection in self.connections:
            if (str(connection.to_node.id) == str(self.node_id) and 
                connection.to_input == variable_name):
                
                source_var = connection.from_output
                if source_var in self.context_data:
                    value = self.context_data[source_var]
                    
                    # Check if this is a serialized artifact
                    if isinstance(value, dict) and value.get('_artifact'):
                        if '_error' in value:
                            raise ValueError(f"Artifact '{source_var}' failed to serialize: {value['_error']}")
                        
                        artifact_type = value.get('_type')
                        file_path = value.get('_file')
                        
                        if file_path:
                            # Load from file with provided or default deserializer
                            full_path = os.path.join(self.artifact_storage_dir, file_path)
                            
                            if deserialization_func:
                                # Use user-provided deserialization
                                try:
                                    deserialized = deserialization_func(full_path)
                                except Exception as e:
                                    raise ValueError(f"Failed to deserialize artifact '{source_var}' with provided function: {str(e)}")
                            else:
                                # Try to find registered deserializer or use pickle
                                deserializer = None
                                for type_name, type_info in self.serializers.items():
                                    if type_name.endswith(f".{artifact_type}") or type_info['type_class'].__name__ == artifact_type:
                                        deserializer = type_info['deserialize']
                                        break
                                
                                try:
                                    deserialized = self._load_artifact_from_file(full_path, deserializer)
                                except Exception as e:
                                    raise ValueError(f"Failed to load artifact '{source_var}' from file: {str(e)}")
                            
                            self.log(f"Loaded artifact from file: {source_var} (type: {artifact_type})")
                            # Track this variable as loaded input
                            self.loaded_vars.add(variable_name)
                            # Track the object id to exclude from outputs
                            self.loaded_data_ids.add(id(deserialized))
                            return deserialized
                        else:
                            raise ValueError(f"Artifact '{source_var}' has no file path")
                    else:
                        # Regular serializable value
                        # Track this variable as loaded input
                        self.loaded_vars.add(variable_name)
                        # Track the object id to exclude from outputs
                        self.loaded_data_ids.add(id(value))
                        return value
                else:
                    raise ValueError(f"Connected variable '{source_var}' not found in context")
        
        # If not connected, check if it's in global context (external input)
        if variable_name in self.context_data:
            value = self.context_data[variable_name]
            
            # Check if this is a serialized artifact that needs deserialization
            if isinstance(value, dict) and value.get('_artifact'):
                artifact_type = value.get('_type', '')
                file_path = value.get('_file')
                
                if file_path:
                    # Look for appropriate deserializer
                    full_path = os.path.join(self.artifact_storage_dir, file_path)
                    
                    if deserialization_func:
                        # Use user-provided deserialization
                        try:
                            deserialized = deserialization_func(full_path)
                        except Exception as e:
                            raise ValueError(f"Failed to deserialize artifact '{variable_name}' with provided function: {str(e)}")
                    else:
                        # Try registered deserializers or pickle
                        deserializer = None
                        for type_name, type_info in self.serializers.items():
                            if (artifact_type == type_name or 
                                type_name.endswith(f".{artifact_type}") or 
                                artifact_type in type_name):
                                deserializer = type_info['deserialize']
                                break
                        
                        try:
                            deserialized = self._load_artifact_from_file(full_path, deserializer)
                        except Exception as e:
                            raise ValueError(f"Failed to load artifact '{variable_name}': {str(e)}")
                    
                    self.log(f"Loaded artifact from file: {variable_name} (type: {artifact_type})")
                    # Track this variable as loaded input
                    self.loaded_vars.add(variable_name)
                    return deserialized
            
            # Track this variable as loaded input
            self.loaded_vars.add(variable_name)
            return value
            
        # Variable not found - provide helpful error message
        available_vars = list(self.context_data.keys())
        available_artifacts = list(self.artifacts.keys())
        raise ValueError(
            f"Input variable '{variable_name}' not found.\n"
            f"Available in context_data: {available_vars}\n"
            f"Available as artifacts: {available_artifacts}\n"
            f"Make sure the variable is connected or the name matches the output from the previous node."
        )
    

    
    def set_output(self, variable_name: str, value: Any):
        """
        Explicitly set an output variable.
        
        Args:
            variable_name: Name of the output variable
            value: Value to set
        """
        self.caller_globals[variable_name] = value
    
    def get_outputs(self) -> Dict[str, Any]:
        """
        Get all output variables created by the current node.
        Automatically detects new variables created since initialization.
        Handles both regular JSON-serializable variables and registered artifacts.
        
        Returns:
            Dictionary of output variable names to their serialized values
        """
        outputs = {}
        current_vars = set(self.caller_globals.keys())
        new_vars = current_vars - self.initial_vars
        
        # First, handle registered artifacts
        for artifact_name, artifact_info in self.artifacts.items():
            # Skip artifacts that were loaded via get_arg() - they're inputs, not outputs
            if artifact_name in self.loaded_vars:
                continue
            
            # Only include artifacts that are new variables (created in this node)
            if artifact_name not in new_vars:
                continue
                
            try:
                # Save artifact to file
                file_path = self._save_artifact_to_file(
                    artifact_name, 
                    artifact_info['data'],
                    artifact_info.get('serializer')
                )
                
                outputs[artifact_name] = {
                    '_artifact': True,
                    '_type': artifact_info['type'],
                    '_file': file_path
                }
                self.log(f"Serialized artifact to file: {artifact_name} -> {file_path}")
            except Exception as e:
                self.log(f"Failed to serialize artifact {artifact_name}: {str(e)}", 'ERROR')
                outputs[artifact_name] = {
                    '_artifact': True,
                    '_type': artifact_info['type'],
                    '_error': f"Serialization failed: {str(e)}"
                }
        
        # Then handle regular variables
        import types
        for var_name in new_vars:
            # Skip loaded input variables
            if var_name in self.loaded_vars:
                continue
            
            value = self.caller_globals[var_name]
            
            # Skip modules
            if isinstance(value, types.ModuleType):
                continue
                
            if (not var_name.startswith('_') and 
                not var_name in ['WarpDrive', 'wd'] and
                var_name not in ['os', 'sys', 'json', 'pd', 'np', 'pandas', 'numpy', 'sklearn', 'torch', 'tensorflow'] and
                var_name not in self.artifacts):  # Skip artifacts already handled
                try:
                    # Test if serializable (don't use default= here - we want it to fail for non-serializable)
                    json.dumps(value)
                    outputs[var_name] = value
                except (TypeError, ValueError):
                    # Non-serializable object - check if we have a registered serializer for this type
                    value_type = type(value)
                    serializer_found = False
                    
                    for type_name, type_info in self.serializers.items():
                        if isinstance(value, type_info.get('type_class', type)):
                            # Found a registered serializer for this type
                            try:
                                file_path = self._save_artifact_to_file(
                                    var_name,
                                    value,
                                    type_info['serialize']
                                )
                                outputs[var_name] = {
                                    '_artifact': True,
                                    '_type': value_type.__name__,
                                    '_file': file_path
                                }
                                self.log(f"Auto-serialized {var_name} as artifact (type: {value_type.__name__})")
                                serializer_found = True
                                break
                            except Exception as e:
                                self.log(f"Failed to serialize {var_name}: {str(e)}", 'ERROR')
                    
                    if not serializer_found:
                        # No serializer available - convert to string representation
                        outputs[var_name] = {
                            '_artifact': False,
                            '_type': type(value).__name__,
                            '_string_repr': str(value),
                            '_note': 'Non-serializable object converted to string. Consider using register_artifact() for proper handling.'
                        }
        
        return outputs
    
    def log(self, message: str, level: str = 'INFO'):
        """
        Log a message during node execution.
        
        Args:
            message: Log message
            level: Log level (DEBUG, INFO, WARNING, ERROR)
        """
        print(f"[{level}] Node {self.node_id}: {message}")
    
    def register_artifact_type(self, type_class, serializer_func, deserializer_func):
        """
        Register a serialization/deserialization pair for a specific type.
        
        Args:
            type_class: The class/type to register (e.g., pd.DataFrame, sklearn.base.BaseEstimator)
            serializer_func: Function that takes an object and returns serializable data
            deserializer_func: Function that takes serialized data and returns the original object
        
        Example:
            import pandas as pd
            import pickle
            
            def serialize_dataframe(df):
                return df.to_json()
            
            def deserialize_dataframe(json_str):
                return pd.read_json(json_str)
            
            wd.register_artifact_type(pd.DataFrame, serialize_dataframe, deserialize_dataframe)
        """
        type_name = f"{type_class.__module__}.{type_class.__qualname__}"
        self.serializers[type_name] = {
            'serialize': serializer_func,
            'deserialize': deserializer_func,
            'type_class': type_class
        }
        self.log(f"Registered artifact type: {type_name}")
    
    def register_artifact(self, variable_name: str, data, serializer_func=None, deserializer_func=None):
        """
        Register a variable as an artifact with custom serialization.
        
        Args:
            variable_name: Name of the variable
            data: The actual data object
            serializer_func: Optional custom serializer for this specific variable
            deserializer_func: Optional custom deserializer for this specific variable
        
        If serializer_func is not provided, will try to use registered type serializers.
        
        Example:
            # Using custom serializer for this variable
            import pickle
            model = train_model()
            wd.register_artifact('model', model, 
                               lambda obj: pickle.dumps(obj).hex(),
                               lambda hex_str: pickle.loads(bytes.fromhex(hex_str)))
            
            # Using registered type serializer
            df = pd.DataFrame({'a': [1,2,3]})
            wd.register_artifact('dataframe', df)  # Uses registered pd.DataFrame serializer
        """
        # Try to find appropriate serializer
        if serializer_func is None or deserializer_func is None:
            data_type = type(data)
            type_name = f"{data_type.__module__}.{data_type.__qualname__}"
            
            if type_name in self.serializers:
                serializer_func = self.serializers[type_name]['serialize']
                deserializer_func = self.serializers[type_name]['deserialize']
            else:
                # Check if data type is a subclass of any registered types
                for registered_type_name, type_info in self.serializers.items():
                    if isinstance(data, type_info['type_class']):
                        serializer_func = type_info['serialize']
                        deserializer_func = type_info['deserialize']
                        break
                
                if serializer_func is None:
                    raise ValueError(f"No serializer found for type {type_name}. "
                                   f"Please provide custom serializer or register the type first.")
        
        # Store the artifact
        self.artifacts[variable_name] = {
            'data': data,
            'serializer': serializer_func,
            'deserializer': deserializer_func,
            'type': type(data).__name__
        }
        
        self.log(f"Registered artifact: {variable_name} (type: {type(data).__name__})")
    
    def get_artifact(self, variable_name: str):
        """
        Retrieve a registered artifact.
        
        Args:
            variable_name: Name of the artifact variable
            
        Returns:
            The deserialized artifact data
        """
        if variable_name not in self.artifacts:
            raise ValueError(f"Artifact '{variable_name}' not found")
        
        return self.artifacts[variable_name]['data']
    
    def list_artifacts(self) -> Dict[str, str]:
        """
        List all registered artifacts.
        
        Returns:
            Dictionary mapping artifact names to their types
        """
        return {name: info['type'] for name, info in self.artifacts.items()}
    
    def _save_artifact_to_file(self, artifact_name: str, data: Any, serializer_func=None) -> str:
        """
        Save artifact to a file using the provided serializer or pickle as default.
        
        Args:
            artifact_name: Name of the artifact
            data: The data to save
            serializer_func: Optional custom serializer function
            
        Returns:
            Relative file path where the artifact was saved
        """
        import pickle
        import base64
        
        # Create safe filename
        safe_name = artifact_name.replace('/', '_').replace('\\', '_')
        file_path = os.path.join(self.artifact_storage_dir, f"{safe_name}.pkl")
        
        if serializer_func:
            # Use custom serializer - save the serialized data
            serialized_data = serializer_func(data)
            with open(file_path, 'wb') as f:
                pickle.dump(serialized_data, f)
        else:
            # Use pickle directly
            with open(file_path, 'wb') as f:
                pickle.dump(data, f)
        
        # Return relative path from MEDIA_ROOT
        return os.path.relpath(file_path, settings.MEDIA_ROOT)
    
    def _load_artifact_from_file(self, file_path: str, deserializer_func=None) -> Any:
        """
        Load artifact from a file using the provided deserializer or pickle as default.
        
        Args:
            file_path: Relative path from MEDIA_ROOT
            deserializer_func: Optional custom deserializer function
            
        Returns:
            The deserialized data
        """
        import pickle
        
        # Get absolute path
        abs_path = os.path.join(settings.MEDIA_ROOT, file_path)
        
        with open(abs_path, 'rb') as f:
            if deserializer_func:
                # Load serialized data then deserialize
                serialized_data = pickle.load(f)
                return deserializer_func(serialized_data)
            else:
                # Use pickle directly
                return pickle.load(f)
    
    def _register_builtin_serializers(self):
        """Register built-in serializers for common types."""
        import pickle
        import base64
        
        # Generic pickle-based serializer for objects that support it
        def pickle_serialize(obj):
            return base64.b64encode(pickle.dumps(obj)).decode('utf-8')
        
        def pickle_deserialize(data):
            return pickle.loads(base64.b64decode(data.encode('utf-8')))
        
        # Try to register pandas DataFrame
        try:
            import pandas as pd
            def df_serialize(df):
                return df.to_json(orient='records')
            
            def df_deserialize(json_str):
                return pd.read_json(json_str, orient='records')
            
            self.register_artifact_type(pd.DataFrame, df_serialize, df_deserialize)
        except ImportError:
            pass
        
        # Try to register numpy arrays
        try:
            import numpy as np
            def np_serialize(arr):
                return {
                    'data': arr.tolist(),
                    'dtype': str(arr.dtype),
                    'shape': arr.shape
                }
            
            def np_deserialize(data):
                return np.array(data['data'], dtype=data['dtype']).reshape(data['shape'])
            
            self.register_artifact_type(np.ndarray, np_serialize, np_deserialize)
        except ImportError:
            pass
        
        # Try to register scikit-learn models (generic pickle approach)
        try:
            import sklearn.base
            self.register_artifact_type(sklearn.base.BaseEstimator, pickle_serialize, pickle_deserialize)
        except ImportError:
            pass
        
        # Try to register PyTorch models
        try:
            import torch.nn
            def torch_serialize(model):
                import io
                buffer = io.BytesIO()
                torch.save(model, buffer)
                return base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            def torch_deserialize(data):
                import io
                buffer = io.BytesIO(base64.b64decode(data.encode('utf-8')))
                return torch.load(buffer)
            
            self.register_artifact_type(torch.nn.Module, torch_serialize, torch_deserialize)
        except ImportError:
            pass
    
    def _load_context_from_storage(self, node_id: str, execution_id: str) -> Dict[str, Any]:
        """
        Load execution context from storage (for container-based execution).
        
        Args:
            node_id: Node UUID
            execution_id: Execution UUID
            
        Returns:
            Execution context dictionary
        """
        try:
            # Try to import Django models (may not be available in containers)
            from ..models import Node, PipelineExecution, NodeConnection, NodeExecution
            
            # Get node and execution info
            node = Node.objects.get(pk=node_id)
            execution = PipelineExecution.objects.get(pk=execution_id)
            
            # Get all node executions from previous nodes
            previous_executions = NodeExecution.objects.filter(
                pipeline_execution=execution,
                status='completed',
                node__order__lt=node.order
            ).order_by('node__order')
            
            # Build context data from previous node outputs
            context_data = {}
            for prev_exec in previous_executions:
                if prev_exec.output_data:
                    context_data.update(prev_exec.output_data)
            
            # Get connections
            connections = list(NodeConnection.objects.filter(
                from_node__pipeline=node.pipeline
            ))
            
            return {
                'node_id': str(node_id),
                'execution_id': str(execution_id),
                'context_data': context_data,
                'connections': connections
            }
            
        except ImportError:
            # Running in container without Django - try to load from file
            return self._load_context_from_file(node_id, execution_id)
        except Exception as e:
            print(f"[WARNING] Failed to load context from storage: {e}")
            return {}
    
    def _load_context_from_file(self, node_id: str, execution_id: str) -> Dict[str, Any]:
        """
        Load execution context from file system (for containerized execution).
        
        Args:
            node_id: Node UUID
            execution_id: Execution UUID
            
        Returns:
            Execution context dictionary
        """
        import pickle
        
        try:
            # Look for context file in artifact storage
            context_file = os.path.join(
                settings.MEDIA_ROOT if hasattr(settings, 'MEDIA_ROOT') else '/tmp',
                'artifacts',
                str(execution_id),
                f'_context_{node_id}.pkl'
            )
            
            if os.path.exists(context_file):
                with open(context_file, 'rb') as f:
                    return pickle.load(f)
        except Exception as e:
            print(f"[WARNING] Failed to load context from file: {e}")
        
        return {}
    
    def _load_artifacts_from_context(self):
        """Load artifacts from context_data (from previous nodes)."""
        if not self.context_data:
            return
            
        # Check for artifacts directly in context_data (from get_outputs)
        # The context_data contains the outputs from previous nodes
        for var_name, value in self.context_data.items():
            if isinstance(value, dict) and value.get('_artifact'):
                try:
                    # Extract artifact info
                    type_str = value.get('_type', value.get('type', ''))
                    file_path = value.get('_file')
                    
                    if not file_path:
                        # Old format with _data - skip or handle legacy
                        continue
                    
                    # Find the appropriate deserializer
                    deserializer = None
                    for registered_type, funcs in self.serializers.items():
                        # Match by short name (e.g., "DataFrame" matches "pandas.core.frame.DataFrame")
                        if (type_str == registered_type or 
                            registered_type.endswith(f".{type_str}") or 
                            type_str.endswith(registered_type) or 
                            registered_type in type_str):
                            deserializer = funcs['deserialize']
                            break
                    
                    # Load from file
                    obj = self._load_artifact_from_file(file_path, deserializer)
                    
                    # Store it as an available artifact
                    self.artifacts[var_name] = {
                        'data': obj,
                        'type': type_str
                    }
                    print(f"[INFO] Node {self.node_id}: Loaded artifact '{var_name}' from file: {file_path}")
                        
                except Exception as e:
                    print(f"[ERROR] Node {self.node_id}: Failed to load artifact '{var_name}': {e}")
                
        # Also check for artifacts in nested artifacts key
        if 'artifacts' in self.context_data:
            artifacts_data = self.context_data['artifacts']
            for var_name, artifact_info in artifacts_data.items():
                try:
                    # Get the type and serialized data
                    type_str = artifact_info.get('type', '')
                    serialized_data = artifact_info.get('serialized_data')
                    
                    if serialized_data is None:
                        continue
                    
                    # Find the appropriate deserializer
                    deserializer = None
                    for registered_type, funcs in self.serializers.items():
                        if type_str.endswith(registered_type) or registered_type in type_str:
                            deserializer = funcs['deserialize']
                            break
                    
                    if deserializer:
                        # Deserialize the object
                        obj = deserializer(serialized_data)
                        # Store it as an available artifact
                        self.artifacts[var_name] = {
                            'data': obj,
                            'type': type_str
                        }
                        print(f"[INFO] Node {self.node_id}: Loaded artifact '{var_name}' from context")
                    else:
                        print(f"[WARNING] Node {self.node_id}: No deserializer found for artifact '{var_name}' of type '{type_str}'")
                        
                except Exception as e:
                    print(f"[ERROR] Node {self.node_id}: Failed to load artifact '{var_name}': {e}")
    
    def get_node_info(self) -> Dict[str, Any]:
        """
        Get information about the current node.
        
        Returns:
            Dictionary with node metadata
        """
        if not self.node_id:
            return {}
            
        try:
            from ..models import Node
            node = Node.objects.get(id=self.node_id)
            return {
                'id': str(node.id),
                'name': node.name,
                'description': node.description,
                'pipeline_id': str(node.pipeline.id),
                'pipeline_name': node.pipeline.name
            }
        except Node.DoesNotExist:
            return {}
    
    def get_execution_info(self) -> Dict[str, Any]:
        """
        Get information about the current pipeline execution.
        
        Returns:
            Dictionary with execution metadata
        """
        if not self.execution_id:
            return {}
            
        try:
            execution = PipelineExecution.objects.get(id=self.execution_id)
            return {
                'id': str(execution.id),
                'pipeline_id': str(execution.pipeline.id),
                'pipeline_name': execution.pipeline.name,
                'status': execution.status,
                'started_at': execution.started_at.isoformat() if execution.started_at else None,
                'created_by': execution.created_by.username if execution.created_by else None
            }
        except PipelineExecution.DoesNotExist:
            return {}


class NodeExecutionContext:
    """
    Context manager for node execution with automatic cleanup and output capture.
    """
    
    def __init__(self, node: Node, execution: PipelineExecution, 
                 context_data: Dict[str, Any], connections: List[NodeConnection]):
        self.node = node
        self.execution = execution
        self.context_data = context_data
        self.connections = connections
        self.warpdrive = None
        
    def __enter__(self) -> WarpDrive:
        """Enter the execution context and create WarpDrive instance."""
        execution_context = {
            'node_id': str(self.node.id),
            'execution_id': str(self.execution.id),
            'context_data': self.context_data,
            'connections': self.connections
        }
        
        self.warpdrive = WarpDrive(execution_context)
        return self.warpdrive
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit the execution context and capture outputs."""
        if self.warpdrive and not exc_type:
            # Capture outputs automatically
            outputs = self.warpdrive.get_outputs()
            
            # Update node execution with outputs
            try:
                node_execution = NodeExecution.objects.filter(
                    pipeline_execution=self.execution,
                    node=self.node
                ).latest('started_at')
                
                current_output = node_execution.output_data or {}
                current_output.update(outputs)
                node_execution.output_data = current_output
                node_execution.save()
                
            except NodeExecution.DoesNotExist:
                pass