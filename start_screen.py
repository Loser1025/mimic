import sys
import time
import random

class C:
    """配色定義（V3計画.py の Razer Green を継承）"""
    RESET   = "\033[0m"
    _RG     = "\033[38;2;0;255;0m"      # Razer Green
    _WHITE  = "\033[38;2;255;255;255m"  # Pure White
    _GRAY   = "\033[38;2;110;110;130m"  # Muted Gray

def progressive_build_animation():
    m = C._RG
    w = C._WHITE
    g = C._GRAY
    r = C.RESET

    # 描画するアスキーアート
    aa_lines = [
        "  _    _ _    _ _____ __  __  ____   _____   ____  ",
        " | |  | |  \  | |_   _|  \/  |/ __ \ / ____| |___ \ ",
        " | |  | ||  \ | | | | | \  / | |  | | |  __    __) |",
        " | |  | || . \| | | | | |\/| | |  | | | |_ |  |__ < ",
        " | |__| || |\  || | |_| |  | | |__| | |__| |  ___) |",
        "  \____/ |_| \_||_____|_|  |_|\____/ \_____| |____/ "
    ]

    # --- Step 1: Scanning System (プログレスバー) ---
    print(f"\n{g}[ SYSTEM CHECK ]{r}")
    for i in range(21):
        percent = i * 5
        # █（フルブロック）と ░（ライトシェード）の組み合わせ
        bar = "█" * i + "░" * (20 - i)
        sys.stdout.write(f"\r  {m}{bar}{r} {percent}%")
        sys.stdout.flush()
        # 速度にランダム性を持たせて「解析してる感」を出す
        time.sleep(0.03 + random.random() * 0.07)
    
    print(f"\n\n{w}  >> INITIALIZING UNIMOG CORE...{r}\n")
    time.sleep(0.6)

    # --- Step 2: Line-by-Line AA Build (AAの段階描画) ---
    for line in aa_lines:
        # 1行ずつ Razer Green で描画
        sys.stdout.write(f"{m}{line}{r}\n")
        sys.stdout.flush()
        # Claude Code 風の「重み」のあるディレイ
        time.sleep(0.12)

    # --- Step 3: Status Deployment (最終ステータス) ---
    time.sleep(0.5)
    print(f"\n{w}  [ STATUS ] {m}ONLINE{r} / {w}VERSION 3.0.0{r}")
    print(f"{g}  --------------------------------------------------{r}\n")
    
    # ユーザーへの入力準備完了合図
    sys.stdout.write(f"{m}⚡{r} {w}Ready for instructions...{r}\n")

if __name__ == "__main__":
    try:
        progressive_build_animation()
    except KeyboardInterrupt:
        pass