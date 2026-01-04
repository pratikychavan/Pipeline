"""
Control Plane views for agent configuration management.

These views handle CRUD operations for:
- Agent profiles
- Tool definitions
- Agent-Tool mappings
- Business conditions
- Agent-Condition bindings
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_http_methods, require_POST
from django.db.models import Count, Q
from django import forms

from .control_plane_models import (
    AgentProfile,
    ToolDefinition,
    AgentToolMapping,
    BusinessCondition,
    AgentConditionBinding,
)
from .control_plane_forms import (
    AgentProfileForm,
    ToolDefinitionForm,
    AgentToolMappingForm,
    BusinessConditionForm,
    AgentConditionBindingForm,
)


# ============================================================================
# AGENT PROFILE CRUD
# ============================================================================

@login_required
def agent_list(request):
    """List all agent profiles."""
    agents = AgentProfile.objects.all().annotate(
        tool_count=Count('tool_mappings'),
        condition_count=Count('condition_bindings')
    )
    
    # Filter by status if provided
    status_filter = request.GET.get('status')
    if status_filter:
        agents = agents.filter(status=status_filter)
    
    context = {
        'agents': agents,
        'status_filter': status_filter,
        'title': 'Agent Profiles'
    }
    
    return render(request, 'agent_integration/control_plane/agent_list.html', context)


@login_required
def agent_list_api(request):
    """API endpoint to list active agent profiles."""
    from django.http import JsonResponse
    
    agents = AgentProfile.objects.filter(status='active').values(
        'id', 'name', 'description', 'llm_config', 'status'
    )
    
    return JsonResponse({
        'agents': list(agents)
    })


@login_required
def agent_create(request):
    """Create a new agent profile."""
    if request.method == 'POST':
        form = AgentProfileForm(request.POST)
        if form.is_valid():
            agent = form.save(commit=False)
            agent.created_by = request.user
            agent.save()
            
            messages.success(request, f"Agent profile '{agent.name}' created successfully.")
            return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    else:
        form = AgentProfileForm()
    
    context = {
        'form': form,
        'title': 'Create Agent Profile',
        'action': 'Create'
    }
    
    return render(request, 'agent_integration/control_plane/agent_form.html', context)


@login_required
def agent_detail(request, agent_id):
    """View agent profile details."""
    agent = get_object_or_404(
        AgentProfile.objects.annotate(
            tool_count=Count('tool_mappings'),
            condition_count=Count('condition_bindings')
        ),
        pk=agent_id
    )
    
    tool_mappings = agent.tool_mappings.select_related('tool').all()
    condition_bindings = agent.condition_bindings.select_related('condition').all()
    
    context = {
        'agent': agent,
        'tool_mappings': tool_mappings,
        'condition_bindings': condition_bindings,
        'title': f'Agent: {agent.name}'
    }
    
    return render(request, 'agent_integration/control_plane/agent_detail.html', context)


@login_required
def agent_edit(request, agent_id):
    """Edit agent profile."""
    agent = get_object_or_404(AgentProfile, pk=agent_id)
    
    # Check if agent can be edited
    if agent.status == 'active':
        messages.warning(
            request,
            "Warning: Editing an active agent may affect ongoing executions. Consider creating a new version instead."
        )
    
    if request.method == 'POST':
        form = AgentProfileForm(request.POST, instance=agent)
        if form.is_valid():
            form.save()
            messages.success(request, f"Agent profile '{agent.name}' updated successfully.")
            return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    else:
        form = AgentProfileForm(instance=agent)
    
    context = {
        'form': form,
        'agent': agent,
        'title': f'Edit Agent: {agent.name}',
        'action': 'Update'
    }
    
    return render(request, 'agent_integration/control_plane/agent_form.html', context)


@login_required
@require_POST
def agent_activate(request, agent_id):
    """Activate an agent profile."""
    agent = get_object_or_404(AgentProfile, pk=agent_id)
    
    if agent.status != 'draft':
        messages.error(request, "Only draft agents can be activated.")
        return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    
    # TODO: Validate agent completeness (has tools, conditions, etc.)
    
    agent.status = 'active'
    agent.save()
    
    messages.success(request, f"Agent '{agent.name}' activated successfully.")
    return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)


@login_required
@require_POST
def agent_deactivate(request, agent_id):
    """Deactivate an agent profile."""
    agent = get_object_or_404(AgentProfile, pk=agent_id)
    
    if agent.status != 'active':
        messages.error(request, "Only active agents can be deactivated.")
        return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    
    # TODO: Check for active runs
    
    agent.status = 'archived'
    agent.save()
    
    messages.success(request, f"Agent '{agent.name}' deactivated and archived.")
    return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)


# ============================================================================
# TOOL DEFINITION CRUD
# ============================================================================

@login_required
def tool_list(request):
    """List all tool definitions."""
    tools = ToolDefinition.objects.all().annotate(
        agent_count=Count('agent_mappings')
    )
    
    # Filter by enabled status if provided
    enabled_filter = request.GET.get('enabled')
    if enabled_filter == 'true':
        tools = tools.filter(is_enabled=True)
    elif enabled_filter == 'false':
        tools = tools.filter(is_enabled=False)
    
    context = {
        'tools': tools,
        'enabled_filter': enabled_filter,
        'title': 'Tool Registry'
    }
    
    return render(request, 'agent_integration/control_plane/tool_list.html', context)


@login_required
def tool_create(request):
    """Create a new tool definition."""
    if request.method == 'POST':
        form = ToolDefinitionForm(request.POST)
        if form.is_valid():
            tool = form.save()
            messages.success(request, f"Tool '{tool.name}' registered successfully.")
            return redirect('agent_integration:cp_tool_detail', tool_id=tool.id)
    else:
        form = ToolDefinitionForm()
    
    context = {
        'form': form,
        'title': 'Register Tool',
        'action': 'Register'
    }
    
    return render(request, 'agent_integration/control_plane/tool_form.html', context)


@login_required
def tool_detail(request, tool_id):
    """View tool definition details."""
    tool = get_object_or_404(
        ToolDefinition.objects.annotate(
            agent_count=Count('agent_mappings')
        ),
        pk=tool_id
    )
    
    agent_mappings = tool.agent_mappings.select_related('agent').all()
    
    context = {
        'tool': tool,
        'agent_mappings': agent_mappings,
        'title': f'Tool: {tool.name}'
    }
    
    return render(request, 'agent_integration/control_plane/tool_detail.html', context)


@login_required
def tool_edit(request, tool_id):
    """Edit tool definition."""
    tool = get_object_or_404(ToolDefinition, pk=tool_id)
    
    if request.method == 'POST':
        form = ToolDefinitionForm(request.POST, instance=tool)
        if form.is_valid():
            form.save()
            messages.success(request, f"Tool '{tool.name}' updated successfully.")
            return redirect('agent_integration:cp_tool_detail', tool_id=tool.id)
    else:
        form = ToolDefinitionForm(instance=tool)
    
    context = {
        'form': form,
        'tool': tool,
        'title': f'Edit Tool: {tool.name}',
        'action': 'Update'
    }
    
    return render(request, 'agent_integration/control_plane/tool_form.html', context)


@login_required
@require_POST
def tool_toggle_enabled(request, tool_id):
    """Toggle tool enabled status."""
    tool = get_object_or_404(ToolDefinition, pk=tool_id)
    tool.is_enabled = not tool.is_enabled
    tool.save()
    
    status = "enabled" if tool.is_enabled else "disabled"
    messages.success(request, f"Tool '{tool.name}' {status}.")
    return redirect('agent_integration:cp_tool_detail', tool_id=tool.id)


# ============================================================================
# AGENT-TOOL MAPPING CRUD
# ============================================================================

@login_required
def agent_tool_mapping_create(request, agent_id):
    """Create a tool mapping for an agent."""
    agent = get_object_or_404(AgentProfile, pk=agent_id)
    
    if request.method == 'POST':
        form = AgentToolMappingForm(request.POST)
        if form.is_valid():
            mapping = form.save(commit=False)
            mapping.agent = agent
            mapping.save()
            
            messages.success(request, f"Tool '{mapping.tool.name}' mapped to agent '{agent.name}'.")
            return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    else:
        form = AgentToolMappingForm(initial={'agent': agent})
        form.fields['agent'].widget = forms.HiddenInput()
    
    context = {
        'form': form,
        'agent': agent,
        'title': f'Add Tool to {agent.name}',
        'action': 'Add'
    }
    
    return render(request, 'agent_integration/control_plane/mapping_form.html', context)


@login_required
def agent_tool_mapping_edit(request, mapping_id):
    """Edit an agent-tool mapping."""
    mapping = get_object_or_404(AgentToolMapping, pk=mapping_id)
    
    if request.method == 'POST':
        form = AgentToolMappingForm(request.POST, instance=mapping)
        if form.is_valid():
            form.save()
            messages.success(request, "Tool mapping updated successfully.")
            return redirect('agent_integration:cp_agent_detail', agent_id=mapping.agent.id)
    else:
        form = AgentToolMappingForm(instance=mapping)
    
    context = {
        'form': form,
        'mapping': mapping,
        'title': f'Edit Mapping: {mapping.tool.name}',
        'action': 'Update'
    }
    
    return render(request, 'agent_integration/control_plane/mapping_form.html', context)


@login_required
@require_POST
def agent_tool_mapping_delete(request, mapping_id):
    """Delete an agent-tool mapping."""
    mapping = get_object_or_404(AgentToolMapping, pk=mapping_id)
    agent_id = mapping.agent.id
    tool_name = mapping.tool.name
    
    mapping.delete()
    messages.success(request, f"Tool '{tool_name}' removed from agent.")
    return redirect('agent_integration:cp_agent_detail', agent_id=agent_id)


# ============================================================================
# BUSINESS CONDITION CRUD
# ============================================================================

@login_required
def condition_list(request):
    """List all business conditions."""
    conditions = BusinessCondition.objects.all().annotate(
        agent_count=Count('agent_bindings')
    )
    
    # Filter by active status
    active_filter = request.GET.get('active')
    if active_filter == 'true':
        conditions = conditions.filter(is_active=True)
    elif active_filter == 'false':
        conditions = conditions.filter(is_active=False)
    
    context = {
        'conditions': conditions,
        'active_filter': active_filter,
        'title': 'Business Conditions'
    }
    
    return render(request, 'agent_integration/control_plane/condition_list.html', context)


@login_required
def condition_create(request):
    """Create a new business condition."""
    if request.method == 'POST':
        form = BusinessConditionForm(request.POST)
        if form.is_valid():
            condition = form.save()
            messages.success(request, f"Condition '{condition.name}' created successfully.")
            return redirect('agent_integration:cp_condition_detail', condition_id=condition.id)
    else:
        form = BusinessConditionForm()
    
    context = {
        'form': form,
        'title': 'Create Business Condition',
        'action': 'Create'
    }
    
    return render(request, 'agent_integration/control_plane/condition_form.html', context)


@login_required
def condition_detail(request, condition_id):
    """View business condition details."""
    condition = get_object_or_404(
        BusinessCondition.objects.annotate(
            agent_count=Count('agent_bindings')
        ),
        pk=condition_id
    )
    
    agent_bindings = condition.agent_bindings.select_related('agent').all()
    
    context = {
        'condition': condition,
        'agent_bindings': agent_bindings,
        'title': f'Condition: {condition.name}'
    }
    
    return render(request, 'agent_integration/control_plane/condition_detail.html', context)


@login_required
def condition_edit(request, condition_id):
    """Edit business condition."""
    condition = get_object_or_404(BusinessCondition, pk=condition_id)
    
    # Check if condition is bound to active agents
    active_bindings_count = condition.agent_bindings.filter(
        agent__status='active',
        is_enabled=True
    ).count()
    
    if active_bindings_count > 0:
        messages.warning(
            request,
            f"Warning: This condition is bound to {active_bindings_count} active agent(s). Changes may affect ongoing executions."
        )
    
    if request.method == 'POST':
        form = BusinessConditionForm(request.POST, instance=condition)
        if form.is_valid():
            form.save()
            messages.success(request, f"Condition '{condition.name}' updated successfully.")
            return redirect('agent_integration:cp_condition_detail', condition_id=condition.id)
    else:
        form = BusinessConditionForm(instance=condition)
    
    context = {
        'form': form,
        'condition': condition,
        'title': f'Edit Condition: {condition.name}',
        'action': 'Update'
    }
    
    return render(request, 'agent_integration/control_plane/condition_form.html', context)


# ============================================================================
# AGENT-CONDITION BINDING CRUD
# ============================================================================

@login_required
def agent_condition_binding_create(request, agent_id):
    """Create a condition binding for an agent."""
    agent = get_object_or_404(AgentProfile, pk=agent_id)
    
    if request.method == 'POST':
        form = AgentConditionBindingForm(request.POST)
        if form.is_valid():
            binding = form.save(commit=False)
            binding.agent = agent
            binding.save()
            
            messages.success(request, f"Condition '{binding.condition.name}' bound to agent '{agent.name}'.")
            return redirect('agent_integration:cp_agent_detail', agent_id=agent.id)
    else:
        form = AgentConditionBindingForm(initial={'agent': agent})
        form.fields['agent'].widget = forms.HiddenInput()
    
    context = {
        'form': form,
        'agent': agent,
        'title': f'Add Condition to {agent.name}',
        'action': 'Add'
    }
    
    return render(request, 'agent_integration/control_plane/binding_form.html', context)


@login_required
def agent_condition_binding_edit(request, binding_id):
    """Edit an agent-condition binding."""
    binding = get_object_or_404(AgentConditionBinding, pk=binding_id)
    
    if request.method == 'POST':
        form = AgentConditionBindingForm(request.POST, instance=binding)
        if form.is_valid():
            form.save()
            messages.success(request, "Condition binding updated successfully.")
            return redirect('agent_integration:cp_agent_detail', agent_id=binding.agent.id)
    else:
        form = AgentConditionBindingForm(instance=binding)
    
    context = {
        'form': form,
        'binding': binding,
        'title': f'Edit Binding: {binding.condition.name}',
        'action': 'Update'
    }
    
    return render(request, 'agent_integration/control_plane/binding_form.html', context)


@login_required
@require_POST
def agent_condition_binding_delete(request, binding_id):
    """Delete an agent-condition binding."""
    binding = get_object_or_404(AgentConditionBinding, pk=binding_id)
    agent_id = binding.agent.id
    condition_name = binding.condition.name
    
    binding.delete()
    messages.success(request, f"Condition '{condition_name}' removed from agent.")
    return redirect('agent_integration:cp_agent_detail', agent_id=agent_id)


# ============================================================================
# CONTROL PLANE DASHBOARD
# ============================================================================

@login_required
def control_plane_dashboard(request):
    """Main control plane dashboard."""
    stats = {
        'agent_count': AgentProfile.objects.count(),
        'active_agents': AgentProfile.objects.filter(status='active').count(),
        'tool_count': ToolDefinition.objects.count(),
        'enabled_tools': ToolDefinition.objects.filter(is_enabled=True).count(),
        'condition_count': BusinessCondition.objects.count(),
        'active_conditions': BusinessCondition.objects.filter(is_active=True).count(),
    }
    
    recent_agents = AgentProfile.objects.all().order_by('-created_at')[:5]
    recent_tools = ToolDefinition.objects.all().order_by('-created_at')[:5]
    recent_conditions = BusinessCondition.objects.all().order_by('-created_at')[:5]
    
    context = {
        'stats': stats,
        'recent_agents': recent_agents,
        'recent_tools': recent_tools,
        'recent_conditions': recent_conditions,
        'title': 'Control Plane Dashboard'
    }
    
    return render(request, 'agent_integration/control_plane/dashboard.html', context)
