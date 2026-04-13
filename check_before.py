
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Print lines 760 to 780
for i in range(760, min(780, len(lines))):
    line = lines[i]
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    print(f"{i+1:4}: {'.' * indent}{stripped}", end='')
