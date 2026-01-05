"""
URL configuration for agent integration API and UI.
"""

from django.urls import path
from . import views, ui_views, control_plane_views as cp_views

app_name = 'agent_integration'

urlpatterns = [
    # UI Views (for integration testing)
    path('dashboard/', ui_views.agent_dashboard, name='agent_dashboard'),
    path('runs/<uuid:agent_run_id>/detail/', ui_views.agent_run_detail, name='agent_run_detail'),
    path('runs/<uuid:agent_run_id>/graph/', ui_views.agent_run_graph_view, name='agent_run_graph_view'),
    path('runs/<uuid:agent_run_id>/debug/', ui_views.debug_context_view, name='debug_context_view'),
    path('pipelines/<uuid:pipeline_id>/start/', ui_views.start_agent_run_ui, name='start_agent_run_ui'),
    path('runs/<uuid:agent_run_id>/resume/', ui_views.resume_agent_run, name='resume_agent_run'),
    path('runs/<uuid:agent_run_id>/abort/', ui_views.abort_agent_run, name='abort_agent_run'),
    
    # Control Plane Dashboard
    path('control-plane/', cp_views.control_plane_dashboard, name='cp_dashboard'),
    
    # Agent Profile Views (READ-ONLY + GOVERNANCE)
    path('control-plane/agents/', cp_views.agent_list, name='cp_agent_list'),
    path('control-plane/agents/api/', cp_views.agent_list_api, name='cp_agent_list_api'),
    path('control-plane/agents/bind-workspace/', cp_views.agent_create_from_workspace, name='cp_agent_create_from_workspace'),
    path('control-plane/agents/<uuid:agent_id>/', cp_views.agent_detail, name='cp_agent_detail'),
    path('control-plane/agents/<uuid:agent_id>/validate/', cp_views.agent_validate, name='cp_agent_validate'),
    path('control-plane/agents/<uuid:agent_id>/activate/', cp_views.agent_activate, name='cp_agent_activate'),
    path('control-plane/agents/<uuid:agent_id>/deactivate/', cp_views.agent_deactivate, name='cp_agent_deactivate'),
    
    # Tool Definition CRUD
    path('control-plane/tools/', cp_views.tool_list, name='cp_tool_list'),
    path('control-plane/tools/create/', cp_views.tool_create, name='cp_tool_create'),
    path('control-plane/tools/<uuid:tool_id>/', cp_views.tool_detail, name='cp_tool_detail'),
    path('control-plane/tools/<uuid:tool_id>/edit/', cp_views.tool_edit, name='cp_tool_edit'),
    path('control-plane/tools/<uuid:tool_id>/toggle/', cp_views.tool_toggle_enabled, name='cp_tool_toggle'),
    
    # Agent-Tool Mapping CRUD
    path('control-plane/agents/<uuid:agent_id>/tools/add/', cp_views.agent_tool_mapping_create, name='cp_mapping_create'),
    path('control-plane/mappings/<uuid:mapping_id>/edit/', cp_views.agent_tool_mapping_edit, name='cp_mapping_edit'),
    path('control-plane/mappings/<uuid:mapping_id>/delete/', cp_views.agent_tool_mapping_delete, name='cp_mapping_delete'),
    
    # Business Condition CRUD
    path('control-plane/conditions/', cp_views.condition_list, name='cp_condition_list'),
    path('control-plane/conditions/create/', cp_views.condition_create, name='cp_condition_create'),
    path('control-plane/conditions/<uuid:condition_id>/', cp_views.condition_detail, name='cp_condition_detail'),
    path('control-plane/conditions/<uuid:condition_id>/edit/', cp_views.condition_edit, name='cp_condition_edit'),
    
    # Agent-Condition Binding CRUD
    path('control-plane/agents/<uuid:agent_id>/conditions/add/', cp_views.agent_condition_binding_create, name='cp_binding_create'),
    path('control-plane/bindings/<uuid:binding_id>/edit/', cp_views.agent_condition_binding_edit, name='cp_binding_edit'),
    path('control-plane/bindings/<uuid:binding_id>/delete/', cp_views.agent_condition_binding_delete, name='cp_binding_delete'),
    
    # API endpoints (existing)
    path('api/pipelines/<uuid:pipeline_id>/execute/', views.start_agent_run, name='start_agent_run'),
    path('api/runs/<uuid:agent_run_id>/', views.get_agent_run_status, name='agent_run_status'),
    path('api/runs/<uuid:agent_run_id>/decisions/', views.get_agent_decisions, name='agent_decisions'),
    path('api/runs/<uuid:agent_run_id>/spec/', views.get_runtime_spec, name='runtime_spec'),
    path('api/runs/<uuid:agent_run_id>/respond/', views.respond_to_human_intervention, name='respond_intervention'),
]
