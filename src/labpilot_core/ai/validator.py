"""AI code validator with self-correction loop.

Validates AI-generated code before execution and provides automatic correction
via feedback to the AI provider. Two main validation types:

1. DSL GUI validation - Ensures AI-generated Qt DSL code is safe and correct
2. AnalyseNode validation - Ensures Python analysis code is secure

On validation failure, sends correction prompt back to AI (up to 2 retries).
All retries are invisible to the user - they only see the final corrected code.
"""

from __future__ import annotations

import ast
import logging
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from labpilot_core.ai.provider import AIProvider

__all__ = ["CodeValidator", "ValidationError"]

log = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when code validation fails."""


class CodeValidator:
    """Validates AI-generated code before showing to user.

    On failure: sends correction prompt to model (up to 2 retries).
    All retries are invisible to the user.

    Example:
        >>> validator = CodeValidator()
        >>> code, was_corrected = await validator.validate_and_correct(
        ...     "broken_dsl_code", "dsl_gui", ai_provider
        ... )
        >>> if was_corrected:
        ...     print("AI fixed the code automatically")
    """

    def __init__(self) -> None:
        """Initialize code validator."""
        pass

    async def validate_and_correct(
        self,
        code: str,
        kind: Literal["dsl_gui", "analyse_function"],
        provider: AIProvider,
        max_retries: int = 2,
    ) -> tuple[str, bool]:
        """Validate code and auto-correct if needed.

        Args:
            code: Python source code to validate.
            kind: Type of code validation to perform.
            provider: AI provider for correction requests.
            max_retries: Maximum number of correction attempts.

        Returns:
            Tuple of (final_code, was_corrected).

        Raises:
            ValidationError: If code cannot be corrected after max retries.
        """
        original_code = code
        was_corrected = False

        for attempt in range(max_retries + 1):
            try:
                # Validate current code
                if kind == "dsl_gui":
                    errors = self.validate_dsl(code)
                elif kind == "analyse_function":
                    errors = self.validate_analyse(code, allowed_imports=[])
                else:
                    raise ValidationError(f"Unknown validation kind: {kind}")

                if not errors:
                    # Validation passed
                    log.info(f"Code validation passed (attempt {attempt + 1})")
                    return code, was_corrected

                # Validation failed - try correction if retries remain
                if attempt < max_retries:
                    log.warning(f"Code validation failed (attempt {attempt + 1}): {len(errors)} errors")

                    correction_prompt = self._build_correction_prompt(code, errors, kind)
                    corrected_code = await self._request_correction(provider, correction_prompt)

                    if corrected_code:
                        code = corrected_code
                        was_corrected = True
                        log.info("AI provided correction, retrying validation")
                    else:
                        log.error("AI failed to provide correction")
                        break
                else:
                    # No more retries
                    log.error(f"Max retries exceeded, validation still failing: {errors}")
                    break

            except Exception as e:
                log.error(f"Validation attempt {attempt + 1} failed: {e}")
                if attempt >= max_retries:
                    break

        # All attempts failed
        if kind == "dsl_gui":
            final_errors = self.validate_dsl(code)
        else:
            final_errors = self.validate_analyse(code, allowed_imports=[])

        raise ValidationError(
            f"Code validation failed after {max_retries} correction attempts. "
            f"Errors: {'; '.join(final_errors)}"
        )

    def validate_dsl(self, code: str) -> list[str]:
        """Validate DSL GUI code.

        Args:
            code: Python DSL code to validate.

        Returns:
            List of error strings. Empty list = validation passed.

        Checks:
        1. Valid Python syntax
        2. No raw Qt imports/classes
        3. All source= refs use "device.param" format
        4. All device= refs are valid device names
        5. show(w) or show(window) present as last meaningful statement
        6. No dangerous imports (os, sys, subprocess, socket)
        """
        errors = []

        try:
            # Check 1: Valid Python syntax
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                errors.append(f"Syntax error: {e}")
                return errors  # Can't continue with broken syntax

            # Check 2: No raw Qt imports
            qt_violations = self._check_qt_imports(tree)
            errors.extend(qt_violations)

            # Check 3: Source format validation
            source_errors = self._check_source_format(tree)
            errors.extend(source_errors)

            # Check 4: Device validation (TODO: check against actual registry)
            device_errors = self._check_device_references(tree)
            errors.extend(device_errors)

            # Check 5: show() call present
            show_errors = self._check_show_call(tree)
            errors.extend(show_errors)

            # Check 6: Dangerous imports
            import_errors = self._check_dangerous_imports(tree)
            errors.extend(import_errors)

        except Exception as e:
            errors.append(f"Validation error: {e}")

        return errors

    def validate_analyse(self, code: str, allowed_imports: list[str]) -> list[str]:
        """Validate AnalyseNode code.

        Args:
            code: Python analysis function code.
            allowed_imports: List of allowed import modules.

        Returns:
            List of error strings. Empty list = validation passed.

        Checks:
        1. Valid Python syntax
        2. Defines function named "analyse" with correct signature
        3. Only allowed imports permitted
        4. No calls to eval, exec, open, __import__
        5. No attribute access to __class__, __globals__, __builtins__
        6. Function body returns a dict (best-effort AST check)
        """
        errors = []

        # Default allowed imports for analysis
        default_allowed = {
            "numpy", "scipy", "pandas", "xarray", "matplotlib", "sklearn",
            "math", "statistics", "itertools", "functools", "operator",
            "collections", "lmfit"
        }
        all_allowed = default_allowed | set(allowed_imports)

        try:
            # Check 1: Valid Python syntax
            try:
                tree = ast.parse(code)
            except SyntaxError as e:
                errors.append(f"Syntax error: {e}")
                return errors

            # Check 2: analyse function exists with correct signature
            func_errors = self._check_analyse_function(tree)
            errors.extend(func_errors)

            # Check 3: Import restrictions
            import_errors = self._check_analyse_imports(tree, all_allowed)
            errors.extend(import_errors)

            # Check 4: Dangerous function calls
            call_errors = self._check_analyse_calls(tree)
            errors.extend(call_errors)

            # Check 5: Dangerous attribute access
            attr_errors = self._check_analyse_attributes(tree)
            errors.extend(attr_errors)

            # Check 6: Function returns dict (best effort)
            return_errors = self._check_analyse_returns(tree)
            errors.extend(return_errors)

        except Exception as e:
            errors.append(f"Validation error: {e}")

        return errors

    def _check_qt_imports(self, tree: ast.AST) -> list[str]:
        """Check for raw Qt imports/usage."""
        errors = []

        qt_modules = {
            "PyQt6", "PyQt5", "PySide6", "PySide2", "tkinter",
            "QWidget", "QMainWindow", "QApplication", "QLabel",
            "QPushButton", "QVBoxLayout", "QHBoxLayout"
        }

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                # Check import statements
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if any(qt_mod in alias.name for qt_mod in qt_modules):
                            errors.append(
                                f"Raw Qt import not allowed: {alias.name}. "
                                f"Use LabPilot DSL functions instead."
                            )
                elif isinstance(node, ast.ImportFrom) and node.module:
                    if any(qt_mod in node.module for qt_mod in qt_modules):
                        errors.append(
                            f"Raw Qt import not allowed: from {node.module}. "
                            f"Use LabPilot DSL functions instead."
                        )

            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                # Check for Qt class instantiation
                if node.func.id in qt_modules:
                    errors.append(
                        f"Raw Qt class usage not allowed: {node.func.id}(). "
                        f"Use LabPilot DSL functions instead."
                    )

        return errors

    def _check_source_format(self, tree: ast.AST) -> list[str]:
        """Check source= parameters use correct format."""
        errors = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Check function calls with source keyword
                for keyword in node.keywords:
                    if keyword.arg in ("source", "x_source", "y_source"):
                        if isinstance(keyword.value, ast.Constant):
                            source = keyword.value.value
                            if isinstance(source, str):
                                if "." not in source:
                                    errors.append(
                                        f"Source '{source}' must use 'device.parameter' format"
                                    )
                                elif source.count(".") != 1:
                                    errors.append(
                                        f"Source '{source}' must have exactly one dot"
                                    )
                                else:
                                    device, param = source.split(".")
                                    if not device or not param:
                                        errors.append(
                                            f"Source '{source}' has empty device or parameter"
                                        )

        return errors

    def _check_device_references(self, tree: ast.AST) -> list[str]:
        """Check device= parameters reference valid devices."""
        errors = []

        # TODO: Check against actual device registry
        # For now, just validate format
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                for keyword in node.keywords:
                    if keyword.arg == "device":
                        if isinstance(keyword.value, ast.Constant):
                            device = keyword.value.value
                            if isinstance(device, str):
                                if not device:
                                    errors.append("Device name cannot be empty")
                                # Add more device validation here when registry is available

        return errors

    def _check_show_call(self, tree: ast.AST) -> list[str]:
        """Check that show() is called as final statement."""
        errors = []

        # Find all show() calls
        show_calls = []
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and
                isinstance(node.func, ast.Name) and
                node.func.id == "show"):
                show_calls.append(node)

        if not show_calls:
            errors.append(
                "Missing show() call. DSL code must end with show(window) "
                "to display the generated window."
            )

        return errors

    def _check_dangerous_imports(self, tree: ast.AST) -> list[str]:
        """Check for dangerous imports in DSL code."""
        errors = []

        dangerous = {"os", "sys", "subprocess", "socket", "pathlib", "shutil", "glob"}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module in dangerous:
                        errors.append(f"Dangerous import not allowed: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module in dangerous:
                    errors.append(f"Dangerous import not allowed: from {node.module}")

        return errors

    def _check_analyse_function(self, tree: ast.AST) -> list[str]:
        """Check analyse function signature."""
        errors = []

        # Find analyse function
        analyse_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "analyse"
        ]

        if not analyse_funcs:
            errors.append(
                "Missing 'analyse' function. Code must define: "
                "def analyse(data: xr.Dataset, params: dict) -> dict:"
            )
            return errors

        func = analyse_funcs[0]

        # Check signature
        if len(func.args.args) != 2:
            errors.append(
                "analyse() function must have exactly 2 parameters: "
                "def analyse(data: xr.Dataset, params: dict) -> dict:"
            )

        # Check parameter names (best effort)
        if len(func.args.args) >= 2:
            if func.args.args[0].arg != "data":
                errors.append("First parameter should be named 'data'")
            if func.args.args[1].arg != "params":
                errors.append("Second parameter should be named 'params'")

        return errors

    def _check_analyse_imports(self, tree: ast.AST, allowed: set[str]) -> list[str]:
        """Check analyse function imports."""
        errors = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name.split(".")[0]
                    if module not in allowed:
                        errors.append(f"Import not allowed: {alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module.split(".")[0]
                if module not in allowed:
                    errors.append(f"Import not allowed: from {node.module}")

        return errors

    def _check_analyse_calls(self, tree: ast.AST) -> list[str]:
        """Check for dangerous function calls in analyse code."""
        errors = []

        blocked_funcs = {
            "eval", "exec", "compile", "open", "__import__",
            "globals", "locals", "vars", "dir", "getattr",
            "setattr", "delattr", "hasattr", "callable"
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in blocked_funcs:
                    errors.append(f"Function call not allowed: {node.func.id}()")

        return errors

    def _check_analyse_attributes(self, tree: ast.AST) -> list[str]:
        """Check for dangerous attribute access."""
        errors = []

        blocked_attrs = {
            "__class__", "__bases__", "__subclasses__", "__mro__",
            "__globals__", "__dict__", "__code__", "__func__", "__self__"
        }

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in blocked_attrs:
                    errors.append(f"Attribute access not allowed: {node.attr}")

        return errors

    def _check_analyse_returns(self, tree: ast.AST) -> list[str]:
        """Check that analyse function returns dict (best effort)."""
        errors = []

        # Find analyse function
        analyse_funcs = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == "analyse"
        ]

        if not analyse_funcs:
            return errors  # Already caught in function check

        func = analyse_funcs[0]

        # Look for return statements
        has_return = False
        for node in ast.walk(func):
            if isinstance(node, ast.Return) and node.value:
                has_return = True
                # Check if it looks like dict construction
                if isinstance(node.value, ast.Dict):
                    # Good - explicit dict literal
                    pass
                elif isinstance(node.value, ast.Name):
                    # Variable return - could be dict
                    pass
                else:
                    # Log warning but don't fail validation
                    log.warning(f"analyse() return type unclear: {ast.dump(node.value)}")

        if not has_return:
            errors.append("analyse() function must return a dict")

        return errors

    def _build_correction_prompt(self, code: str, errors: list[str], kind: str) -> str:
        """Build correction prompt for AI.

        Args:
            code: Original code with errors.
            errors: List of validation errors.
            kind: Type of code ("dsl_gui" or "analyse_function").

        Returns:
            Correction prompt string.
        """
        error_list = "\n".join(f"  {i+1}. {error}" for i, error in enumerate(errors))

        if kind == "dsl_gui":
            return f"""Your generated DSL code has {len(errors)} error(s):

