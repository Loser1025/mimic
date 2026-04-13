
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(len(lines)):
    if 'await asyncio.gather(send_loop(), receive_loop())' in lines[i]:
        lines[i] = ' ' * 16 + lines[i].lstrip()
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Fixed gather indentation to 16 spaces.")
