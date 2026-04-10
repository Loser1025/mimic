import sys
import time

# --- class C のネオンカラー定義 ---
class C:
    RESET   = "\033[0m"
    BOLD    = "\033[1m"
    _RG     = "\033[38;2;0;255;0m"      # Razer Green (メイン)
    _WHITE  = "\033[38;2;255;255;255m"  # Pure White (重要)
    _RG_DIM = "\033[38;2;60;60;80m"     # Deep Slate (枠線・グリッチ用)

def print_aa_start_screen():
    """
    Glinting ASCII Art Start Screen for unimog3.
    AA from image_d50b8c.png. Swaps Main<->Dim.
    """
    # ── カラー定義 ────────────────────────────────────────────────
    m = C._RG
    w = C._WHITE
    g = C._RG_DIM
    r = C.RESET

    # ── AA Base (Razer Green)
    unimog_base = [
        f"{m}  _    _ _    _ _____ __  __  ____   _____   ____  ",
        f"{m} | |  | |  \\  | |_   _|  \\/  |/ __ \\ / ____| |___ \\ ",
        f"{m} | |  | ||  \\ | | | | | \\  / | |  | | |  __    __) |",
        f"{m} | |  | || . \\| | | | | |\\/| | |  | | | |_ |  |__ < ",
        f"{m} | |__| || |\\  || | |_| |  | | |__| | |__| |  ___) |",
        f"{m}  \\____/ |_| \\_||_____|_|  |_|\\____/ \\_____| |____/ "
    ]

    # Glitch text uses Dim color Deep Slate
    glint_text = [
        f"{g}  _    _ _    _ _____ __  __  ____   _____   ____  ",
        f"{g} | |  | |  \\  | |_   _|  \\/  |/ __ \\ / ____| |___ \\ ",
        f"{g} | |  | ||  \\ | | | | | \\  / | |  | | |  __    __) |",
        f"{g} | |  | || . \\| | | | | |\\/| | |  | | | |_ |  |__ < ",
        f"{g} | |__| || |\\  || | |_| |  | | |__| | |__| |  ___) |",
        f"{g}  \\____/ |_| \\_||_____|_|  |_|\\____/ \\_____| |____/ "
    ]

    # AA Subtitle
    subtitle = f"[{m}Gemini Multi-Account Hybrid AI Agent{r}] // {w}unimog3{r}"

    def _print_glint():
        print("\n")
        # Step 1: Subtitle first
        print(f"{'  ' * 8}{subtitle}\n")
        sys.stdout.flush()
        time.sleep(1.0) # Subtitle duration

        # Step 2: Print Main text
        print("\n".join(unimog_base))
        sys.stdout.flush()

        # Step 3: Glitch Swapping effect Main->Dim->Main
        time.sleep(0.3)
        # Swap Main<->Dim
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
    print_aa_start_screen()
