import sys
sys.path.insert(0, r'C:\Users\Loser\Desktop\-\-\NEWUNI')
from agent import read_file_tool, write_file_tool, call_model

# Test reading .env
print("Reading .env:")
try:
    content = read_file_tool(r'C:\Users\Loser\Desktop\-\-\NEWUNI\.env')
    print(content[:200])
except Exception as e:
    print(f"Error: {e}")

# Test writing a file
print("\nWriting test file...")
try:
    write_file_tool(r'C:\Users\Loser\Desktop\-\-\NEWUNI\test_output.txt', "Hello from AI agent!")
    print("Write succeeded.")
except Exception as e:
    print(f"Error: {e}")

# Test calling model (simple prompt)
print("\nCalling model with prompt 'Say hello in one word'...")
try:
    response = call_model("Say hello in one word")
    print(f"Response: {response}")
except Exception as e:
    print(f"Error: {e}")

# Clean up test file
import os
try:
    os.remove(r'C:\Users\Loser\Desktop\-\-\NEWUNI\test_output.txt')
    print("\nCleaned up test file.")
except:
    pass