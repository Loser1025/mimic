"""
voicevox_gui.py
────────────────────────────────────────────────────────────────
VOICEVOX + Gemini Flash + Whisper
近未来 HUD インターフェース (PyQt6)

起動方法:
    python voicevox_gui.py
"""

import sys
import re
import time
import random
import math
import threading
from pathlib import Path
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QLabel, QFrame, QSizePolicy, QTextEdit,
)
from PyQt6.QtCore import (
    Qt, QTimer, QThread, pyqtSignal, QRectF, QPointF,
)
from PyQt6.QtGui import (
    QPainter, QPen, QBrush, QColor, QFont, QFontMetrics,
    QRadialGradient, QLinearGradient, QPalette, QTextCursor, QTextCharFormat,
)

# ── パス設定 ──────────────────────────────────────────────────────
_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE))

import voicevox_agent as _va
import V4 as _v4

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

# ── メッセージ種別判定 ─────────────────────────────────────────────
def _classify(text: str) -> str:
    t = text.strip()
    if '[あなた]'  in t: return 'user'
    if 'AI >'      in t: return 'ai'
    if any(x in t for x in ['[ツール]', 'ツールを実行', '[結果]', '⚡']): return 'tool'
    if any(x in t for x in ['[エラー]', '✗', 'APIError']): return 'error'
    if any(x in t for x in ['録音中', '🎙']): return 'system'
    return 'system'

# ════════════════════════════════════════════════════════════════
#  Visualizer
# ════════════════════════════════════════════════════════════════

