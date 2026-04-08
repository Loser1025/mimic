import os
import sys
import time
import math
import tkinter as tk
from tkinter import filedialog
from dotenv import load_dotenv
from groq import Groq
from pydub import AudioSegment

# Python 3.13 shim for audioop
try:
    import audioop
except ImportError:
    try:
        import audioop_lts as audioop
        import sys as sys_mod
        sys_mod.modules['audioop'] = audioop
    except ImportError:
        pass

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def transcribe_file(file_path):
    temp_audio_path = "temp_audio_for_groq.mp3"
    
    try:
        # Step 1: Audio Extraction
        print(f"\n[Step 1/3] Extracting audio from: {os.path.basename(file_path)}...")
        start_time = time.time()
        
        audio = AudioSegment.from_file(file_path)
        audio.export(temp_audio_path, format="mp3")
        
        elapsed = time.time() - start_time
        print(f"  -> Audio extraction completed in {elapsed:.2f} seconds.")

        # File Size Check (Groq Limit: 25MB)
        file_size_mb = os.path.getsize(temp_audio_path) / (1024 * 1024)
        print(f"  -> Extracted audio size: {file_size_mb:.2f} MB")
        
        # Step 2: Upload and Transcription
        print(f"[Step 2/3] Transcribing... (This may take a few minutes)")
        start_time = time.time()
        
        max_size_mb = 24  # Safe limit slightly below 25MB
        if file_size_mb > max_size_mb:
            print(f"  -> File exceeds {max_size_mb}MB. Splitting audio into chunks...")
            
            # Calculate number of chunks needed
            num_chunks = math.ceil(file_size_mb / max_size_mb)
            chunk_length_ms = len(audio) // num_chunks
            full_transcription = []

            for i in range(num_chunks):
                start_ms = i * chunk_length_ms
                # Ensure the last chunk goes to the end of the file
                end_ms = (i + 1) * chunk_length_ms if i < num_chunks - 1 else len(audio)
                
                chunk = audio[start_ms:end_ms]
                chunk_path = f"temp_chunk_{i}.mp3"
                chunk.export(chunk_path, format="mp3")
                
                print(f"    Processing chunk {i+1}/{num_chunks}...", end="\r")
                
                with open(chunk_path, "rb") as file:
                    chunk_text = client.audio.transcriptions.create(
                        file=(chunk_path, file),
                        model="whisper-large-v3",
                        response_format="text",
                    )
                    full_transcription.append(chunk_text)
                
                os.remove(chunk_path) # Clean up chunk file immediately
            
            transcription = "\n".join(full_transcription)
            print(f"\n  -> All chunks processed.")
        else:
            # Single file processing
            with open(temp_audio_path, "rb") as file:
                transcription = client.audio.transcriptions.create(
                    file=(temp_audio_path, file),
                    model="whisper-large-v3",
                    response_format="text",
                )
        
        elapsed = time.time() - start_time
        print(f"  -> Transcription completed in {elapsed:.2f} seconds.")

        # Step 3: Saving Result
        print(f"[Step 3/3] Saving result to text file...")
        output_path = os.path.splitext(file_path)[0] + "_raw_transcription.txt"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(transcription)
        
        print(f"\nSUCCESS: Result saved to:\n{output_path}")

    except Exception as e:
        print(f"\nERROR occurred during processing: {e}")
    finally:
        if os.path.exists(temp_audio_path):
            os.remove(temp_audio_path)

def main():
    root = tk.Tk()
    root.withdraw()
    
    print("\n--- Raw Transcription Mode ---")
    selected_files = tk.filedialog.askopenfilenames(
        title="Select audio/video files",
        filetypes=[("Audio/Video files", "*.mp3 *.wav *.m4a *.mp4 *.mov *.mkv *.flac"), ("All files", "*.*")]
    )

    if not selected_files:
        print("No files selected. Exiting...")
        return

    files_to_process = list(selected_files)
    print(f"Selected {len(files_to_process)} file(s).")

    for file_path in files_to_process:
        print("-" * 50)
        print(f"Processing: {file_path}")
        transcribe_file(file_path)
    
    print("\n" + "-" * 50)
    print("All tasks completed.")

if __name__ == "__main__":
    main()
