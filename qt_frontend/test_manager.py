#!/usr/bin/env python3
"""
Test script for LabPilot Qt Material Manager
Quick way to test the new Qt interface
"""

import sys
import os
from pathlib import Path

# Add the qt_frontend directory to Python path
qt_frontend_dir = Path(__file__).parent
sys.path.insert(0, str(qt_frontend_dir))

def test_manager():
    """Test the Qt Material manager"""
    try:
        print("🚀 Starting LabPilot Qt Material Manager...")
        print("=" * 50)

        # Import and run the manager
        from manager_main import main
        return main()

    except ImportError as e:
        print(f"❌ Import Error: {e}")
        print("\nMake sure you have installed the requirements:")
        print("pip install -r requirements.txt")
        print("\nRequired packages:")
        print("- PyQt6")
        print("- qt-material")
        print("- pyqtgraph")
        print("- requests")
        return 1

    except Exception as e:
        print(f"❌ Error starting manager: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_manager())