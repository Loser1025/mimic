import json, urllib.request, urllib.parse, sys, os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.colorchooser import askcolor
from PIL import Image, ImageTk, ImageDraw, ImageFont

sys.stdout.reconfigure(encoding='utf-8')

# ===== 固定設定 =====
CREDS_PATH = 'C:/Users/弁護士法人響/.config/gws/authorized_user.json'
SSID       = '1CjLomIoC_DAFoiEnIS3c_h8lUv3sB0oOyUHxTD68CZk'
SHEET_ID   = 0

# ===== 認証 =====
def get_access_token():
    creds = json.load(open(CREDS_PATH))
    data = urllib.parse.urlencode({**creds, 'grant_type': 'refresh_token'}).encode()
    return json.loads(urllib.request.urlopen(
        urllib.request.Request('https://oauth2.googleapis.com/token', data=data)
    ).read())['access_token']

def rgb_to_sheets_color(rgb):
    return {'red': rgb[0]/255, 'green': rgb[1]/255, 'blue': rgb[2]/255}

# ===== 画像をドット化 =====
def dotify_image(image_path, canvas_w, canvas_h, method):
    img = Image.open(image_path).convert('RGB')
    resample = Image.Resampling.NEAREST if method == 'ドット絵（NEAREST）' else Image.Resampling.LANCZOS
    return img.resize((canvas_w, canvas_h), resample)

