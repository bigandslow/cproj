#!/usr/bin/env python3
"""
Manual fixes for line length violations
"""

def fix_lines():
    with open('cproj.py', 'r') as f:
        lines = f.readlines()

    fixed_lines = []

    for i, line in enumerate(lines):
        orig = line.rstrip('\n')

        # Skip if already short enough
        if len(orig) <= 79:
            fixed_lines.append(line)
            continue

        # Apply specific fixes for common patterns
        fixed = False

        # Handle long subprocess.run calls
        if 'subprocess.run(' in orig and ', capture_output=True' in orig:
            # Split capture_output to new line
            parts = orig.split(', capture_output=True')
            if len(parts) == 2:
                indent = len(orig) - len(orig.lstrip())
                new_line = parts[0] + ',\n' + ' ' * (indent + 4) + 'capture_output=True' + parts[1] + '\n'
                fixed_lines.append(new_line)
                fixed = True

        # Handle long print statements with f-strings
        elif orig.strip().startswith('print(f"') and len(orig) > 79:
            # Try to split long f-strings
            if ': ' in orig and 'f"' in orig:
                parts = orig.split(': ', 1)
                if len(parts) == 2:
                    indent = len(orig) - len(orig.lstrip())
                    new_line = parts[0] + ': "\n' + ' ' * (indent + 4) + 'f"' + parts[1] + '\n'
                    fixed_lines.append(new_line)
                    fixed = True

        # Handle long input() calls
        elif 'input(' in orig and len(orig) > 79:
            # Split long input strings
            input_pos = orig.find('input(')
            if input_pos >= 0:
                before = orig[:input_pos]
                after = orig[input_pos+6:]  # Skip 'input('
                if '"' in after:
                    quote_pos = after.find('"')
                    if quote_pos >= 0:
                        indent = len(orig) - len(orig.lstrip())
                        new_line = before + 'input(\n' + ' ' * (indent + 4) + after + '\n'
                        fixed_lines.append(new_line)
                        fixed = True

        if not fixed:
            fixed_lines.append(line)

    with open('cproj.py', 'w') as f:
        f.writelines(fixed_lines)

if __name__ == '__main__':
    fix_lines()
    print("Applied manual fixes")