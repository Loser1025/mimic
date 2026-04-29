import os
import itertools
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()  # reads .env in current directory

# Retrieve the three OpenRouter keys
KEYS = [
    os.getenv("OR_KEY_1"),
    os.getenv("OR_KEY_2"),
    os.getenv("OR_KEY_3"),
]
# Filter out any None values
KEYS = [k for k in KEYS if k]
if not KEYS:
    raise ValueError("No OpenRouter keys found in .env file. Check OR_KEY_1, OR_KEY_2, OR_KEY_3.")

# Create an iterator that cycles through the keys
key_cycler = itertools.cycle(KEYS)

def get_client():
    """Return an OpenAI client configured with the next key in rotation."""
    api_key = next(key_cycler)
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

def read_file_tool(file_path: str) -> str:
    """
    Read the content of a file.
    Args:
        file_path: Path to the file (relative or absolute).
    Returns:
        File content as string.
    """
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    return p.read_text(encoding="utf-8")

def write_file_tool(file_path: str, content: str) -> None:
    """
    Write content to a file, overwriting if it exists.
    Args:
        file_path: Path to the file.
        content: Text to write.
    """
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")

def append_file_tool(file_path: str, content: str) -> None:
    """
    Append content to a file.
    Args:
        file_path: Path to the file.
        content: Text to append.
    """
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(content)

def call_model(prompt: str, model: str = "openai/gpt-oss-120b:free", temperature: float = 0.7) -> str:
    """
    Call the LLM via OpenRouter with automatic key rotation.
    Args:
        prompt: User prompt.
        model: Model identifier on OpenRouter.
        temperature: Sampling temperature.
    Returns:
        Model response text.
    """
    client = get_client()
    completion = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    return completion.choices[0].message.content

# Example usage / simple CLI
if __name__ == "__main__":
    print("AI Coding Agent with rotating OpenRouter keys (gpt-oss-120b)")
    print("Type 'exit' to quit.")
    while True:
        user_input = input("\nYou: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break
        try:
            response = call_model(user_input)
            print("\nAgent:", response)
        except Exception as e:
            print(f"\nError: {e}")
