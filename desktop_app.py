import json
import queue
import re
import shutil
import sys
import threading
import uuid
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, request as flask_request

PROFILES_BASE_DIR = Path.home() / "Douyin_Profiles"
START_URL = "https://creator.douyin.com/"
MAX_ACCOUNTS = 50
APP_NAME = "\u6296\u97f3\u591a\u5f00\u77e9\u9635\u7cfb\u7edf"
APP_SUBTITLE = "by \u5c16\u53eb\uff08\u4ec5\u4f9b\u5b66\u4e60\u53c2\u8003\uff09"
API_PORT = 5001


def sanitize_account_name(name: str) -> str:
    if name is None:
        return ""
    name = str(name).strip()
    if not name:
        return ""
    name = re.sub(r"[\/\\:\*\?\"<>\|\x00-\x1f]+", "_", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name


# ═══════════════════════════════════════════════════════════════
#  Flask API（在后台线程中运行，供 OpenClaw 等 AI Agent 调用）
# ═══════════════════════════════════════════════════════════════
_flask_app = Flask(__name__)
_flask_app.config["JSON_AS_ASCII"] = False
_publish_queue: queue.Queue = queue.Queue()
_log_queue: queue.Queue = queue.Queue()
_api_enabled = False


@_flask_app.post("/api/publish")
def _api_publish():
    if not _api_enabled:
        return jsonify(ok=False, error="API is disabled"), 403
    data = flask_request.get_json(silent=True) or {}
    account = data.get("account", "")
    file_paths = data.get("file_paths", data.get("video_path", ""))
    caption = data.get("caption", "")
    post_type = data.get("post_type", "video")
    if not account or not file_paths:
        return jsonify(ok=False, error="account and file_paths are required"), 400
    _publish_queue.put((account, file_paths, caption, post_type))
    _log_queue.put(f"\u6536\u5230\u6307\u4ee4  \u8d26\u53f7={account}  \u7c7b\u578b={post_type}  \u6587\u4ef6={file_paths}")
    return jsonify(ok=True, status="queued", account=account, post_type=post_type), 202


@_flask_app.get("/api/health")
def _api_health():
    return jsonify(ok=True, app=APP_NAME, port=API_PORT)


# ═══════════════════════════════════════════════════════════════
#  ToggleSwitch（必须在模块级定义，Signal/Property 才能正确注册）
# ═══════════════════════════════════════════════════════════════
from PySide6.QtCore import (
    Qt, QUrl, QTimer, QSize, QMimeData, QPointF, QPoint,
    QPropertyAnimation, QEasingCurve, QRectF, Property, Signal, QDateTime, QLocale,
)
from PySide6.QtGui import (
    QFont, QDropEvent, QDragEnterEvent, QDragMoveEvent,
    QPainter, QColor, QBrush,
)
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QButtonGroup,
    QComboBox,
    QDateTimeEdit,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWebEngineCore import (
    QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings,
)
from PySide6.QtWebEngineWidgets import QWebEngineView


class ToggleSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        self._knob_x = 3.0

        self._anim = QPropertyAnimation(self, b"knob_x")
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.InOutCubic)

    def isChecked(self):
        return self._checked

    def setChecked(self, val):
        if val == self._checked:
            return
        self._checked = val
        end = 23.0 if val else 3.0
        self._anim.stop()
        self._anim.setStartValue(self._knob_x)
        self._anim.setEndValue(end)
        self._anim.start()
        self.toggled.emit(val)

    def _get_knob_x(self):
        return self._knob_x

    def _set_knob_x(self, v):
        self._knob_x = v
        self.update()

    knob_x = Property(float, _get_knob_x, _set_knob_x)

    def mousePressEvent(self, e):
        self.setChecked(not self._checked)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        track = QColor("#6366F1") if self._checked else QColor("#3F3F46")
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(track))
        p.drawRoundedRect(QRectF(0, 0, 44, 24), 12, 12)
        p.setBrush(QBrush(QColor("#FFFFFF")))
        p.drawEllipse(QRectF(self._knob_x, 3.0, 18, 18))
        p.end()


