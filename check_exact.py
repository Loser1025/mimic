
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()
    line = lines[774] # line 775
    print(f"Line 775: {repr(line)}")
    print(f"Chars: {[c for c in line[:20]]}")
