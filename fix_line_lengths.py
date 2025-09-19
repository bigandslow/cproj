#!/usr/bin/env python3
"""Fix remaining line length issues in cproj.py"""

import re
import subprocess

def get_violations():
    """Get all E501 violations from flake8"""
    result = subprocess.run(
        ["flake8", "cproj.py", "--select=E501"],
        capture_output=True,
        text=True
    )
    violations = []
    for line in result.stdout.strip().split('\n'):
        if line:
            match = re.match(r'cproj\.py:(\d+):80: E501 line too long \((\d+) > 79 characters\)', line)
            if match:
                violations.append((int(match.group(1)), int(match.group(2))))
    return violations

def fix_line(line):
    """Fix a line that's too long"""
    if len(line) <= 79:
        return line

    # Handle f-strings in print statements
    if 'print(' in line and ('f"' in line or "f'" in line):
        # Extract indentation
        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * (indent + 4)
        
        # Split f-strings at logical points
        if '": ' in line:
            parts = line.split('": ', 1)
            if len(parts) == 2 and len(parts[0]) > 40:
                return parts[0] + '": "\n' + indent_str + '"' + parts[1].lstrip('"')
        
        # Split at Path() expressions
        if 'Path(wt[' in line and len(line) > 85:
            # Break before Path
            line = line.replace('f"', 'f"', 1).replace('{Path', '"\n' + indent_str + 'f"{Path', 1)
            return line

    # Handle echo statements in multiline strings
    if 'echo "' in line and len(line) > 85:
        # Break echo statements logically
        if 'terminal in' in line:
            line = line.replace('terminal in"', 'terminal in this"', 1)
            line = line.replace(' \\', '', 1)
            return line[:79] + '" \\\n'

    return line

def main():
    # Read the file
    with open('cproj.py', 'r') as f:
        lines = f.readlines()

    # Get all violations
    violations = get_violations()
    print(f"Found {len(violations)} violations to fix")

    # Fix violations from bottom to top (to preserve line numbers)
    fixed_count = 0
    for line_num, length in reversed(violations):
        idx = line_num - 1
        if idx < len(lines):
            original = lines[idx].rstrip('\n')
            fixed = fix_line(original)
            if fixed != original:
                lines[idx] = fixed if fixed.endswith('\n') else fixed + '\n'
                fixed_count += 1
                print(f"Fixed line {line_num} (was {length} chars)")

    # Write the file back
    with open('cproj.py', 'w') as f:
        f.writelines(lines)

    print(f"\nFixed {fixed_count} violations")

    # Check remaining violations
    violations = get_violations()
    print(f"Remaining violations: {len(violations)}")

if __name__ == "__main__":
    main()