# ===== 画像にドットテキストを重ねる =====
def overlay_dot_text(base_img, text, position, fg_color, size_pct=100):
    """
    base_img (canvas サイズの PIL Image) にテキストをドット化して上書きする。
    高解像度でレンダリング → canvas サイズへ NEAREST リサイズ で自然にドット化。
    """
    w, h = base_img.size
    scale = 8
    rw, rh = w * scale, h * scale

    # base_img を高解像度に引き伸ばす
    big_img = base_img.resize((rw, rh), Image.Resampling.NEAREST)
    draw = ImageDraw.Draw(big_img)

    lines = text.strip().splitlines() or ['']
    n_lines = len(lines)
    font_size = max(10, int(rh // max(n_lines + 2, 4) * size_pct / 100))

    font = None
    for font_path in [
        'C:/Windows/Fonts/meiryo.ttc',
        'C:/Windows/Fonts/msgothic.ttc',
        'C:/Windows/Fonts/YuGothM.ttc',
        'C:/Windows/Fonts/arial.ttf',
    ]:
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default()

    line_bboxes = [draw.textbbox((0, 0), line, font=font) for line in lines]
    line_heights = [b[3] - b[1] for b in line_bboxes]
    line_widths  = [b[2] - b[0] for b in line_bboxes]
    total_h = sum(line_heights) + (n_lines - 1) * int(font_size * 0.25)

    if position == '上':
        y = int(rh * 0.05)
    elif position == '下':
        y = rh - total_h - int(rh * 0.05)
    else:  # 中央
        y = (rh - total_h) // 2

    for i, line in enumerate(lines):
        x = (rw - line_widths[i]) // 2
        draw.text((x, y), line, fill=fg_color, font=font)
        y += line_heights[i] + int(font_size * 0.25)

    # canvas サイズへ NEAREST でドット化
    return big_img.resize((w, h), Image.Resampling.NEAREST)

# ===== PIL Image → スプレッドシートへ送信 =====
def send_pil_to_sheets(pil_img, canvas_w, canvas_h, log_fn):
    token = get_access_token()
    img = pil_img.convert('RGB')
    pixels = img.load()

    requests = [
        {"updateDimensionProperties": {
            "range": {"sheetId": SHEET_ID, "dimension": "COLUMNS",
                      "startIndex": 0, "endIndex": canvas_w},
            "properties": {"pixelSize": 8}, "fields": "pixelSize"
        }},
        {"updateDimensionProperties": {
            "range": {"sheetId": SHEET_ID, "dimension": "ROWS",
                      "startIndex": 0, "endIndex": canvas_h},
            "properties": {"pixelSize": 8}, "fields": "pixelSize"
        }}
    ]

    for r in range(canvas_h):
        c = 0
        while c < canvas_w:
            color = pixels[c, r]
            sc = c
            while c < canvas_w and pixels[c, r] == color:
                c += 1
            requests.append({'repeatCell': {
                'range': {'sheetId': SHEET_ID,
                          'startRowIndex': r, 'endRowIndex': r+1,
                          'startColumnIndex': sc, 'endColumnIndex': c},
                'cell': {'userEnteredFormat': {'backgroundColor': rgb_to_sheets_color(color)}},
                'fields': 'userEnteredFormat.backgroundColor'
            }})

    total = len(requests)
    log_fn(f'送信開始（{total} リクエスト）')

    BATCH = 500
    url = f'https://sheets.googleapis.com/v4/spreadsheets/{SSID}:batchUpdate'
    for i in range(0, total, BATCH):
        batch = requests[i:i+BATCH]
        body = json.dumps({'requests': batch}).encode()
        urllib.request.urlopen(urllib.request.Request(
            url, data=body,
            headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
        ))
        done = min(i+BATCH, total)
        log_fn(f'  {done}/{total} 完了（{done*100//total}%）')

    log_fn('✓ 完成！スプレッドシートを確認してください。')

# ===== GUI =====
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('🎨 GeminiArt – スプレッドシートに描画')
        self.resizable(False, False)
        self.configure(bg='#1e1e2e', padx=20, pady=20)

        self.image_path  = tk.StringVar(value='')
        self.canvas_size = tk.StringVar(value='64 × 64')
        self.method      = tk.StringVar(value='ドット絵（NEAREST）')
        self.text_pos    = tk.StringVar(value='中央')
        self.font_size   = tk.IntVar(value=100)
        self.fg_color    = (255, 255, 255)

        self._build_ui()

    # ---- ユーティリティ ----
    def _label(self, parent, text, **kw):
        return tk.Label(parent, text=text, bg='#1e1e2e', fg='#cdd6f4',
                        font=('Arial', 10), **kw)

    def _rgb_to_hex(self, rgb):
        return '#{:02x}{:02x}{:02x}'.format(*rgb)

    def _canvas_wh(self):
        s = self.canvas_size.get().replace(' ', '').split('×')
        return int(s[0]), int(s[1])

    def _build_ui(self):
        tk.Label(self, text='🎨  GeminiArt', bg='#1e1e2e', fg='#cba6f7',
                 font=('Arial', 16, 'bold')).pack(pady=(0, 14))

        # ── 画像選択 ──
        self._label(self, '画像ファイル').pack(anchor='w')
        frm_file = tk.Frame(self, bg='#1e1e2e')
        frm_file.pack(fill='x', pady=(2, 8))
        self.lbl_file = tk.Label(frm_file, textvariable=self.image_path,
                                 bg='#313244', fg='#a6e3a1', font=('Arial', 9),
                                 width=42, anchor='w', padx=6, pady=4, relief='flat')
        self.lbl_file.pack(side='left', fill='x', expand=True)
        tk.Button(frm_file, text='📂 選択', command=self._pick_file,
                  bg='#89b4fa', fg='#1e1e2e', font=('Arial', 10, 'bold'),
                  relief='flat', padx=10, cursor='hand2').pack(side='left', padx=(6, 0))

        # ── プレビュー ──
        self.preview_lbl = tk.Label(self, bg='#313244', width=64, height=8,
                                    text='画像を選択するとプレビュー表示', fg='#6c7086',
                                    font=('Arial', 9))
        self.preview_lbl.pack(fill='x', pady=(0, 10))

        # ── テキストオーバーレイ ──
        sep_frm = tk.Frame(self, bg='#45475a', height=1)
        sep_frm.pack(fill='x', pady=(0, 10))

        self._label(self, '🔤  テキストオーバーレイ（任意）').pack(anchor='w')

        self.txt_entry = tk.Text(self, height=3, bg='#313244', fg='#cdd6f4',
                                 font=('Arial', 11), relief='flat',
                                 insertbackground='#cba6f7', padx=6, pady=4)
        self.txt_entry.pack(fill='x', pady=(2, 8))
        self.txt_entry.bind('<KeyRelease>', lambda _: self._refresh_preview())

        # 位置 + 文字色
        frm_txt_cfg = tk.Frame(self, bg='#1e1e2e')
        frm_txt_cfg.pack(fill='x', pady=(0, 10))

        frm_pos = tk.Frame(frm_txt_cfg, bg='#1e1e2e')
        frm_pos.pack(side='left', padx=(0, 20))
        self._label(frm_pos, 'テキスト位置').pack(anchor='w')
        for val in ('上', '中央', '下'):
            tk.Radiobutton(frm_pos, text=val, variable=self.text_pos, value=val,
                           bg='#1e1e2e', fg='#cdd6f4', selectcolor='#313244',
                           activebackground='#1e1e2e', activeforeground='#cba6f7',
                           font=('Arial', 10), command=self._refresh_preview
                           ).pack(side='left', padx=4)

        frm_color = tk.Frame(frm_txt_cfg, bg='#1e1e2e')
        frm_color.pack(side='left', padx=(0, 20))
        self._label(frm_color, '文字色').pack(anchor='w')
        self.fg_patch = tk.Button(frm_color, text='      ', relief='flat',
                                  cursor='hand2', command=self._pick_fg_color,
                                  bg=self._rgb_to_hex(self.fg_color))
        self.fg_patch.pack(fill='x')

        frm_size = tk.Frame(frm_txt_cfg, bg='#1e1e2e')
        frm_size.pack(side='left')
        self.size_label = self._label(frm_size, f'文字サイズ: 100%')
        self.size_label.pack(anchor='w')
        tk.Scale(frm_size, variable=self.font_size,
                 from_=25, to=200, resolution=5, orient='horizontal',
                 length=140, bg='#313244', fg='#cdd6f4', troughcolor='#45475a',
                 highlightthickness=0, bd=0, activebackground='#89b4fa',
                 command=lambda v: (self.size_label.configure(text=f'文字サイズ: {v}%'),
                                    self._refresh_preview())
                 ).pack()

        # ── 設定 ──
        sep_frm2 = tk.Frame(self, bg='#45475a', height=1)
        sep_frm2.pack(fill='x', pady=(0, 10))

        frm_cfg = tk.Frame(self, bg='#1e1e2e')
        frm_cfg.pack(fill='x', pady=(0, 4))

        frm_left = tk.Frame(frm_cfg, bg='#1e1e2e')
        frm_left.pack(side='left', padx=(0, 16))
        self._label(frm_left, 'キャンバスサイズ').pack(anchor='w')
        cb_size = ttk.Combobox(frm_left, textvariable=self.canvas_size, width=14,
                               values=['32 × 32', '64 × 64', '96 × 96', '128 × 128'],
                               state='readonly')
        cb_size.pack()
        cb_size.bind('<<ComboboxSelected>>', lambda _: self._refresh_preview())

        frm_right = tk.Frame(frm_cfg, bg='#1e1e2e')
        frm_right.pack(side='left')
        self._label(frm_right, 'リサイズ方式').pack(anchor='w')
        cb_method = ttk.Combobox(frm_right, textvariable=self.method, width=22,
                                 values=['ドット絵（NEAREST）', '写真・イラスト（LANCZOS）'],
                                 state='readonly')
        cb_method.pack()
        cb_method.bind('<<ComboboxSelected>>', lambda _: self._refresh_preview())

        # ── 実行ボタン ──
        frm_btns = tk.Frame(self, bg='#1e1e2e')
        frm_btns.pack(fill='x', pady=(14, 4))

        self.btn_apply = tk.Button(frm_btns, text='🚀  スプレッドシートに描画',
                                   command=self._run,
                                   bg='#a6e3a1', fg='#1e1e2e',
                                   font=('Arial', 12, 'bold'),
                                   relief='flat', pady=10, cursor='hand2')
        self.btn_apply.pack(side='left', fill='x', expand=True, padx=(0, 4))

        self.btn_save = tk.Button(frm_btns, text='💾 保存',
                                  command=self._save_image,
                                  bg='#89b4fa', fg='#1e1e2e',
                                  font=('Arial', 12, 'bold'),
                                  relief='flat', pady=10, cursor='hand2')
        self.btn_save.pack(side='left')

        # ── ログ ──
        self._label(self, 'ログ').pack(anchor='w', pady=(8, 2))
        self.log_box = tk.Text(self, height=8, bg='#181825', fg='#cdd6f4',
                               font=('Consolas', 9), relief='flat',
                               state='disabled', padx=6, pady=4)
        self.log_box.pack(fill='x')

    # ---- イベント ----
    def _pick_file(self):
        path = filedialog.askopenfilename(
            title='画像を選択',
            filetypes=[('画像ファイル', '*.png *.jpg *.jpeg *.gif *.bmp *.webp'),
                       ('すべて', '*.*')]
        )
        if not path:
            return
        self.image_path.set(path)
        self._refresh_preview()

    def _pick_fg_color(self):
        rgb_full, _ = askcolor(color=self._rgb_to_hex(self.fg_color),
                               parent=self, title='文字色を選択')
        if rgb_full:
            self.fg_color = tuple(int(v) for v in rgb_full)
            self.fg_patch.configure(bg=self._rgb_to_hex(self.fg_color))
            self._refresh_preview()

    def _build_preview_image(self):
        """現在の設定でプレビュー用 PIL Image を生成。画像未選択時は None を返す。"""
        path = self.image_path.get()
        if not path or not os.path.exists(path):
            return None
        w, h = self._canvas_wh()
        img = dotify_image(path, w, h, self.method.get())
        text = self.txt_entry.get('1.0', 'end').strip()
        if text:
            img = overlay_dot_text(img, text, self.text_pos.get(), self.fg_color,
                                   self.font_size.get())
        return img

    def _refresh_preview(self):
        try:
            img = self._build_preview_image()
            if img is None:
                return
            w, h = img.size
            scale = max(1, 256 // max(w, h))
            img_disp = img.resize((w * scale, h * scale), Image.Resampling.NEAREST)
            photo = ImageTk.PhotoImage(img_disp)
            self.preview_lbl.configure(image=photo, text='', bg='#000000',
                                       width=img_disp.width, height=img_disp.height)
            self.preview_lbl.image = photo
        except Exception as e:
            self.preview_lbl.configure(text=f'プレビュー失敗: {e}', image='', bg='#313244')

    def _log(self, msg):
        self.log_box.configure(state='normal')
        self.log_box.insert('end', msg + '\n')
        self.log_box.see('end')
        self.log_box.configure(state='disabled')
        self.update()

    def _save_image(self):
        img = self._build_preview_image()
        if img is None:
            messagebox.showerror('エラー', '画像ファイルを選択してください。')
            return
        save_path = filedialog.asksaveasfilename(
            title='ドット絵を保存',
            defaultextension='.png',
            filetypes=[('PNG', '*.png'), ('JPEG', '*.jpg'), ('すべて', '*.*')]
        )
        if not save_path:
            return
        img.save(save_path)
        self._log(f'✓ 保存しました: {save_path}')

    def _run(self):
        path = self.image_path.get()
        if not path or not os.path.exists(path):
            messagebox.showerror('エラー', '画像ファイルを選択してください。')
            return

        self.btn_apply.configure(state='disabled', text='送信中...')
        self.log_box.configure(state='normal')
        self.log_box.delete('1.0', 'end')
        self.log_box.configure(state='disabled')

        try:
            img = self._build_preview_image()
            w, h = self._canvas_wh()
            send_pil_to_sheets(img, w, h, self._log)
        except Exception as e:
            self._log(f'❌ エラー: {e}')
            messagebox.showerror('エラー', str(e))
        finally:
            self.btn_apply.configure(state='normal', text='🚀  スプレッドシートに描画')

if __name__ == '__main__':
    app = App()
    app.mainloop()
