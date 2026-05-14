import os
import subprocess
import sys

base = r"C:\Users\Loser\Desktop\-\tamalabo"
target_dir = None
for d in os.listdir(base):
    full = os.path.join(base, d)
    if os.path.isdir(full) and "文字" in d:
        target_dir = full
        break

if target_dir is None:
    print("ERROR: target directory not found")
    sys.exit(1)

print(f"Target dir: {target_dir}")
script = os.path.join(target_dir, "transcribe_raw.py")
print(f"Script: {script}")

subprocess.Popen(
    [sys.executable, script],
    cwd=target_dir,
    creationflags=subprocess.CREATE_NEW_CONSOLE
)
print("Launched.")
