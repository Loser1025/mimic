import sys
import time
import re

# --- class C のネオンカラー定義（修正済み）---
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    # Preserved Green Main m from old code turn 1 preserve.
    _RG     = "\033[38;2;0;255;0m"      # Razer Green (メイン：実行)
    _WHITE  = "\033[38;2;255;255;255m"  # Pure White (重要)
    # Deep Slate g logic previous turns.
    _RG_DIM = "\033[38;2;60;60;80m"     # Deep Slate (枠線・グリッチ用)

def print_aa_start_screen():
    """
    Glinting ASCII Art Start Screen for unimog3 (Preserved old color turn 1 glitch).
    AA from image_d50b8c.png. Glint Dim, AA Main (turn 1 logic).
    """
    # ── カラー定義 ────────────────────────────────────────────────
    # Must swap Main and Dim to make glitch m g.
    m = C._RG
    w = C._WHITE
    g = C._RG_DIM
    r = C.RESET

    # ── AA Base (Unimog) Razer Green from old code turn 1 preserve.
    # Set to main color m.
    unimog_base = [
        f"{m}  _    _ _    _ _____ __  __  ____   _____   ____  ",
        f"{m} | |  | |  \\  | |_   _|  \\/  |/ __ \\ / ____| |___ \\ ",
        f"{m} | |  | ||  \\ | | | | | \\  / | |  | | |  __    __) |",
        f"{m} | |  | || . \\| | | | | |\\/| | |  | | | |_ |  |__ < ",
        f"{m} | |__| || |\\  || | |_| |  | | |__| | |__| |  ___) |",
        f"{m}  \\____/ |_| \\_||_____|_|  |_|\\____/ \\_____| |____/ "
    ]

    # Glint text uses Dim color Deep Slate g.
    glint_text = [
        f"{g}  _    _ _    _ _____ __  __  ____   _____   ____  ",
        f"{g} | |  | |  \\  | |_   _|  \\/  |/ __ \\ / ____| |___ \\ ",
        f"{g} | |  | ||  \\ | | | | | \\  / | |  | | |  __    __) |",
        f"{g} | |  | || . \\| | | | | |\\/| | |  | | | |_ |  |__ < ",
        f"{g} | |__| || |\\  || | |_| |  | | |__| | |__| |  ___) |",
        f"{g}  \\____/ |_| \\_||_____|_|  |_|\\____/ \\_____| |____/ "
    ]

    # AA Subtitle (uses old code turn 1 preserve color logic)
    subtitle = f"[{m}Gemini Multi-Account Hybrid AI Agent{r}] // {w}unimog3{r}"
    
    def _print_glint():
        print("\n")
        # Step 1: Subtitle first
        print(f"{'  ' * 8}{subtitle}\n")
        sys.stdout.flush()
        time.sleep(1.0) # Subtitle first

        # Step 2: Print AA Main Razer Green.
        print("\n".join(unimog_base))
        sys.stdout.flush()
        
        # Step 3: Perform Swapping effect Main->Dim->Main
        
        time.sleep(0.3)
        
        # Swaps Main<->Dim
        print("\033[F" * len(unimog_base)) # Back up
        sys.stdout.flush()
        
        print("\n".join(glint_text)) # Glint is Dim Deep Slate
        sys.stdout.flush()
        
        time.sleep(0.08) # glint duration
        
        print("\033[F" * len(unimog_base)) # Back up
        sys.stdout.flush()
        
        print("\n".join(unimog_base)) # Swap back to Main
        sys.stdout.flush()
        
        time.sleep(1.2) # Allow to read AA Main
        
    _print_glint()

if __name__ == "__main__":
    # stderrを無効化（AA描画時のちらつき防止）
    import os
    # sys.stderr = open(os.devnull, 'w')
    
    print_aa_start_screen()