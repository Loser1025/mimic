
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

start = max(0, 770 - 1)
end = min(len(lines), 790)
for i in range(start, end):
    line = lines[i]
    # Show leading spaces as dots
    stripped = line.lstrip()
    indent = len(line) - len(stripped)
    print(f"{i+1:4}: {'.' * indent}{stripped}", end='')
