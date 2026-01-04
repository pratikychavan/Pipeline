from django import forms
from django.contrib.auth.models import User
from .models import Pipeline, Node
import json

class PipelineForm(forms.ModelForm):
    global_arguments_text = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'db_host\nbatch_size\napi_key'
        }),
        label='Global Argument Names',
        help_text='List argument names (one per line) that will be prompted during execution'
    )
    
    class Meta:
        model = Pipeline
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter pipeline name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter pipeline description'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Populate global_arguments_text from instance
            if self.instance.global_arguments:
                self.initial['global_arguments_text'] = '\n'.join(self.instance.global_arguments)
    
    def clean_global_arguments_text(self):
        text = self.cleaned_data.get('global_arguments_text', '').strip()
        if not text:
            return []
        # Split by newlines and filter out empty lines
        arg_names = [line.strip() for line in text.split('\n') if line.strip()]
        return arg_names
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.global_arguments = self.cleaned_data.get('global_arguments_text', [])
        if commit:
            instance.save()
        return instance

class NodeForm(forms.ModelForm):
    class Meta:
        model = Node
        fields = ['name', 'description', 'code', 'input_variable_mappings']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter node name'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Enter node description'}),
            'code': forms.Textarea(attrs={
                'class': 'form-control code-editor custom-handled', 
                'rows': 15, 
                'placeholder': '# Write your Python code here\n# Example:\n# wd = WarpDrive()\n# df = wd.get_arg("input_data", deserialization_func=pd.read_parquet)\n# result = process(df)\n# wd.save_artifact("output", result, serialization_func=result.to_parquet)',
                'required': False  # Remove HTML5 required validation since CodeMirror handles this
            }),
            'input_variable_mappings': forms.HiddenInput(),
        }
    
    def __init__(self, *args, **kwargs):
        self.pipeline = kwargs.pop('pipeline', None)
        super().__init__(*args, **kwargs)
    
    def clean(self):
        cleaned_data = super().clean()
        
        # Validate code field (since we removed HTML5 required validation)
        code = cleaned_data.get('code', '').strip()
        if not code:
            raise forms.ValidationError({'code': 'Code field is required.'})
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        if commit:
            instance.save()
        return instance

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