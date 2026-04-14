"""
voice_gui.py
────────────────────────────────────────────────────────────────
UNIMOG Voice - 近未来 HUD インターフェース
Sci-Fi PyQt6 GUI for Gemini Live API Voice Agent

起動方法:
    python voice_gui.py
"""

import sys
import asyncio
import re
import math
import random
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QFrame, QSizePolicy, QTextEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF,
    QPropertyAnimation, QEasingCurve,
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QPainterPath, QLinearGradient, QRadialGradient, QPalette,
    QTextCursor, QTextCharFormat, QConicalGradient,
)

# ── パス設定 ──────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

# ANSI エスケープ除去
_ANSI_RE = re.compile(r'\x1b\[[0-9;]*[mKJHABCDfsuhl]')
def strip_ansi(t: str) -> str:
    return _ANSI_RE.sub('', t)

# ── カラーパレット ─────────────────────────────────────────────────
_BG       = "#03060d"
_BG2      = "#060d1a"
_PANEL    = "#08121f"
_BORDER   = "#0a2035"
_CYAN     = "#00e5ff"
_CYAN_DIM = "#004d5a"
_GREEN    = "#00e676"
_GREEN_DIM= "#003d20"
_PURPLE   = "#d500f9"
_ORANGE   = "#ff6d00"
_RED      = "#ff1744"
_YELLOW   = "#ffd600"
_GRAY     = "#2a4a5a"
_WHITE    = "#cce8f4"
_DIM      = "#0b1e2d"

# ── メッセージ種別判定 ─────────────────────────────────────────────
def _classify(text: str) -> str:
    t = text.strip()
    if '[あなた]'  in t: return 'user'
    if '[AI]'     in t: return 'ai'
    if any(x in t for x in ['[ツール]', '[引数]', '[結果]', '⚡', '並列実行']): return 'tool'
    if any(x in t for x in ['[エラー]', '✗', 'APIError', 'Traceback', 'Error']): return 'error'
    if any(x in t for x in ['🧠', '💡', '[RAG]', '教訓', '記憶']): return 'memory'
    if any(x in t for x in ['[AutoGit]', 'バックアップ', 'チェックポイント', 'ロールバック']): return 'git'
    if any(x in t for x in ['接続完了', '接続中', '再接続', '終了']): return 'connect'
    if any(x in t for x in ['書き込み確認', '削除確認', '⚠']): return 'confirm'
    return 'system'

# ════════════════════════════════════════════════════════════════
#  GridBackground — 背景グリッド
# ════════════════════════════════════════════════════════════════