# ═══════════════════════════════════════════════════════════════
#  主程序
# ═══════════════════════════════════════════════════════════════
def main() -> int:

    # ── API 后台线程（daemon=True 保证退出时不阻塞） ────────
    def _run_flask_server():
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        _flask_app.run(host="127.0.0.1", port=API_PORT, use_reloader=False)

    # ── AutoPublishPage ──────────────────────────────────────
    class AutoPublishPage(QWebEnginePage):
        def __init__(self, profile, parent=None):
            super().__init__(profile, parent)
            self._pending_files = []

        def set_pending_files(self, paths):
            if isinstance(paths, str):
                self._pending_files = [p.strip() for p in paths.split(",") if p.strip()]
            elif isinstance(paths, list):
                self._pending_files = list(paths)
            else:
                self._pending_files = []

        def chooseFiles(self, mode, old_files, accepted_mime):
            if self._pending_files:
                result = list(self._pending_files)
                self._pending_files = []
                return result
            return super().chooseFiles(mode, old_files, accepted_mime)

    # ── App / 数据 ───────────────────────────────────────────
    PROFILES_BASE_DIR.mkdir(parents=True, exist_ok=True)

    qapp = QApplication(sys.argv)
    qapp.setApplicationName(APP_NAME)

    if sys.platform == "win32":
        _primary_font = "Microsoft YaHei"
    else:
        _primary_font = "PingFang SC"
    base_font = QFont(_primary_font, 12)
    base_font.setStyleStrategy(QFont.PreferAntialias)
    base_font.setHintingPreference(QFont.PreferFullHinting)
    qapp.setFont(base_font)

    profile_cache: dict = {}
    views: dict = {}
    page_indices: dict = {}
    dir_to_display: dict = {}
    # 内存排期队列（本次运行有效；与 README 描述一致）
    scheduled_tasks: list = []

    _api_thread_started = False

    # ── 主窗口 ──
    window = QWidget()
    window.setObjectName("mainWindow")
    window.setWindowTitle(f"{APP_NAME} — {APP_SUBTITLE}")
    window.resize(1440, 920)

    # ═══════════════════════════════════════════════════════════
    #  左侧边栏
    # ═══════════════════════════════════════════════════════════
    sidebar = QWidget()
    sidebar.setObjectName("sidebar")
    sidebar.setFixedWidth(220)
    sb_layout = QVBoxLayout(sidebar)
    sb_layout.setContentsMargins(20, 24, 20, 20)
    sb_layout.setSpacing(4)

    brand = QLabel(APP_NAME)
    brand.setObjectName("brand")
    brand.setAlignment(Qt.AlignLeft)
    sb_layout.addWidget(brand)

    subtitle = QLabel(APP_SUBTITLE)
    subtitle.setObjectName("subtitle")
    subtitle.setAlignment(Qt.AlignLeft)
    sb_layout.addWidget(subtitle)

    sb_layout.addSpacing(16)

    count_label = QLabel("0 / %d accounts" % MAX_ACCOUNTS)
    count_label.setObjectName("countLabel")
    count_label.setAlignment(Qt.AlignLeft)
    sb_layout.addWidget(count_label)

    sb_layout.addSpacing(8)

    account_list = QListWidget()
    account_list.setObjectName("accountList")
    account_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sb_layout.addWidget(account_list, 1)

    sb_layout.addSpacing(8)

    input_field = QLineEdit()
    input_field.setObjectName("accountInput")
    input_field.setPlaceholderText("\u8f93\u5165\u65b0\u8d26\u53f7\u540d\u79f0\u2026")
    sb_layout.addWidget(input_field)

    sb_layout.addSpacing(6)

    btn_row = QWidget()
    btn_row.setObjectName("btnRow")
    btn_row_layout = QHBoxLayout(btn_row)
    btn_row_layout.setContentsMargins(0, 0, 0, 0)
    btn_row_layout.setSpacing(8)

    add_btn = QPushButton("\u65b0\u5efa")
    add_btn.setObjectName("addBtn")
    add_btn.setToolTip("\u65b0\u5efa\u8d26\u53f7")
    rename_btn = QPushButton("\u91cd\u547d\u540d")
    rename_btn.setObjectName("renameBtn")
    rename_btn.setToolTip("\u91cd\u547d\u540d")
    del_btn = QPushButton("\u5220\u9664")
    del_btn.setObjectName("delBtn")
    del_btn.setToolTip("\u5220\u9664\u8d26\u53f7")

    btn_row_layout.addWidget(add_btn, 1)
    btn_row_layout.addWidget(rename_btn, 1)
    btn_row_layout.addWidget(del_btn, 1)
    sb_layout.addWidget(btn_row)

    # ── 侧边栏底部：API 开关 + 缓存清理 ──
    sb_layout.addSpacing(14)

    sep_line = QFrame()
    sep_line.setObjectName("sidebarSep")
    sep_line.setFrameShape(QFrame.HLine)
    sb_layout.addWidget(sep_line)

    sb_layout.addSpacing(10)

    # API 状态卡片
    api_card = QWidget()
    api_card.setObjectName("apiCard")
    api_card_layout = QVBoxLayout(api_card)
    api_card_layout.setContentsMargins(12, 10, 12, 10)
    api_card_layout.setSpacing(6)

    api_card_top = QHBoxLayout()
    api_card_top.setSpacing(8)

    api_dot = QLabel("\u25CF")
    api_dot.setObjectName("apiDot")
    api_dot.setFixedWidth(14)
    api_card_top.addWidget(api_dot)

    api_card_title = QLabel("API \u670d\u52a1")
    api_card_title.setObjectName("apiCardTitle")
    api_card_top.addWidget(api_card_title)
    api_card_top.addStretch()

    api_checkbox = ToggleSwitch()
    api_card_top.addWidget(api_checkbox)

    api_card_layout.addLayout(api_card_top)

    api_status_label = QLabel("\u672a\u542f\u52a8")
    api_status_label.setObjectName("apiStatusLabel")
    api_status_label.setWordWrap(True)
    api_card_layout.addWidget(api_status_label)

    sb_layout.addWidget(api_card)

    sb_layout.addSpacing(8)

    clear_cache_btn = QPushButton("\u6e05\u7406\u7f13\u5b58")
    clear_cache_btn.setObjectName("clearCacheBtn")
    clear_cache_btn.setToolTip("\u6e05\u7406\u6240\u6709\u8d26\u53f7\u7684 HTTP \u7f13\u5b58\uff08\u4e0d\u5f71\u54cd\u767b\u5f55\u72b6\u6001\uff09")
    sb_layout.addWidget(clear_cache_btn)

    sb_layout.addSpacing(8)

    btn_create_task = QPushButton("\u23f0 \u521b\u5efa\u81ea\u52a8\u4efb\u52a1")
    btn_create_task.setObjectName("scheduleCreateBtn")
    btn_create_task.setToolTip(
        "\u521b\u5efa\u7acb\u5373\u6216\u5b9a\u65f6\u53d1\u5e03\u4efb\u52a1\uff08\u4e0e API \u5171\u7528\u81ea\u52a8\u5316\u903b\u8f91\uff09"
    )
    btn_manage_tasks = QPushButton("\U0001f4cb \u6392\u671f\u7ba1\u7406")
    btn_manage_tasks.setObjectName("scheduleManageBtn")
    btn_manage_tasks.setToolTip("\u67e5\u770b\u3001\u53d6\u6d88\u6216\u7acb\u5373\u6267\u884c\u5f85\u53d1\u5e03\u4efb\u52a1")
    sb_layout.addWidget(btn_create_task)
    sb_layout.addWidget(btn_manage_tasks)

    sb_layout.addSpacing(6)
    powered_label = QLabel("Powered by QtWebEngine")
    powered_label.setObjectName("poweredLabel")
    powered_label.setAlignment(Qt.AlignCenter)
    sb_layout.addWidget(powered_label)

    # ═══════════════════════════════════════════════════════════
    #  右侧内容区
    # ═══════════════════════════════════════════════════════════
    right_panel = QWidget()
    right_panel.setObjectName("rightPanel")
    right_layout = QVBoxLayout(right_panel)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(0)

    top_bar = QWidget()
    top_bar.setObjectName("topBar")
    top_bar.setFixedHeight(56)
    top_bar_layout = QHBoxLayout(top_bar)
    top_bar_layout.setContentsMargins(16, 0, 16, 0)
    top_bar_layout.setSpacing(6)

    back_btn = QPushButton("\u2190")
    back_btn.setObjectName("navBtn")
    back_btn.setToolTip("\u540e\u9000")
    back_btn.setFixedSize(36, 32)
    top_bar_layout.addWidget(back_btn)

    forward_btn = QPushButton("\u2192")
    forward_btn.setObjectName("navBtn")
    forward_btn.setToolTip("\u524d\u8fdb")
    forward_btn.setFixedSize(36, 32)
    top_bar_layout.addWidget(forward_btn)

    top_bar_layout.addSpacing(8)

    title_label = QLabel("\u9009\u62e9\u4e00\u4e2a\u8d26\u53f7\u5f00\u59cb")
    title_label.setObjectName("titleLabel")
    top_bar_layout.addWidget(title_label)
    top_bar_layout.addStretch()

    refresh_btn = QPushButton("\u5237\u65b0")
    refresh_btn.setObjectName("refreshBtn")
    refresh_btn.setToolTip("\u5237\u65b0\u5f53\u524d\u8d26\u53f7\u9875\u9762")
    top_bar_layout.addWidget(refresh_btn)

    # accent line below top bar
    accent_line = QFrame()
    accent_line.setObjectName("accentLine")
    accent_line.setFixedHeight(2)

    # ── 顶部 Toast 通知条 ──
    toast_label = QLabel()
    toast_label.setObjectName("toastLabel")
    toast_label.setAlignment(Qt.AlignCenter)
    toast_label.setFixedHeight(0)
    toast_label.setVisible(False)

    _toast_timer = QTimer()
    _toast_timer.setSingleShot(True)

    def show_toast(text: str, color: str = "#10B981", duration: int = 3000):
        toast_label.setText(text)
        toast_label.setStyleSheet(
            f"background: {color}; color: #FFFFFF; font-size: 12px; font-weight: 600;"
            f"padding: 0 16px; letter-spacing: 0.3px; border: none;"
        )
        toast_label.setFixedHeight(36)
        toast_label.setVisible(True)
        _toast_timer.stop()
        try:
            _toast_timer.timeout.disconnect()
        except RuntimeError:
            pass
        _toast_timer.timeout.connect(lambda: (toast_label.setVisible(False), toast_label.setFixedHeight(0)))
        _toast_timer.start(duration)

    right_layout.addWidget(top_bar)
    right_layout.addWidget(accent_line)
    right_layout.addWidget(toast_label)

    stacked = QStackedWidget()
    stacked.setObjectName("pageStack")
    right_layout.addWidget(stacked, 1)

    empty_page = QLabel(f"{APP_NAME}\n\n\u5728\u5de6\u4fa7\u8f93\u5165\u540d\u79f0\u5e76\u70b9\u51fb\u300c\u65b0\u5efa\u300d\u521b\u5efa\u8d26\u53f7")
    empty_page.setObjectName("emptyPage")
    empty_page.setAlignment(Qt.AlignCenter)
    empty_idx = stacked.addWidget(empty_page)

    # ── API 日志面板 ──
    api_log_panel = QWidget()
    api_log_panel.setObjectName("apiLogPanel")
    api_log_panel.setVisible(False)
    api_log_layout = QVBoxLayout(api_log_panel)
    api_log_layout.setContentsMargins(0, 0, 0, 0)
    api_log_layout.setSpacing(0)

    api_log_header = QWidget()
    api_log_header.setObjectName("apiLogHeader")
    api_log_header.setFixedHeight(32)
    alh_layout = QHBoxLayout(api_log_header)
    alh_layout.setContentsMargins(16, 0, 16, 0)
    api_log_title = QLabel("API LOG")
    api_log_title.setObjectName("apiLogTitle")
    alh_layout.addWidget(api_log_title)
    alh_layout.addStretch()
    api_log_clear_btn = QPushButton("\u2715")
    api_log_clear_btn.setObjectName("apiLogClearBtn")
    api_log_clear_btn.setToolTip("\u6e05\u7a7a\u65e5\u5fd7")
    api_log_clear_btn.setFixedSize(24, 24)
    alh_layout.addWidget(api_log_clear_btn)
    api_log_layout.addWidget(api_log_header)

    api_log_text = QTextEdit()
    api_log_text.setObjectName("apiLogText")
    api_log_text.setReadOnly(True)
    api_log_text.setFixedHeight(170)
    api_log_layout.addWidget(api_log_text)

    right_layout.addWidget(api_log_panel)

    def api_log(msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        api_log_text.append(f'<span style="color:#818CF8">[{ts}]</span> {msg}')
        api_log_text.verticalScrollBar().setValue(api_log_text.verticalScrollBar().maximum())

    api_log_clear_btn.clicked.connect(lambda: api_log_text.clear())

    # ═══════════════════════════════════════════════════════════
    #  布局组合
    # ═══════════════════════════════════════════════════════════
    splitter = QSplitter()
    splitter.setOrientation(Qt.Horizontal)
    splitter.setChildrenCollapsible(False)
    splitter.setHandleWidth(1)
    splitter.addWidget(sidebar)
    splitter.addWidget(right_panel)
    splitter.setStretchFactor(0, 0)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([220, 1220])

    root = QHBoxLayout(window)
    root.setContentsMargins(0, 0, 0, 0)
    root.setSpacing(0)
    root.addWidget(splitter)

    _mono = '"Cascadia Mono", "Consolas", "SF Mono", "Menlo", monospace'

    # ═══════════════════════════════════════════════════════════
    #  样式表 — Hyper3D / Modern AI SaaS dark theme
    # ═══════════════════════════════════════════════════════════
    window.setStyleSheet(f"""

        /* ── 全局基底 ── */
        #mainWindow {{
            background: #09090B;
        }}

        /* ── 侧边栏 ── */
        #sidebar {{
            background: #121214;
            border-right: 1px solid rgba(255, 255, 255, 0.05);
        }}
        #brand {{
            color: #FAFAFA;
            font-size: 16px;
            font-weight: 800;
            letter-spacing: 1.2px;
            padding: 0;
            background: transparent;
        }}
        #subtitle {{
            color: #52525B;
            font-size: 10px;
            font-weight: 400;
            letter-spacing: 0.3px;
            padding: 2px 0 0 0;
            background: transparent;
        }}
        #countLabel {{
            color: #818CF8;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1px;
            text-transform: uppercase;
            padding: 0;
            background: transparent;
        }}

        /* ── 账号列表 ── */
        #accountList {{
            background: transparent;
            border: none;
            outline: none;
            font-size: 13px;
        }}
        #accountList::item {{
            color: #A1A1AA;
            padding: 8px 12px;
            border-radius: 8px;
            margin: 2px 0;
            border-left: 3px solid transparent;
        }}
        #accountList::item:selected {{
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border-left: 3px solid #818CF8;
        }}
        #accountList::item:hover:!selected {{
            background: rgba(255, 255, 255, 0.05);
            color: #E4E4E7;
        }}

        /* ── 输入框 ── */
        #accountInput {{
            background: #18181B;
            color: #E4E4E7;
            border: 1px solid #27272A;
            border-radius: 8px;
            padding: 9px 12px;
            font-size: 12px;
        }}
        #accountInput:focus {{
            border-color: #6366F1;
            background: rgba(99, 102, 241, 0.06);
        }}
        #accountInput::placeholder {{
            color: #52525B;
        }}

        /* ── 侧边栏按钮组 ── */
        #addBtn, #renameBtn, #delBtn {{
            background: #18181B;
            color: #A1A1AA;
            border: 1px solid #27272A;
            border-radius: 8px;
            padding: 7px 0;
            font-size: 11px;
            font-weight: 600;
        }}
        #addBtn:hover {{
            background: #4F46E5;
            color: #FFFFFF;
            border-color: #4F46E5;
        }}
        #addBtn:pressed {{
            background: #4338CA;
            border-color: #4338CA;
        }}
        #renameBtn:hover {{
            background: rgba(255, 255, 255, 0.08);
            color: #E4E4E7;
            border-color: #3F3F46;
        }}
        #delBtn:hover {{
            background: rgba(239, 68, 68, 0.12);
            color: #EF4444;
            border-color: rgba(239, 68, 68, 0.3);
        }}
        #delBtn:pressed {{
            background: rgba(239, 68, 68, 0.22);
        }}

        /* ── 侧边栏底部控件 ── */
        #sidebarSep {{
            color: rgba(255, 255, 255, 0.05);
            background: rgba(255, 255, 255, 0.05);
            max-height: 1px;
        }}

        /* API 状态卡片 */
        #apiCard {{
            background: #18181B;
            border: 1px solid #27272A;
            border-radius: 10px;
        }}
        #apiDot {{
            color: #52525B;
            font-size: 10px;
            background: transparent;
        }}
        #apiCardTitle {{
            color: #A1A1AA;
            font-size: 12px;
            font-weight: 600;
            background: transparent;
        }}
        /* ToggleSwitch is custom-painted, no QSS needed */
        #apiStatusLabel {{
            color: #52525B;
            font-size: 10px;
            font-weight: 500;
            padding: 0;
            background: transparent;
            letter-spacing: 0.3px;
        }}

        #clearCacheBtn {{
            background: #18181B;
            color: #A1A1AA;
            border: 1px solid #27272A;
            border-radius: 8px;
            padding: 7px 0;
            font-size: 11px;
            font-weight: 500;
        }}
        #clearCacheBtn:hover {{
            background: rgba(245, 158, 11, 0.12);
            color: #F59E0B;
            border-color: rgba(245, 158, 11, 0.3);
        }}

        #scheduleCreateBtn, #scheduleManageBtn {{
            background: #18181B;
            color: #A1A1AA;
            border: 1px solid #27272A;
            border-radius: 8px;
            padding: 8px 10px;
            font-size: 11px;
            font-weight: 600;
        }}
        #scheduleCreateBtn:hover {{
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border-color: rgba(99, 102, 241, 0.35);
        }}
        #scheduleManageBtn:hover {{
            background: rgba(34, 197, 94, 0.12);
            color: #22C55E;
            border-color: rgba(34, 197, 94, 0.3);
        }}

        #poweredLabel {{
            color: #27272A;
            font-size: 9px;
            padding: 6px 0 0 0;
            background: transparent;
            letter-spacing: 0.5px;
        }}

        /* Toast 通知 */
        #toastLabel {{
            border: none;
            border-radius: 0;
        }}

        /* ── 右侧面板 ── */
        #rightPanel {{
            background: #09090B;
        }}
        #topBar {{
            background: #121214;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
        }}
        #accentLine {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 rgba(99, 102, 241, 0),
                stop:0.15 #6366F1,
                stop:0.5 #A78BFA,
                stop:0.85 #6366F1,
                stop:1 rgba(99, 102, 241, 0));
            min-height: 2px;
            max-height: 2px;
            border: none;
        }}

        /* ── 导航按钮 ── */
        #navBtn {{
            background: #18181B;
            color: #A1A1AA;
            border: 1px solid #27272A;
            border-radius: 8px;
            font-size: 13px;
            font-weight: bold;
            padding: 0;
        }}
        #navBtn:hover {{
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border-color: rgba(99, 102, 241, 0.35);
        }}
        #navBtn:pressed {{
            background: rgba(99, 102, 241, 0.25);
        }}
        #titleLabel {{
            color: #FAFAFA;
            font-size: 14px;
            font-weight: 600;
            background: transparent;
            letter-spacing: 0.3px;
        }}
        #refreshBtn {{
            background: #18181B;
            color: #A1A1AA;
            border: 1px solid #27272A;
            border-radius: 8px;
            padding: 6px 16px;
            font-size: 11px;
            font-weight: 600;
        }}
        #refreshBtn:hover {{
            background: rgba(99, 102, 241, 0.15);
            color: #818CF8;
            border-color: rgba(99, 102, 241, 0.35);
        }}

        /* ── 页面栈 & 空态 ── */
        #pageStack {{
            background: #09090B;
        }}
        #emptyPage {{
            color: #3F3F46;
            font-size: 17px;
            font-weight: 500;
            background: transparent;
            line-height: 170%;
        }}

        /* ── API 日志面板 ── */
        #apiLogPanel {{
            background: #0C0C0E;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }}
        #apiLogHeader {{
            background: rgba(99, 102, 241, 0.06);
            border-bottom: 1px solid rgba(255, 255, 255, 0.04);
        }}
        #apiLogTitle {{
            color: #818CF8;
            font-size: 10px;
            font-weight: 700;
            letter-spacing: 1.8px;
            background: transparent;
        }}
        #apiLogClearBtn {{
            background: transparent;
            color: #52525B;
            border: none;
            font-size: 14px;
            font-weight: bold;
            border-radius: 6px;
        }}
        #apiLogClearBtn:hover {{
            color: #EF4444;
            background: rgba(239, 68, 68, 0.1);
        }}
        #apiLogText {{
            background: #09090B;
            color: #D4D4D8;
            border: none;
            font-family: {_mono};
            font-size: 11px;
            padding: 10px 14px;
            selection-background-color: rgba(99, 102, 241, 0.25);
        }}

        /* ── 分割器 ── */
        QSplitter::handle {{
            background: rgba(255, 255, 255, 0.03);
        }}

        /* ── 滚动条 ── */
        QScrollBar:vertical {{
            background: transparent;
            width: 6px;
            margin: 0;
        }}
        QScrollBar::handle:vertical {{
            background: rgba(255, 255, 255, 0.07);
            border-radius: 3px;
            min-height: 28px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: rgba(99, 102, 241, 0.4);
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 6px;
            margin: 0;
        }}
        QScrollBar::handle:horizontal {{
            background: rgba(255, 255, 255, 0.07);
            border-radius: 3px;
            min-width: 28px;
        }}
        QScrollBar::handle:horizontal:hover {{
            background: rgba(99, 102, 241, 0.4);
        }}
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
            width: 0;
        }}

        /* ── 对话框全局美化 ── */
        QMessageBox {{
            background: #18181B;
        }}
        QMessageBox QLabel {{
            color: #E4E4E7;
            font-size: 13px;
        }}
        QMessageBox QPushButton {{
            background: #27272A;
            color: #E4E4E7;
            border: 1px solid #3F3F46;
            border-radius: 6px;
            padding: 6px 20px;
            font-size: 12px;
            font-weight: 500;
        }}
        QMessageBox QPushButton:hover {{
            background: #6366F1;
            color: #FFFFFF;
            border-color: #6366F1;
        }}

        QInputDialog {{
            background: #18181B;
        }}
        QInputDialog QLabel {{
            color: #E4E4E7;
        }}
        QInputDialog QLineEdit {{
            background: #09090B;
            color: #FAFAFA;
            border: 1px solid #27272A;
            border-radius: 6px;
            padding: 6px 10px;
        }}
        QInputDialog QLineEdit:focus {{
            border-color: #6366F1;
        }}
        QInputDialog QPushButton {{
            background: #27272A;
            color: #E4E4E7;
            border: 1px solid #3F3F46;
            border-radius: 6px;
            padding: 6px 18px;
        }}
        QInputDialog QPushButton:hover {{
            background: #6366F1;
            color: #FFFFFF;
            border-color: #6366F1;
        }}
    """)

    # ═══════════════════════════════════════════════════════════
    #  Profile \u9694\u79bb
    # ═══════════════════════════════════════════════════════════
    # Anti-detection JS — 在页面 DOM 创建前注入，覆盖常见指纹检测点
    _STEALTH_JS = r"""
    (function(){
        // 1. navigator.webdriver → undefined (最重要的检测点)
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

        // 2. 伪装 chrome runtime 对象（缺失即被判定非 Chrome）
        if (!window.chrome) { window.chrome = {}; }
        if (!window.chrome.runtime) {
            window.chrome.runtime = {
                connect: function(){},
                sendMessage: function(){}
            };
        }

        // 3. 伪装 plugins 数组（空数组 = headless）
        Object.defineProperty(navigator, 'plugins', {
            get: () => [
                {name:'Chrome PDF Plugin', filename:'internal-pdf-viewer',
                 description:'Portable Document Format',length:1},
                {name:'Chrome PDF Viewer', filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai',
                 description:'',length:1},
                {name:'Native Client', filename:'internal-nacl-plugin',
                 description:'',length:2}
            ]
        });

        // 4. 伪装 languages（缺省会暴露）
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en-US', 'en']
        });

        // 5. 伪装 permissions query（Notification 检测点）
        const origQuery = window.Permissions && Permissions.prototype.query;
        if (origQuery) {
            Permissions.prototype.query = function(params) {
                if (params.name === 'notifications') {
                    return Promise.resolve({state: Notification.permission});
                }
                return origQuery.call(this, params);
            };
        }

        // 6. WebGL vendor/renderer 正常化
        const getParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Google Inc. (Apple)';
            if (p === 37446) return 'ANGLE (Apple, ANGLE Metal Renderer: Apple M-series, Unspecified Version)';
            return getParam.call(this, p);
        };

        // 7. 屏蔽 Headless 检测 (connection.rtt)
        if (navigator.connection) {
            Object.defineProperty(navigator.connection, 'rtt', {get: () => 100});
        }
    })();
    """

    def get_profile(dir_name: str) -> QWebEngineProfile:
        if dir_name in profile_cache:
            return profile_cache[dir_name]

        root_dir = PROFILES_BASE_DIR / dir_name
        persistent = root_dir / "webengine"
        cache = root_dir / "webengine_cache"
        persistent.mkdir(parents=True, exist_ok=True)
        cache.mkdir(parents=True, exist_ok=True)

        profile = QWebEngineProfile(dir_name, qapp)
        profile.setPersistentStoragePath(str(persistent))
        profile.setCachePath(str(cache))
        profile.setPersistentCookiesPolicy(QWebEngineProfile.ForcePersistentCookies)

        # UA 清洗：移除 QtWebEngine 特征、HeadlessChrome 特征
        ua = profile.httpUserAgent()
        ua = re.sub(r"\s*QtWebEngine/[\d.]+", "", ua)
        ua = re.sub(r"\s*HeadlessChrome/", " Chrome/", ua)
        ua = re.sub(r"\s{2,}", " ", ua).strip()
        profile.setHttpUserAgent(ua)

        # 每个 profile 独立的 settings 硬化
        s = profile.settings()
        s.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        s.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        s.setAttribute(QWebEngineSettings.JavascriptCanOpenWindows, False)
        s.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, False)
        s.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        s.setAttribute(QWebEngineSettings.ScrollAnimatorEnabled, True)

        # 注入 stealth 脚本（DocumentCreation 阶段，早于页面 JS 执行）
        stealth = QWebEngineScript()
        stealth.setName(f"stealth_{dir_name}")
        stealth.setSourceCode(_STEALTH_JS)
        stealth.setInjectionPoint(QWebEngineScript.DocumentCreation)
        stealth.setWorldId(QWebEngineScript.MainWorld)
        stealth.setRunsOnSubFrames(True)
        profile.scripts().insert(stealth)

        profile_cache[dir_name] = profile
        return profile

    # ═══════════════════════════════════════════════════════════
    #  \u9875\u9762\u7ba1\u7406
    # ═══════════════════════════════════════════════════════════
    def update_count():
        n = account_list.count()
        count_label.setText(f"{n} / {MAX_ACCOUNTS} accounts")

    def create_page_slot(dir_name: str) -> int:
        container = QWidget()
        container.setProperty("_dn", dir_name)
        cl = QVBoxLayout(container)
        cl.setContentsMargins(0, 0, 0, 0)
        ph = QLabel("\u23f3 \u6b63\u5728\u51c6\u5907\u52a0\u8f7d\u2026")
        ph.setAlignment(Qt.AlignCenter)
        ph.setStyleSheet("color:#52525B; font-size:13px; background:transparent;")
        cl.addWidget(ph, 1)
        idx = stacked.addWidget(container)
        page_indices[dir_name] = idx
        views[dir_name] = None
        return idx

    def ensure_loaded(dir_name: str) -> None:
        if views.get(dir_name) is not None:
            return
        idx = page_indices.get(dir_name)
        if idx is None:
            return

        container = stacked.widget(idx)
        layout = container.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        profile = get_profile(dir_name)
        view = QWebEngineView()
        page = AutoPublishPage(profile, view)
        view.setPage(page)
        layout.addWidget(view, 1)
        views[dir_name] = view

        QTimer.singleShot(80, lambda: view.load(QUrl(START_URL)))

    def simulate_file_drop(target_view, paths_str):
        """Qt 级别拖放模拟，绕过 Chromium 的 user-gesture 限制。"""
        if isinstance(paths_str, str):
            paths = [p.strip() for p in paths_str.split(",") if p.strip()]
        else:
            paths = list(paths_str)
        if not paths:
            api_log("\u26a0\ufe0f \u65e0\u6587\u4ef6\u8def\u5f84\uff0c\u8df3\u8fc7\u62d6\u653e")
            return

        target = target_view.focusProxy()
        if target is None:
            target = target_view

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(p) for p in paths])

        center = QPoint(target.width() // 2, target.height() // 2)

        enter_evt = QDragEnterEvent(center, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        enter_evt.acceptProposedAction()
        qapp.sendEvent(target, enter_evt)

        move_evt = QDragMoveEvent(center, Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        move_evt.acceptProposedAction()
        qapp.sendEvent(target, move_evt)

        drop_evt = QDropEvent(QPointF(center), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        drop_evt.acceptProposedAction()
        qapp.sendEvent(target, drop_evt)

        api_log(f"\U0001f4e4 \u62d6\u653e\u6a21\u62df\u5b8c\u6210: {paths}")

    # ═══════════════════════════════════════════════════════════
    #  \u8d26\u53f7\u7ba1\u7406
    # ═══════════════════════════════════════════════════════════
    def dir_name_for_row(row: int):
        item = account_list.item(row)
        if not item:
            return None
        return item.data(Qt.UserRole)

    def add_account_to_list(dir_name: str, display_name: str, select: bool = False):
        dir_to_display[dir_name] = display_name
        item = QListWidgetItem(display_name)
        item.setData(Qt.UserRole, dir_name)
        account_list.addItem(item)
        create_page_slot(dir_name)
        update_count()
        if select:
            account_list.setCurrentItem(item)

    def switch_to(dir_name: str):
        idx = page_indices.get(dir_name)
        if idx is None:
            return
        stacked.setCurrentIndex(idx)
        display = dir_to_display.get(dir_name, dir_name)
        title_label.setText(display)
        window.setWindowTitle(f"{APP_NAME} \u2014 {display}")
        ensure_loaded(dir_name)

    # ═══════════════════════════════════════════════════════════
    #  \u4e8b\u4ef6\u56de\u8c03
    # ═══════════════════════════════════════════════════════════
    def on_selection():
        row = account_list.currentRow()
        dn = dir_name_for_row(row)
        if dn:
            switch_to(dn)

    def on_add():
        raw = input_field.text().strip()
        name = sanitize_account_name(raw)
        if not name:
            QMessageBox.warning(window, "\u63d0\u793a", "\u8bf7\u8f93\u5165\u6709\u6548\u7684\u8d26\u53f7\u540d\u79f0")
            return
        if name in page_indices:
            for i in range(account_list.count()):
                if dir_name_for_row(i) == name:
                    account_list.setCurrentRow(i)
                    break
            return
        if len(page_indices) >= MAX_ACCOUNTS:
            QMessageBox.warning(window, "\u63d0\u793a", f"\u6700\u591a\u652f\u6301 {MAX_ACCOUNTS} \u4e2a\u8d26\u53f7")
            return
        (PROFILES_BASE_DIR / name).mkdir(parents=True, exist_ok=True)
        input_field.clear()
        add_account_to_list(name, name, select=True)

    def on_del():
        row = account_list.currentRow()
        dn = dir_name_for_row(row)
        if dn is None:
            return
        display = dir_to_display.get(dn, dn)
        reply = QMessageBox.question(
            window, "\u786e\u8ba4\u5220\u9664",
            f"\u5220\u9664\u300c{display}\u300d\u53ca\u5176\u5168\u90e8\u6570\u636e\uff1f\n\u6b64\u64cd\u4f5c\u4e0d\u53ef\u64a4\u9500\u3002",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        # 1) 停止 WebView 和 Page
        v = views.pop(dn, None)
        if v:
            v.stop()
            v.setPage(None)
            v.deleteLater()

        # 2) 清理 Profile 缓存并释放对象
        prof = profile_cache.pop(dn, None)
        if prof:
            prof.clearHttpCache()

        # 3) 移除 stacked widget 页面
        idx = page_indices.pop(dn, None)
        if idx is not None:
            w = stacked.widget(idx)
            if w:
                stacked.removeWidget(w)
                w.deleteLater()

        dir_to_display.pop(dn, None)
        account_list.takeItem(row)
        update_count()

        # 4) 强制处理待销毁对象，释放文件锁
        qapp.processEvents()

        # 5) 删除本地目录（账号数据 + webengine 持久化 + 缓存，全部清除）
        target = PROFILES_BASE_DIR / dn
        if target.exists():
            shutil.rmtree(target, ignore_errors=True)

        page_indices.clear()
        vb = dict(views)
        views.clear()
        for i in range(account_list.count()):
            d = dir_name_for_row(i)
            if d is None:
                continue
            for si in range(stacked.count()):
                w = stacked.widget(si)
                if w and w.property("_dn") == d:
                    page_indices[d] = si
                    views[d] = vb.get(d)
                    break
            else:
                create_page_slot(d)

        if account_list.count() > 0:
            account_list.setCurrentRow(min(row, account_list.count() - 1))
        else:
            title_label.setText("\u9009\u62e9\u4e00\u4e2a\u8d26\u53f7\u5f00\u59cb")
            window.setWindowTitle(f"{APP_NAME} \u2014 {APP_SUBTITLE}")
            stacked.setCurrentIndex(empty_idx)

        scheduled_tasks[:] = [t for t in scheduled_tasks if t.get("account") != dn]

    def on_rename():
        row = account_list.currentRow()
        dn = dir_name_for_row(row)
        if dn is None:
            return
        old = dir_to_display.get(dn, dn)
        new_name, ok = QInputDialog.getText(window, "\u91cd\u547d\u540d", "\u65b0\u540d\u79f0\uff1a", text=old)
        if not ok or not new_name.strip():
            return
        new_name = new_name.strip()
        dir_to_display[dn] = new_name
        account_list.item(row).setText(new_name)
        if account_list.currentRow() == row:
            title_label.setText(new_name)
            window.setWindowTitle(f"{APP_NAME} \u2014 {new_name}")

    def on_back():
        dn = dir_name_for_row(account_list.currentRow())
        if dn:
            v = views.get(dn)
            if v and v.history().canGoBack():
                v.back()

    def on_forward():
        dn = dir_name_for_row(account_list.currentRow())
        if dn:
            v = views.get(dn)
            if v and v.history().canGoForward():
                v.forward()

    def on_refresh():
        dn = dir_name_for_row(account_list.currentRow())
        if dn:
            v = views.get(dn)
            if v:
                v.reload()

    # ── API 服务开关 ──
    def toggle_api_service(checked: bool):
        nonlocal _api_thread_started
        global _api_enabled
        _api_enabled = checked
        if checked:
            if not _api_thread_started:
                t = threading.Thread(target=_run_flask_server, daemon=True)
                t.start()
                _api_thread_started = True
            api_status_label.setText("http://127.0.0.1:%d/api/publish" % API_PORT)
            api_status_label.setStyleSheet(
                "color: #10B981; font-size: 10px; font-weight: 500;"
                "padding: 0; background: transparent; letter-spacing: 0.3px;"
            )
            api_dot.setText("\u25CF")
            api_dot.setStyleSheet("color: #10B981; font-size: 10px; background: transparent;")
            api_card.setStyleSheet(
                "#apiCard { background: rgba(16, 185, 129, 0.06);"
                "border: 1px solid rgba(16, 185, 129, 0.2); border-radius: 10px; }"
            )
            api_log_panel.setVisible(True)
            api_log("\U0001f680 API \u670d\u52a1\u5df2\u542f\u52a8\uff0c\u7aef\u53e3 %d" % API_PORT)
            queue_poll_timer.start(300)
            show_toast("\u2713  API \u670d\u52a1\u5df2\u542f\u52a8\uff0c\u76d1\u542c\u7aef\u53e3 %d" % API_PORT, "#10B981", 3500)
        else:
            api_status_label.setText("\u672a\u542f\u52a8")
            api_status_label.setStyleSheet(
                "color: #52525B; font-size: 10px; font-weight: 500;"
                "padding: 0; background: transparent; letter-spacing: 0.3px;"
            )
            api_dot.setText("\u25CF")
            api_dot.setStyleSheet("color: #52525B; font-size: 10px; background: transparent;")
            api_card.setStyleSheet(
                "#apiCard { background: #18181B;"
                "border: 1px solid #27272A; border-radius: 10px; }"
            )
            api_log("\U0001f6d1 API \u5df2\u7981\u7528\uff0c\u65b0\u8bf7\u6c42\u5c06\u8fd4\u56de 403")
            api_log_panel.setVisible(False)
            queue_poll_timer.stop()
            show_toast("\u2715  API \u670d\u52a1\u5df2\u5173\u95ed", "#52525B", 2500)

    # ── OpenClaw 发布指令处理（支持视频 / 图文双模式） ──
    def handle_openclaw_publish(account_name: str, file_paths: str, caption: str, post_type: str):
        name = sanitize_account_name(account_name)
        api_log(f"\U0001f4e5 \u5904\u7406\u6307\u4ee4  \u8d26\u53f7=<b>{account_name}</b> \u2192 dir=<b>{name}</b>  \u7c7b\u578b={post_type}")

        if name not in page_indices:
            api_log(f'\u274c \u8d26\u53f7 "{name}" \u4e0d\u5b58\u5728\u3002\u5f53\u524d: {list(page_indices.keys())}')
            return

        switch_to(name)
        view = views.get(name)
        if view is None:
            api_log(f"\u274c \u8d26\u53f7 {name} \u7684 WebView \u672a\u52a0\u8f7d")
            return

        page = view.page()
        if isinstance(page, AutoPublishPage):
            page.set_pending_files(file_paths)
            api_log(f"\U0001f4ce \u6587\u4ef6\u5df2\u9884\u8bbe: {file_paths}")

        safe_post_type = "image" if post_type == "image" else "video"
        caption_js = json.dumps(caption, ensure_ascii=False)

        js_navigate = """
(function() {
    var postType = '""" + safe_post_type + """';
    var safe_caption_json = """ + caption_js + """;

    // ── Step 1: 点击左侧【高清发布】 ──
    var t1 = setInterval(function() {
        var btn = document.getElementById('douyin-creator-master-side-upload');
        if (btn) { btn.click(); clearInterval(t1); stepTwo(); }
    }, 1000);

    // ── Step 2: 切换图文/视频 Tab ──
    function stepTwo() {
        var t2 = setInterval(function() {
            var tabs = document.querySelectorAll('div[class^="tab-item"]');
            var targetText = postType === 'image' ? '发布图文' : '发布视频';
            for (var i = 0; i < tabs.length; i++) {
                if (tabs[i].innerText.trim() === targetText) {
                    tabs[i].click(); clearInterval(t2);
                    console.log('[DouyinBot] Tab切换完成: ' + targetText);
                    stepThree();
                    return;
                }
            }
        }, 1000);
    }

    // ── Step 3: 点击【上传】按钮触发文件选择（配合 Python 拖放双保险） ──
    function stepThree() {
        var t3 = setInterval(function() {
            var targetText = postType === 'image' ? '上传图文' : '上传视频';
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                if (btns[i].innerText.includes(targetText)) {
                    btns[i].click();
                    clearInterval(t3);
                    console.log('[DouyinBot] 上传按钮已点击，等待编辑器...');
                    stepFour_waitForEditor();
                    return;
                }
            }
        }, 1000);
    }

    // ── Step 4: 动态轮询等待富文本编辑器出现，然后注入文案 ──
    function stepFour_waitForEditor() {
        console.log('[DouyinBot] 等待上传完成，轮询输入框...');
        var t4 = setInterval(function() {
            var editor = document.querySelector('.zone-container')
                      || document.querySelector('[contenteditable="true"]')
                      || document.querySelector('[data-slate-editor="true"]');

            if (editor && editor.offsetHeight > 0) {
                clearInterval(t4);
                console.log('[DouyinBot] 输入框已就绪，注入文案');

                editor.focus();
                var dataTransfer = new DataTransfer();
                dataTransfer.setData('text/plain', safe_caption_json);
                var pasteEvent = new ClipboardEvent('paste', {
                    clipboardData: dataTransfer, bubbles: true, cancelable: true
                });
                editor.dispatchEvent(pasteEvent);
                editor.dispatchEvent(new Event('input', { bubbles: true }));
                console.log('[DouyinBot] 文案已粘贴: ' + safe_caption_json);

                setTimeout(stepFive, 3000);
            }
        }, 2000);
    }

    // ── Step 5: 勾选【不允许】保存 ──
    function stepFive() {
        console.log('[DouyinBot] Step5: 查找不允许保存选项');
        var labels = Array.from(document.querySelectorAll('label'));
        var noSaveLabel = labels.find(function(l) { return l.innerText.indexOf('不允许') !== -1; });
        if (noSaveLabel) {
            var checkbox = noSaveLabel.querySelector('input[type="checkbox"]');
            if (checkbox && !checkbox.checked) {
                noSaveLabel.click();
                console.log('[DouyinBot] 已勾选"不允许"');
            } else {
                console.log('[DouyinBot] "不允许"已处于选中状态');
            }
        }
        setTimeout(stepSix, 2000);
    }

    // ── Step 6: 精准点击【发布】按钮（测试期间注释 click） ──
    function stepSix() {
        console.log('[DouyinBot] Step6: 查找发布按钮');
        var btns = Array.from(document.querySelectorAll('button'));
        var publishBtn = btns.find(function(b) { return b.innerText.trim() === '发布'; });
        if (publishBtn) {
            console.log('[DouyinBot] 找到发布按钮，模拟点击');
            // publishBtn.click();  // 测试流程无误后解开此行
        } else {
            console.log('[DouyinBot] 未找到发布按钮');
        }
    }
})();
"""
        api_log("JS 自动化脚本已注入 (Step 1→6)")
        QTimer.singleShot(500, lambda: page.runJavaScript(js_navigate))

        captured_view = view
        captured_paths = file_paths
        def do_file_drop():
            api_log("执行拖放上传（双保险）…")
            simulate_file_drop(captured_view, captured_paths)

        QTimer.singleShot(8000, do_file_drop)

    # ── 定时发布（内存队列 + 1s 调度，与 README 一致） ──
    def qdt_to_datetime(qdt: QDateTime) -> datetime:
        if qdt is None:
            return datetime.now()
        try:
            if hasattr(qdt, "toPython"):
                py = qdt.toPython()
                if isinstance(py, datetime):
                    return py
        except Exception:
            pass
        return datetime.fromtimestamp(qdt.toSecsSinceEpoch())

    def tick_scheduled():
        """每秒最多执行一条到期任务，避免同账号并发自动化。"""
        now = datetime.now()
        due = [t for t in scheduled_tasks if t.get("status") == "pending" and t.get("run_at") and now >= t["run_at"]]
        if not due:
            return
        due.sort(key=lambda x: x["run_at"])
        task = due[0]
        scheduled_tasks.remove(task)
        acc = task["account"]
        label = dir_to_display.get(acc, acc)
        show_toast(f"\u5b9a\u65f6\u4efb\u52a1\u5f00\u59cb: {label}", "#6366F1", 4000)
        api_log(f"\u23f0 \u5b9a\u65f6\u89e6\u53d1  \u8d26\u53f7={acc}")
        handle_openclaw_publish(acc, task["file_paths"], task["caption"], task["post_type"])

    def on_create_scheduled_task():
        if account_list.count() == 0:
            QMessageBox.warning(window, "\u63d0\u793a", "\u8bf7\u5148\u5728\u5de6\u4fa7\u521b\u5efa\u8d26\u53f7")
            return

        dlg = QDialog(window)
        dlg.setWindowTitle("\u521b\u5efa\u81ea\u52a8\u4efb\u52a1")
        dlg.resize(500, 460)
        dlg.setStyleSheet(
            """
            QDialog { background: #18181B; }
            QLabel { color: #E4E4E7; font-size: 12px; }
            QTextEdit { background: #09090B; color: #FAFAFA; border: 1px solid #27272A; border-radius: 6px; }
            QComboBox, QDateTimeEdit { background: #09090B; color: #FAFAFA; border: 1px solid #27272A;
                border-radius: 6px; padding: 6px; min-height: 26px; }
            QRadioButton { color: #A1A1AA; }
            QPushButton { background: #27272A; color: #E4E4E7; border: 1px solid #3F3F46; border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: #6366F1; color: #FFFFFF; border-color: #6366F1; }
        """
        )

        root = QVBoxLayout(dlg)
        form = QFormLayout()

        combo = QComboBox()
        for i in range(account_list.count()):
            item = account_list.item(i)
            combo.addItem(item.text(), item.data(Qt.UserRole))

        files_row = QHBoxLayout()
        pick_btn = QPushButton("\u9009\u62e9\u6587\u4ef6\u2026")
        path_display = QLabel("\uff08\u672a\u9009\u62e9\uff09")
        path_display.setWordWrap(True)
        path_display.setStyleSheet("color:#71717A;")
        chosen_paths: list = []

        def _pick():
            paths, _ = QFileDialog.getOpenFileNames(
                window,
                "\u9009\u62e9\u8981\u53d1\u5e03\u7684\u6587\u4ef6",
                str(Path.home()),
            )
            if paths:
                chosen_paths.clear()
                chosen_paths.extend(paths)
                short = ", ".join(Path(p).name for p in paths[:3])
                if len(paths) > 3:
                    short += f" \u7b49 {len(paths)} \u4e2a\u6587\u4ef6"
                path_display.setText(short)
                path_display.setStyleSheet("color:#E4E4E7;")

        pick_btn.clicked.connect(_pick)
        files_row.addWidget(pick_btn, 0)
        files_row.addWidget(path_display, 1)
        form.addRow("\u8d26\u53f7", combo)
        form.addRow("\u6587\u4ef6", files_row)

        cap = QTextEdit()
        cap.setPlaceholderText("\u6587\u6848\uff08\u53ef\u9009\uff09")
        cap.setMaximumHeight(80)
        form.addRow("\u6587\u6848", cap)

        pt_layout = QHBoxLayout()
        rb_vid = QRadioButton("\u89c6\u9891")
        rb_img = QRadioButton("\u56fe\u6587")
        rb_vid.setChecked(True)
        pt_layout.addWidget(rb_vid)
        pt_layout.addWidget(rb_img)
        form.addRow("\u7c7b\u578b", pt_layout)

        mode_row = QHBoxLayout()
        rb_now = QRadioButton("\u7acb\u5373\u53d1\u5e03")
        rb_later = QRadioButton("\u5b9a\u65f6\u53d1\u5e03")
        rb_now.setChecked(True)
        mode_row.addWidget(rb_now)
        mode_row.addWidget(rb_later)
        form.addRow("\u6a21\u5f0f", mode_row)

        dt_edit = QDateTimeEdit(QDateTime.currentDateTime().addSecs(300))
        dt_edit.setCalendarPopup(True)
        dt_edit.setDisplayFormat("yyyy-MM-dd HH:mm")
        dt_edit.setLocale(QLocale(QLocale.Chinese, QLocale.China))
        dt_edit.setEnabled(False)

        def _toggle_sched():
            dt_edit.setEnabled(rb_later.isChecked())

        rb_now.toggled.connect(_toggle_sched)
        rb_later.toggled.connect(_toggle_sched)
        form.addRow("\u8ba1\u5212\u65f6\u95f4", dt_edit)

        root.addLayout(form)

        btn_row = QHBoxLayout()
        ok_btn = QPushButton("\u786e\u5b9a")
        cancel_btn = QPushButton("\u53d6\u6d88")
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        def _accept():
            if not chosen_paths:
                QMessageBox.warning(dlg, "\u63d0\u793a", "\u8bf7\u9009\u62e9\u81f3\u5c11\u4e00\u4e2a\u6587\u4ef6")
                return
            fps = ",".join(chosen_paths)
            post_type = "image" if rb_img.isChecked() else "video"
            caption_text = cap.toPlainText().strip()
            account_dir = combo.currentData()

            if rb_now.isChecked():
                dlg.accept()
                label = dir_to_display.get(account_dir, account_dir)
                show_toast(f"\u7acb\u5373\u53d1\u5e03: {label}", "#10B981", 3500)
                handle_openclaw_publish(account_dir, fps, caption_text, post_type)
                return

            qdt = dt_edit.dateTime()
            run_at = qdt_to_datetime(qdt)
            if run_at <= datetime.now():
                QMessageBox.warning(
                    dlg,
                    "\u63d0\u793a",
                    "\u5b9a\u65f6\u65f6\u95f4\u5fc5\u987b\u665a\u4e8e\u5f53\u524d\u65f6\u95f4",
                )
                return
            scheduled_tasks.append(
                {
                    "id": str(uuid.uuid4()),
                    "account": account_dir,
                    "file_paths": fps,
                    "caption": caption_text,
                    "post_type": post_type,
                    "run_at": run_at,
                    "status": "pending",
                }
            )
            dlg.accept()
            show_toast("\u5df2\u52a0\u5165\u6392\u671f\u961f\u5217", "#6366F1", 3000)

        ok_btn.clicked.connect(_accept)
        cancel_btn.clicked.connect(dlg.reject)

        dlg.exec()

    def on_open_task_queue():
        dlg = QDialog(window)
        dlg.setWindowTitle("\u6392\u671f\u7ba1\u7406")
        dlg.resize(800, 460)
        dlg.setStyleSheet(
            """
            QDialog { background: #18181B; }
            QLabel { color: #E4E4E7; }
            QTableWidget { background: #09090B; color: #E4E4E7; gridline-color: #27272A;
                border: 1px solid #27272A; border-radius: 6px; }
            QHeaderView::section { background: #18181B; color: #A1A1AA; padding: 6px; border: none; }
            QPushButton { background: #27272A; color: #E4E4E7; border: 1px solid #3F3F46;
                border-radius: 6px; padding: 6px 14px; }
            QPushButton:hover { background: #6366F1; color: #FFFFFF; border-color: #6366F1; }
        """
        )
        vl = QVBoxLayout(dlg)
        hint = QLabel(
            "\u672c\u6b21\u8fd0\u884c\u5185\u5b58\u50a8\uff0c\u9000\u51fa\u8f6f\u4ef6\u540e\u6e05\u7a7a\u3002"
        )
        hint.setStyleSheet("color:#52525B; font-size:11px;")
        vl.addWidget(hint)

        table = QTableWidget(0, 4)
        table.setHorizontalHeaderLabels(
            [
                "\u8ba1\u5212\u65f6\u95f4",
                "\u8d26\u53f7",
                "\u7c7b\u578b",
                "\u6587\u4ef6\u6458\u8981",
            ]
        )
        hdr = table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        vl.addWidget(table)

        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("\u5237\u65b0")
        run_btn = QPushButton("\u7acb\u5373\u6267\u884c\u9009\u4e2d")
        cancel_btn = QPushButton("\u53d6\u6d88\u9009\u4e2d")
        close_btn = QPushButton("\u5173\u95ed")
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(run_btn)
        btn_row.addWidget(cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        vl.addLayout(btn_row)

        def refresh():
            table.setRowCount(0)
            for t in scheduled_tasks:
                if t.get("status") != "pending":
                    continue
                row = table.rowCount()
                table.insertRow(row)
                ra = t["run_at"]
                ts = ra.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ra, datetime) else str(ra)
                acc = t["account"]
                disp = dir_to_display.get(acc, acc)
                fp = t["file_paths"]
                if len(fp) > 80:
                    fp = fp[:77] + "..."
                it0 = QTableWidgetItem(ts)
                it0.setData(Qt.UserRole, t["id"])
                table.setItem(row, 0, it0)
                table.setItem(row, 1, QTableWidgetItem(disp))
                table.setItem(row, 2, QTableWidgetItem(t.get("post_type", "")))
                table.setItem(row, 3, QTableWidgetItem(fp))

        def selected_id():
            r = table.currentRow()
            if r < 0:
                return None
            it = table.item(r, 0)
            return it.data(Qt.UserRole) if it else None

        def do_run():
            tid = selected_id()
            if not tid:
                QMessageBox.information(dlg, "\u63d0\u793a", "\u8bf7\u9009\u62e9\u4e00\u884c")
                return
            found = None
            for t in scheduled_tasks:
                if t.get("id") == tid:
                    found = t
                    break
            if not found:
                refresh()
                return
            scheduled_tasks.remove(found)
            refresh()
            handle_openclaw_publish(found["account"], found["file_paths"], found["caption"], found["post_type"])
            show_toast("\u5df2\u7acb\u5373\u6267\u884c\u6392\u671f\u4efb\u52a1", "#22C55E", 3000)

        def do_cancel():
            tid = selected_id()
            if not tid:
                QMessageBox.information(dlg, "\u63d0\u793a", "\u8bf7\u9009\u62e9\u4e00\u884c")
                return
            for i, t in enumerate(scheduled_tasks):
                if t.get("id") == tid:
                    scheduled_tasks.pop(i)
                    break
            refresh()
            show_toast("\u5df2\u53d6\u6d88\u6392\u671f\u4efb\u52a1", "#F59E0B", 2500)

        refresh_btn.clicked.connect(refresh)
        run_btn.clicked.connect(do_run)
        cancel_btn.clicked.connect(do_cancel)
        close_btn.clicked.connect(dlg.accept)

        refresh()
        dlg.exec()

    schedule_timer = QTimer()
    schedule_timer.timeout.connect(tick_scheduled)
    schedule_timer.start(1000)

    # ── 主线程轮询队列（线程安全的跨线程通信） ──
    def poll_publish_queue():
        while not _publish_queue.empty():
            try:
                account, file_paths, caption, post_type = _publish_queue.get_nowait()
                handle_openclaw_publish(account, file_paths, caption, post_type)
            except queue.Empty:
                break
        while not _log_queue.empty():
            try:
                msg = _log_queue.get_nowait()
                api_log(msg)
            except queue.Empty:
                break

    queue_poll_timer = QTimer()
    queue_poll_timer.timeout.connect(poll_publish_queue)

    # ── \u6e05\u7406\u7f13\u5b58 ──
    def on_clear_cache():
        reply = QMessageBox.question(
            window,
            "\U0001f9f9 \u6e05\u7406\u7f13\u5b58",
            "\u786e\u5b9a\u8981\u6e05\u7406\u6240\u6709\u8d26\u53f7\u7684\u8fd0\u884c\u7f13\u5b58\u5417\uff1f\n\uff08\u4e0d\u4f1a\u5f71\u54cd\u767b\u5f55\u72b6\u6001\uff09",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for name, profile in profile_cache.items():
            profile.clearHttpCache()
        QMessageBox.information(window, "\u2705 \u5b8c\u6210", "\u7f13\u5b58\u6e05\u7406\u5b8c\u6bd5\uff01")

    # ── \u4fe1\u53f7\u8fde\u63a5 ──
    account_list.currentRowChanged.connect(lambda _: on_selection())
    add_btn.clicked.connect(on_add)
    del_btn.clicked.connect(on_del)
    rename_btn.clicked.connect(on_rename)
    back_btn.clicked.connect(on_back)
    forward_btn.clicked.connect(on_forward)
    refresh_btn.clicked.connect(on_refresh)
    input_field.returnPressed.connect(on_add)
    api_checkbox.toggled.connect(toggle_api_service)
    clear_cache_btn.clicked.connect(on_clear_cache)
    btn_create_task.clicked.connect(on_create_scheduled_task)
    btn_manage_tasks.clicked.connect(on_open_task_queue)

    # ── \u52a0\u8f7d\u5df2\u6709\u8d26\u53f7 ──
    existing = sorted(
        [p.name for p in PROFILES_BASE_DIR.iterdir() if p.is_dir()],
        key=lambda s: s.lower(),
    )
    for dn in existing:
        add_account_to_list(dn, dn, select=False)

    if account_list.count() > 0:
        account_list.setCurrentRow(0)
    else:
        stacked.setCurrentIndex(empty_idx)

    # ── 退出清理（防止 QTimer / WebEngine 残留导致 abort） ──
    def _on_about_to_quit():
        queue_poll_timer.stop()
        schedule_timer.stop()
        for _name, prof in profile_cache.items():
            prof.clearHttpCache()

    qapp.aboutToQuit.connect(_on_about_to_quit)

    # ── fade-in animation (uses windowOpacity to avoid GPU conflict with WebEngine) ──
    window.setWindowOpacity(0.0)
    window.show()

    fade_in = QPropertyAnimation(window, b"windowOpacity")
    fade_in.setDuration(450)
    fade_in.setStartValue(0.0)
    fade_in.setEndValue(1.0)
    fade_in.setEasingCurve(QEasingCurve.OutCubic)
    fade_in.start()
    window._fade_in = fade_in  # prevent GC before animation completes

    return qapp.exec()


if __name__ == "__main__":
    raise SystemExit(main())
