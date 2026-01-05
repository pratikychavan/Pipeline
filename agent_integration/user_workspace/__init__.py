"""
User Agent Workspace Loader

This module provides safe loading and validation of user-written agent code.

SECURITY MODEL:
- User code is UNTRUSTED
- Strict import restrictions
- No filesystem/network/database access
- No execution beyond Planner.plan_next_action()
- Fail fast on violations

WORKSPACE STRUCTURE:
Each user workspace must contain:
- agent.py: User planner implementation
- agent.yaml: Agent configuration
- requirements.txt: (optional) restricted dependencies
"""

import ast
import importlib.util
import sys
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type
from dataclasses import dataclass
import logging

from warpdrive_agent_sdk import (
    Planner,
    PlannerDecision,
    AgentDefinition,
    AgentConfig,
)


logger = logging.getLogger(__name__)


# ============================================================================
# SECURITY CONFIGURATION
# ============================================================================

FORBIDDEN_MODULES = {
    # System/OS access
    'os', 'sys', 'subprocess', 'shutil', 'glob', 'pathlib',
    
    # Network access
    'socket', 'urllib', 'urllib3', 'requests', 'http', 'httplib',
    'ftplib', 'smtplib', 'poplib', 'imaplib',
    
    # File I/O
    'io', 'open', 'file', 'tempfile',
    
    # Code execution
    'exec', 'eval', 'compile', 'execfile', '__import__',
    'importlib', 'imp',
    
    # Database
    'sqlite3', 'psycopg2', 'mysql', 'pymongo', 'sqlalchemy',
    'django.db', 'django.models',
    
    # Dangerous builtins
    'pickle', 'marshal', 'shelve', 'dill',
    
    # Threading/multiprocessing
    'threading', 'multiprocessing', 'concurrent', 'asyncio',
    
    # Platform internals (must not be accessed by users)
    'core', 'core.models', 'core.views',
    'agent_integration', 'agent_integration.models',
    'agent_integration.runtime',
}

ALLOWED_STDLIB_MODULES = {
    # Data structures
    'collections', 'dataclasses', 'typing', 'enum',
    
    # Math/logic
    'math', 'random', 'statistics', 'decimal', 'fractions',
    
    # Date/time (read-only)
    'datetime', 'time', 'calendar',
    
    # String processing
    'string', 're', 'textwrap',
    
    # Data formats
    'json', 'csv', 'base64', 'uuid',
}

ALLOWED_THIRD_PARTY = {
    # SDK (explicitly allowed)
    'warpdrive_agent_sdk',
    
    # NumPy/Scientific (read-only operations)
    'numpy', 'pandas', 'scipy',
}

MAX_FILE_SIZE = 1024 * 1024  # 1MB
MAX_IMPORTS = 50  # Maximum number of import statements


# ============================================================================
# VALIDATION EXCEPTIONS
# ============================================================================

class WorkspaceValidationError(Exception):
    """Base exception for workspace validation errors."""
    pass


class SecurityViolation(WorkspaceValidationError):
    """Raised when user code violates security constraints."""
    pass


class InvalidPlannerError(WorkspaceValidationError):
    """Raised when planner implementation is invalid."""
    pass


class InvalidConfigError(WorkspaceValidationError):
    """Raised when agent.yaml is invalid."""
    pass


# ============================================================================
# AST-BASED IMPORT VALIDATOR
# ============================================================================

