"""
AI Chat Widget for LabPilot

Simple chat interface that integrates with AI workflow generation tools.
"""

import asyncio
import json
from typing import Any

from PyQt6.QtCore import QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QTextCharFormat, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QTextEdit, QLineEdit,
    QScrollArea, QLabel, QFrame, QMessageBox, QSplitter
)

from labpilot_core.core.session import Session
from labpilot_core.ai.tool_registry import ToolRegistry


class AIWorker(QThread):
    """Background worker for AI operations."""

    response_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, tool_registry: ToolRegistry, tool_name: str, parameters: dict):
        super().__init__()
        self.tool_registry = tool_registry
        self.tool_name = tool_name
        self.parameters = parameters

    def run(self):
        """Execute AI tool in background."""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(
                self.tool_registry.execute_tool(self.tool_name, self.parameters)
            )
            loop.close()

            if result.get('success', False):
                self.response_received.emit(json.dumps(result, indent=2))
            else:
                self.error_occurred.emit(f"Tool failed: {result}")

        except Exception as e:
            self.error_occurred.emit(f"Error: {str(e)}")


class ChatWidget(QWidget):
    """AI Chat interface widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.session = Session()
        self.tool_registry = ToolRegistry(self.session)
        self.worker = None

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        """Set up the user interface."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)

        # Header
        header = QLabel("🤖 AI Workflow Assistant")
        header.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        header.setStyleSheet("color: #4a9eff; padding: 10px;")
        layout.addWidget(header)

        # Chat display area
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setFont(QFont("Consolas", 10))
        self.chat_display.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #ffffff;
                border: 1px solid #3c3c3c;
                padding: 8px;
                border-radius: 5px;
            }
        """)
        layout.addWidget(self.chat_display)

        # Input area
        input_layout = QHBoxLayout()

        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Ask me to generate a workflow... (e.g., 'Create a temperature sweep from 10K to 300K')")
        self.input_field.setFont(QFont("Arial", 11))
        self.input_field.setStyleSheet("""
            QLineEdit {
                padding: 8px;
                border: 2px solid #3c3c3c;
                border-radius: 5px;
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QLineEdit:focus {
                border-color: #4a9eff;
            }
        """)
        input_layout.addWidget(self.input_field)

        self.send_button = QPushButton("Send")
        self.send_button.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        self.send_button.setStyleSheet("""
            QPushButton {
                background-color: #4a9eff;
                color: #ffffff;
                border: none;
                padding: 8px 20px;
                border-radius: 5px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #3a8eef;
            }
            QPushButton:pressed {
                background-color: #2a7edf;
            }
            QPushButton:disabled {
                background-color: #666666;
            }
        """)
        input_layout.addWidget(self.send_button)

        layout.addLayout(input_layout)

        # Quick action buttons
        actions_layout = QHBoxLayout()

        quick_actions = [
            ("🌡️ Temperature Sweep", "Create a temperature sweep from 10K to 300K measuring resistance"),
            ("🌈 Spectroscopy", "Scan laser wavelength from 600nm to 800nm"),
            ("📷 Imaging", "Take 10 camera images with 50ms exposure"),
            ("📊 Time Series", "Monitor temperature for 60 seconds")
        ]

        for label, prompt in quick_actions:
            btn = QPushButton(label)
            btn.setStyleSheet("""
                QPushButton {
                    background-color: #2b2b2b;
                    color: #ffffff;
                    border: 1px solid #4a9eff;
                    padding: 5px 10px;
                    border-radius: 3px;
                    font-size: 9px;
                }
                QPushButton:hover {
                    background-color: #4a9eff;
                }
            """)
            btn.clicked.connect(lambda checked, p=prompt: self._send_quick_action(p))
            actions_layout.addWidget(btn)

        layout.addLayout(actions_layout)

        # Add welcome message
        self._add_message("assistant",
            "Hello! I'm your AI workflow assistant. I can help you create custom workflows for your laboratory instruments.\n\n"
            "Try asking me to:\n"
            "• 'Create a temperature sweep from 10K to 300K'\n"
            "• 'Generate a spectroscopy workflow from 600 to 800nm'\n"
            "• 'Make an imaging workflow with 10 images'\n"
            "• 'Monitor power for 60 seconds'\n\n"
            "I'll generate the Python code, show it to you for review, and save it as a workflow!")

    def _connect_signals(self):
        """Connect UI signals."""
        self.send_button.clicked.connect(self._send_message)
        self.input_field.returnPressed.connect(self._send_message)

    def _send_quick_action(self, prompt: str):
        """Send a pre-defined prompt."""
        self.input_field.setText(prompt)
        self._send_message()

    def _send_message(self):
        """Handle sending a message."""
        message = self.input_field.text().strip()
        if not message:
            return

        # Add user message to chat
        self._add_message("user", message)
        self.input_field.clear()

        # Disable input while processing
        self.send_button.setEnabled(False)
        self.input_field.setEnabled(False)

        # Add processing indicator
        self._add_message("assistant", "🤔 Analyzing your request and generating workflow code...")

        # Process with AI
        self._process_with_ai(message)

    def _process_with_ai(self, message: str):
        """Process message with AI workflow generation."""
        # Determine workflow name from message
        workflow_name = self._extract_workflow_name(message)

        # Start AI tool execution
        parameters = {
            "request": message,
            "workflow_name": workflow_name
        }

        self.worker = AIWorker(self.tool_registry, "generate_workflow_code", parameters)
        self.worker.response_received.connect(self._handle_ai_response)
        self.worker.error_occurred.connect(self._handle_ai_error)
        self.worker.finished.connect(self._reset_ui)
        self.worker.start()

    def _extract_workflow_name(self, message: str) -> str:
        """Extract a reasonable workflow name from the message."""
        message_lower = message.lower()

        if "temperature" in message_lower:
            return "TemperatureSweep"
        elif "spectroscopy" in message_lower or "wavelength" in message_lower or "spectrum" in message_lower:
            return "SpectroscopyMeasurement"
        elif "image" in message_lower or "camera" in message_lower:
            return "ImagingWorkflow"
        elif "time" in message_lower or "monitor" in message_lower:
            return "TimeSeriesMonitoring"
        elif "power" in message_lower:
            return "PowerMeasurement"
        elif "scan" in message_lower:
            return "ScanningMeasurement"
        else:
            return "CustomWorkflow"

    def _handle_ai_response(self, response: str):
        """Handle successful AI response."""
        try:
            result = json.loads(response)

            # Show generated code to user
            workflow_code = result.get('workflow_code', '')
            workflow_name = result.get('description', 'Generated Workflow')

            # Add formatted response
            self._add_message("assistant",
                f"✅ I've generated your workflow code for '{workflow_name}'!\n\n"
                "Here's the Python code I created:")

            # Add code in a formatted way
            self._add_code_block(workflow_code)

            # Add action options
            self._add_message("assistant",
                "What would you like to do?\n"
                "• Type 'save' to save this workflow\n"
                "• Type 'modify [changes]' to request modifications\n"
                "• Ask for a different type of workflow")

            # Store the result for potential saving
            self.last_generated_workflow = result

        except json.JSONDecodeError:
            self._add_message("assistant", f"✅ Workflow generated!\n\n{response}")

    def _handle_ai_error(self, error: str):
        """Handle AI processing error."""
        self._add_message("assistant", f"❌ Sorry, I encountered an error: {error}")

    def _reset_ui(self):
        """Reset UI after processing."""
        self.send_button.setEnabled(True)
        self.input_field.setEnabled(True)
        self.input_field.setFocus()

    def _add_message(self, sender: str, message: str):
        """Add a message to the chat display."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        # Add sender label
        if sender == "user":
            cursor.insertText("🧑 You: ")
        else:
            cursor.insertText("🤖 Assistant: ")

        # Add message content
        cursor.insertText(f"{message}\n\n")

        # Auto-scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _add_code_block(self, code: str):
        """Add formatted code block to chat."""
        cursor = self.chat_display.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)

        # Set code formatting
        format = QTextCharFormat()
        format.setBackground(QColor("#2d2d2d"))
        format.setForeground(QColor("#a0a0a0"))
        format.setFontFamily("Consolas")

        cursor.insertText("\n--- Python Code ---\n", format)
        cursor.insertText(code[:1000] + "..." if len(code) > 1000 else code, format)
        cursor.insertText("\n--- End Code ---\n\n", format)

        # Auto-scroll to bottom
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class FloatingChatWidget(QWidget):
    """Floating chat widget that can be docked to the main window."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Tool)
        self.setWindowTitle("AI Workflow Assistant")
        self.setGeometry(100, 100, 500, 600)

        # Set up layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Add chat widget
        self.chat_widget = ChatWidget()
        layout.addWidget(self.chat_widget)

        # Styling
        self.setStyleSheet("""
            FloatingChatWidget {
                background-color: #2b2b2b;
                border: 2px solid #4a9eff;
                border-radius: 10px;
            }
        """)