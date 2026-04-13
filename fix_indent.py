
import re

path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# Target the broken block: starts with safe_print and ends with a RuntimeError or a broken attempt to fix it.
# The broken part currently looks like: safe_print(...)`r`n await asyncio.sleep(0)`r`n continue
# We use a regex that matches the literal `r`n and the surrounding text.

pattern = r'safe_print\(C\.gray\(f"  \[DBG\] receive: .*?flush=True\).*?(?:`r`n|`n|\\r\\n|\\n).*?continue'
replacement = (
    '                            safe_print(C.gray(f"  [DBG] receive: ターン{_turn} 完了→次のターンへ"), flush=True)\n'
    '                            await asyncio.sleep(0)\n'
    '                            continue'
)

new_content = re.sub(pattern, replacement, content, flags=re.DOTALL)

with open(path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Fix applied successfully via Python.")