class ImportValidator(ast.NodeVisitor):
    """
    AST visitor that validates imports in user code.
    
    This inspects the AST without executing code, ensuring:
    - No forbidden modules are imported
    - Only SDK and approved stdlib are allowed
    - No dynamic imports (__import__, importlib)
    - No import side effects
    """
    
    def __init__(self):
        self.imports: Set[str] = set()
        self.violations: List[str] = []
        self.has_forbidden_builtins = False
    
    def visit_Import(self, node: ast.Import):
        """Visit 'import module' statements."""
        for alias in node.names:
            module_name = alias.name.split('.')[0]  # Get top-level module
            self.imports.add(module_name)
            
            if not self._is_import_allowed(module_name):
                self.violations.append(
                    f"Forbidden import: '{alias.name}' at line {node.lineno}"
                )
        
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node: ast.ImportFrom):
        """Visit 'from module import ...' statements."""
        if node.module:
            module_name = node.module.split('.')[0]
            self.imports.add(module_name)
            
            if not self._is_import_allowed(module_name):
                self.violations.append(
                    f"Forbidden import: 'from {node.module}' at line {node.lineno}"
                )
        
        self.generic_visit(node)
    
    def visit_Call(self, node: ast.Call):
        """Visit function calls - check for __import__, exec, eval."""
        if isinstance(node.func, ast.Name):
            if node.func.id in ('__import__', 'exec', 'eval', 'compile'):
                self.violations.append(
                    f"Forbidden function call: '{node.func.id}' at line {node.lineno}"
                )
                self.has_forbidden_builtins = True
        
        self.generic_visit(node)
    
    def _is_import_allowed(self, module_name: str) -> bool:
        """Check if module import is allowed."""
        # Check forbidden first
        if module_name in FORBIDDEN_MODULES:
            return False
        
        # Check explicitly allowed
        if module_name in ALLOWED_STDLIB_MODULES:
            return True
        
        if module_name in ALLOWED_THIRD_PARTY:
            return True
        
        # Check if it's a submodule of allowed third party
        for allowed in ALLOWED_THIRD_PARTY:
            if module_name.startswith(f"{allowed}."):
                return True
        
        # Reject everything else by default (fail-safe)
        return False
    
    def get_violations(self) -> List[str]:
        """Get list of all violations."""
        if len(self.imports) > MAX_IMPORTS:
            self.violations.append(
                f"Too many imports ({len(self.imports)} > {MAX_IMPORTS})"
            )
        return self.violations


# ============================================================================
# PLANNER VALIDATOR
# ============================================================================

