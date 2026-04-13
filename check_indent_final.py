
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the line with 'async def run_voice_mode'
start_line = -1
for i, line in enumerate(lines):
    if 'async def run_voice_mode' in line:
        start_line = i
        break

if start_line != -1:
    print(f"run_voice_mode start: line {start_line+1}, indent {len(lines[start_line]) - len(lines[start_line].lstrip())}")
    # Print lines from there to 800 with space counts
    for i in range(start_line, min(800, len(lines))):
        line = lines[i]
        indent = len(line) - len(line.lstrip())
        print(f"{i+1:4}: [{indent:2}] {line.strip()}")
else:
    print("Could not find run_voice_mode")
