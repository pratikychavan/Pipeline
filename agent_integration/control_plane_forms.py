"""
Forms for Control Plane CRUD operations.
"""

from django import forms
from django.core.exceptions import ValidationError
import json

from .control_plane_models import (
    AgentProfile,
    ToolDefinition,
    AgentToolMapping,
    BusinessCondition,
    AgentConditionBinding,
)


class AgentProfileForm(forms.ModelForm):
    """Form for creating/editing agent profiles."""
    
    retry_policy_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control font-monospace'}),
        required=False,
        help_text="JSON format: {\"backoff_seconds\": 5, \"max_attempts\": 3}"
    )
    
    guardrail_config_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'class': 'form-control font-monospace'}),
        required=False,
        help_text="JSON format: {\"loop_detection\": true, \"max_loop_iterations\": 10}"
    )
    
    llm_config_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control font-monospace'}),
        required=False,
        help_text="JSON format: {\"max_tokens\": 2000, \"top_p\": 1.0}"
    )
    
    class Meta:
        model = AgentProfile
        fields = [
            'name',
            'description',
            'status',
            'max_steps',
            'max_retries',
            'require_human_approval',
            'llm_model',
            'llm_temperature',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
            'max_steps': forms.NumberInput(attrs={'class': 'form-control'}),
            'max_retries': forms.NumberInput(attrs={'class': 'form-control'}),
            'require_human_approval': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'llm_model': forms.TextInput(attrs={'class': 'form-control'}),
            'llm_temperature': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate JSON fields from model
        if self.instance and self.instance.pk:
            self.fields['retry_policy_json'].initial = json.dumps(
                self.instance.retry_policy, indent=2
            ) if self.instance.retry_policy else '{}'
            
            self.fields['guardrail_config_json'].initial = json.dumps(
                self.instance.guardrail_config, indent=2
            ) if self.instance.guardrail_config else '{}'
            
            self.fields['llm_config_json'].initial = json.dumps(
                self.instance.llm_config, indent=2
            ) if self.instance.llm_config else '{}'
    
    def clean_retry_policy_json(self):
        """Validate and parse retry policy JSON."""
        data = self.cleaned_data['retry_policy_json']
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def clean_guardrail_config_json(self):
        """Validate and parse guardrail config JSON."""
        data = self.cleaned_data['guardrail_config_json']
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def clean_llm_config_json(self):
        """Validate and parse LLM config JSON."""
        data = self.cleaned_data['llm_config_json']
        if not data:
            return {}
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def clean_status(self):
        """Validate status transitions."""
        status = self.cleaned_data['status']
        
        if self.instance and self.instance.pk:
            old_status = self.instance.status
            
            # Prevent activating without confirmation (handled in view)
            if old_status == 'draft' and status == 'active':
                # TODO: Add check for agent completeness
                pass
            
            # Prevent unarchiving without explicit action
            if old_status == 'archived' and status != 'archived':
                raise ValidationError("Cannot change status of archived agent. Create a new agent instead.")
        
        return status
    
    def save(self, commit=True):
        """Save with JSON fields."""
        instance = super().save(commit=False)
        
        # Set JSON fields from cleaned data
        instance.retry_policy = self.cleaned_data['retry_policy_json']
        instance.guardrail_config = self.cleaned_data['guardrail_config_json']
        instance.llm_config = self.cleaned_data['llm_config_json']
        
        if commit:
            instance.save()
        
        return instance


class ToolDefinitionForm(forms.ModelForm):
    """Form for creating/editing tool definitions."""
    
    input_schema_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'class': 'form-control font-monospace'}),
        help_text='JSON Schema: {"type": "object", "properties": {...}}'
    )
    
    output_schema_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'class': 'form-control font-monospace'}),
        help_text='JSON Schema: {"type": "object", "properties": {...}}'
    )
    
    class Meta:
        model = ToolDefinition
        fields = [
            'name',
            'description',
            'executor_type',
            'pipeline',
            'node_name',
            'is_enabled',
            'estimated_duration_seconds',
            'cost_estimate',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'executor_type': forms.Select(attrs={'class': 'form-select'}),
            'pipeline': forms.Select(attrs={'class': 'form-select'}),
            'node_name': forms.TextInput(attrs={'class': 'form-control'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'estimated_duration_seconds': forms.NumberInput(attrs={'class': 'form-control'}),
            'cost_estimate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Populate JSON fields from model
        if self.instance and self.instance.pk:
            self.fields['input_schema_json'].initial = json.dumps(
                self.instance.input_schema, indent=2
            )
            self.fields['output_schema_json'].initial = json.dumps(
                self.instance.output_schema, indent=2
            )
    
    def clean_input_schema_json(self):
        """Validate input schema JSON."""
        data = self.cleaned_data['input_schema_json']
        try:
            schema = json.loads(data)
            # Basic JSON Schema validation
            if not isinstance(schema, dict):
                raise ValidationError("Schema must be a JSON object")
            return schema
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def clean_output_schema_json(self):
        """Validate output schema JSON."""
        data = self.cleaned_data['output_schema_json']
        try:
            schema = json.loads(data)
            if not isinstance(schema, dict):
                raise ValidationError("Schema must be a JSON object")
            return schema
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def save(self, commit=True):
        """Save with JSON fields."""
        instance = super().save(commit=False)
        
        instance.input_schema = self.cleaned_data['input_schema_json']
        instance.output_schema = self.cleaned_data['output_schema_json']
        
        if commit:
            instance.save()
        
        return instance


class AgentToolMappingForm(forms.ModelForm):
    """Form for mapping tools to agents."""
    
    prerequisites_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'form-control font-monospace'}),
        required=False,
        help_text='JSON array: ["tool_name_1", "tool_name_2"]'
    )
    
    class Meta:
        model = AgentToolMapping
        fields = [
            'agent',
            'tool',
            'is_allowed',
            'max_calls',
            'priority',
            'notes',
        ]
        widgets = {
            'agent': forms.Select(attrs={'class': 'form-select'}),
            'tool': forms.Select(attrs={'class': 'form-select'}),
            'is_allowed': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'max_calls': forms.NumberInput(attrs={'class': 'form-control'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'rows': 2, 'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            self.fields['prerequisites_json'].initial = json.dumps(
                self.instance.prerequisites, indent=2
            ) if self.instance.prerequisites else '[]'
    
    def clean_prerequisites_json(self):
        """Validate prerequisites JSON."""
        data = self.cleaned_data['prerequisites_json']
        if not data:
            return []
        try:
            prereqs = json.loads(data)
            if not isinstance(prereqs, list):
                raise ValidationError("Prerequisites must be a JSON array")
            return prereqs
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def save(self, commit=True):
        """Save with JSON fields."""
        instance = super().save(commit=False)
        instance.prerequisites = self.cleaned_data['prerequisites_json']
        
        if commit:
            instance.save()
        
        return instance


class BusinessConditionForm(forms.ModelForm):
    """Form for creating business conditions."""
    
    condition_config_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 6, 'class': 'form-control font-monospace'}),
        help_text='Configuration for condition evaluation'
    )
    
    test_cases_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 4, 'class': 'form-control font-monospace'}),
        required=False,
        help_text='Array of test cases: [{"input": {...}, "expected": true}]'
    )
    
    class Meta:
        model = BusinessCondition
        fields = [
            'name',
            'description',
            'version',
            'condition_type',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'rows': 3, 'class': 'form-control'}),
            'version': forms.TextInput(attrs={'class': 'form-control'}),
            'condition_type': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            self.fields['condition_config_json'].initial = json.dumps(
                self.instance.condition_config, indent=2
            )
            self.fields['test_cases_json'].initial = json.dumps(
                self.instance.test_cases, indent=2
            ) if self.instance.test_cases else '[]'
    
    def clean_condition_config_json(self):
        """Validate condition config JSON."""
        data = self.cleaned_data['condition_config_json']
        try:
            config = json.loads(data)
            if not isinstance(config, dict):
                raise ValidationError("Config must be a JSON object")
            return config
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def clean_test_cases_json(self):
        """Validate test cases JSON."""
        data = self.cleaned_data['test_cases_json']
        if not data:
            return []
        try:
            cases = json.loads(data)
            if not isinstance(cases, list):
                raise ValidationError("Test cases must be a JSON array")
            return cases
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def save(self, commit=True):
        """Save with JSON fields."""
        instance = super().save(commit=False)
        instance.condition_config = self.cleaned_data['condition_config_json']
        instance.test_cases = self.cleaned_data['test_cases_json']
        
        if commit:
            instance.save()
        
        return instance