class VoiceVisualizer(QWidget):
    _STATES = {
        'idle':       ('STANDBY',   _GRAY,   0.25),
        'listening':  ('LISTENING', _CYAN,   1.00),
        'processing': ('THINKING',  _PURPLE, 0.90),
        'speaking':   ('SPEAKING',  _GREEN,  1.00),
        'error':      ('ERROR',     _RED,    1.00),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(250, 250)
        self._state = 'idle'
        self._active = False
        self._bars = [0.1] * 64
        self._angle = 0
        self._pulse = 0
        
        t = QTimer(self)
        t.timeout.connect(self._animate)
        t.start(16)

    def set_state(self, state: str):
        if state in self._STATES:
            self._state = state
            self._active = (state != 'idle')
            self.update()

    def _animate(self):
        rot_speed = 1.5 if self._active else 0.4
        self._angle = (self._angle + rot_speed) % 360
        self._pulse = (self._pulse + 0.08) % (math.pi * 2)
        
        for i in range(len(self._bars)):
            target = random.uniform(0.1, 0.8) if self._active else random.uniform(0.05, 0.12)
            self._bars[i] += (target - self._bars[i]) * 0.15
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h / 2
        R = min(w, h) / 2 - 15
        
        label, hex_col, intensity = self._STATES.get(self._state, self._STATES['idle'])
        col = QColor(hex_col)
        
        # 背景の円形グロー
        grad = QRadialGradient(cx, cy, R)
        c_glow = QColor(col)
        c_glow.setAlpha(int(30 * intensity * (1.0 + 0.1 * math.sin(self._pulse))))
        grad.setColorAt(0, c_glow)
        grad.setColorAt(1, QColor(0,0,0,0))
        p.fillRect(0,0,w,h, QBrush(grad))

        # 外周アーク
        p.setPen(QPen(col, 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(QRectF(cx-R, cy-R, R*2, R*2), int(self._angle*16), 110*16)
        p.drawArc(QRectF(cx-R, cy-R, R*2, R*2), int((self._angle+180)*16), 110*16)
        
        # 周波数バー (円形)
        r_in = R * 0.45
        r_out = R * 0.85
        for i, b in enumerate(self._bars):
            ang = (i / 64) * 2 * math.pi - math.pi/2
            ri = r_in
            ro = r_in + (r_out - r_in) * b
            alpha = int(220 * b * intensity)
            pc = QColor(col); pc.setAlpha(alpha)
            p.setPen(QPen(pc, 2.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(
                QPointF(cx + ri * math.cos(ang), cy + ri * math.sin(ang)),
                QPointF(cx + ro * math.cos(ang), cy + ro * math.sin(ang))
            )

        # ステータス表示
        p.setPen(QColor(col))
        p.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        fm = QFontMetrics(p.font())
        p.drawText(int(cx - fm.horizontalAdvance(label)/2), int(cy + fm.height()/3), label)
        p.end()

# ════════════════════════════════════════════════════════════════
#  ConversationLog
# ════════════════════════════════════════════════════════════════

class ConversationLog(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {_BG2};
                color: {_WHITE};
                border: 1px solid {_BORDER};
                padding: 12px;
                line-height: 1.4;
            }}
        """)
        self.setFont(QFont("Consolas", 10))

    def add_entry(self, kind: str, text: str):
        colors = {
            'user': _CYAN,
            'ai': _GREEN,
            'tool': _PURPLE,
            'error': _RED,
            'system': _GRAY
        }
        col = colors.get(kind, _WHITE)
        
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        
        # タイムスタンプ
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_GRAY))
        fmt.setFontPointSize(8)
        cursor.insertText(f"[{datetime.now().strftime('%H:%M:%S')}] ", fmt)
        
        # プレフィックス
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(col))
        fmt.setFontWeight(QFont.Weight.Bold)
        fmt.setFontPointSize(9)
        prefix = kind.upper()
        cursor.insertText(f"{prefix:>7} | ", fmt)
        
        # 本文
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(_WHITE if kind in ('user', 'ai') else col))
        fmt.setFontWeight(QFont.Weight.Bold if kind in ('user', 'ai') else QFont.Weight.Normal)
        fmt.setFontPointSize(10)
        cursor.insertText(f"{text}\n", fmt)
        
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

# ════════════════════════════════════════════════════════════════
#  Execution Thread
# ════════════════════════════════════════════════════════════════

class VoicevoxAgentThread(QThread):
    message = pyqtSignal(str, str)
    status = pyqtSignal(str, bool)
    vis_state = pyqtSignal(str)

    def run(self):
        cfg = _va.load_vvx_config()
        
        def on_state(s):
            self.vis_state.emit(s)
            if s == 'listening': self.status.emit('LISTENING', True)
            elif s == 'processing': self.status.emit('THINKING', True)
            elif s == 'speaking': self.status.emit('SPEAKING', True)
            else: self.status.emit('ONLINE', True)

        agent = _va.VoicevoxAgent(cfg, on_state_change=on_state)
        
        # safe_print をフックして GUI ログへ送る
        def patched_print(*args, **kwargs):
            raw = ' '.join(str(a) for a in args)
            text = strip_ansi(raw).strip()
            if not text: return
            kind = _classify(text)
            self.message.emit(kind, text)
        
        _va.safe_print = patched_print
        _v4.safe_print = patched_print
        
        self.status.emit('ONLINE', True)
        self.message.emit('system', 'エージェントが起動しました。')
        
        try:
            agent.run_voice(cfg['whisper_model'])
        except Exception as e:
            self.message.emit('error', f'エラーが発生しました: {e}')
        finally:
            self.status.emit('OFFLINE', False)
            self.vis_state.emit('idle')

# ════════════════════════════════════════════════════════════════
#  Main Window
# ════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("UNILIVE VOICEVOX HUD")
        self.setMinimumSize(900, 600)
        self.resize(1100, 750)
        self.setStyleSheet(f"background-color: {_BG}; color: {_WHITE};")
        
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # ヘッダーエリア
        header = QHBoxLayout()
        title = QLabel("◈ UNILIVE HUD INTERFACE")
        title.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {_CYAN};")
        header.addWidget(title)
        header.addStretch()
        self.st_lbl = QLabel("OFFLINE")
        self.st_lbl.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        header.addWidget(self.st_lbl)
        layout.addLayout(header)

        # メイン分割エリア
        split = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(split, 1)
        
        # 左側: ビジュアルパネル
        left_panel = QFrame()
        left_panel.setStyleSheet(f"background-color: {_BG2}; border: 1px solid {_BORDER};")
        ll = QVBoxLayout(left_panel)
        self.vis = VoiceVisualizer()
        ll.addStretch()
        ll.addWidget(self.vis)
        ll.addStretch()
        
        split.addWidget(left_panel)
        
        # 右側: ログパネル
        self.log = ConversationLog()
        split.addWidget(self.log)
        
        split.setSizes([350, 750])
        
        # フッター
        footer = QLabel(f"WORK DIR: {Path.cwd()}")
        footer.setFont(QFont("Consolas", 7))
        footer.setStyleSheet(f"color: {_GRAY};")
        layout.addWidget(footer)

        # スレッド開始
        self.thread = VoicevoxAgentThread()
        self.thread.message.connect(self.log.add_entry)
        self.thread.vis_state.connect(self.vis.set_state)
        self.thread.status.connect(self._on_status)
        self.thread.start()

    def _on_status(self, label, connected):
        self.st_lbl.setText(label)
        self.st_lbl.setStyleSheet(f"color: {_GREEN if connected else _RED};")

    def closeEvent(self, event):
        if self.thread.isRunning():
            self.thread.terminate()
            self.thread.wait()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
