from django.urls import path
from . import views
from .test_views import drag_test

urlpatterns = [
    # Pipeline management
    path('', views.PipelineListView.as_view(), name='pipeline_list'),
    path('create/', views.PipelineCreateView.as_view(), name='pipeline_create'),
    path('<uuid:pk>/', views.pipeline_detail, name='pipeline_detail'),
    path('<uuid:pk>/edit/', views.PipelineUpdateView.as_view(), name='pipeline_update'),
    path('<uuid:pk>/delete/', views.PipelineDeleteView.as_view(), name='pipeline_delete'),
    path('<uuid:pk>/execute/', views.execute_pipeline, name='execute_pipeline'),
    path('<uuid:pk>/status/', views.pipeline_status, name='pipeline_status'),
    path('<uuid:pk>/executions/', views.pipeline_executions, name='pipeline_executions'),
    
    # Node management
    path('<uuid:pipeline_pk>/nodes/create/', views.node_create, name='node_create'),
    path('nodes/<uuid:pk>/edit/', views.node_edit, name='node_edit'),
    path('nodes/<uuid:pk>/delete/', views.node_delete, name='node_delete'),
    path('nodes/<uuid:pk>/variables/', views.get_node_variables, name='get_node_variables'),
    path('nodes/<uuid:pk>/code/', views.get_node_code, name='get_node_code'),
    
    # Code analysis
    path('ajax/detect-outputs/', views.detect_outputs, name='detect_outputs'),
    path('ajax/pipeline-inputs/<uuid:pk>/', views.get_pipeline_inputs, name='get_pipeline_inputs'),
    
    # Execution management
    path('executions/', views.execution_list, name='execution_list'),
    path('executions/<uuid:pk>/', views.execution_detail, name='execution_detail'),
    
    # AJAX endpoints
    path('ajax/update-node-position/', views.update_node_position, name='update_node_position'),
    path('ajax/create-connection/', views.create_connection, name='create_connection'),
    
    # Test endpoints
    path('test/drag/', drag_test, name='drag_test'),
]