"""
Simple test runner for ECS connection capacity testing.
Works on both Windows and Linux.
"""

import sys
import subprocess
from pathlib import Path

def main():
    """Run the ECS testing suite."""
    
    print("="*60)
    print("ECS Connection Capacity Test Suite")
    print("="*60)
    print("")
    
    # Step 1: Check environment
    print("Step 1: Checking ECS environment...")
    print("-" * 60)
    try:
        result = subprocess.run(
            [sys.executable, "check_ecs_environment.py"],
            cwd=Path(__file__).parent,
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"Error running environment check: {e}")
        return 1
    
    print("")
    print("="*60)
    print("")
    
    # Step 2: Ask if user wants to run capacity test
    print("Step 2: Connection capacity test")
    print("-" * 60)
    print("This will test connection capacity by progressively")
    print("testing 10, 25, 50, 100, 200, 500, 1000+ connections.")
    print("")
    
    response = input("Run connection capacity test? (y/n): ").strip().lower()
    if response == 'y':
        try:
            result = subprocess.run(
                [sys.executable, "test_connection_capacity.py"],
                cwd=Path(__file__).parent,
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"Error running capacity test: {e}")
            return 1
    else:
        print("Skipping capacity test.")
    
    print("")
    print("="*60)
    print("Test suite complete!")
    print("="*60)
    
    return 0

if __name__ == "__main__":
    sys.exit(main())

