
import re

path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Remove lines that look like the output of the check_indent script
# Example: " 774: . 775: ................async def receive_loop():"
cleaned_lines = []
for line in lines:
    # Regex to match lines that start with " [number]: "
    if re.match(r'^\s*\d+:\s+', line):
        # If it's a debris line, we try to recover the actual code part
        # The code part starts after the last ": ...."
        match = re.search(r':\s*(?:\.\s*)*(.+)$', line)
        if match:
            # We don't know the correct indentation, so this is risky.
            # Better to just remove the line and let the function rewrite fix it.
            continue
        else:
            continue
    cleaned_lines.append(line)

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(cleaned_lines)

print("Cleaned debris from file.")
