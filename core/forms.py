from django import forms
from django.contrib.auth.models import User
from .models import Pipeline, Node, NodeConnection
import json

class PipelineForm(forms.ModelForm):
    class Meta:
        model = Pipeline
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter pipeline name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter pipeline description'}),
        }

class NodeForm(forms.ModelForm):
    class Meta:
        model = Node
        fields = ['name', 'description', 'code', 'input_variables', 'output_variables']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter node name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Enter node description'}),
            'code': forms.Textarea(attrs={
                'class': 'form-control code-editor custom-handled', 
                'rows': 15, 
                'placeholder': '# Write your Python code here\n# Example:\n# def process_data(input_data):\n#     result = input_data * 2\n#     return result',
                'required': False  # Remove HTML5 required validation since CodeMirror handles this
            }),
            'input_variables': forms.HiddenInput(),
            'output_variables': forms.HiddenInput(),
        }
    
    input_vars_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter input variable names (comma-separated)'
        }),
        help_text="Comma-separated list of input variable names"
    )
    
    output_vars_text = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter output variable names (comma-separated)'
        }),
        help_text="Comma-separated list of output variable names"
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Convert JSON lists to comma-separated strings for display
            if self.instance.input_variables:
                self.fields['input_vars_text'].initial = ', '.join(self.instance.input_variables)
            if self.instance.output_variables:
                self.fields['output_vars_text'].initial = ', '.join(self.instance.output_variables)
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate code field (since we removed HTML5 required validation)
        code = cleaned_data.get('code', '').strip()
        if not code:
            raise forms.ValidationError({'code': 'Code field is required.'})
        
        # Convert comma-separated strings to JSON lists
        input_vars_text = cleaned_data.get('input_vars_text', '')
        output_vars_text = cleaned_data.get('output_vars_text', '')
        
        if input_vars_text:
            input_vars = [var.strip() for var in input_vars_text.split(',') if var.strip()]
            cleaned_data['input_variables'] = input_vars
        else:
            cleaned_data['input_variables'] = []
            
        if output_vars_text:
            output_vars = [var.strip() for var in output_vars_text.split(',') if var.strip()]
            cleaned_data['output_variables'] = output_vars
        else:
            cleaned_data['output_variables'] = []
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Ensure input_variables and output_variables are set from cleaned_data
        if hasattr(self, 'cleaned_data'):
            instance.input_variables = self.cleaned_data.get('input_variables', [])
            instance.output_variables = self.cleaned_data.get('output_variables', [])
        
        if commit:
            instance.save()
        return instance

class NodeConnectionForm(forms.ModelForm):
    class Meta:
        model = NodeConnection
        fields = ['from_node', 'to_node', 'from_output', 'to_input']
        widgets = {
            'from_node': forms.Select(attrs={'class': 'form-control'}),
            'to_node': forms.Select(attrs={'class': 'form-control'}),
            'from_output': forms.Select(attrs={'class': 'form-control'}),
            'to_input': forms.Select(attrs={'class': 'form-control'}),
        }
    
    def __init__(self, *args, **kwargs):
        pipeline = kwargs.pop('pipeline', None)
        super().__init__(*args, **kwargs)
        
        if pipeline:
            self.fields['from_node'].queryset = Node.objects.filter(pipeline=pipeline)
            self.fields['to_node'].queryset = Node.objects.filter(pipeline=pipeline)

class CodeExecutionForm(forms.Form):
    """Form for executing pipeline with initial parameters"""
    initial_data = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 5,
            'placeholder': '{\n  "variable1": "value1",\n  "variable2": 42\n}'
        }),
        help_text="Initial variables in JSON format (optional)"
    )
    
    def clean_initial_data(self):
        data = self.cleaned_data['initial_data']
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError:
                raise forms.ValidationError("Invalid JSON format")
        return {}