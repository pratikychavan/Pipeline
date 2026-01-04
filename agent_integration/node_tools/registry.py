"""
Node Tool Registry - Maps nodes to tool wrappers.

This module provides a registry for discovering and instantiating
node tool wrappers. It does NOT modify node execution logic.
"""

import uuid
from typing import Dict, List, Optional
from django.core.cache import cache

from core.models import Node, Pipeline
from .executor import NodeToolExecutor


class NodeToolRegistry:
    """
    Registry for node tool wrappers.
    
    This provides a central place to:
    - Discover all nodes in a pipeline
    - Create tool wrappers for nodes
    - Cache tool instances
    """
    
    _cache_timeout = 300  # 5 minutes
    
    @classmethod
    def get_tools_for_pipeline(cls, pipeline_id: uuid.UUID) -> List[NodeToolExecutor]:
        """
        Get all tool wrappers for nodes in a pipeline.
        
        Args:
            pipeline_id: Pipeline to get tools for
        
        Returns:
            List of NodeToolExecutor instances
        """
        cache_key = f'node_tools:pipeline:{pipeline_id}'
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        # Query nodes for this pipeline
        nodes = Node.objects.filter(
            pipeline_id=pipeline_id
        ).select_related('pipeline').order_by('order')
        
        # Create tool wrapper for each node
        tools = [
            NodeToolExecutor(
                node_id=node.id,
                node_name=node.name,
                node=node,  # Pass node to avoid extra query
            )
            for node in nodes
        ]
        
        cache.set(cache_key, tools, cls._cache_timeout)
        return tools
    
    @classmethod
    def get_tool_by_node_id(cls, node_id: uuid.UUID) -> Optional[NodeToolExecutor]:
        """
        Get tool wrapper for a specific node.
        
        Args:
            node_id: Node to get tool for
        
        Returns:
            NodeToolExecutor or None if not found
        """
        cache_key = f'node_tool:{node_id}'
        cached = cache.get(cache_key)
        
        if cached:
            return cached
        
        try:
            node = Node.objects.select_related('pipeline').get(pk=node_id)
            tool = NodeToolExecutor(
                node_id=node.id,
                node_name=node.name,
                node=node,
            )
            cache.set(cache_key, tool, cls._cache_timeout)
            return tool
        except Node.DoesNotExist:
            return None
    
    @classmethod
    def get_tool_by_name(
        cls,
        pipeline_id: uuid.UUID,
        node_name: str,
    ) -> Optional[NodeToolExecutor]:
        """
        Get tool wrapper by node name within a pipeline.
        
        Args:
            pipeline_id: Pipeline containing the node
            node_name: Name of the node
        
        Returns:
            NodeToolExecutor or None if not found
        """
        try:
            node = Node.objects.select_related('pipeline').get(
                pipeline_id=pipeline_id,
                name=node_name,
            )
            return NodeToolExecutor(
                node_id=node.id,
                node_name=node.name,
                node=node,
            )
        except Node.DoesNotExist:
            return None
    
    @classmethod
    def get_tool_definitions(cls, pipeline_id: uuid.UUID) -> List[Dict]:
        """
        Get tool definitions for all nodes in a pipeline.
        
        This is what gets passed to the agent for tool selection.
        
        Args:
            pipeline_id: Pipeline to get tool definitions for
        
        Returns:
            List of tool definition dictionaries
        """
        tools = cls.get_tools_for_pipeline(pipeline_id)
        return [tool.get_tool_definition() for tool in tools]
    
    @classmethod
    def invalidate_cache(cls, pipeline_id: Optional[uuid.UUID] = None):
        """
        Invalidate cached tool wrappers.
        
        Call this when nodes are added/modified/deleted.
        
        Args:
            pipeline_id: If provided, only invalidate for this pipeline
        """
        if pipeline_id:
            cache.delete(f'node_tools:pipeline:{pipeline_id}')
        else:
            # Clear all node tool caches
            cache.delete_pattern('node_tools:*')
            cache.delete_pattern('node_tool:*')


# Convenience function for direct access
def get_node_tool(node_id: uuid.UUID) -> Optional[NodeToolExecutor]:
    """
    Get a node tool wrapper by node ID.
    
    This is a convenience wrapper around NodeToolRegistry.
    
    Args:
        node_id: Node to wrap
    
    Returns:
        NodeToolExecutor or None
    """
    return NodeToolRegistry.get_tool_by_node_id(node_id)