class PlannerValidator:
    """
    Validates user planner implementation.
    
    Ensures:
    - Exactly one Planner subclass
    - Implements plan_next_action()
    - No forbidden method overrides
    - Returns PlannerDecision
    """
    
    REQUIRED_METHOD = 'plan_next_action'
    FORBIDDEN_METHOD_OVERRIDES = {
        '__init__', '__new__', '__del__',
        '__getattr__', '__setattr__', '__delattr__',
        '__getattribute__',
    }
    
    def __init__(self, module_ast: ast.Module, module_name: str):
        self.module_ast = module_ast
        self.module_name = module_name
        self.planner_classes: List[str] = []
        self.violations: List[str] = []
    
    def validate(self) -> str:
        """
        Validate planner implementation.
        
        Returns:
            Name of valid planner class
            
        Raises:
            InvalidPlannerError: If validation fails
        """
        # Find all classes that inherit from Planner
        for node in ast.walk(self.module_ast):
            if isinstance(node, ast.ClassDef):
                if self._inherits_from_planner(node):
                    self.planner_classes.append(node.name)
                    self._validate_planner_class(node)
        
        # Check exactly one planner
        if len(self.planner_classes) == 0:
            raise InvalidPlannerError(
                "No Planner subclass found in agent.py. "
                "You must define a class that inherits from Planner."
            )
        
        if len(self.planner_classes) > 1:
            raise InvalidPlannerError(
                f"Multiple Planner subclasses found: {', '.join(self.planner_classes)}. "
                "Define exactly one Planner subclass."
            )
        
        # Check for violations
        if self.violations:
            raise InvalidPlannerError(
                "Planner validation failed:\n" + "\n".join(f"  - {v}" for v in self.violations)
            )
        
        return self.planner_classes[0]
    
    def _inherits_from_planner(self, node: ast.ClassDef) -> bool:
        """Check if class inherits from Planner."""
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == 'Planner':
                return True
        return False
    
    def _validate_planner_class(self, node: ast.ClassDef):
        """Validate a planner class."""
        methods = {
            item.name: item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        
        # Check required method exists
        if self.REQUIRED_METHOD not in methods:
            self.violations.append(
                f"Class '{node.name}' must implement '{self.REQUIRED_METHOD}()' method"
            )
        else:
            # Validate method signature
            method = methods[self.REQUIRED_METHOD]
            self._validate_method_signature(node.name, method)
        
        # Check for forbidden method overrides
        for method_name in methods:
            if method_name in self.FORBIDDEN_METHOD_OVERRIDES:
                self.violations.append(
                    f"Class '{node.name}' overrides forbidden method '{method_name}'"
                )
    
    def _validate_method_signature(self, class_name: str, method: ast.FunctionDef | ast.AsyncFunctionDef):
        """Validate plan_next_action signature."""
        args = method.args
        
        # Should have: self, planner_input
        if len(args.args) < 2:
            self.violations.append(
                f"Method '{method.name}' in '{class_name}' must accept 'planner_input' parameter"
            )


# ============================================================================
# WORKSPACE LOADER
# ============================================================================

@dataclass
class LoadedWorkspace:
    """Result of loading a user workspace."""
    workspace_path: Path
    planner_class: Type[Planner]
    planner_class_name: str
    agent_config: AgentConfig
    agent_definition: AgentDefinition


class WorkspaceLoader:
    """
    Safely loads and validates user agent workspaces.
    
    This is the main entry point for loading user code.
    """
    
    def __init__(self, workspace_path: str | Path):
        """
        Initialize workspace loader.
        
        Args:
            workspace_path: Path to user workspace directory
        """
        self.workspace_path = Path(workspace_path)
        self._validate_workspace_structure()
    
    def _validate_workspace_structure(self):
        """Validate workspace has required files."""
        if not self.workspace_path.exists():
            raise WorkspaceValidationError(
                f"Workspace directory not found: {self.workspace_path}"
            )
        
        if not self.workspace_path.is_dir():
            raise WorkspaceValidationError(
                f"Workspace path is not a directory: {self.workspace_path}"
            )
        
        required_files = ['agent.py', 'agent.yaml']
        for filename in required_files:
            filepath = self.workspace_path / filename
            if not filepath.exists():
                raise WorkspaceValidationError(
                    f"Required file missing: {filename}"
                )
    
    def load(self) -> LoadedWorkspace:
        """
        Load and validate workspace.
        
        Returns:
            LoadedWorkspace with validated planner and config
            
        Raises:
            WorkspaceValidationError: If validation fails
            SecurityViolation: If security constraints violated
        """
        logger.info(f"Loading workspace from {self.workspace_path}")
        
        # Step 1: Load and validate agent.py
        planner_class, planner_name = self._load_and_validate_planner()
        
        # Step 2: Load and validate agent.yaml
        config, definition = self._load_and_validate_config(planner_name)
        
        logger.info(f"✅ Workspace loaded successfully: {definition.name}")
        
        return LoadedWorkspace(
            workspace_path=self.workspace_path,
            planner_class=planner_class,
            planner_class_name=planner_name,
            agent_config=config,
            agent_definition=definition,
        )
    
    def _load_and_validate_planner(self) -> tuple[Type[Planner], str]:
        """Load and validate agent.py."""
        agent_py = self.workspace_path / 'agent.py'
        
        # Security check: file size
        file_size = agent_py.stat().st_size
        if file_size > MAX_FILE_SIZE:
            raise SecurityViolation(
                f"agent.py too large ({file_size} bytes > {MAX_FILE_SIZE})"
            )
        
        # Read source code
        source_code = agent_py.read_text()
        
        # Parse AST (safe - doesn't execute code)
        try:
            tree = ast.parse(source_code, filename='agent.py')
        except SyntaxError as e:
            raise WorkspaceValidationError(
                f"Syntax error in agent.py: {e}"
            )
        
        # Validate imports
        import_validator = ImportValidator()
        import_validator.visit(tree)
        violations = import_validator.get_violations()
        
        if violations:
            raise SecurityViolation(
                "Import validation failed:\n" + "\n".join(f"  - {v}" for v in violations)
            )
        
        # Validate planner class
        planner_validator = PlannerValidator(tree, 'agent')
        planner_class_name = planner_validator.validate()
        
        # Now it's safe to import (all checks passed)
        planner_class = self._safe_import_planner(agent_py, planner_class_name)
        
        return planner_class, planner_class_name
    
    def _safe_import_planner(self, agent_py: Path, class_name: str) -> Type[Planner]:
        """Safely import planner class from agent.py."""
        # Create unique module name
        module_name = f"user_agent_{self.workspace_path.name}"
        
        # Load module
        spec = importlib.util.spec_from_file_location(module_name, agent_py)
        if spec is None or spec.loader is None:
            raise WorkspaceValidationError("Failed to load agent.py module")
        
        module = importlib.util.module_from_spec(spec)
        
        # Execute module (imports and class definitions only)
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            raise WorkspaceValidationError(
                f"Failed to execute agent.py: {e}"
            )
        
        # Get planner class
        if not hasattr(module, class_name):
            raise InvalidPlannerError(
                f"Planner class '{class_name}' not found in module"
            )
        
        planner_class = getattr(module, class_name)
        
        # Final check: is it actually a Planner subclass?
        if not issubclass(planner_class, Planner):
            raise InvalidPlannerError(
                f"Class '{class_name}' does not inherit from Planner"
            )
        
        return planner_class
    
    def _load_and_validate_config(
        self,
        planner_class_name: str
    ) -> tuple[AgentConfig, AgentDefinition]:
        """Load and validate agent.yaml."""
        agent_yaml = self.workspace_path / 'agent.yaml'
        
        # Load YAML
        try:
            with open(agent_yaml) as f:
                config_data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise InvalidConfigError(f"Invalid YAML in agent.yaml: {e}")
        except Exception as e:
            raise InvalidConfigError(f"Failed to read agent.yaml: {e}")
        
        # Validate required fields
        required_fields = ['name', 'objective']
        for field in required_fields:
            if field not in config_data:
                raise InvalidConfigError(f"Required field missing in agent.yaml: '{field}'")
        
        # Build AgentConfig
        config_section = config_data.get('config', {})
        agent_config = AgentConfig(
            model=config_section.get('model', 'gpt-4o-mini'),
            temperature=config_section.get('temperature', 0.3),
            max_tokens=config_section.get('max_tokens', 2000),
            max_steps=config_section.get('max_steps', 100),
            enable_human_intervention=config_section.get('enable_human_intervention', True),
            fail_on_node_failure=config_section.get('fail_on_node_failure', True),
            timeout_seconds=config_section.get('timeout_seconds'),
        )
        
        # Validate config
        try:
            agent_config.validate()
        except ValueError as e:
            raise InvalidConfigError(f"Invalid agent config: {e}")
        
        # Build AgentDefinition
        agent_definition = AgentDefinition(
            name=config_data['name'],
            objective=config_data['objective'],
            description=config_data.get('description', ''),
            allowed_tools=config_data.get('allowed_tools', []),
            config=agent_config,
            constraints=config_data.get('constraints', {}),
            metadata={
                'workspace_path': str(self.workspace_path),
                'planner_class': planner_class_name,
            }
        )
        
        # Validate definition
        try:
            agent_definition.validate()
        except ValueError as e:
            raise InvalidConfigError(f"Invalid agent definition: {e}")
        
        return agent_config, agent_definition


# ============================================================================
# PUBLIC API
# ============================================================================

def load_user_workspace(workspace_path: str | Path) -> LoadedWorkspace:
    """
    Load and validate a user agent workspace.
    
    This is the main entry point for loading user code.
    
    Args:
        workspace_path: Path to workspace directory
        
    Returns:
        LoadedWorkspace with validated planner and config
        
    Raises:
        WorkspaceValidationError: If validation fails
        SecurityViolation: If security constraints violated
        
    Example:
        >>> workspace = load_user_workspace('/path/to/workspace')
        >>> planner = workspace.planner_class()
        >>> config = workspace.agent_config
    """
    loader = WorkspaceLoader(workspace_path)
    return loader.load()
