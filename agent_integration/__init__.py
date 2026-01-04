"""
Agent Integration Layer for Pipeline System

This module provides LLM-based orchestration ON TOP OF the existing
deterministic pipeline execution engine.

The LLM acts as a CONTROLLER, not a processor.
It decides execution flow, but does not execute nodes directly.
"""

__version__ = '1.0.0'
