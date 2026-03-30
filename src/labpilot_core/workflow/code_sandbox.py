"""Restricted Python code execution for AnalyseNode.

Two-layer security model:
1. AST validation - reject dangerous imports and function calls
2. Subprocess execution - resource limits and isolation

This enables safe execution of AI-generated analysis code in workflow nodes.
"""

from __future__ import annotations

import ast
import multiprocessing
import resource
import sys
from io import StringIO
from typing import Any

import xarray as xr

__all__ = ["CodeSandbox", "SandboxError", "execute_analysis_code"]


class SandboxError(Exception):
    """Raised when code execution fails or is blocked."""


class CodeValidator:
    """AST-based code validation for security."""

    # Allowed imports for analysis code
    ALLOWED_IMPORTS = {
        "numpy",
        "scipy",
        "pandas",
        "xarray",
        "matplotlib",
        "sklearn",
        "math",
        "statistics",
        "itertools",
        "functools",
        "operator",
        "collections",
    }

    # Dangerous functions that are always blocked
    BLOCKED_FUNCTIONS = {
        "eval",
        "exec",
        "compile",
        "open",
        "__import__",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "hasattr",
        "callable",
    }

    # Dangerous attributes (dunder methods)
    BLOCKED_ATTRIBUTES = {
        "__class__",
        "__bases__",
        "__subclasses__",
        "__mro__",
        "__globals__",
        "__dict__",
        "__code__",
        "__func__",
        "__self__",
    }

    @classmethod
    def validate_code(cls, code: str, allowed_imports: list[str]) -> None:
        """Validate Python code using AST analysis.

        Args:
            code: Python source code to validate.
            allowed_imports: List of allowed import modules.

        Raises:
            SandboxError: If code contains dangerous constructs.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SandboxError(f"Syntax error in code: {e}")

        # Combine default and user-specified allowed imports
        all_allowed = cls.ALLOWED_IMPORTS | set(allowed_imports)

        # Walk the AST and check each node
        for node in ast.walk(tree):
            cls._validate_node(node, all_allowed)

    @classmethod
    def _validate_node(cls, node: ast.AST, allowed_imports: set[str]) -> None:
        """Validate a single AST node."""

        # Check imports
        if isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name.split(".")[0]  # Get root module
                if module not in allowed_imports:
                    raise SandboxError(f"Import not allowed: {alias.name}")

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                module = node.module.split(".")[0]  # Get root module
                if module not in allowed_imports:
                    raise SandboxError(f"Import not allowed: {node.module}")

        # Check function calls
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in cls.BLOCKED_FUNCTIONS:
                    raise SandboxError(f"Function call not allowed: {node.func.id}")

        # Check attribute access
        elif isinstance(node, ast.Attribute):
            if node.attr in cls.BLOCKED_ATTRIBUTES:
                raise SandboxError(f"Attribute access not allowed: {node.attr}")

        # Block file operations
        elif isinstance(node, ast.With):
            # Look for 'with open(...)' patterns
            if (isinstance(node.items[0].context_expr, ast.Call) and
                isinstance(node.items[0].context_expr.func, ast.Name) and
                node.items[0].context_expr.func.id == "open"):
                raise SandboxError("File operations not allowed")


def _execute_in_subprocess(
    code: str,
    data: dict[str, Any],
    params: dict[str, Any],
    timeout: float,
) -> dict[str, Any]:
    """Execute code in subprocess with resource limits.

    This function runs in the subprocess - it sets resource limits
    and executes the user code.
    """
    try:
        # Set CPU time limit (10 seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (10, 10))

        # Set memory limit (512 MB)
        resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))

        # Redirect stdout/stderr to capture output
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()

        try:
            # Create restricted globals - only safe builtins + allowed imports
            safe_globals = {
                "__builtins__": {
                    # Safe built-ins only
                    "abs": abs,
                    "all": all,
                    "any": any,
                    "bool": bool,
                    "dict": dict,
                    "enumerate": enumerate,
                    "float": float,
                    "int": int,
                    "len": len,
                    "list": list,
                    "max": max,
                    "min": min,
                    "range": range,
                    "round": round,
                    "set": set,
                    "sorted": sorted,
                    "str": str,
                    "sum": sum,
                    "tuple": tuple,
                    "type": type,
                    "zip": zip,
                },
            }

            # Allow safe imports
            try:
                import numpy as np
                safe_globals["numpy"] = np
                safe_globals["np"] = np
            except ImportError:
                pass

            try:
                import scipy
                safe_globals["scipy"] = scipy
            except ImportError:
                pass

            try:
                import pandas as pd
                safe_globals["pandas"] = pd
                safe_globals["pd"] = pd
            except ImportError:
                pass

            safe_globals["xarray"] = xr
            safe_globals["xr"] = xr

            # Execute the code
            exec(code, safe_globals)

            # The code should define an 'analyse' function
            if "analyse" not in safe_globals:
                raise SandboxError("Code must define an 'analyse' function")

            analyse_func = safe_globals["analyse"]

            # Convert data dict to xarray Dataset if needed
            if isinstance(data, dict):
                # Simple conversion - assume data is dict of arrays
                dataset = xr.Dataset(data)
            else:
                dataset = data

            # Call the analysis function
            result = analyse_func(dataset, params)

            if not isinstance(result, dict):
                raise SandboxError("analyse() function must return a dict")

            return result

        finally:
            # Restore stdout/stderr
            sys.stdout = old_stdout
            sys.stderr = old_stderr

    except Exception as e:
        # Return error info
        return {"__error__": str(e)}


class CodeSandbox:
    """Secure execution environment for analysis code."""

    def __init__(self):
        """Initialize sandbox."""
        self.validator = CodeValidator()

    def execute(
        self,
        code: str,
        data: dict[str, Any],
        params: dict[str, Any] | None = None,
        allowed_imports: list[str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Execute analysis code safely.

        Args:
            code: Python code defining analyse(data, params) -> dict function.
            data: Input data dict (will be converted to xarray.Dataset).
            params: Parameters dict passed to analyse function.
            allowed_imports: Additional allowed imports beyond defaults.
            timeout: Execution timeout in seconds.

        Returns:
            Result dict from analyse function.

        Raises:
            SandboxError: If code validation or execution fails.
        """
        if params is None:
            params = {}
        if allowed_imports is None:
            allowed_imports = []

        # Step 1: Validate code using AST
        try:
            self.validator.validate_code(code, allowed_imports)
        except SandboxError:
            raise  # Re-raise validation errors
        except Exception as e:
            raise SandboxError(f"Code validation failed: {e}")

        # Step 2: Execute in subprocess with resource limits
        try:
            # Use multiprocessing for isolation
            with multiprocessing.Pool(processes=1) as pool:
                async_result = pool.apply_async(
                    _execute_in_subprocess,
                    (code, data, params, timeout)
                )

                # Wait for result with timeout
                result = async_result.get(timeout=timeout)

                # Check for errors
                if "__error__" in result:
                    raise SandboxError(f"Execution error: {result['__error__']}")

                return result

        except multiprocessing.TimeoutError:
            raise SandboxError(f"Code execution timed out after {timeout}s")
        except Exception as e:
            raise SandboxError(f"Execution failed: {e}")


def execute_analysis_code(
    code: str,
    data: dict[str, Any],
    params: dict[str, Any] | None = None,
    allowed_imports: list[str] | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Execute analysis code in sandbox (convenience function).

    Args:
        code: Python code with analyse(data, params) -> dict function.
        data: Input data.
        params: Analysis parameters.
        allowed_imports: Additional imports to allow.
        timeout: Timeout in seconds.

    Returns:
        Analysis results dict.

    Raises:
        SandboxError: If execution fails.

    Example:
        >>> code = '''
        ... def analyse(data, params):
        ...     import numpy as np
        ...     mean_val = np.mean(data['signal'])
        ...     return {'mean': mean_val, 'status': 'success'}
        ... '''
        >>> data = {'signal': [1, 2, 3, 4, 5]}
        >>> result = execute_analysis_code(code, data)
        >>> print(result)  # {'mean': 3.0, 'status': 'success'}
    """
    sandbox = CodeSandbox()
    return sandbox.execute(code, data, params, allowed_imports, timeout)
