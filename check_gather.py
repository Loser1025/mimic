
path = r'C:\Users\Loser\Desktop\-\-\unilive\voice_agent.py'
with open(path, 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find the gather line and the lines around it
for i in range(len(lines)):
    if 'await asyncio.gather(send_loop(), receive_loop())' in lines[i]:
        print(f"Line {i+1}: {repr(lines[i])}")
        # Print 5 lines before and after
        for j in range(i-5, i+6):
            if 0 <= j < len(lines):
                print(f"{j+1:4}: {'.' * (len(lines[j]) - len(lines[j].lstrip()))}{lines[j].strip()}")
