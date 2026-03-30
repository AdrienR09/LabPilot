#!/usr/bin/env python3
"""
AI Assistant Page - Chat Interface with Tool Execution
Converts React AI assistant to Qt Material Design
"""

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QLineEdit,
    QLabel, QPushButton, QScrollArea, QFrame, QSplitter,
    QListWidget, QListWidgetItem, QGroupBox, QCheckBox,
    QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QThread, QObject
from PyQt6.QtGui import QFont, QTextCursor, QPixmap
from datetime import datetime
from typing import Dict, List, Optional
import json

class ChatMessage(QFrame):
    """Individual chat message widget"""

    def __init__(self, content: str, is_user: bool = True, timestamp: Optional[datetime] = None):
        super().__init__()
        self.content = content
        self.is_user = is_user
        self.timestamp = timestamp or datetime.now()
        self.setup_ui()

    def setup_ui(self):
        """Setup message UI"""
        self.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # Message container
        message_container = QFrame()
        message_container.setObjectName("message_container")

        # Style based on sender
        if self.is_user:
            message_container.setStyleSheet("""
                #message_container {
                    background-color: #2196F3;
                    color: white;
                    border-radius: 12px;
                    padding: 12px 16px;
                    margin-left: 60px;
                }
            """)
            layout.setAlignment(Qt.AlignmentFlag.AlignRight)
        else:
            message_container.setStyleSheet("""
                #message_container {
                    background-color: #f0f0f0;
                    color: #333;
                    border-radius: 12px;
                    padding: 12px 16px;
                    margin-right: 60px;
                }
            """)
            layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        container_layout = QVBoxLayout(message_container)

        # Message content
        content_label = QLabel(self.content)
        content_label.setWordWrap(True)
        content_label.setStyleSheet("border: none; background: transparent;")
        container_layout.addWidget(content_label)

        # Timestamp
        timestamp_label = QLabel(self.timestamp.strftime("%H:%M"))
        timestamp_label.setStyleSheet("""
            font-size: 10px;
            color: #666;
            margin-top: 4px;
        """)
        if self.is_user:
            timestamp_label.setStyleSheet(timestamp_label.styleSheet() + "color: #bbdefb;")
        container_layout.addWidget(timestamp_label)

        layout.addWidget(message_container)

class ToolExecutionWidget(QFrame):
    """Widget showing AI tool execution progress"""

    def __init__(self, tool_name: str):
        super().__init__()
        self.tool_name = tool_name
        self.setup_ui()

    def setup_ui(self):
        """Setup tool execution UI"""
        self.setFrameStyle(QFrame.Shape.Box)
        self.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: #fff3e0;
                padding: 12px;
                margin: 8px 0;
            }
        """)

        layout = QVBoxLayout(self)

        # Header
        header_layout = QHBoxLayout()

        icon_label = QLabel("🔧")
        icon_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(icon_label)

        title_label = QLabel(f"Executing: {self.tool_name}")
        title_label.setStyleSheet("font-weight: bold; color: #e65100;")
        header_layout.addWidget(title_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Progress bar
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #ddd;
                border-radius: 4px;
                background-color: #f5f5f5;
                height: 8px;
            }
            QProgressBar::chunk {
                background-color: #ff9800;
                border-radius: 3px;
            }
        """)
        layout.addWidget(self.progress_bar)

    def set_completed(self, success: bool = True):
        """Mark execution as completed"""
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)

        if success:
            self.setStyleSheet(self.styleSheet().replace("#fff3e0", "#e8f5e8").replace("#e65100", "#2e7d32"))
        else:
            self.setStyleSheet(self.styleSheet().replace("#fff3e0", "#ffebee").replace("#e65100", "#c62828"))

