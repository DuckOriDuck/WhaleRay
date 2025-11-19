#!/usr/bin/env python3
"""
Clean __pycache__ directories and .pyc files from lambda directories
"""
import os
import shutil
from pathlib import Path

def clean_pycache(root_dir):
    """Remove all __pycache__ directories and .pyc files"""
    root_path = Path(root_dir)

    # Remove __pycache__ directories
    for pycache_dir in root_path.rglob('__pycache__'):
        if pycache_dir.is_dir():
            print(f"Removing: {pycache_dir}")
            shutil.rmtree(pycache_dir)

    # Remove .pyc files
    for pyc_file in root_path.rglob('*.pyc'):
        print(f"Removing: {pyc_file}")
        pyc_file.unlink()

    print("Cleanup complete!")

if __name__ == "__main__":
    # Clean entire lambda directory
    script_dir = Path(__file__).parent
    clean_pycache(script_dir)
    print(f"Cleaned: {script_dir}")