class AgentConditionBindingForm(forms.ModelForm):
    """Form for binding conditions to agents."""
    
    parameters_json = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 3, 'class': 'form-control font-monospace'}),
        required=False,
        help_text='Parameters to pass to condition: {"key": "value"}'
    )
    
    class Meta:
        model = AgentConditionBinding
        fields = [
            'agent',
            'condition',
            'evaluation_point',
            'on_true_action',
            'on_false_action',
            'max_evaluations',
            'priority',
            'is_enabled',
        ]
        widgets = {
            'agent': forms.Select(attrs={'class': 'form-select'}),
            'condition': forms.Select(attrs={'class': 'form-select'}),
            'evaluation_point': forms.Select(attrs={'class': 'form-select'}),
            'on_true_action': forms.Select(attrs={'class': 'form-select'}),
            'on_false_action': forms.Select(attrs={'class': 'form-select'}),
            'max_evaluations': forms.NumberInput(attrs={'class': 'form-control'}),
            'priority': forms.NumberInput(attrs={'class': 'form-control'}),
            'is_enabled': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        if self.instance and self.instance.pk:
            self.fields['parameters_json'].initial = json.dumps(
                self.instance.parameters, indent=2
            ) if self.instance.parameters else '{}'
    
    def clean_parameters_json(self):
        """Validate parameters JSON."""
        data = self.cleaned_data['parameters_json']
        if not data:
            return {}
        try:
            params = json.loads(data)
            if not isinstance(params, dict):
                raise ValidationError("Parameters must be a JSON object")
            return params
        except json.JSONDecodeError as e:
            raise ValidationError(f"Invalid JSON: {e}")
    
    def save(self, commit=True):
        """Save with JSON fields."""
        instance = super().save(commit=False)
        instance.parameters = self.cleaned_data['parameters_json']
        
        if commit:
            instance.save()
        
        return instance