class AIAssistantPage(QWidget):
    """AI Assistant page with chat interface and tool execution"""

    # Signals
    message_sent = pyqtSignal(str)
    clear_chat_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.api_client = None
        self.conversation_history = []
        self.ai_available = True  # Set AI as available by default
        self.setup_ui()

        # Initialize AI status
        self.update_ai_status(True)

    def setup_ui(self):
        """Setup AI assistant page UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(20)

        # Header
        header_layout = QHBoxLayout()

        title = QLabel("AI Assistant")
        title.setStyleSheet("font-size: 28px; font-weight: bold; color: #333;")
        header_layout.addWidget(title)

        # AI Status indicator
        self.ai_status_label = QLabel("◉ AI Online")
        self.ai_status_label.setStyleSheet("font-size: 16px; color: #4CAF50; font-weight: bold;")
        header_layout.addWidget(self.ai_status_label)

        header_layout.addStretch()

        # Clear chat button
        clear_btn = QPushButton("✕ Clear Chat")
        clear_btn.clicked.connect(self.clear_chat)
        header_layout.addWidget(clear_btn)

        layout.addLayout(header_layout)

        # Main chat area
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Chat area (left side)
        chat_frame = QFrame()
        chat_frame.setFrameStyle(QFrame.Shape.Box)
        chat_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
        """)

        chat_layout = QVBoxLayout(chat_frame)

        # Messages scroll area
        self.messages_scroll = QScrollArea()
        self.messages_scroll.setWidgetResizable(True)
        self.messages_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self.messages_widget = QWidget()
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.messages_scroll.setWidget(self.messages_widget)
        chat_layout.addWidget(self.messages_scroll)

        # Input area
        input_frame = QFrame()
        input_frame.setFrameStyle(QFrame.Shape.NoFrame)
        input_layout = QHBoxLayout(input_frame)

        self.message_input = QLineEdit()
        self.message_input.setPlaceholderText("Ask me about your lab setup, instruments, or data analysis...")
        self.message_input.returnPressed.connect(self.send_message)
        self.message_input.setStyleSheet("""
            QLineEdit {
                border: 1px solid #ddd;
                border-radius: 20px;
                padding: 10px 16px;
                font-size: 14px;
            }
            QLineEdit:focus {
                border-color: #2196F3;
            }
        """)
        input_layout.addWidget(self.message_input)

        send_btn = QPushButton("Send")
        send_btn.setObjectName("send_button")
        send_btn.clicked.connect(self.send_message)
        send_btn.setStyleSheet("""
            #send_button {
                background-color: #2196F3;
                color: white;
                border: none;
                border-radius: 20px;
                padding: 10px 20px;
                font-weight: bold;
            }
            #send_button:hover {
                background-color: #1976D2;
            }
            #send_button:disabled {
                background-color: #ccc;
            }
        """)
        input_layout.addWidget(send_btn)

        chat_layout.addWidget(input_frame)

        main_splitter.addWidget(chat_frame)

        # Tools panel (right side)
        tools_frame = self.create_tools_panel()
        main_splitter.addWidget(tools_frame)

        # Set splitter proportions (70% chat, 30% tools)
        main_splitter.setSizes([700, 300])

        layout.addWidget(main_splitter)

        # Load initial messages
        self.load_initial_messages()

    def create_tools_panel(self) -> QFrame:
        """Create tools and capabilities panel"""
        tools_frame = QFrame()
        tools_frame.setFrameStyle(QFrame.Shape.Box)
        tools_frame.setStyleSheet("""
            QFrame {
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                background-color: white;
            }
        """)
        tools_frame.setMaximumWidth(300)

        layout = QVBoxLayout(tools_frame)

        # Title
        title = QLabel("Available Tools")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #333; padding: 12px;")
        layout.addWidget(title)

        # Tools list
        tools_list = [
            ("🔧", "List Instruments", "Show all connected instruments"),
            ("⚡", "Control Devices", "Connect/disconnect instruments"),
            ("📊", "Analyze Data", "Process and visualize results"),
            ("🔍", "Search Files", "Find configuration files"),
            ("⚙️", "Generate Code", "Create measurement scripts"),
            ("📈", "Plot Results", "Create graphs and charts"),
            ("🤖", "Run Workflows", "Execute automated experiments")
        ]

        for icon, name, description in tools_list:
            tool_item = self.create_tool_item(icon, name, description)
            layout.addWidget(tool_item)

        layout.addStretch()

        # Capabilities info
        info_group = QGroupBox("Capabilities")
        info_group.setStyleSheet("""
            QGroupBox {
                font-weight: bold;
                border: 1px solid #ddd;
                border-radius: 6px;
                margin: 8px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
        """)

        info_layout = QVBoxLayout(info_group)

        capabilities = [
            "✅ Instrument control",
            "✅ Data analysis",
            "✅ Code generation",
            "✅ File management",
            "✅ Plot creation",
            "❌ Hardware repair",
            "❌ Physical connections"
        ]

        for capability in capabilities:
            cap_label = QLabel(capability)
            cap_label.setStyleSheet("font-size: 12px; padding: 2px;")
            info_layout.addWidget(cap_label)

        layout.addWidget(info_group)

        return tools_frame

    def create_tool_item(self, icon: str, name: str, description: str) -> QFrame:
        """Create individual tool item"""
        item = QFrame()
        item.setFrameStyle(QFrame.Shape.NoFrame)
        item.setStyleSheet("""
            QFrame {
                border: 1px solid #f0f0f0;
                border-radius: 6px;
                background-color: #fafafa;
                margin: 4px;
                padding: 8px;
            }
            QFrame:hover {
                background-color: #f0f0f0;
            }
        """)

        layout = QVBoxLayout(item)
        layout.setSpacing(4)

        # Header with icon and name
        header_layout = QHBoxLayout()

        icon_label = QLabel(icon)
        icon_label.setStyleSheet("font-size: 16px;")
        header_layout.addWidget(icon_label)

        name_label = QLabel(name)
        name_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(name_label)

        header_layout.addStretch()
        layout.addLayout(header_layout)

        # Description
        desc_label = QLabel(description)
        desc_label.setStyleSheet("font-size: 10px; color: #666;")
        desc_label.setWordWrap(True)
        layout.addWidget(desc_label)

        return item

    def load_initial_messages(self):
        """Load initial welcome messages"""
        welcome_msg = """Hello! I'm your AI assistant for laboratory automation. I can help you with:

• Managing and controlling instruments
• Analyzing experimental data
• Generating measurement scripts
• Creating visualizations and plots
• Troubleshooting setup issues

Just ask me anything about your lab setup or experiments!"""

        self.add_message(welcome_msg, is_user=False)

    def add_message(self, content: str, is_user: bool = True):
        """Add message to chat"""
        message = ChatMessage(content, is_user)
        self.messages_layout.addWidget(message)

        # Scroll to bottom
        self.messages_scroll.verticalScrollBar().setValue(
            self.messages_scroll.verticalScrollBar().maximum()
        )

        # Store in history
        self.conversation_history.append({
            "content": content,
            "is_user": is_user,
            "timestamp": datetime.now().isoformat()
        })

    def add_tool_execution(self, tool_name: str) -> ToolExecutionWidget:
        """Add tool execution widget"""
        tool_widget = ToolExecutionWidget(tool_name)
        self.messages_layout.addWidget(tool_widget)

        # Scroll to bottom
        self.messages_scroll.verticalScrollBar().setValue(
            self.messages_scroll.verticalScrollBar().maximum()
        )

        return tool_widget

    def send_message(self):
        """Send user message"""
        message_text = self.message_input.text().strip()
        if not message_text:
            return

        # Add user message
        self.add_message(message_text, is_user=True)
        self.message_input.clear()

        # Emit signal for processing
        self.message_sent.emit(message_text)

        if not self.ai_available:
            # Show offline message
            self.add_message("AI Assistant is currently offline. Please check your connection and try again.", is_user=False)
        else:
            # Simulate AI response (replace with real API call)
            self.simulate_ai_response(message_text)

    def simulate_ai_response(self, user_message: str):
        """Simulate AI response for development"""
        # Add typing indicator or tool execution
        if "instrument" in user_message.lower() or "device" in user_message.lower():
            tool_widget = self.add_tool_execution("list_adapters")

            # Simulate tool completion
            QTimer.singleShot(2000, lambda: self.complete_tool_execution(tool_widget, True))

            # Add response after tool execution
            QTimer.singleShot(2500, lambda: self.add_message(
                "I found 4 instruments in your setup:\n• Main Spectrometer (Connected)\n• CCD Camera (Disconnected)\n• Sample X-Stage (Connected)\n• Reference Photodiode (Connected)",
                is_user=False
            ))

        elif "data" in user_message.lower() or "analysis" in user_message.lower():
            QTimer.singleShot(1000, lambda: self.add_message(
                "I can help you analyze your experimental data. What type of analysis would you like to perform? I can:\n\n• Create plots and visualizations\n• Calculate statistics\n• Fit curves to your data\n• Export results in various formats",
                is_user=False
            ))

        else:
            QTimer.singleShot(1000, lambda: self.add_message(
                "I understand you're asking about lab automation. Could you be more specific about what you'd like help with? I can assist with instrument control, data analysis, or workflow creation.",
                is_user=False
            ))

    def complete_tool_execution(self, tool_widget: ToolExecutionWidget, success: bool):
        """Mark tool execution as completed"""
        tool_widget.set_completed(success)

    def clear_chat(self):
        """Clear all chat messages"""
        # Clear message widgets
        for i in reversed(range(self.messages_layout.count())):
            widget = self.messages_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()

        # Clear history
        self.conversation_history.clear()

        # Reload initial messages
        self.load_initial_messages()

    def set_api_client(self, client):
        """Set API client for backend communication"""
        self.api_client = client

    def update_ai_status(self, available: bool):
        """Update AI availability status"""
        self.ai_available = available
        if available:
            self.ai_status_label.setText("◉ AI Online")
            self.ai_status_label.setStyleSheet("font-size: 16px; color: #4CAF50; font-weight: bold;")
        else:
            self.ai_status_label.setText("◯ AI Offline")
            self.ai_status_label.setStyleSheet("font-size: 16px; color: #f44336; font-weight: bold;")

    def refresh_data(self):
        """Refresh AI status and capabilities"""
        if self.api_client:
            # TODO: Check AI availability via API
            pass