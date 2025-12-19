"""
Pipeline Execution Package

This package provides a clean interface for executing pipeline nodes,
similar to the POC's WarpDrive but integrated with Django models.
"""

from .warpdrive import WarpDrive
from .backends import LocalExecutionBackend, KubernetesExecutionBackend
from .registry import ExecutionRegistry, get_execution_backend

__all__ = ['WarpDrive', 'LocalExecutionBackend', 'KubernetesExecutionBackend', 'ExecutionRegistry', 'get_execution_backend']