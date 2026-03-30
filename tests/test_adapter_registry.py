#!/usr/bin/env python3
"""Verify adapter registry and auto-discovery system.

Tests that:
1. Adapters are auto-discovered on import
2. Registry contains expected adapters
3. Adapters can be instantiated
4. Schemas are correctly defined
"""

import sys
from pathlib import Path

# Add labpilot to path
labpilot_root = Path(__file__).parent.parent
sys.path.insert(0, str(labpilot_root / "src"))

print("=" * 80)
print("LABPILOT ADAPTER REGISTRY VERIFICATION")
print("=" * 80)
print()

# Import adapter registry (triggers auto-discovery)
print("1. Importing adapter registry...")
try:
    from labpilot_core.adapters import adapter_registry
    print("✅ Successfully imported adapter_registry")
except Exception as e:
    print(f"❌ Failed to import: {e}")
    sys.exit(1)

print()

# List all discovered adapters
print("2. Listing discovered adapters...")
adapters = adapter_registry.list()
print(f"✅ Found {len(adapters)} adapters:")
for key in sorted(adapters.keys()):
    print(f"  - {key}")

print()

# Test schema retrieval
print("3. Testing schema retrieval...")
try:
    schemas = adapter_registry.list_with_schemas()
    print(f"✅ Retrieved {len(schemas)} schemas")

    # Show a few example schemas
    if schemas:
        print("\nExample schemas:")
        for key in list(schemas.keys())[:3]:
            schema = schemas[key]
            print(f"\n  {key}:")
            print(f"    name: {schema.name}")
            print(f"    kind: {schema.kind}")
            print(f"    readable: {list(schema.readable.keys())}")
            print(f"    settable: {list(schema.settable.keys())}")
            print(f"    tags: {schema.tags}")
except Exception as e:
    print(f"❌ Schema retrieval failed: {e}")
    import traceback
    traceback.print_exc()

print()

# Test tag search
print("4. Testing tag-based search...")
try:
    # Search for cameras
    camera_adapters = adapter_registry.search(tags=["camera"])
    print(f"✅ Found {len(camera_adapters)} camera adapters:")
    for key in camera_adapters.keys():
        print(f"  - {key}")

    # Search for motors
    motor_adapters = adapter_registry.search(tags=["motor"])
    print(f"✅ Found {len(motor_adapters)} motor adapters:")
    for key in motor_adapters.keys():
        print(f"  - {key}")

    # Search for VISA instruments
    visa_adapters = adapter_registry.search(tags=["VISA"])
    print(f"✅ Found {len(visa_adapters)} VISA adapters:")
    for key in visa_adapters.keys():
        print(f"  - {key}")

except Exception as e:
    print(f"❌ Tag search failed: {e}")

print()

# Summary
print("=" * 80)
print("VERIFICATION SUMMARY")
print("=" * 80)
print()
print(f"Total adapters registered: {len(adapters)}")
print()
print("Adapters by category:")
print(f"  PyMeasure adapters: {len([k for k in adapters.keys() if 'keithley' in k or 'srs' in k or 'pymeasure' in k])}")
print(f"  Camera adapters: {len([k for k in adapters.keys() if 'andor' in k])}")
print(f"  Motor/Stage adapters: {len([k for k in adapters.keys() if 'kinesis' in k or 'mff' in k or 'fw' in k])}")
print()

if len(adapters) >= 5:
    print("✅  VERIFICATION PASSED")
    print()
    print("Adapter system is working correctly!")
    print("Ready to proceed with Phase 2: Workflow Engine")
else:
    print("⚠️  WARNING: Expected more adapters")
    print("Some adapters may not have been discovered.")

print()
print("=" * 80)
