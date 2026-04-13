
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(len(lines)):
    line = lines[i]
    if 'safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 完了' in line:
        # Correct current and next two lines to 24 spaces
        lines[i] = ' ' * 24 + line.lstrip()
        if i + 1 < len(lines) and 'await asyncio.sleep(0)' in lines[i+1]:
            lines[i+1] = ' ' * 24 + lines[i+1].lstrip()
        if i + 2 < len(lines) and 'continue' in lines[i+2]:
            lines[i+2] = ' ' * 24 + lines[i+2].lstrip()
        break

with open(path, 'w', encoding='utf-8') as f:
    f.writelines(lines)

print("Indentation fixed successfully.")
