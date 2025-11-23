#!/usr/bin/env python3
"""
Cross-platform zip creation script for Lambda packaging.
No dependency on 'zip' command - uses Python's built-in zipfile module.
"""
import os
import sys
import zipfile
from pathlib import Path


def create_zip(source_dir: str, output_zip: str, exclude_patterns: list = None):
    """
    Create a zip file from a directory.

    Args:
        source_dir: Directory to zip
        output_zip: Output zip file path
        exclude_patterns: List of patterns to exclude (e.g., ['__pycache__', '*.pyc'])
    """
    if exclude_patterns is None:
        exclude_patterns = ['__pycache__', '*.pyc', '.pytest_cache', '*.egg-info']

    source_path = Path(source_dir).resolve()
    output_path = Path(output_zip).resolve()

    if not source_path.exists():
        print(f"Error: Source directory does not exist: {source_path}", file=sys.stderr)
        print("", file=sys.stderr)
        print("This usually means the dependencies have not been installed yet.", file=sys.stderr)
        print("", file=sys.stderr)
        print("Please run one of the following commands:", file=sys.stderr)
        print("  1. terraform apply -target=null_resource.common_layer_dependencies", file=sys.stderr)
        print("  2. terraform apply -replace=null_resource.common_layer_dependencies", file=sys.stderr)
        sys.exit(1)

    # Create parent directory for output zip if it doesn't exist
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Remove existing zip file if it exists
    if output_path.exists():
        output_path.unlink()

    def should_exclude(path: Path) -> bool:
        """Check if path should be excluded based on patterns."""
        path_str = str(path)
        for pattern in exclude_patterns:
            if pattern.startswith('*'):
                if path_str.endswith(pattern[1:]):
                    return True
            elif pattern in path.parts:
                return True
        return False

    # Create zip file
    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(source_path):
            root_path = Path(root)

            # Filter and sort directories for deterministic walk
            dirs[:] = sorted([d for d in dirs if not should_exclude(root_path / d)])

            for file in sorted(files):
                file_path = root_path / file

                # Skip excluded files
                if should_exclude(file_path):
                    continue

                # Calculate relative path from source directory
                arcname = str(file_path.relative_to(source_path)).replace(os.sep, '/')

                # Create ZipInfo with fixed timestamp for determinism
                zinfo = zipfile.ZipInfo(arcname)
                zinfo.date_time = (2020, 1, 1, 0, 0, 0)
                zinfo.compress_type = zipfile.ZIP_DEFLATED

                # Preserve file permissions
                st = os.stat(file_path)
                zinfo.external_attr = (st.st_mode & 0xFFFF) << 16

                with open(file_path, 'rb') as f:
                    zipf.writestr(zinfo, f.read())

    print(f"Created {output_path} from {source_path}")
    return 0


if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <source_dir> <output_zip>", file=sys.stderr)
        sys.exit(1)

    source_dir = sys.argv[1]
    output_zip = sys.argv[2]

    sys.exit(create_zip(source_dir, output_zip))
