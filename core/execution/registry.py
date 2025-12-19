"""
Execution registry for managing different execution backends.
"""

from typing import Dict, Type, Optional
from django.conf import settings
from .backends import ExecutionBackend, LocalExecutionBackend, KubernetesExecutionBackend, CloudFunctionBackend


class ExecutionRegistry:
    """Registry for managing execution backends."""
    
    _backends: Dict[str, Type[ExecutionBackend]] = {
        'local': LocalExecutionBackend,
        'kubernetes': KubernetesExecutionBackend,
        'aws': CloudFunctionBackend,
        'gcp': CloudFunctionBackend,
    }
    
    _instances: Dict[str, ExecutionBackend] = {}
    
    @classmethod
    def register_backend(cls, name: str, backend_class: Type[ExecutionBackend]):
        """Register a new execution backend."""
        cls._backends[name] = backend_class
    
    @classmethod
    def get_backend(cls, name: Optional[str] = None) -> ExecutionBackend:
        """Get an execution backend instance."""
        
        # Use default from settings if no name provided
        if name is None:
            name = getattr(settings, 'PIPELINE_EXECUTION_BACKEND', 'local')
        
        # Return cached instance if exists
        if name in cls._instances:
            return cls._instances[name]
        
        # Create new instance
        if name not in cls._backends:
            raise ValueError(f"Unknown execution backend: {name}")
        
        backend_class = cls._backends[name]
        
        # Get backend configuration from settings
        backend_config = getattr(settings, 'PIPELINE_BACKEND_CONFIG', {}).get(name, {})
        
        # Create and cache instance
        instance = backend_class(**backend_config)
        cls._instances[name] = instance
        
        return instance
    
    @classmethod
    def list_backends(cls) -> list:
        """List all available backend names."""
        return list(cls._backends.keys())
    
    @classmethod
    def clear_cache(cls):
        """Clear cached backend instances."""
        cls._instances.clear()


# Convenience function
def get_execution_backend(name: Optional[str] = None) -> ExecutionBackend:
    """Get an execution backend instance."""
    return ExecutionRegistry.get_backend(name)