class GridBackground(QWidget):
    """パースペクティブグリッド + スキャンライン背景"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._scan_y   = 0
        self._timer    = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(30)

    def _tick(self):
        self._scan_y = (self._scan_y + 2) % max(self.height(), 1)
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # ── 背景
        p.fillRect(0, 0, w, h, QColor(_BG))

        # ── グリッド線
        grid_c = QColor(_BORDER)
        grid_c.setAlpha(60)
        pen = QPen(grid_c, 1)
        p.setPen(pen)
        step = 40
        for x in range(0, w, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h, step):
            p.drawLine(0, y, w, y)

        # ── スキャンライン
        scan_c = QColor(_CYAN)
        scan_c.setAlpha(18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(scan_c))
        p.drawRect(0, self._scan_y, w, 3)

        # ── 薄いヴィネット
        grad = QRadialGradient(w / 2, h / 2, max(w, h) * 0.7)
        grad.setColorAt(0, QColor(0, 0, 0, 0))
        grad.setColorAt(1, QColor(0, 0, 0, 120))
        p.setBrush(QBrush(grad))
        p.drawRect(0, 0, w, h)

        p.end()


# ════════════════════════════════════════════════════════════════
#  VoiceVisualizer — アニメーション音声ビジュアライザー
# ════════════════════════════════════════════════════════════════

class VoiceVisualizer(QWidget):
    """
    近未来スタイルの音声ビジュアライザー
    - 外リング: 目盛り + 回転アーク
    - 中間リング: 64本の周波数バー
    - 内円: 脈動グロー + ステータス文字
    """

    _STATES = {
        'idle':       ('STANDBY',   _GRAY,   0.25),
        'listening':  ('LISTENING', _CYAN,   1.00),
        'processing': ('PROCESSING',_PURPLE, 0.90),
        'speaking':   ('SPEAKING',  _GREEN,  1.00),
        'error':      ('ERROR',     _RED,    1.00),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background: transparent;")

        self._state       = 'idle'
        n = 64
        self._bars        = [random.uniform(0.02, 0.12) for _ in range(n)]
        self._bar_targets = [random.uniform(0.02, 0.12) for _ in range(n)]
        self._arc_angle   = 0.0
        self._arc2_angle  = 180.0
        self._pulse       = 0.0
        self._pulse_dir   = 1
        self._glow_t      = 0.0
        self._glow_dir    = 1
        self._active      = False
        self._tick_count  = 0

        t = QTimer(self)
        t.timeout.connect(self._animate)
        t.start(16)

    def set_state(self, state: str):
        self._state  = state
        self._active = state in ('listening', 'processing', 'speaking')
        self.update()

    def _animate(self):
        self._tick_count += 1
        speed = 0.08 if self._active else 0.02
        for i in range(len(self._bars)):
            self._bars[i] += (self._bar_targets[i] - self._bars[i]) * 0.12
            if random.random() < speed:
                hi = 0.90 if self._active else 0.10
                self._bar_targets[i] = random.uniform(0.03, hi)

        rot = 1.4 if self._active else 0.25
        self._arc_angle  = (self._arc_angle  + rot)       % 360
        self._arc2_angle = (self._arc2_angle - rot * 0.7) % 360

        self._pulse   += 0.05 * self._pulse_dir
        if self._pulse >= 1.0: self._pulse_dir = -1
        if self._pulse <= 0.0: self._pulse_dir  =  1

        self._glow_t  += 0.025 * self._glow_dir
        if self._glow_t >= 1.0: self._glow_dir = -1
        if self._glow_t <= 0.2: self._glow_dir  =  1

        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()
        cx, cy = w / 2.0, h / 2.0
        R = min(w, h) / 2.0 - 6

        label, hex_col, intensity = self._STATES.get(self._state, self._STATES['idle'])
        col = QColor(hex_col)
        eff = intensity * self._glow_t  # effective brightness

        # ── 外リング: 目盛り ──────────────────────────────────────
        tick_R = R - 2
        for i in range(72):
            a = math.radians(i * 5)
            is_major = (i % 9 == 0)
            l0 = tick_R - (8 if is_major else 4)
            l1 = tick_R
            c = QColor(col)
            c.setAlpha(int((90 if is_major else 40) * intensity))
            p.setPen(QPen(c, 1.5 if is_major else 0.8))
            p.drawLine(
                QPointF(cx + l0 * math.cos(a), cy + l0 * math.sin(a)),
                QPointF(cx + l1 * math.cos(a), cy + l1 * math.sin(a)),
            )

        # ── 外リング: 回転アーク2本 ───────────────────────────────
        arc_R = R - 4
        rect  = QRectF(cx - arc_R, cy - arc_R, arc_R * 2, arc_R * 2)
        for angle, span, width, alpha_mul in [
            (self._arc_angle,   100,  2.5, 1.0),
            (self._arc2_angle,   60,  1.5, 0.6),
        ]:
            c = QColor(col); c.setAlpha(int(200 * eff * alpha_mul))
            pen = QPen(c, width)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawArc(rect, int(angle * 16), int(span * 16))

        # ── 周波数バー ────────────────────────────────────────────
        n = len(self._bars)
        r_inner = R * 0.38
        r_outer = R * 0.72
        for i, bar in enumerate(self._bars):
            a = (i / n) * 2 * math.pi - math.pi / 2
            ri = r_inner
            ro = r_inner + (r_outer - r_inner) * bar
            alpha = int(200 * bar * intensity)
            c = QColor(col); c.setAlpha(alpha)
            pen = QPen(c, 1.8)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.drawLine(
                QPointF(cx + ri * math.cos(a), cy + ri * math.sin(a)),
                QPointF(cx + ro * math.cos(a), cy + ro * math.sin(a)),
            )

        # ── 内円グロー ────────────────────────────────────────────
        inner_r = R * 0.34 * (1.0 + self._pulse * 0.06 * intensity)
        for gi in range(5):
            gr = inner_r + gi * 7
            ga = int(35 * (1 - gi / 5) * eff)
            gc = QColor(col); gc.setAlpha(ga)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(gc))
            p.drawEllipse(QPointF(cx, cy), gr, gr)

        # メイン内円
        grad = QRadialGradient(cx, cy, inner_r)
        c0 = QColor(col); c0.setAlpha(int(50 * intensity))
        c1 = QColor(col); c1.setAlpha(0)
        grad.setColorAt(0, c0); grad.setColorAt(1, c1)
        p.setBrush(QBrush(grad))
        rim = QColor(col); rim.setAlpha(int(150 * intensity))
        p.setPen(QPen(rim, 1.5))
        p.drawEllipse(QPointF(cx, cy), inner_r, inner_r)

        # ── ステータステキスト ────────────────────────────────────
        font = QFont("Consolas", 9, QFont.Weight.Bold)
        p.setFont(font)
        tc = QColor(col); tc.setAlpha(int(230 * eff))
        p.setPen(tc)
        fm = QFontMetrics(font)
        tw = fm.horizontalAdvance(label)
        p.drawText(QPointF(cx - tw / 2, cy + fm.height() / 3), label)

        p.end()


# ════════════════════════════════════════════════════════════════
#  HoloPanel — コーナーブラケット付きパネル
# ════════════════════════════════════════════════════════════════

class HoloPanel(QFrame):
    """近未来スタイルのパネル外枠（コーナーブラケット + タイトル）"""

    def __init__(self, title: str = "", color: str = _CYAN, parent=None):
        super().__init__(parent)
        self._title = title
        self._color = QColor(color)
        self._glow  = 0.6
        self._gdir  = 1
        self.setStyleSheet("background: transparent; border: none;")
        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(50)

    def _tick(self):
        self._glow += 0.018 * self._gdir
        if self._glow >= 1.0: self._gdir = -1
        if self._glow <= 0.3: self._gdir  =  1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        L, T = 18, 2

        c = QColor(self._color); c.setAlpha(int(180 * self._glow))
        p.setPen(QPen(c, T))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # 4コーナー
        segs = [
            ((0,0),(L,0)), ((0,0),(0,L)),
            ((w-L,0),(w,0)), ((w,0),(w,L)),
            ((0,h-L),(0,h)), ((0,h),(L,h)),
            ((w-L,h),(w,h)), ((w,h-L),(w,h)),
        ]
        for (x1,y1),(x2,y2) in segs:
            p.drawLine(x1, y1, x2, y2)

        # タイトル
        if self._title:
            font = QFont("Consolas", 8, QFont.Weight.Bold)
            p.setFont(font)
            tc = QColor(self._color); tc.setAlpha(200)
            p.setPen(tc)
            p.drawText(10, 12, self._title)

        p.end()


# ════════════════════════════════════════════════════════════════
#  ConversationLog — 会話ログ
# ════════════════════════════════════════════════════════════════

_MSG_STYLE = {
    'user':    {'prefix': '▶ YOU     ', 'fg': _CYAN,   'bold': True },
    'ai':      {'prefix': '◈ AI      ', 'fg': _GREEN,  'bold': True },
    'tool':    {'prefix': '⚙ TOOL    ', 'fg': _PURPLE, 'bold': False},
    'error':   {'prefix': '✖ ERROR   ', 'fg': _RED,    'bold': True },
    'memory':  {'prefix': '◎ MEMORY  ', 'fg': _YELLOW, 'bold': False},
    'git':     {'prefix': '⌥ GIT     ', 'fg': _ORANGE, 'bold': False},
    'connect': {'prefix': '◉ SYSTEM  ', 'fg': _GREEN,  'bold': False},
    'confirm': {'prefix': '⚠ CONFIRM ', 'fg': _ORANGE, 'bold': True },
    'system':  {'prefix': '· LOG     ', 'fg': _GRAY,   'bold': False},
}

class ConversationLog(QTextEdit):
    """スクロール可能な会話/ログウィジェット"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFont(QFont("Consolas", 10))
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG2};
                color: {_WHITE};
                border: none;
                padding: 8px 10px;
                selection-background-color: #00e5ff25;
            }}
            QScrollBar:vertical {{
                background: {_BG};
                width: 5px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {_CYAN_DIM};
                border-radius: 2px;
                min-height: 20px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {_CYAN};
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

    def add_entry(self, kind: str, text: str):
        style = _MSG_STYLE.get(kind, _MSG_STYLE['system'])
        ts = datetime.now().strftime('%H:%M:%S')

        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if cursor.position() > 0:
            cursor.insertText('\n')

        # タイムスタンプ
        fmt_ts = QTextCharFormat()
        fmt_ts.setForeground(QColor(_GRAY))
        fmt_ts.setFont(QFont("Consolas", 8))
        cursor.setCharFormat(fmt_ts)
        cursor.insertText(f'[{ts}]  ')

        # プレフィックス
        fmt_pfx = QTextCharFormat()
        fmt_pfx.setForeground(QColor(style['fg']))
        fmt_pfx.setFont(QFont("Consolas", 9, QFont.Weight.Bold if style['bold'] else QFont.Weight.Normal))
        cursor.setCharFormat(fmt_pfx)
        cursor.insertText(style['prefix'])

        # 本文
        fmt_txt = QTextCharFormat()
        is_main = kind in ('user', 'ai')
        fmt_txt.setForeground(QColor(_WHITE if is_main else style['fg']))
        fmt_txt.setFont(QFont("Consolas", 10, QFont.Weight.Bold if (is_main and style['bold']) else QFont.Weight.Normal))
        cursor.setCharFormat(fmt_txt)
        cursor.insertText(text)

        self.setTextCursor(cursor)
        self.ensureCursorVisible()


# ════════════════════════════════════════════════════════════════
#  HeaderBar — タイトル・ステータス・時計
# ════════════════════════════════════════════════════════════════

class HeaderBar(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self._status       = 'OFFLINE'
        self._connected    = False
        self._blink        = True
        self._arc          = 0.0
        self._model_str    = '—'

        t = QTimer(self)
        t.timeout.connect(self._tick)
        t.start(500)

        t2 = QTimer(self)
        t2.timeout.connect(self.update)
        t2.start(1000)

    def _tick(self):
        self._blink = not self._blink
        self._arc   = (self._arc + 3) % 360
        self.update()

    def set_status(self, label: str, connected: bool):
        self._status    = label
        self._connected = connected
        self.update()

    def set_model(self, model: str):
        self._model_str = model
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        # 背景
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0, QColor("#0b1a2e"))
        grad.setColorAt(1, QColor(_BG))
        p.fillRect(0, 0, w, h, QBrush(grad))

        # 下ボーダー（3層グロー）
        for i, alpha in enumerate([80, 40, 15]):
            c = QColor(_CYAN); c.setAlpha(alpha)
            p.setPen(QPen(c, 1))
            p.drawLine(0, h - 1 - i, w, h - 1 - i)

        # タイトル "UNIMOG"
        font_big = QFont("Consolas", 15, QFont.Weight.Bold)
        p.setFont(font_big)
        p.setPen(QColor(_CYAN))
        p.drawText(16, 36, "UNIMOG")

        font_sub = QFont("Consolas", 7)
        p.setFont(font_sub)
        p.setPen(QColor(_CYAN_DIM))
        p.drawText(105, 24, "VOICE  INTERFACE")
        p.drawText(105, 36, "GEMINI  LIVE  API  //  V4  STACK")

        # モデル名
        font_mdl = QFont("Consolas", 7)
        p.setFont(font_mdl)
        p.setPen(QColor(_GRAY))
        p.drawText(105, 47, self._model_str)

        # ── ステータスエリア（中央）────────────────────────────────
        cx = w // 2
        col = QColor(_GREEN if self._connected else _RED)

        # LEDグロー
        if self._blink and self._connected:
            for i in range(5):
                gc = QColor(col); gc.setAlpha(50 - i * 10)
                p.setBrush(QBrush(gc))
                p.setPen(Qt.PenStyle.NoPen)
                p.drawEllipse(QPointF(cx, h / 2), 6 + i * 4, 6 + i * 4)

        p.setBrush(QBrush(col))
        p.setPen(QPen(QColor(_WHITE), 1))
        p.drawEllipse(QPointF(cx, h / 2), 6, 6)

        font_st = QFont("Consolas", 9, QFont.Weight.Bold)
        p.setFont(font_st)
        p.setPen(col)
        p.drawText(cx + 14, int(h / 2) + 4, self._status)

        # ── 時計（右）────────────────────────────────────────────
        now      = datetime.now()
        time_str = now.strftime('%H:%M:%S')
        date_str = now.strftime('%Y-%m-%d')

        font_t = QFont("Consolas", 14, QFont.Weight.Bold)
        p.setFont(font_t)
        p.setPen(QColor(_CYAN))
        fm = QFontMetrics(font_t)
        p.drawText(w - fm.horizontalAdvance(time_str) - 16, 34, time_str)

        font_d = QFont("Consolas", 8)
        p.setFont(font_d)
        p.setPen(QColor(_GRAY))
        fm2 = QFontMetrics(font_d)
        p.drawText(w - fm2.horizontalAdvance(date_str) - 16, 46, date_str)

        p.end()


# ════════════════════════════════════════════════════════════════
#  SystemPanel — 左パネル（ビジュアライザー + メトリクス）
# ════════════════════════════════════════════════════════════════

class MetricRow(QWidget):
    """1行のメトリクス表示"""

    def __init__(self, key: str, value: str = '—', key_col=_GRAY, val_col=_WHITE, parent=None):
        super().__init__(parent)
        self._key     = key
        self._value   = value
        self._key_col = key_col
        self._val_col = val_col
        self.setMinimumHeight(18)

    def set_value(self, v: str):
        self._value = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        font_k = QFont("Consolas", 8)
        font_v = QFont("Consolas", 9, QFont.Weight.Bold)

        p.setFont(font_k)
        p.setPen(QColor(self._key_col))
        p.drawText(6, 14, self._key)

        p.setFont(font_v)
        p.setPen(QColor(self._val_col))
        fm = QFontMetrics(font_k)
        p.drawText(70, 14, self._value)
        p.end()


class SystemPanel(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(220)
        self.setMaximumWidth(270)
        self.setStyleSheet(f"background-color: {_BG2};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(4)

        # ── ビジュアライザー ──────────────────────────────────────
        self.visualizer = VoiceVisualizer()
        layout.addWidget(self.visualizer, 3)

        # 仕切り
        layout.addWidget(self._sep(_CYAN))

        # ── ステータスタイトル ────────────────────────────────────
        lbl = QLabel(" ◈ SYSTEM STATUS")
        lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        lbl.setStyleSheet(f"color: {_CYAN}; padding: 2px;")
        layout.addWidget(lbl)

        # ── メトリクス ────────────────────────────────────────────
        self.met_model  = MetricRow("MODEL",  "—", _GRAY, _CYAN)
        self.met_voice  = MetricRow("VOICE",  "—", _GRAY, _CYAN)
        self.met_tools  = MetricRow("TOOLS",  "—", _GRAY, _GREEN)
        self.met_memory = MetricRow("MEMORY", "—", _GRAY, _YELLOW)
        self.met_git    = MetricRow("GIT",    "—", _GRAY, _ORANGE)

        for m in [self.met_model, self.met_voice, self.met_tools, self.met_memory, self.met_git]:
            layout.addWidget(m)

        layout.addWidget(self._sep(_BORDER))

        # ── 接続ステータス ────────────────────────────────────────
        self.status_lbl = QLabel("● INITIALIZING")
        self.status_lbl.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self.status_lbl.setStyleSheet(f"color: {_GRAY}; padding: 4px;")
        self.status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_lbl)

        layout.addStretch()

        # フッター
        footer = QLabel("UNIMOG v2.0 // PyQt6")
        footer.setFont(QFont("Consolas", 7))
        footer.setStyleSheet(f"color: {_BORDER}; padding: 2px;")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(footer)

    def _sep(self, color: str) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {color};")
        return line

    def set_metric(self, key: str, value: str):
        m = {
            'model':  self.met_model,
            'voice':  self.met_voice,
            'tools':  self.met_tools,
            'memory': self.met_memory,
            'git':    self.met_git,
        }.get(key)
        if m:
            m.set_value(value)

    def set_status(self, label: str, connected: bool):
        col = _GREEN if connected else (_ORANGE if label == 'CONNECTING' else _RED)
        self.status_lbl.setText(f'● {label}')
        self.status_lbl.setStyleSheet(f"color: {col}; padding: 4px;")


# ════════════════════════════════════════════════════════════════
#  VoiceAgentThread — 音声エージェント実行スレッド
# ════════════════════════════════════════════════════════════════

class VoiceAgentThread(QThread):
    message   = pyqtSignal(str, str)   # (kind, text)
    status    = pyqtSignal(str, bool)  # (label, connected)
    metric    = pyqtSignal(str, str)   # (key, value)
    vis_state = pyqtSignal(str)        # visualizer state name

    def run(self):
        try:
            import voice_agent as _va
            import V4 as _v4
        except ImportError as e:
            self.message.emit('error', f'インポートエラー: {e}')
            return

        _self = self

        def _patched_print(*args, **kwargs):
            raw  = ' '.join(str(a) for a in args)
            text = strip_ansi(raw).strip()
            if not text:
                return

            kind = _classify(text)
            _self.message.emit(kind, text)

            # ステータス・ビジュアライザー連動
            if '接続完了' in text:
                _self.status.emit('ONLINE', True)
                _self.vis_state.emit('listening')
            elif '接続中' in text or '再接続' in text:
                _self.status.emit('CONNECTING', False)
                _self.vis_state.emit('processing')
            elif '[エラー]' in text or 'APIError' in text or '✗' in text:
                _self.vis_state.emit('error')
            elif '⚡' in text or '[ツール]' in text:
                _self.vis_state.emit('processing')
            elif '[結果]' in text or '[AutoGit]' in text:
                _self.vis_state.emit('listening')
            elif '[あなた]' in text:
                _self.vis_state.emit('listening')
            elif '[AI]' in text:
                _self.vis_state.emit('speaking')

            # ツール登録数
            if 'ツール登録' in text:
                m = re.search(r'(\d+)\s*件', text)
                if m: _self.metric.emit('tools', f'{m.group(1)} items')

            # AutoGit
            if '[AutoGit]' in text:
                short = re.sub(r'\[AutoGit\]', '', text).strip()[:20]
                _self.metric.emit('git', short)

            # 教訓数
            if ('教訓' in text or 'lessons' in text) and '件' in text:
                m = re.search(r'(\d+)\s*件', text)
                if m: _self.metric.emit('memory', f'{m.group(1)} lessons')

        _v4.safe_print     = _patched_print
        _va.safe_print     = _patched_print

        try:
            cfg = _va.load_config()
        except SystemExit:
            self.message.emit('error', '.env の読み込みに失敗しました')
            return

        # モデル・ボイス情報
        mdl = cfg['model']
        self.metric.emit('model', mdl[-28:] if len(mdl) > 28 else mdl)
        self.metric.emit('voice', cfg.get('voice_name', '—'))
        cwd = cfg.get('cwd', '')
        self.metric.emit('cwd',  ('...' + cwd[-20:]) if len(cwd) > 20 else cwd)

        self.status.emit('CONNECTING', False)
        self.vis_state.emit('processing')
        self.message.emit('connect', '音声エージェントを初期化しています...')

        try:
            asyncio.run(_va.run_voice_mode(cfg))
        except Exception as e:
            self.message.emit('error', f'実行エラー: {e}')
        finally:
            self.status.emit('OFFLINE', False)
            self.vis_state.emit('idle')


# ════════════════════════════════════════════════════════════════
#  MainWindow
# ════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("UNIMOG VOICE — HUD Interface")
        self.setMinimumSize(1050, 680)
        self.resize(1300, 820)

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {_BG};
                color: {_WHITE};
                font-family: Consolas;
            }}
            QSplitter::handle {{
                background-color: {_BORDER};
            }}
        """)

        self._build_ui()
        self._start_agent()

    # ── UI構築 ────────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ヘッダー
        self.header = HeaderBar()
        root.addWidget(self.header)

        # メインスプリッター
        split = QSplitter(Qt.Orientation.Horizontal)
        split.setHandleWidth(2)
        root.addWidget(split, 1)

        # ── 左パネル ─────────────────────────────────────────────
        self.sys_panel = SystemPanel()
        split.addWidget(self.sys_panel)

        # ── 右エリア ─────────────────────────────────────────────
        right = QWidget()
        right.setStyleSheet(f"background-color: {_BG};")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)
        rl.setSpacing(4)

        # 会話ログ
        rl.addWidget(self._panel_label("◈  CONVERSATION", _CYAN))
        self.conv_log = ConversationLog()
        rl.addWidget(self.conv_log, 3)

        # ツール/システムログ
        rl.addWidget(self._panel_label("⚙  TOOL EXECUTION  //  SYSTEM LOG", _PURPLE))
        self.tool_log = ConversationLog()
        self.tool_log.setFont(QFont("Consolas", 9))
        rl.addWidget(self.tool_log, 1)

        split.addWidget(right)
        split.setSizes([240, 1060])

        # ── ステータスバー ─────────────────────────────────────────
        sb = QWidget()
        sb.setFixedHeight(22)
        sb.setStyleSheet(f"background: {_BG2}; border-top: 1px solid {_BORDER};")
        sb_l = QHBoxLayout(sb)
        sb_l.setContentsMargins(8, 0, 8, 0)

        self.sb_text = QLabel("SYSTEM READY")
        self.sb_text.setFont(QFont("Consolas", 8))
        self.sb_text.setStyleSheet(f"color: {_GRAY};")
        sb_l.addWidget(self.sb_text)
        sb_l.addStretch()

        ver = QLabel("UNIMOG v2.0  //  GEMINI LIVE API  //  PyQt6 6.11")
        ver.setFont(QFont("Consolas", 7))
        ver.setStyleSheet(f"color: {_BORDER};")
        sb_l.addWidget(ver)

        root.addWidget(sb)

    def _panel_label(self, text: str, color: str) -> QLabel:
        lbl = QLabel(f"  {text}")
        lbl.setFont(QFont("Consolas", 8, QFont.Weight.Bold))
        lbl.setFixedHeight(22)
        lbl.setStyleSheet(
            f"color: {color}; background: {_PANEL}; "
            f"border-left: 2px solid {color}; padding-left: 6px;"
        )
        return lbl

    # ── エージェント起動 ──────────────────────────────────────────
    def _start_agent(self):
        self.agent = VoiceAgentThread()
        self.agent.message.connect(self._on_message)
        self.agent.status.connect(self._on_status)
        self.agent.metric.connect(self._on_metric)
        self.agent.vis_state.connect(self._on_vis)
        self.agent.start()

    # ── シグナルハンドラ ─────────────────────────────────────────
    def _on_message(self, kind: str, text: str):
        # 表示するテキストを整形
        clean = text
        for pfx in ('[あなた]', '[AI]'):
            clean = clean.replace(pfx, '').strip()

        if kind in ('user', 'ai'):
            self.conv_log.add_entry(kind, clean)
            who = "YOU" if kind == 'user' else " AI"
            self.sb_text.setText(f'[{who}] {clean[:80]}{"..." if len(clean)>80 else ""}')
        else:
            self.tool_log.add_entry(kind, clean)
            if kind not in ('system',):
                self.sb_text.setText(clean[:100])

    def _on_status(self, label: str, connected: bool):
        self.header.set_status(label, connected)
        self.sys_panel.set_status(label, connected)

    def _on_metric(self, key: str, value: str):
        if key == 'model':
            self.header.set_model(value)
        self.sys_panel.set_metric(key, value)

    def _on_vis(self, state: str):
        self.sys_panel.visualizer.set_state(state)

    def closeEvent(self, event):
        if hasattr(self, 'agent') and self.agent.isRunning():
            self.agent.terminate()
            self.agent.wait(2000)
        event.accept()


# ════════════════════════════════════════════════════════════════
#  Entry Point
# ════════════════════════════════════════════════════════════════

def main():
    # Windows High-DPI 対応
    try:
        from PyQt6.QtCore import Qt
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName("UNIMOG VOICE")

    # グローバルダークパレット
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(_BG))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(_WHITE))
    pal.setColor(QPalette.ColorRole.Base,            QColor(_BG2))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(_PANEL))
    pal.setColor(QPalette.ColorRole.Text,            QColor(_WHITE))
    pal.setColor(QPalette.ColorRole.Button,          QColor(_PANEL))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(_WHITE))
    pal.setColor(QPalette.ColorRole.Highlight,       QColor(_CYAN))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(_BG))
    app.setPalette(pal)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