{error_list}

Original code:
```python
{code}
```

Please provide ONLY the corrected Python DSL code. No explanation. No markdown.

Requirements:
- Use only LabPilot DSL functions (window, spectrum_plot, image_view, etc.)
- Source strings must use "device.parameter" format
- End with show(window) call
- No raw PyQt6/Qt imports
- No dangerous imports (os, sys, subprocess)"""

        else:  # analyse_function
            return f"""Your generated analysis function has {len(errors)} error(s):

{error_list}

Original code:
```python
{code}
```

Please provide ONLY the corrected Python function code. No explanation. No markdown.

Requirements:
- Must define: def analyse(data: xr.Dataset, params: dict) -> dict:
- Only safe imports allowed (numpy, scipy, pandas, xarray, etc.)
- No eval, exec, open, or dangerous function calls
- Must return a dict with results
- No access to __class__, __globals__, or other dunder attributes"""

    async def _request_correction(self, provider: AIProvider, prompt: str) -> str | None:
        """Request code correction from AI provider.

        Args:
            provider: AI provider instance.
            prompt: Correction prompt.

        Returns:
            Corrected code or None if failed.
        """
        try:
            from labpilot_core.ai.provider import AIMessage

            messages = [AIMessage(role="user", content=prompt)]

            response = await provider.complete(
                messages=messages,
                temperature=0.1,  # Low temperature for deterministic corrections
                max_tokens=2000
            )

            if response and response.content:
                # Extract code from response (remove any markdown formatting)
                corrected_code = response.content.strip()

                # Remove markdown code blocks if present
                if corrected_code.startswith("```python"):
                    corrected_code = corrected_code[9:]  # Remove ```python
                elif corrected_code.startswith("```"):
                    corrected_code = corrected_code[3:]   # Remove ```

                if corrected_code.endswith("```"):
                    corrected_code = corrected_code[:-3]  # Remove ```

                return corrected_code.strip()

        except Exception as e:
            log.error(f"Failed to request correction: {e}")

        return None
