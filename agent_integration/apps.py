"""
Django app configuration for agent_integration.
"""

from django.apps import AppConfig


class AgentIntegrationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'agent_integration'
    verbose_name = 'Agent Integration'
    
    def ready(self):
        """
        Import any signal handlers or startup code here.
        """
        pass
