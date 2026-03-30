"""
Comprehensive tests for LabPilot AI validation and correction system.

Tests the AI Validator's DSL and analysis code validation, self-correction loops,
and integration with AI providers for error correction.
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
import asyncio
from typing import List, Dict, Any

# Import the AI validation components
from labpilot_core.ai.validator import CodeValidator, ValidationError
from labpilot_core.ai.provider import AIProvider


class MockAIProvider(AIProvider):
    """Mock AI provider for testing."""

    def __init__(self, responses: List[str] = None):
        """Initialize with predefined responses."""
        self.responses = responses or []
        self.call_count = 0

    async def initialize(self, config: Dict[str, Any]):
        """Mock initialization."""
        pass

    async def chat(self, messages: List[Dict[str, str]], use_tools: bool = True) -> tuple[str, int]:
        """Mock chat response."""
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response, 0  # No tool calls in mock
        return "No more responses configured", 0

    async def shutdown(self):
        """Mock shutdown."""
        pass


class TestValidationError:
    """Test ValidationError exception."""

    def test_validation_error_creation(self):
        """Test ValidationError creation and attributes."""
        error = ValidationError("Test error message")
        assert str(error) == "Test error message"
        assert error.args[0] == "Test error message"


class TestCodeValidatorDSL:
    """Test DSL validation functionality."""

    def test_validator_creation(self):
        """Test CodeValidator creation."""
        validator = CodeValidator()
        assert validator is not None

    def test_valid_dsl_code(self):
        """Test validation of correct DSL code."""
        validator = CodeValidator()

        # Valid DSL code
        valid_code = '''from labpilot_core.qt.dsl import *
w = window("Test Window", "vertical")
w.add(spectrum_plot(source="spec.intensities"))
w.add(slider("Power", "laser", "power", 0, 100))
show(w)'''

        errors = validator.validate_dsl(valid_code)
        assert len(errors) == 0

    def test_dsl_missing_import(self):
        """Test validation catches missing DSL import."""
        validator = CodeValidator()

        # Missing import
        invalid_code = '''w = window("Test Window")
show(w)'''

        errors = validator.validate_dsl(invalid_code)
        assert len(errors) > 0
        assert any("import" in error.lower() for error in errors)

    def test_dsl_missing_show(self):
        """Test validation catches missing show() call."""
        validator = CodeValidator()

        # Missing show() call
        invalid_code = '''from labpilot_core.qt.dsl import *
w = window("Test Window")
w.add(spectrum_plot(source="spec.data"))'''

        errors = validator.validate_dsl(invalid_code)
        assert len(errors) > 0
        assert any("show(" in error for error in errors)

    def test_dsl_invalid_source_format(self):
        """Test validation catches invalid source format."""
        validator = CodeValidator()

        # Invalid source - no dot
        invalid_code = '''from labpilot_core.qt.dsl import *
w = window("Test")
w.add(spectrum_plot(source="invalid_source"))
show(w)'''

        errors = validator.validate_dsl(invalid_code)
        assert len(errors) > 0
        assert any("source" in error.lower() for error in errors)

    def test_dsl_syntax_error(self):
        """Test validation catches syntax errors."""
        validator = CodeValidator()

        # Syntax error - missing quote
        invalid_code = '''from labpilot_core.qt.dsl import *
w = window("Test Window)  # Missing closing quote
show(w)'''

        errors = validator.validate_dsl(invalid_code)
        assert len(errors) > 0
        assert any("syntax" in error.lower() or "unterminated" in error.lower() for error in errors)

    def test_dsl_wrong_window_type(self):
        """Test validation catches wrong window() call patterns."""
        validator = CodeValidator()

        # Wrong - not assigning window result
        invalid_code = '''from labpilot_core.qt.dsl import *
window("Test Window")
spectrum_plot(source="device.data")
show()'''

        errors = validator.validate_dsl(invalid_code)
        assert len(errors) > 0


class TestAIValidatorAnalyse:
    """Test analysis code validation functionality."""

    def test_valid_analyse_code(self):
        """Test validation of correct analysis code."""
        validator = CodeValidator()

        # Valid analysis function
        valid_code = '''import numpy as np
import scipy.signal

def analyse_spectrum(data):
    """Find peaks in spectrum data."""
    wavelengths = data['wavelengths']
    intensities = data['intensities']

    # Find peaks
    peaks, _ = scipy.signal.find_peaks(intensities, height=0.1)
    peak_wavelengths = wavelengths[peaks]

    return {
        'peak_count': len(peaks),
        'peak_positions': peak_wavelengths.tolist(),
        'max_intensity': float(np.max(intensities))
    }'''

        errors = validator.validate_analyse(valid_code, allowed_imports=['numpy', 'scipy'])
        assert len(errors) == 0

    def test_analyse_forbidden_import(self):
        """Test validation catches forbidden imports."""
        validator = CodeValidator()

        # Forbidden import
        invalid_code = '''import os
import subprocess

def analyse_data(data):
    # This tries to access filesystem
    os.system("rm -rf /")
    return {}'''

        errors = validator.validate_analyse(invalid_code, allowed_imports=['numpy'])
        assert len(errors) > 0
        assert any("forbidden" in error.lower() or "import" in error.lower() for error in errors)

    def test_analyse_no_function(self):
        """Test validation catches code without function definition."""
        validator = CodeValidator()

        # No function defined
        invalid_code = '''import numpy as np
result = np.mean([1, 2, 3])
print(result)'''

        errors = validator.validate_analyse(invalid_code, allowed_imports=['numpy'])
        assert len(errors) > 0
        assert any("function" in error.lower() for error in errors)

    def test_analyse_syntax_error(self):
        """Test validation catches syntax errors in analysis code."""
        validator = CodeValidator()

        # Syntax error
        invalid_code = '''import numpy as np
def analyse_data(data:
    return np.mean(data)'''  # Missing closing parenthesis

        errors = validator.validate_analyse(invalid_code, allowed_imports=['numpy'])
        assert len(errors) > 0
        assert any("syntax" in error.lower() for error in errors)

    def test_analyse_dangerous_operations(self):
        """Test validation catches dangerous operations."""
        validator = CodeValidator()

        # Dangerous operations
        invalid_code = '''import numpy as np
def analyse_data(data):
    # Dangerous operations
    exec("print('hello')")
    eval("1 + 1")
    __import__("os")
    return {}'''

        errors = validator.validate_analyse(invalid_code, allowed_imports=['numpy'])
        assert len(errors) > 0
        assert any("dangerous" in error.lower() or "forbidden" in error.lower() for error in errors)


class TestValidationAndCorrection:
    """Test the complete validation and correction loop."""

    @pytest.mark.asyncio
    async def test_validate_and_correct_success_first_try(self):
        """Test validation succeeds on first attempt."""
        validator = CodeValidator()
        provider = MockAIProvider()

        valid_code = '''from labpilot_core.qt.dsl import *
w = window("Test")
w.add(spectrum_plot(source="device.data"))
show(w)'''

        corrected_code, was_corrected = await validator.validate_and_correct(
            valid_code, "dsl_gui", provider, max_retries=2
        )

        assert corrected_code == valid_code
        assert was_corrected == False
        assert provider.call_count == 0  # No correction calls

    @pytest.mark.asyncio
    async def test_validate_and_correct_success_after_retry(self):
        """Test validation succeeds after correction."""
        validator = CodeValidator()

        # Mock provider returns corrected code
        corrected_code_response = '''from labpilot_core.qt.dsl import *
w = window("Test Window", "vertical")
w.add(spectrum_plot(source="device.data"))
show(w)'''

        provider = MockAIProvider([corrected_code_response])

        # Invalid code - missing show()
        invalid_code = '''from labpilot_core.qt.dsl import *
w = window("Test Window")
w.add(spectrum_plot(source="device.data"))'''

        corrected_code, was_corrected = await validator.validate_and_correct(
            invalid_code, "dsl_gui", provider, max_retries=2
        )

        assert "show(w)" in corrected_code
        assert was_corrected == True
        assert provider.call_count == 1  # One correction call

    @pytest.mark.asyncio
    async def test_validate_and_correct_fails_max_retries(self):
        """Test validation fails after max retries."""
        validator = CodeValidator()

        # Mock provider returns invalid code each time
        invalid_responses = [
            '''# Still missing show()
from labpilot_core.qt.dsl import *
w = window("Test")''',
            '''# Still invalid
from labpilot_core.qt.dsl import *
window("Test")'''
        ]

        provider = MockAIProvider(invalid_responses)

        # Invalid code
        invalid_code = '''from labpilot_core.qt.dsl import *
w = window("Test")'''

        with pytest.raises(ValidationError, match="Failed to correct code"):
            await validator.validate_and_correct(
                invalid_code, "dsl_gui", provider, max_retries=2
            )

        assert provider.call_count == 2  # Used all retries

    @pytest.mark.asyncio
    async def test_validate_and_correct_analyse_code(self):
        """Test validation and correction for analysis code."""
        validator = CodeValidator()

        # Mock provider returns corrected analysis code
        corrected_response = '''import numpy as np

def analyse_spectrum(data):
    """Analyse spectrum data safely."""
    wavelengths = data['wavelengths']
    intensities = data['intensities']

    # Find maximum
    max_idx = np.argmax(intensities)
    max_wavelength = wavelengths[max_idx]

    return {
        'peak_wavelength': float(max_wavelength),
        'peak_intensity': float(intensities[max_idx])
    }'''

        provider = MockAIProvider([corrected_response])

        # Invalid analysis code - forbidden import
        invalid_code = '''import os
import numpy as np

def analyse_spectrum(data):
    os.system("echo hello")  # Forbidden
    return {}'''

        corrected_code, was_corrected = await validator.validate_and_correct(
            invalid_code, "analyse_function", provider, max_retries=1
        )

        assert "os.system" not in corrected_code
        assert "def analyse_spectrum" in corrected_code
        assert was_corrected == True

    @pytest.mark.asyncio
    async def test_correction_prompt_generation(self):
        """Test that correction prompts are properly generated."""
        validator = CodeValidator()

        # Create a provider that saves the correction request
        correction_requests = []

        class RecordingProvider(AIProvider):
            async def initialize(self, config):
                pass

            async def chat(self, messages, use_tools=True):
                correction_requests.append(messages)
                return "corrected code", 0

            async def shutdown(self):
                pass

        provider = RecordingProvider()

        # Invalid code
        invalid_code = '''from labpilot_core.qt.dsl import *
window("Test")'''  # Missing assignment and show()

        try:
            await validator.validate_and_correct(
                invalid_code, "dsl_gui", provider, max_retries=1
            )
        except ValidationError:
            pass  # Expected to fail with mock "corrected code"

        # Check that correction request was made
        assert len(correction_requests) == 1
        messages = correction_requests[0]

        # Should have system message and user message
        assert len(messages) >= 2

        # System message should contain correction instructions
        system_msg = next(msg for msg in messages if msg["role"] == "system")
        assert "correct" in system_msg["content"].lower()

        # User message should contain the original code and errors
        user_msg = next(msg for msg in messages if msg["role"] == "user")
        assert "window(" in user_msg["content"]
        assert "error" in user_msg["content"].lower()

    @pytest.mark.asyncio
    async def test_validate_different_code_types(self):
        """Test validation works for both DSL and analysis code types."""
        validator = CodeValidator()
        provider = MockAIProvider()

        # Test DSL validation
        dsl_code = '''from labpilot_core.qt.dsl import *
w = window("Test")
show(w)'''

        result1, corrected1 = await validator.validate_and_correct(
            dsl_code, "dsl_gui", provider
        )
        assert not corrected1  # Should pass validation

        # Test analysis validation
        analysis_code = '''import numpy as np

def analyse_data(data):
    return {"mean": float(np.mean(data))}'''

        result2, corrected2 = await validator.validate_and_correct(
            analysis_code, "analyse_function", provider, allowed_imports=['numpy']
        )
        assert not corrected2  # Should pass validation


class TestValidatorIntegration:
    """Test validator integration with real code patterns."""

    def test_realistic_dsl_patterns(self):
        """Test validation of realistic DSL code patterns."""
        validator = CodeValidator()

        # Pattern 1: Simple spectrometer interface
        code1 = '''from labpilot_core.qt.dsl import *

w = window("Spectrometer Control", "vertical")
w.add(spectrum_plot(source="spectrometer.intensities", show_peak=True))
w.add(row(
    slider("Integration Time", "spectrometer", "integration_time", 1, 1000),
    button("Acquire", "trigger", "spectrometer")
))
w.add(value_display("Peak Position", "spectrometer.peak_wavelength"))
show(w)'''

        errors1 = validator.validate_dsl(code1)
        assert len(errors1) == 0

        # Pattern 2: Complex camera interface with tabs
        code2 = '''from labpilot_core.qt.dsl import *

# Control tab
control_tab = column(
    row(
        slider("Exposure", "camera", "exposure_time", 0.1, 1000),
        dropdown("Gain", "camera", "gain", ["Low", "Medium", "High"])
    ),
    row(
        button("Live", "start", "camera"),
        button("Snap", "trigger", "camera"),
        button("Stop", "stop", "camera")
    )
)

# Display tab
display_tab = column(
    image_view(source="camera.frame", colormap="grays", show_roi=True),
    row(
        value_display("FPS", "camera.fps"),
        value_display("Temperature", "camera.temperature", unit="°C")
    )
)

# Main window
w = window("Camera Interface", "vertical")
w.add(tabs(Control=control_tab, Display=display_tab))
show(w)'''

        errors2 = validator.validate_dsl(code2)
        assert len(errors2) == 0

    def test_realistic_analysis_patterns(self):
        """Test validation of realistic analysis code patterns."""
        validator = CodeValidator()

        # Pattern 1: Peak finding analysis
        code1 = '''import numpy as np
import scipy.signal

def analyse_peaks(data):
    """Find and characterize spectral peaks."""
    wavelengths = data['wavelengths']
    intensities = data['intensities']

    # Baseline subtraction
    baseline = np.percentile(intensities, 10)
    corrected = intensities - baseline

    # Find peaks
    peaks, props = scipy.signal.find_peaks(
        corrected,
        height=0.1 * np.max(corrected),
        distance=10
    )

    # Extract peak information
    peak_wavelengths = wavelengths[peaks]
    peak_heights = corrected[peaks]

    return {
        'peak_count': len(peaks),
        'peak_positions': peak_wavelengths.tolist(),
        'peak_intensities': peak_heights.tolist(),
        'total_intensity': float(np.sum(corrected))
    }'''

        errors1 = validator.validate_analyse(
            code1,
            allowed_imports=['numpy', 'scipy', 'matplotlib']
        )
        assert len(errors1) == 0

        # Pattern 2: Statistical analysis
        code2 = '''import numpy as np
import statistics

def analyse_statistics(data):
    """Compute statistical metrics for measurement data."""
    values = data['measurements']

    # Basic statistics
    mean_val = statistics.mean(values)
    std_val = statistics.stdev(values)

    # Numpy-based calculations
    percentiles = np.percentile(values, [25, 50, 75])

    # Signal-to-noise ratio
    signal = mean_val
    noise = std_val
    snr = signal / noise if noise > 0 else float('inf')

    return {
        'mean': float(mean_val),
        'std': float(std_val),
        'median': float(percentiles[1]),
        'q1': float(percentiles[0]),
        'q3': float(percentiles[2]),
        'snr': float(snr),
        'count': len(values)
    }'''

        errors2 = validator.validate_analyse(
            code2,
            allowed_imports=['numpy', 'statistics', 'math']
        )
        assert len(errors2) == 0


if __name__ == "__main__":
    pytest.main([__file__])