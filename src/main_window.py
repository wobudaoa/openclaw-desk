"""
Main Window for OpenClaw Desktop App
"""

import html
import json
import logging
import math
import re
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QMessageBox,
    QPlainTextEdit, QTextEdit, QDialog, QLineEdit, QCheckBox,
    QScrollBar, QStyle, QStyleOptionSlider, QSizePolicy, QLayout, QScrollArea, QToolButton,
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPropertyAnimation,
    QEasingCurve, QPoint, Property, QSize, QEvent
)
from PySide6.QtGui import QFont, QPainter, QColor, QTextDocument, QTextCursor, QFontMetrics, QIcon, QIntValidator

from .gateway_manager import GatewayManager, GatewayStatus
from .browser_view import BrowserView
from .config_utils import iter_openclaw_config_paths
import subprocess

logger = logging.getLogger("openclaw.desktop.main_window")
ANSI_ESCAPE_RE = re.compile(r"\x1b\[([0-9;]*)m")
ANSI_COLOR_MAP = {
    30: "#2f3542",
    31: "#d92d20",
    32: "#16a34a",
    33: "#ca8a04",
    34: "#2563eb",
    35: "#9333ea",
    36: "#0891b2",
    37: "#e5e7eb",
    90: "#6b7280",
    91: "#ef4444",
    92: "#22c55e",
    93: "#eab308",
    94: "#60a5fa",
    95: "#c084fc",
    96: "#22d3ee",
    97: "#f9fafb",
}


from .translations import DEFAULT_LANGUAGE, TRANSLATIONS, tr_text


def app_base_dir() -> Path:
    """Return the writable application base directory for local config/log files."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

def resource_base_dir() -> Path:
    """Return the bundled resource directory used for icons and static files."""
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        return Path(meipass)
    return Path(__file__).resolve().parent.parent


def app_config_path() -> Path:
    """Path to the persistent desktop config file."""
    return app_base_dir() / "config.json"


def ensure_app_config_dir() -> Path:
    """Ensure the local config directory exists before reading or writing config.json."""
    base_dir = app_base_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def load_app_config() -> dict:
    """Load the desktop config JSON; create an empty config file when missing."""
    ensure_app_config_dir()
    path = app_config_path()
    if not path.exists():
        save_app_config({})
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("failed to load app config %s: %s", path, exc)
        save_app_config({})
        return {}
    return data if isinstance(data, dict) else {}


def save_app_config(config: dict) -> None:
    """Persist desktop config as UTF-8 JSON."""
    ensure_app_config_dir()
    path = app_config_path()
    try:
        path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to save app config %s: %s", path, exc)


def plugins_cache_path() -> Path:
    """Path to the cached plugin list used by the in-app plugins page."""
    return app_base_dir() / "plugins.json"


def load_plugins_cache() -> tuple[list[dict[str, str]], bool]:
    """Load cached plugin rows from plugins.json and report whether the cache is valid."""
    ensure_app_config_dir()
    path = plugins_cache_path()
    if not path.exists():
        return [], False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        logger.warning("failed to load plugins cache %s: %s", path, exc)
        return [], False
    rows = data.get("rows") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return [], False
    return rows, True


def save_plugins_cache(rows: list[dict[str, str]]) -> None:
    """Persist the current plugin rows so the page can render instantly on startup."""
    ensure_app_config_dir()
    path = plugins_cache_path()
    payload = {"rows": rows}
    try:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        logger.warning("failed to save plugins cache %s: %s", path, exc)

def load_license_text() -> str:
    """Read the bundled LICENSE file for the About page."""
    license_path = resource_base_dir() / 'LICENSE'
    try:
        return license_path.read_text(encoding='utf-8', errors='replace').strip()
    except OSError as exc:
        logger.warning('failed to load LICENSE %s: %s', license_path, exc)
        return ''

DEFAULT_MAIN_WINDOW_SIZE = (1200, 820)
DEFAULT_GATEWAY_PORT = 18789


def load_main_window_size(config: dict) -> tuple[int, int]:
    """Return the saved main-window size or fall back to the desktop default."""
    saved = config.get('window_size')
    if isinstance(saved, dict):
        try:
            width = int(saved.get('width', DEFAULT_MAIN_WINDOW_SIZE[0]))
            height = int(saved.get('height', DEFAULT_MAIN_WINDOW_SIZE[1]))
            if width > 0 and height > 0:
                return width, height
        except (TypeError, ValueError):
            pass
    return DEFAULT_MAIN_WINDOW_SIZE


def load_gateway_port(config: dict) -> int:
    """Return the saved gateway port or fall back to the default local port."""
    try:
        port = int(config.get('gateway_port', DEFAULT_GATEWAY_PORT))
    except (TypeError, ValueError):
        return DEFAULT_GATEWAY_PORT
    return port if 1 <= port <= 65535 else DEFAULT_GATEWAY_PORT


def show_exit_dialog(parent, include_cancel: bool = True):
    """Show a styled exit confirmation dialog."""
    t = getattr(parent, "_t", lambda key: tr_text(DEFAULT_LANGUAGE, key))
    dialog = QMessageBox(parent)
    dialog.setWindowTitle(t("dialog_exit_title"))
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setText(t("dialog_exit_question"))

    if include_cancel:
        dialog.setInformativeText(t("dialog_exit_info_with_cancel"))
        buttons = (
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
    else:
        dialog.setInformativeText(t("dialog_exit_info_without_cancel"))
        buttons = (
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
        )

    dialog.setStandardButtons(buttons)
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    dialog.setStyleSheet("""
        QMessageBox {
            background-color: #eef2f6;
        }
        QLabel#qt_msgbox_label {
            color: #2f3a46;
            min-width: 275px;
            max-width: 275px;
            padding-top: 2px;
        }
        QLabel#qt_msgbox_informativelabel {
            color: #536171;
            min-width: 275px;
            max-width: 275px;
            line-height: 1.35;
            padding-top: 2px;
        }
        QLabel#qt_msgboxex_icon_label {
            min-width: 40px;
            max-width: 40px;
            padding-right: 6px;
        }
        QMessageBox QPushButton {
            min-width: 58px;
            min-height: 34px;
            max-width: 58px;
            padding: 0 10px;
            background-color: #e6ebf2;
            color: #364152;
            border: 1px solid #d2d9e2;
            border-radius: 17px;
            font-weight: 600;
        }
        QMessageBox QPushButton:hover {
            background-color: #dce4ee;
            border-color: #c5cfda;
        }
        QMessageBox QPushButton:pressed {
            background-color: #cfd9e6;
            border-color: #b9c5d3;
        }
    """)
    dialog.layout().setSpacing(10)
    dialog.layout().setContentsMargins(14, 14, 14, 12)

    yes_button = dialog.button(QMessageBox.StandardButton.Yes)
    no_button = dialog.button(QMessageBox.StandardButton.No)
    cancel_button = dialog.button(QMessageBox.StandardButton.Cancel)

    for button in (yes_button, no_button):
        if button is not None:
            button.setFixedSize(58, 34)

    if cancel_button is not None:
        cancel_button.setFixedSize(82, 34)

    return dialog.exec()


def ansi_to_html(text: str) -> str:
    """Convert common ANSI color sequences into HTML for rich-text output."""
    if not text:
        return ""

    fragments: list[str] = []
    style = {"color": None, "bold": False}
    last_index = 0

    def wrap(chunk: str) -> str:
        escaped = html.escape(chunk).replace("\n", "<br>")
        css_rules = []
        if style["color"]:
            css_rules.append(f"color: {style['color']}")
        if style["bold"]:
            css_rules.append("font-weight: 700")
        if not css_rules:
            return escaped
        return f"<span style=\"{'; '.join(css_rules)}\">{escaped}</span>"

    for match in ANSI_ESCAPE_RE.finditer(text):
        if match.start() > last_index:
            fragments.append(wrap(text[last_index:match.start()]))

        codes = [int(code) for code in match.group(1).split(";") if code] or [0]
        for code in codes:
            if code == 0:
                style["color"] = None
                style["bold"] = False
            elif code == 1:
                style["bold"] = True
            elif code == 22:
                style["bold"] = False
            elif code == 39:
                style["color"] = None
            elif code in ANSI_COLOR_MAP:
                style["color"] = ANSI_COLOR_MAP[code]

        last_index = match.end()

    if last_index < len(text):
        fragments.append(wrap(text[last_index:]))

    return "".join(fragments)


class GatewayActionThread(QThread):
    finished_with_result = Signal(str, bool)

    def __init__(self, gateway_manager, action: str):
        super().__init__()
        self.gateway_manager = gateway_manager   # gateway manager used by the worker thread
        self.action = action                     # gateway action to execute

    def run(self):
        ok = False
        if self.action == "start":
            ok = self.gateway_manager.start()
        elif self.action == "stop":
            ok = self.gateway_manager.stop()
        elif self.action == "restart":
            ok = self.gateway_manager.restart()

        self.finished_with_result.emit(self.action, ok)


class OpenClawCommandThread(QThread):
    """Run an OpenClaw-related PowerShell command and stream output back to the dialog."""

    output_received = Signal(str)
    finished_with_result = Signal(bool)

    def __init__(
        self, gateway_manager: GatewayManager, command: str, success_message: str
    ):
        super().__init__()
        self.gateway_manager = gateway_manager
        self.command = command
        self.success_message = success_message

    def run(self):
        try:
            self.output_received.emit(f"PowerShell: {self.command}\n")
            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", self.command],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    if hasattr(subprocess, "CREATE_NO_WINDOW")
                    else 0
                ),
            )

            for raw_line in iter(process.stdout.readline, b""):
                line = self.gateway_manager._decode_process_output(raw_line).rstrip()
                if line:
                    self.output_received.emit(f"{line}\n")

            return_code = process.wait()
            if return_code == 0:
                self.output_received.emit(f"\n{self.success_message}\n")
                self.finished_with_result.emit(True)
            else:
                self.output_received.emit(
                    f"\nCommand failed with exit code {return_code}.\n"
                )
                self.finished_with_result.emit(False)
        except Exception as exc:
            self.output_received.emit(f"\nFailed to run command: {exc}\n")
            self.finished_with_result.emit(False)


def parse_plugin_list_output(output: str) -> list[dict[str, str]]:
    """Parse both legacy and newer `openclaw plugins list` table layouts."""
    cleaned_output = ANSI_ESCAPE_RE.sub('', output)
    lines = [line.rstrip() for line in cleaned_output.splitlines()]

    top_markers = ('┌', '+')
    bottom_markers = ('└', '+')
    row_markers = ('│', '|')

    top_index = next(
        (
            i for i, line in enumerate(lines)
            if line.strip().startswith(top_markers) and line.strip().endswith(('┐', '+'))
        ),
        -1,
    )
    bottom_index = next(
        (
            i for i in range(len(lines) - 1, -1, -1)
            if lines[i].strip().startswith(bottom_markers) and lines[i].strip().endswith(('┘', '+'))
        ),
        -1,
    )
    if top_index < 0 or bottom_index <= top_index:
        return []

    table_lines = lines[top_index:bottom_index + 1]
    header_index = next(
        (
            i for i, line in enumerate(table_lines)
            if line.strip().startswith(('│ Name', '| Name'))
        ),
        -1,
    )
    if header_index < 0:
        return []

    header_line = table_lines[header_index].strip()
    border_char = header_line[0]
    headers = [part.strip().lower() for part in header_line.strip(border_char).split(border_char)]
    index_map = {name: idx for idx, name in enumerate(headers)}
    required = ('name', 'id', 'status', 'source', 'version')
    if any(name not in index_map for name in required):
        return []

    plugins: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    def cell(cells: list[str], column: str) -> str:
        idx = index_map.get(column, -1)
        return cells[idx] if 0 <= idx < len(cells) else ''

    for line in table_lines[header_index + 2:]:
        stripped = line.strip()
        if stripped.startswith(('└', '+')):
            break
        if not stripped.startswith(row_markers):
            continue

        row_border = stripped[0]
        cells = [part.strip() for part in stripped.strip(row_border).split(row_border)]
        if len(cells) < len(headers):
            cells += [''] * (len(headers) - len(cells))

        row_name = cell(cells, 'name')
        row_id = cell(cells, 'id')
        row_status = cell(cells, 'status')
        row_source = cell(cells, 'source')
        row_version = cell(cells, 'version')
        row_format = cell(cells, 'format')

        is_new_record = bool(row_status)
        if is_new_record:
            if current is not None:
                plugins.append(current)
            current = {
                'name': row_name,
                'id': row_id,
                'status': row_status,
                'source': row_source,
                'version': row_version,
            }
            if row_format:
                current['format'] = row_format
            continue

        if current is None:
            continue

        for key, value in (
            ('name', row_name),
            ('id', row_id),
            ('status', row_status),
            ('source', row_source),
            ('version', row_version),
            ('format', row_format),
        ):
            if value:
                current[key] = f"{current.get(key, '')} {value}".strip()

    if current is not None:
        plugins.append(current)
    return plugins


class PluginListThread(QThread):
    """Load `openclaw plugins list` in the background and return parsed rows."""

    finished_with_result = Signal(bool, object, str)

    def __init__(self, gateway_manager: GatewayManager):
        super().__init__()
        self.gateway_manager = gateway_manager

    def run(self):
        try:
            cmd = self.gateway_manager._find_openclaw_cmd() + ['plugins', 'list']
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                creationflags=(getattr(subprocess, 'CREATE_NO_WINDOW', 0)),
            )
            raw_output, _ = process.communicate(timeout=90)
            output_text = self.gateway_manager._decode_process_output(raw_output)
            ok = process.returncode == 0
            rows = parse_plugin_list_output(output_text) if ok else []
            self.finished_with_result.emit(ok, rows, output_text)
        except subprocess.TimeoutExpired:
            self.finished_with_result.emit(False, [], 'Command timed out while loading plugin list.')
        except Exception as exc:
            self.finished_with_result.emit(False, [], f'Failed to load plugin list: {exc}')




class PluginInstallDialog(QDialog):
    """Small dialog for installing additional plugins without opening a terminal."""

    def __init__(self, gateway_manager: GatewayManager, parent=None):
        super().__init__(parent)
        self.gateway_manager = gateway_manager
        self._command_thread = None
        self._busy_mode = None
        self.setWindowTitle("Get More")
        self.setModal(False)
        self.setMinimumWidth(520)
        self.setMinimumHeight(360)
        self._setup_ui()
        self.refresh_texts()

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog {
                background-color: #ecf0f1;
            }
            QLineEdit, QTextEdit {
                background-color: #f5f7fa;
                color: #2f3a46;
                border: 1px solid #d4dce5;
                border-radius: 10px;
                padding: 10px;
                font-size: 12px;
            }
            QCheckBox {
                color: #3d4852;
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
            }
            QCheckBox::indicator:unchecked {
                border: 1px solid #9aa5b1;
                border-radius: 3px;
                background: white;
            }
            QCheckBox::indicator:checked {
                border: 1px solid #465669;
                border-radius: 3px;
                background: #34495e;
            }
            QPushButton#dialogPrimaryButton {
                background-color: #34495e;
                color: white;
                border: 1px solid #465669;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton#dialogPrimaryButton:hover {
                background-color: #465669;
            }
            QPushButton#dialogPrimaryButton:pressed {
                background-color: #2c3e50;
            }
            QPushButton#dialogPrimaryButton:disabled {
                background-color: #c7cfd8;
                color: #7b8794;
                border-color: #c7cfd8;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        switch_frame = QFrame()
        switch_frame.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border-radius: 8px;
            }
        """)
        switch_row = QHBoxLayout(switch_frame)
        switch_row.setContentsMargins(10, 10, 10, 10)
        switch_row.setSpacing(8)

        self.update_page_button = QPushButton("OpenClaw Update")
        self.update_page_button.setObjectName("dialogPrimaryButton")
        self.update_page_button.clicked.connect(lambda: self._set_page(0))
        switch_row.addWidget(self.update_page_button)

        self.plugins_page_button = QPushButton("Get Plugins")
        self.plugins_page_button.setObjectName("dialogPrimaryButton")
        self.plugins_page_button.clicked.connect(lambda: self._set_page(1))
        switch_row.addWidget(self.plugins_page_button)

        self.skills_page_button = QPushButton("Get Skills")
        self.skills_page_button.setObjectName("dialogPrimaryButton")
        self.skills_page_button.clicked.connect(lambda: self._set_page(2))
        switch_row.addWidget(self.skills_page_button)

        switch_row.addStretch()
        layout.addWidget(switch_frame)

        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._create_update_page())
        self.page_stack.addWidget(self._create_plugins_page())
        self.page_stack.addWidget(self._create_skills_page())
        layout.addWidget(self.page_stack)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        self.output_box.setPlaceholderText("Command output will appear here.")
        self.output_box.setStyleSheet("""
            QTextEdit {
                background-color: #f5f7fa;
                color: #7a1f1f;
                border: 1px solid #d4dce5;
                border-radius: 12px;
                padding: 10px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        layout.addWidget(self.output_box, 1)

        self._set_page(0)

    def _t(self, key: str) -> str:
        parent = self.parent()
        return parent._t(key) if parent is not None and hasattr(parent, '_t') else tr_text(DEFAULT_LANGUAGE, key)

    def refresh_texts(self):
        self.setWindowTitle(self._t("dialog_get_more_title"))
        self.update_page_button.setText(self._t("get_more_update_tab"))
        self.plugins_page_button.setText(self._t("get_more_plugins_tab"))
        self.skills_page_button.setText(self._t("get_more_skills_tab"))
        self.output_box.setPlaceholderText(self._t("get_more_output_placeholder"))
        self.check_update_button.setText(self._t("get_more_check_latest") if self._busy_mode != "checking" else self._t("get_more_checking"))
        self.install_update_button.setText(self._t("get_more_install_update") if self._busy_mode != "updating" else self._t("get_more_updating"))
        self.install_button.setText(self._t("get_more_install_plugins") if self._busy_mode != "installing" else self._t("get_more_installing"))
        self.update_registry_checkbox.setText(self._t("get_more_use_mirror"))
        self.registry_checkbox.setText(self._t("get_more_use_mirror"))
        self.skill_registry_checkbox.setText(self._t("get_more_use_mirror"))
        self.plugin_input.setPlaceholderText(self._t("get_more_plugin_placeholder"))
        self.skill_input.setPlaceholderText(self._t("get_more_skill_placeholder"))
        self.install_skill_button.setText(self._t("get_more_install_skills") if self._busy_mode != "installing_skills" else self._t("get_more_installing"))
        self.open_clawhub_button.setText(self._t("nav_open_clawhub"))
        parent = self.parent()
        expose_mode = bool(parent is not None and getattr(parent, '_expose_mode', False))
        self.open_clawhub_button.setVisible(expose_mode)

    def _create_update_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)

        self.check_update_button = QPushButton("Check Latest Version")
        self.check_update_button.setObjectName("dialogPrimaryButton")
        self.check_update_button.clicked.connect(self._check_update_status)
        button_row.addWidget(self.check_update_button)

        self.install_update_button = QPushButton("Install Update")
        self.install_update_button.setObjectName("dialogPrimaryButton")
        self.install_update_button.clicked.connect(self._install_update)
        button_row.addWidget(self.install_update_button)

        layout.addLayout(button_row)

        self.update_registry_checkbox = QCheckBox(
            "Use npm mirror: https://registry.npmmirror.com"
        )
        self.update_registry_checkbox.setChecked(True)
        layout.addWidget(self.update_registry_checkbox)

        layout.addStretch()
        return page

    def _create_plugins_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.plugin_input = QLineEdit()
        self.plugin_input.setPlaceholderText("Enter plugin name")
        self.plugin_input.setFixedHeight(34)
        self.plugin_input.setStyleSheet("""
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #d0d7de;
                border-radius: 17px;
                padding: 0 16px;
                font-size: 14px;
                selection-background-color: #dce4ee;
            }
            QLineEdit:focus {
                border: 1px solid #465669;
            }
        """)
        top_row.addWidget(self.plugin_input, 1)

        self.install_button = QPushButton("get plugins")
        self.install_button.setObjectName("dialogPrimaryButton")
        self.install_button.clicked.connect(self._start_install)
        top_row.addWidget(self.install_button)

        layout.addLayout(top_row)

        self.registry_checkbox = QCheckBox(
            "Use npm mirror: https://registry.npmmirror.com"
        )
        self.registry_checkbox.setChecked(True)
        layout.addWidget(self.registry_checkbox)

        layout.addStretch()
        return page

    def _create_skills_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.skill_input = QLineEdit()
        self.skill_input.setPlaceholderText("Enter skill name")
        self.skill_input.setFixedHeight(34)
        self.skill_input.setStyleSheet("""
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #d0d7de;
                border-radius: 17px;
                padding: 0 16px;
                font-size: 14px;
                selection-background-color: #dce4ee;
            }
            QLineEdit:focus {
                border: 1px solid #465669;
            }
        """)
        top_row.addWidget(self.skill_input, 1)

        self.install_skill_button = QPushButton("get skills")
        self.install_skill_button.setObjectName("dialogPrimaryButton")
        self.install_skill_button.clicked.connect(self._start_skill_install)
        top_row.addWidget(self.install_skill_button)

        self.open_clawhub_button = QPushButton("Open ClawHub")
        self.open_clawhub_button.setObjectName("dialogPrimaryButton")
        self.open_clawhub_button.clicked.connect(self._open_clawhub_market)
        top_row.addWidget(self.open_clawhub_button)

        layout.addLayout(top_row)

        self.skill_registry_checkbox = QCheckBox(
            "Use npm mirror: https://registry.npmmirror.com"
        )
        self.skill_registry_checkbox.setChecked(True)
        layout.addWidget(self.skill_registry_checkbox)

        layout.addStretch()
        return page

    def open_plugins_page(self):
        self._set_page(1)

    def _set_page(self, index: int):
        self.page_stack.setCurrentIndex(index)
        active_style = """
            QPushButton {
                background-color: #eef2f6;
                color: #2c3e50;
                border: 1px solid #eef2f6;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 700;
            }
        """
        inactive_style = """
            QPushButton {
                background-color: #34495e;
                color: #d6dde5;
                border: 1px solid #465669;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #465669;
            }
        """
        self.update_page_button.setStyleSheet(active_style if index == 0 else inactive_style)
        self.plugins_page_button.setStyleSheet(active_style if index == 1 else inactive_style)
        self.skills_page_button.setStyleSheet(active_style if index == 2 else inactive_style)

    def _append_output(self, text: str):
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)
        self.output_box.insertHtml(ansi_to_html(text))
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)

    def _set_busy(self, busy: bool):
        if not busy:
            self._busy_mode = None
        self.update_page_button.setEnabled(not busy)
        self.plugins_page_button.setEnabled(not busy)
        self.skills_page_button.setEnabled(not busy)
        self.check_update_button.setEnabled(not busy)
        self.install_update_button.setEnabled(not busy)
        self.update_registry_checkbox.setEnabled(not busy)
        self.plugin_input.setEnabled(not busy)
        self.registry_checkbox.setEnabled(not busy)
        self.install_button.setEnabled(not busy)
        self.skill_input.setEnabled(not busy)
        self.skill_registry_checkbox.setEnabled(not busy)
        self.install_skill_button.setEnabled(not busy)
        self.open_clawhub_button.setEnabled(not busy)
        self.install_button.setText(self._t("get_more_installing") if busy else self._t("get_more_install_plugins"))
        self.install_skill_button.setText(self._t("get_more_installing") if busy else self._t("get_more_install_skills"))
        self.check_update_button.setText(self._t("get_more_checking") if busy else self._t("get_more_check_latest"))
        self.install_update_button.setText(self._t("get_more_updating") if busy else self._t("get_more_install_update"))

    def _run_command(self, command: str, success_message: str):
        if self._command_thread and self._command_thread.isRunning():
            return
        self.output_box.clear()
        self._set_busy(True)
        self._command_thread = OpenClawCommandThread(
            self.gateway_manager,
            command,
            success_message,
        )
        self._command_thread.output_received.connect(self._append_output)
        self._command_thread.finished_with_result.connect(self._finish_command)
        self._command_thread.start()

    def _check_update_status(self):
        openclaw_path = self.gateway_manager._find_openclaw_cmd()[0]
        escaped_path = openclaw_path.replace("'", "''")
        command_parts = []
        if self.update_registry_checkbox.isChecked():
            command_parts.append(
                "npm config set registry https://registry.npmmirror.com"
            )
        command_parts.append(f"& '{escaped_path}' update status")
        self._busy_mode = "checking"
        self._run_command(
            "; ".join(command_parts),
            self._t("get_more_update_check_completed"),
        )

    def _install_update(self):
        openclaw_path = self.gateway_manager._find_openclaw_cmd()[0]
        escaped_path = openclaw_path.replace("'", "''")
        command_parts = []
        if self.update_registry_checkbox.isChecked():
            command_parts.append(
                "npm config set registry https://registry.npmmirror.com"
            )
        command_parts.append(f"& '{escaped_path}' update")
        self._busy_mode = "updating"
        self._run_command(
            "; ".join(command_parts),
            self._t("get_more_update_completed"),
        )

    def _start_install(self):
        plugin_name = self.plugin_input.text().strip()
        if not plugin_name:
            self._append_output(self._t("get_more_enter_plugin") + "\n")
            return
        openclaw_path = self.gateway_manager._find_openclaw_cmd()[0]
        escaped_path = openclaw_path.replace("'", "''")
        escaped_name = plugin_name.replace("'", "''")
        command_parts = []
        if self.registry_checkbox.isChecked():
            command_parts.append(
                "npm config set registry https://registry.npmmirror.com"
            )
        command_parts.append(f"& '{escaped_path}' plugins install '{escaped_name}'")
        self._busy_mode = "installing"
        self._run_command(
            "; ".join(command_parts),
            self._t("get_more_plugin_completed"),
        )

    def _start_skill_install(self):
        skill_name = self.skill_input.text().strip()
        if not skill_name:
            self._append_output(self._t("get_more_enter_skill") + "\n")
            return
        escaped_name = skill_name.replace("'", "''")
        command_parts = []
        if self.skill_registry_checkbox.isChecked():
            command_parts.append(
                "npm config set registry https://registry.npmmirror.com"
            )
        command_parts.append(f"npx clawhub@latest install '{escaped_name}'")
        self._busy_mode = "installing_skills"
        self._run_command(
            "; ".join(command_parts),
            self._t("get_more_skill_completed"),
        )

    def _open_clawhub_market(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, "_open_clawhub_market"):
            parent._open_clawhub_market()

    def _finish_command(self, _ok: bool):
        self._set_busy(False)


class SettingsDialog(QDialog):
    """Settings dialog with a left-side tab rail and right-side page stack."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.resize(560, 380)
        self.setMinimumSize(520, 360)
        self._setup_ui()
        self.refresh_texts()

    def _t(self, key: str) -> str:
        parent = self.parent()
        return parent._t(key) if parent is not None and hasattr(parent, '_t') else tr_text(DEFAULT_LANGUAGE, key)

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #ecf0f1; }
            QFrame#settingsRail { background-color: #2c3e50; border-radius: 12px; }
            QPushButton#settingsTabButton {
                background-color: transparent; color: #d6dde5; border: none; border-radius: 8px;
                padding: 10px 12px; text-align: left; font-size: 12px; font-weight: 600;
            }
            QPushButton#settingsTabButton:hover { background-color: #465669; color: white; }
            QFrame#settingsContentCard { background-color: #f5f7fa; border: 1px solid #d4dce5; border-radius: 12px; }
            QLabel#settingsPageTitle { color: #2f3a46; font-size: 16px; font-weight: 700; }
            QLabel#settingsSectionTitle { color: #2f3a46; font-size: 13px; font-weight: 700; }
            QLabel#settingsBodyText { color: #5b6875; font-size: 12px; line-height: 1.4; }
            QPushButton#settingsActionButton {
                background-color: #3b526b; color: white; border: 1px solid #50677f; border-radius: 10px;
                padding: 9px 16px; font-size: 12px; font-weight: 700;
            }
            QPushButton#settingsActionButton:hover { background-color: #465f7a; }
            QPushButton#settingsActionButton:pressed { background-color: #2f4458; }
        """)
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        rail = QFrame(); rail.setObjectName('settingsRail'); rail.setFixedWidth(116)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(10, 10, 10, 10); rail_layout.setSpacing(8)
        self.general_settings_btn = self._create_tab_button(0)
        self.language_settings_btn = self._create_tab_button(1)
        self.about_settings_btn = self._create_tab_button(2)
        for button in (self.general_settings_btn, self.language_settings_btn, self.about_settings_btn):
            rail_layout.addWidget(button)
        rail_layout.addStretch(); root.addWidget(rail)

        self.settings_stack = QStackedWidget()
        self.general_page, self.general_page_title, self.general_page_body = self._create_general_page()
        self.language_page = self._create_language_page()
        self.about_page, self.about_page_title, self.about_license_view = self._create_about_page()
        self.settings_stack.addWidget(self.general_page)
        self.settings_stack.addWidget(self.language_page)
        self.settings_stack.addWidget(self.about_page)
        root.addWidget(self.settings_stack, 1)
        self._set_page(0)

    def _create_tab_button(self, index: int) -> QPushButton:
        button = QPushButton(); button.setObjectName('settingsTabButton')
        button.clicked.connect(lambda: self._set_page(index))
        return button

    def _create_settings_page(self):
        page = QFrame(); page.setObjectName('settingsContentCard')
        layout = QVBoxLayout(page); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(10)
        title_label = QLabel(); title_label.setObjectName('settingsPageTitle'); layout.addWidget(title_label)
        body_label = QLabel(); body_label.setObjectName('settingsBodyText'); body_label.setWordWrap(True); layout.addWidget(body_label)
        layout.addStretch(); return page, title_label, body_label

    def _create_general_page(self):
        page, title_label, body_label = self._create_settings_page()
        layout = page.layout()
        body_label.hide()

        self.general_local_dir_title = QLabel()
        self.general_local_dir_title.setObjectName('settingsSectionTitle')
        layout.insertWidget(2, self.general_local_dir_title)

        self.general_local_dir_body = QLabel()
        self.general_local_dir_body.setObjectName('settingsBodyText')
        self.general_local_dir_body.setWordWrap(True)
        layout.insertWidget(3, self.general_local_dir_body)

        local_dir_row = QHBoxLayout()
        local_dir_row.setSpacing(10)

        self.general_local_dir_input = MaskedDirectoryLineEdit()
        local_dir_row.addWidget(self.general_local_dir_input, 1)

        self.general_open_dir_btn = QPushButton()
        self.general_open_dir_btn.setObjectName('settingsActionButton')
        self.general_open_dir_btn.clicked.connect(self._open_local_openclaw_root)
        local_dir_row.addWidget(self.general_open_dir_btn, 0)
        local_dir_row.addStretch()

        layout.insertLayout(4, local_dir_row)

        self.general_port_title = QLabel()
        self.general_port_title.setObjectName('settingsSectionTitle')
        layout.insertWidget(5, self.general_port_title)

        self.general_port_body = QLabel()
        self.general_port_body.setObjectName('settingsBodyText')
        self.general_port_body.setWordWrap(True)
        layout.insertWidget(6, self.general_port_body)

        port_row = QHBoxLayout()
        port_row.setSpacing(10)

        self.general_port_input = EditableMaskedPortLineEdit()
        port_row.addWidget(self.general_port_input, 1)

        self.general_apply_port_btn = QPushButton()
        self.general_apply_port_btn.setObjectName('settingsActionButton')
        self.general_apply_port_btn.clicked.connect(self._apply_port_and_restart)
        port_row.addWidget(self.general_apply_port_btn, 0)
        port_row.addStretch()

        layout.insertLayout(7, port_row)

        self.general_expose_title = QLabel()
        self.general_expose_title.setObjectName('settingsSectionTitle')
        layout.insertWidget(8, self.general_expose_title)

        self.general_expose_body = QLabel()
        self.general_expose_body.setObjectName('settingsBodyText')
        self.general_expose_body.setWordWrap(True)
        layout.insertWidget(9, self.general_expose_body)

        expose_row = QHBoxLayout()
        expose_row.setSpacing(10)
        self.general_expose_switch = LanguageToggleSwitch()
        self.general_expose_switch.stateChanged.connect(self._on_expose_mode_changed)
        expose_row.addWidget(self.general_expose_switch, 0)
        expose_row.addStretch()
        layout.insertLayout(10, expose_row)
        return page, title_label, body_label

    def _resolve_local_openclaw_root(self) -> Path | None:
        """Resolve the local OpenClaw config directory shown and opened by Settings."""
        for config_path in iter_openclaw_config_paths():
            if not config_path.exists():
                continue
            parent = config_path.parent
            if parent.name == '.openclaw' and parent.exists():
                return parent
            if parent.exists():
                return parent

        roots: list[Path] = []
        seen: set[str] = set()

        def add(path: Path | None):
            if path is None:
                return
            try:
                resolved = path.expanduser().resolve()
            except OSError:
                resolved = path.expanduser()
            key = str(resolved).lower()
            if key in seen:
                return
            seen.add(key)
            roots.append(resolved)

        add(Path.home() / '.openclaw')
        add(app_base_dir() / '.openclaw')
        add(Path.cwd() / '.openclaw')
        for parent in Path.cwd().resolve().parents:
            add(parent / '.openclaw')

        for root in roots:
            if root.exists():
                return root
        return None

    def _open_local_openclaw_root(self):
        """Open the local OpenClaw root folder in Explorer."""
        root = self._resolve_local_openclaw_root()
        if root is None:
            logger.warning('local openclaw root could not be resolved')
            return
        subprocess.Popen(['explorer', str(root)])

    def _apply_port_and_restart(self):
        parent = self.parent()
        if parent is not None and hasattr(parent, 'apply_gateway_port_from_settings'):
            parent.apply_gateway_port_from_settings(self.general_port_input.current_text())
        self.refresh_texts()

    def _create_about_page(self):
        page = QFrame(); page.setObjectName('settingsContentCard')
        layout = QVBoxLayout(page); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(10)
        title_label = QLabel(); title_label.setObjectName('settingsPageTitle'); layout.addWidget(title_label)
        license_view = QPlainTextEdit(); license_view.setReadOnly(True); license_view.setObjectName('aboutLicenseView')
        license_view.setStyleSheet("QPlainTextEdit { background: #ffffff; color: #2f3a46; border: 1px solid #d4dce5; border-radius: 12px; padding: 10px; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }")
        layout.addWidget(license_view, 1)
        return page, title_label, license_view

    def _create_language_page(self) -> QWidget:
        page = QFrame(); page.setObjectName('settingsContentCard')
        layout = QVBoxLayout(page); layout.setContentsMargins(18, 18, 18, 18); layout.setSpacing(14)
        self.language_page_title = QLabel(); self.language_page_title.setObjectName('settingsPageTitle'); layout.addWidget(self.language_page_title)
        self.language_page_body = QLabel(); self.language_page_body.setObjectName('settingsBodyText'); self.language_page_body.setWordWrap(True); layout.addWidget(self.language_page_body)
        toggle_row = QHBoxLayout(); toggle_row.setSpacing(10)
        self.language_english_label = QLabel(); self.language_english_label.setObjectName('settingsBodyText'); toggle_row.addWidget(self.language_english_label)
        self.language_switch = LanguageToggleSwitch(); self.language_switch.setObjectName('languageSwitch'); self.language_switch.stateChanged.connect(self._on_language_switch_changed); toggle_row.addWidget(self.language_switch)
        self.language_zh_label = QLabel(); self.language_zh_label.setObjectName('settingsBodyText'); toggle_row.addWidget(self.language_zh_label)
        toggle_row.addStretch(); layout.addLayout(toggle_row); layout.addStretch(); return page

    def refresh_texts(self):
        self.setWindowTitle(self._t('settings_title'))
        self.general_settings_btn.setText(self._t('settings_tab_general'))
        self.language_settings_btn.setText(self._t('settings_tab_language'))
        self.about_settings_btn.setText(self._t('settings_tab_about'))
        self.general_page_title.setText(self._t('settings_general_title'))
        self.general_page_body.setText(self._t('settings_general_body'))
        self.general_local_dir_title.setText(self._t('settings_general_local_dir_title'))
        self.general_local_dir_body.setText(self._t('settings_general_local_dir_body'))
        self.general_port_title.setText(self._t('settings_general_port_title'))
        self.general_port_body.setText(self._t('settings_general_port_body'))
        self.general_expose_title.setText(self._t('settings_general_expose_title'))
        self.general_expose_body.setText(self._t('settings_general_expose_body'))
        self.general_open_dir_btn.setText(self._t('settings_general_open_dir'))
        self.general_apply_port_btn.setText(self._t('settings_general_apply_port'))
        root = self._resolve_local_openclaw_root()
        real_path = str(root) if root is not None else ''
        self.general_local_dir_input.set_real_text(real_path)
        self.general_open_dir_btn.setToolTip(real_path)
        parent = self.parent()
        current_port = getattr(getattr(parent, 'gateway_manager', None), 'port', DEFAULT_GATEWAY_PORT)
        self.general_port_input.set_mask_text(self._t('settings_general_port_masked'))
        self.general_port_input.set_real_text(str(current_port))
        expose_checked = bool(parent is not None and getattr(parent, '_expose_mode', False))
        self.general_expose_switch.blockSignals(True); self.general_expose_switch.setChecked(expose_checked); self.general_expose_switch.blockSignals(False)
        self.language_page_title.setText(self._t('settings_language_title'))
        self.language_page_body.setText(self._t('settings_language_body'))
        self.language_english_label.setText(self._t('settings_language_english'))
        self.language_zh_label.setText(self._t('settings_language_zh'))
        self.about_page_title.setText(self._t('settings_about_title'))
        self.about_license_view.setPlainText(load_license_text())
        parent = self.parent()
        checked = bool(parent is not None and getattr(parent, '_language', DEFAULT_LANGUAGE) == 'zh-CN')
        self.language_switch.blockSignals(True); self.language_switch.setChecked(checked); self.language_switch.blockSignals(False)

    def _on_language_switch_changed(self, state: int):
        parent = self.parent()
        if parent is not None and hasattr(parent, 'set_language'):
            parent.set_language('zh-CN' if state == Qt.CheckState.Checked.value else 'en')
        self.refresh_texts()

    def _on_expose_mode_changed(self, state: int):
        parent = self.parent()
        if parent is not None and hasattr(parent, 'set_expose_mode'):
            parent.set_expose_mode(state == Qt.CheckState.Checked.value)
        self.refresh_texts()

    def _set_page(self, index: int):
        self.settings_stack.setCurrentIndex(index)
        active = 'background-color: #eef2f6; color: #2c3e50;'
        inactive = ''
        for i, button in enumerate((self.general_settings_btn, self.language_settings_btn, self.about_settings_btn)):
            button.setStyleSheet(active if i == index else inactive)


class PluginToggleDialog(QDialog):
    """Confirm and run enable/disable actions for a single plugin."""

    action_completed = Signal(str, bool)

    def __init__(self, gateway_manager: GatewayManager, plugin: dict[str, str], enabled: bool, parent=None):
        super().__init__(parent)
        self.gateway_manager = gateway_manager
        self.plugin = dict(plugin)
        self.plugin_id = plugin.get('id', '').strip()
        self.plugin_name = plugin.get('name', self.plugin_id).strip() or self.plugin_id
        self.target_enabled = not enabled
        self._command_thread = None
        self.setModal(True)
        self.resize(560, 380)
        self.setMinimumSize(520, 340)
        self._setup_ui()
        self.refresh_texts()

    def _t(self, key: str) -> str:
        parent = self.parent()
        return parent._t(key) if parent is not None and hasattr(parent, '_t') else tr_text(DEFAULT_LANGUAGE, key)

    def _setup_ui(self):
        self.setStyleSheet("""
            QDialog { background-color: #ecf0f1; }
            QFrame#pluginToggleCard { background-color: #f5f7fa; border: 1px solid #d4dce5; border-radius: 14px; }
            QLabel#pluginToggleTitle { color: #2f3a46; font-size: 16px; font-weight: 700; }
            QLabel#pluginToggleBody { color: #5b6875; font-size: 12px; line-height: 1.4; }
            QCheckBox { color: #2f3a46; font-size: 12px; }
            QPushButton#pluginTogglePrimary {
                background-color: #34495e; color: white; border: 1px solid #465669; border-radius: 10px;
                padding: 8px 16px; font-size: 12px; font-weight: 700;
            }
            QPushButton#pluginTogglePrimary:hover { background-color: #465669; }
            QPushButton#pluginTogglePrimary:pressed { background-color: #2c3e50; }
            QPushButton#pluginToggleSecondary {
                background-color: #e8edf3; color: #34495e; border: 1px solid #cfd7e2; border-radius: 10px;
                padding: 8px 16px; font-size: 12px; font-weight: 600;
            }
            QPushButton#pluginToggleSecondary:hover { background-color: #dde5ee; }
            QTextEdit {
                background-color: #f5f7fa; color: #7a1f1f; border: 1px solid #d4dce5; border-radius: 12px;
                padding: 10px; font-family: Consolas, 'Courier New', monospace; font-size: 12px;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        card = QFrame()
        card.setObjectName('pluginToggleCard')
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        self.title_label = QLabel()
        self.title_label.setObjectName('pluginToggleTitle')
        card_layout.addWidget(self.title_label)

        self.body_label = QLabel()
        self.body_label.setObjectName('pluginToggleBody')
        self.body_label.setWordWrap(True)
        card_layout.addWidget(self.body_label)

        self.busy_label = QLabel()
        self.busy_label.setObjectName('pluginToggleBody')
        self.busy_label.setWordWrap(True)
        self.busy_label.setStyleSheet('color: #b42318; font-size: 12px; font-weight: 700;')
        self.busy_label.hide()
        card_layout.addWidget(self.busy_label)

        self.registry_checkbox = QCheckBox()
        self.registry_checkbox.setChecked(True)
        self.registry_checkbox.setVisible(self.target_enabled)
        card_layout.addWidget(self.registry_checkbox)

        button_row = QHBoxLayout()
        button_row.setSpacing(8)
        button_row.addStretch()

        self.cancel_button = QPushButton()
        self.cancel_button.setObjectName('pluginToggleSecondary')
        self.cancel_button.clicked.connect(self.reject)
        button_row.addWidget(self.cancel_button)

        self.confirm_button = QPushButton()
        self.confirm_button.setObjectName('pluginTogglePrimary')
        self.confirm_button.clicked.connect(self._run_action)
        button_row.addWidget(self.confirm_button)
        card_layout.addLayout(button_row)

        self.output_box = QTextEdit()
        self.output_box.setReadOnly(True)
        card_layout.addWidget(self.output_box, 1)

        root.addWidget(card, 1)

    def refresh_texts(self):
        self.setWindowTitle(self._t('plugins_toggle_dialog_title'))
        self.title_label.setText(self._t('plugins_toggle_enable_title') if self.target_enabled else self._t('plugins_toggle_disable_title'))
        self.body_label.setText(
            self._t('plugins_toggle_enable_body').format(name=self.plugin_name)
            if self.target_enabled else
            self._t('plugins_toggle_disable_body').format(name=self.plugin_name)
        )
        self.registry_checkbox.setText(self._t('get_more_use_mirror'))
        self.cancel_button.setText(self._t('plugins_toggle_cancel'))
        self.confirm_button.setText(self._t('plugins_toggle_enable_confirm') if self.target_enabled else self._t('plugins_toggle_disable_confirm'))
        self.output_box.setPlaceholderText(self._t('plugins_toggle_output_placeholder'))

    def _set_busy(self, busy: bool):
        self.confirm_button.setEnabled(not busy)
        if self.target_enabled:
            self.registry_checkbox.setEnabled(not busy)
        self.busy_label.setText(self._t('plugins_toggle_busy_enable') if self.target_enabled else self._t('plugins_toggle_busy_disable'))
        self.busy_label.setVisible(busy)
        self.cancel_button.setEnabled(not busy)

    def _append_output(self, text: str):
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)
        self.output_box.insertHtml(ansi_to_html(text))
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)

    def _run_action(self):
        if self._command_thread is not None and self._command_thread.isRunning():
            return
        openclaw_path = self.gateway_manager._find_openclaw_cmd()[0]
        escaped_path = openclaw_path.replace("'", "''")
        escaped_id = self.plugin_id.replace("'", "''")
        action = 'enable' if self.target_enabled else 'disable'
        command_parts = []
        if self.target_enabled and self.registry_checkbox.isChecked():
            command_parts.append('npm config set registry https://registry.npmmirror.com')
        command_parts.append(f"& '{escaped_path}' plugins {action} '{escaped_id}'")
        success_message = self._t('plugins_toggle_enable_completed') if self.target_enabled else self._t('plugins_toggle_disable_completed')
        self.output_box.clear()
        self._set_busy(True)
        self._command_thread = OpenClawCommandThread(self.gateway_manager, '; '.join(command_parts), success_message)
        self._command_thread.output_received.connect(self._append_output)
        self._command_thread.finished_with_result.connect(self._finish_action)
        self._command_thread.start()

    def _finish_action(self, ok: bool):
        self.cancel_button.setEnabled(True)
        self.cancel_button.setText(self._t('plugins_toggle_close'))
        self.busy_label.setVisible(False)
        if ok:
            self.action_completed.emit(self.plugin_id, self.target_enabled)

    def closeEvent(self, event):
        if self._command_thread is not None and self._command_thread.isRunning():
            event.ignore()
            return
        super().closeEvent(event)


class ChromeScrollBar(QScrollBar):
    def sizeHint(self):
        base = super().sizeHint()
        if self.orientation() == Qt.Orientation.Vertical:
            return QSize(12, base.height())
        return QSize(base.width(), 12)

    def paintEvent(self, event):
        option = QStyleOptionSlider()
        self.initStyleOption(option)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        slider_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ScrollBar,
            option,
            QStyle.SubControl.SC_ScrollBarSlider,
            self,
        )
        if not slider_rect.isValid():
            return

        if self.orientation() == Qt.Orientation.Vertical:
            slider_rect = slider_rect.adjusted(2, 0, -2, 0)
        else:
            slider_rect = slider_rect.adjusted(0, 2, 0, -2)

        color = QColor("#c7ccd3")
        if self.isSliderDown():
            color = QColor("#9ea7b2")
        elif self.underMouse():
            color = QColor("#b3bac3")

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(color)
        radius = min(slider_rect.width(), slider_rect.height()) / 2
        painter.drawRoundedRect(slider_rect, radius, radius)


class PortToggleButton(QPushButton):
    """Header button that keeps the port label clear and only masks the numeric value."""

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self._port_text = str(port)
        self._prefix_text = "Port: "
        self._port_visible = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

    def set_port_visible(self, visible: bool):
        self._port_visible = visible
        self.update()

    def set_port(self, port: int):
        self._port_text = str(port)
        self.updateGeometry()
        self.update()

    def set_prefix_text(self, prefix_text: str):
        self._prefix_text = prefix_text.rstrip() + " "
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(f"{self._prefix_text}{self._port_text}") + 16
        height = max(18, metrics.height())
        return QSize(width, height)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        color = QColor("white" if self.underMouse() else "#bdc3c7")
        painter.setPen(color)
        metrics = painter.fontMetrics()
        baseline = (self.height() + metrics.ascent() - metrics.descent()) // 2
        prefix = self._prefix_text
        painter.drawText(0, baseline, prefix)
        prefix_width = metrics.horizontalAdvance(prefix)
        if self._port_visible:
            painter.drawText(prefix_width, baseline, self._port_text)
            return
        value_width = metrics.horizontalAdvance(self._port_text)
        blur_rect = self.rect().adjusted(prefix_width - 1, 3, -6, -3)
        blur_rect.setWidth(value_width + 10)
        base_fill = QColor("#c9d1da" if self.underMouse() else "#b8c2cc")
        edge_fill = QColor(base_fill); edge_fill.setAlpha(55)
        center_fill = QColor(base_fill); center_fill.setAlpha(105)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge_fill); painter.drawRoundedRect(blur_rect.adjusted(-2, 0, 2, 0), 5, 5)
        painter.setBrush(center_fill); painter.drawRoundedRect(blur_rect, 4, 4)


class LanguageToggleSwitch(QCheckBox):
    """Compact pill switch used by the language settings page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(52, 30)

    def sizeHint(self) -> QSize:
        return QSize(52, 30)

    def hitButton(self, pos):
        """Make the full pill area clickable instead of only the default checkbox indicator."""
        return self.rect().contains(pos)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        radius = rect.height() / 2
        track_color = QColor('#34495e') if self.isChecked() else QColor('#b8c2cc')
        knob_diameter = rect.height() - 8
        knob_y = rect.y() + 4
        knob_x = rect.right() - knob_diameter - 4 if self.isChecked() else rect.x() + 4

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(rect, radius, radius)

        painter.setBrush(QColor('white'))
        painter.drawEllipse(int(knob_x), int(knob_y), int(knob_diameter), int(knob_diameter))

        if self.hasFocus():
            focus_color = QColor('#aeb8c4')
            focus_color.setAlpha(110)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(focus_color)
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius + 1, radius + 1)



class ActionPillSwitch(LanguageToggleSwitch):
    """A pill switch that looks interactive but only emits an action request."""

    actionRequested = Signal()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.actionRequested.emit()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.actionRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class MaskedDirectoryLineEdit(QLineEdit):
    """Read-only line edit that toggles between a placeholder and the real local directory."""

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self._real_text = initial_text
        self._masked = True
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            """
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #d0d7de;
                border-radius: 17px;
                padding: 0 16px;
                font-size: 14px;
                selection-background-color: #dce4ee;
            }
            QLineEdit[masked="true"] {
                background: #edf1f5;
                color: #7a8694;
                border: 1px solid #d5dce4;
            }
            QLineEdit:focus {
                border: 1px solid #465669;
            }
            """
        )
        self._sync_display()

    def set_real_text(self, text: str):
        self._real_text = text
        self._sync_display()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._masked = not self._masked
            self._sync_display()
            event.accept()
            return
        super().mousePressEvent(event)

    def _sync_display(self):
        self.blockSignals(True)
        self.setProperty("masked", self._masked)
        self.setText("Local Directory" if self._masked else self._real_text)
        if not self._masked:
            self.setCursorPosition(0)
        self.style().unpolish(self)
        self.style().polish(self)
        self.blockSignals(False)



class EditableMaskedPortLineEdit(QLineEdit):
    """Masked port field that only becomes editable from the trailing edit action."""

    def __init__(self, port: int = DEFAULT_GATEWAY_PORT, parent=None):
        super().__init__(parent)
        self._real_text = str(port)
        self._masked = True
        self._editing = False
        self._mask_text = "Port"
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(34)
        self.setMaxLength(5)
        self.setValidator(QIntValidator(1, 65535, self))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            """
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #d0d7de;
                border-radius: 17px;
                padding: 0 46px 0 16px;
                font-size: 14px;
                selection-background-color: #dce4ee;
            }
            QLineEdit[masked="true"] {
                background: #edf1f5;
                color: #7a8694;
                border: 1px solid #d5dce4;
            }
            QLineEdit:focus {
                border: 1px solid #465669;
            }
            """
        )
        edit_icon = resource_base_dir() / 'assets' / 'edit.png'
        self._edit_button = QToolButton(self)
        self._edit_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self._edit_button.setIcon(QIcon(str(edit_icon)))
        self._edit_button.setIconSize(QSize(14, 14))
        self._edit_button.setStyleSheet(
            "QToolButton { border: none; background: transparent; padding: 0; } QToolButton:hover { background: transparent; }"
        )
        self._edit_button.clicked.connect(self.start_editing)
        self.editingFinished.connect(self._finish_editing)
        self._sync_display()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        size = 20
        x = self.width() - size - 12
        y = (self.height() - size) // 2
        self._edit_button.setGeometry(x, y, size, size)

    def set_real_text(self, text: str):
        self._real_text = str(text).strip()
        if not self._editing:
            self._sync_display()

    def set_mask_text(self, text: str):
        self._mask_text = text or "Port"
        if not self._editing:
            self._sync_display()

    def current_text(self) -> str:
        return self.text().strip() if self._editing else self._real_text

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._editing:
            self._masked = not self._masked
            self._sync_display()
            event.accept()
            return
        super().mousePressEvent(event)

    def start_editing(self):
        self._editing = True
        self._masked = False
        self.blockSignals(True)
        self.setProperty('masked', False)
        self.setReadOnly(False)
        self.setCursor(Qt.CursorShape.IBeamCursor)
        self.setText(self._real_text)
        self.blockSignals(False)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setFocus()
        self.selectAll()

    def _finish_editing(self):
        if not self._editing:
            return
        edited = self.text().strip()
        if edited:
            self._real_text = edited
        self._editing = False
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._sync_display()

    def _sync_display(self):
        self.blockSignals(True)
        self.setProperty('masked', self._masked)
        self.setText(self._mask_text if self._masked else self._real_text)
        if not self._masked:
            self.setCursorPosition(0)
        self.style().unpolish(self)
        self.style().polish(self)
        self.blockSignals(False)




class StatusIndicator(QLabel):
    """Custom status indicator widget."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._language = DEFAULT_LANGUAGE
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedSize(120, 30)
        self.setStyleSheet("""
            QLabel {
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }
        """)
        self.set_status(GatewayStatus.STOPPED)

    def set_status(self, status: GatewayStatus, language: str | None = None):
        if language is not None:
            self._language = language
        colors = {GatewayStatus.STOPPED: "#e74c3c", GatewayStatus.STARTING: "#f39c12", GatewayStatus.LOADING: "#3498db", GatewayStatus.RUNNING: "#27ae60", GatewayStatus.STOPPING: "#f39c12", GatewayStatus.ERROR: "#e74c3c"}
        keys = {GatewayStatus.STOPPED: "status_stopped", GatewayStatus.STARTING: "status_starting", GatewayStatus.LOADING: "status_loading", GatewayStatus.RUNNING: "status_running", GatewayStatus.STOPPING: "status_stopping", GatewayStatus.ERROR: "status_error"}
        color = colors.get(status, "#95a5a6")
        text_value = tr_text(self._language, keys.get(status, "status_unknown"))
        self.setStyleSheet(f"""QLabel {{ background-color: {color}; color: white; border-radius: 15px; font-weight: bold; font-size: 12px; }}""")
        self.setText(text_value)


class RotatingEmojiLabel(QLabel):
    """Emoji label that supports status spinning and directed travel."""

    def __init__(self, emoji: str, parent=None):
        super().__init__(emoji, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._angle = 0.0                        # current lobster rotation angle
        self._status_spinning = False            # whether status-driven spinning is active
        self._spin_paused_for_move = False       # whether status spinning is paused during travel
        self._text_color = QColor("#3498db")     # lobster glyph color
        self._rotation_step = 4.0                # degrees advanced per animation tick
        self._timer = QTimer(self)               # timer driving rotation updates
        self._timer.setInterval(24)
        self._timer.timeout.connect(self._tick)
        self._move_animation = QPropertyAnimation(self, b"pos", self)  # movement tween for the lobster
        self._move_animation.setDuration(1200)
        self._move_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._move_animation.finished.connect(self._on_move_finished)
        self._move_animation.valueChanged.connect(lambda _: self.update())
        self._pending_move_target = None         # queued movement destination
        self._heading_target = None              # target angle before moving
        self._settle_target = None               # upright angle to settle toward
        self._idle_settle_timer = QTimer(self)   # delayed return-to-upright timer
        self._idle_settle_timer.setSingleShot(True)
        self._idle_settle_timer.setInterval(5000)
        self._idle_settle_timer.timeout.connect(self._schedule_idle_settle)

    def set_text_color(self, color: str):
        self._text_color = QColor(color)
        self.update()

    def get_rotation_angle(self):
        return self._angle

    def set_rotation_angle(self, angle: float):
        self._angle = angle % 360.0
        self.update()

    rotationAngle = Property(float, get_rotation_angle, set_rotation_angle)

    def set_spinning(self, spinning: bool):
        was_spinning = self._status_spinning
        self._status_spinning = spinning
        if self._status_spinning:
            self._spin_paused_for_move = False
            self._settle_target = None
            self._idle_settle_timer.stop()
            if not self._timer.isActive():
                self._timer.start()
            return

        if was_spinning and not self._status_spinning:
            self._spin_paused_for_move = False
            self._idle_settle_timer.stop()
            if self._move_animation.state() == QPropertyAnimation.State.Running or self._heading_target is not None:
                return
            self._settle_target = self._closest_upright_angle(self._angle)
            if not self._timer.isActive():
                self._timer.start()
            return

    def animate_to(self, target_pos: QPoint):
        if self.pos() == target_pos:
            if not self._status_spinning:
                self._start_idle_settle_timer()
            return
        self._idle_settle_timer.stop()
        self._pending_move_target = target_pos
        self._settle_target = None
        self._heading_target = self._compute_heading(target_pos)
        if self._status_spinning:
            self._spin_paused_for_move = True
        if self._move_animation.state() == QPropertyAnimation.State.Running:
            self._move_animation.stop()
        if not self._timer.isActive():
            self._timer.start()

    def _start_move_animation(self, target_pos: QPoint):
        if self._move_animation.state() == QPropertyAnimation.State.Running:
            self._move_animation.stop()
        self._move_animation.setStartValue(self.pos())
        self._move_animation.setEndValue(target_pos)
        self._move_animation.start()

    def _on_move_finished(self):
        if self._status_spinning:
            self._spin_paused_for_move = False
            if not self._timer.isActive():
                self._timer.start()
            return
        self._start_idle_settle_timer()

    def _tick(self):
        if self._heading_target is not None:
            if self._advance_toward(self._heading_target):
                self._heading_target = None
                if self._pending_move_target is not None:
                    target_pos = self._pending_move_target
                    self._pending_move_target = None
                    self._start_move_animation(target_pos)
            return

        if self._status_spinning and not self._spin_paused_for_move:
            self._angle = (self._angle + self._rotation_step) % 360.0
            self.update()
            return

        if self._settle_target is not None:
            if self._advance_toward(self._settle_target):
                self._angle = 0.0
                self._settle_target = None
                self.update()
            return

        self._timer.stop()

    def _start_idle_settle_timer(self):
        if self._status_spinning:
            return
        self._idle_settle_timer.start()

    def _schedule_idle_settle(self):
        if self._status_spinning or self._heading_target is not None:
            return
        if self._move_animation.state() == QPropertyAnimation.State.Running:
            return
        self._settle_target = self._closest_upright_angle(self._angle)
        if not self._timer.isActive():
            self._timer.start()

    def _advance_toward(self, target: float) -> bool:
        diff = self._shortest_angle_delta(self._angle, target)
        if abs(diff) <= self._rotation_step:
            self._angle = target % 360.0
            self.update()
            return True
        self._angle = (self._angle + self._rotation_step * (1 if diff > 0 else -1)) % 360.0
        self.update()
        return False

    def _compute_heading(self, target_pos: QPoint) -> float:
        current_center = QPoint(
            self.x() + self.width() // 2,
            self.y() + self.height() // 2,
        )
        target_center = QPoint(
            target_pos.x() + self.width() // 2,
            target_pos.y() + self.height() // 2,
        )
        dx = target_center.x() - current_center.x()
        dy = target_center.y() - current_center.y()
        if dx == 0 and dy == 0:
            return self._angle
        return math.degrees(math.atan2(dx, -dy)) % 360.0

    def _closest_upright_angle(self, angle: float) -> float:
        normalized = angle % 360.0
        return 0.0 if normalized <= 180.0 else 360.0

    def _shortest_angle_delta(self, current: float, target: float) -> float:
        return (target - current + 540.0) % 360.0 - 180.0

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        vertical_offset, scale = self._movement_overlay_state()
        painter.translate(self.width() / 2, self.height() / 2)
        painter.translate(0, vertical_offset)
        painter.rotate(self._angle)
        painter.scale(scale, scale)
        painter.translate(-self.width() / 2, -self.height() / 2)
        painter.setFont(self.font())
        painter.setPen(self._text_color)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())

    def _movement_overlay_state(self) -> tuple[float, float]:
        if self._move_animation.state() != QPropertyAnimation.State.Running:
            return 0.0, 1.0

        duration = max(1, self._move_animation.duration())
        progress = max(0.0, min(1.0, self._move_animation.currentTime() / duration))

        # Ramp the effect in/out so the motion settles naturally.
        envelope = math.sin(math.pi * progress)
        phase = progress * math.tau * 2.0

        vertical_offset = math.sin(phase * 1.15) * 3.5 * envelope
        scale = 1.0 + math.sin(phase) * 0.05 * envelope
        return vertical_offset, scale


class WelcomePage(QWidget):
    """Welcome page that keeps the lobster draggable across the page."""

    def __init__(self, icon_label: RotatingEmojiLabel, parent=None):
        super().__init__(parent)
        self.icon_label = icon_label
        self.icon_label.setParent(self)
        self.text_container = QWidget(self)
        self._icon_has_custom_position = False
        self.text_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.text_container.setStyleSheet("background: transparent;")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setStyleSheet("background: transparent; border: none;")

    def set_text_content(self, widget: QWidget):
        widget.setParent(self.text_container)
        layout = QVBoxLayout(self.text_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(widget)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_content()

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return

        clicked_widget = self.childAt(event.position().toPoint())
        if clicked_widget not in (None, self):
            super().mousePressEvent(event)
            return

        target = self._clamped_icon_top_left(event.position().toPoint())
        self.icon_label.animate_to(target)
        self._icon_has_custom_position = True
        event.accept()

    def _layout_content(self):
        page_width = self.width()
        page_height = self.height()

        text_size = self.text_container.sizeHint()
        text_x = max(0, (page_width - text_size.width()) // 2)
        text_y = max(0, int(page_height * 0.52))
        self.text_container.setGeometry(text_x, text_y, text_size.width(), text_size.height())

        if not self._icon_has_custom_position:
            icon_x = (page_width - self.icon_label.width()) // 2
            icon_y = max(24, text_y - self.icon_label.height() - 26)
            self.icon_label.move(icon_x, icon_y)
        else:
            self.icon_label.move(self._clamped_icon_top_left(self.icon_label.pos()))
        self.icon_label.raise_()

    def _clamped_icon_top_left(self, point: QPoint) -> QPoint:
        target_x = point.x() - self.icon_label.width() // 2
        target_y = point.y() - self.icon_label.height() // 2
        max_x = max(0, self.width() - self.icon_label.width())
        max_y = max(0, self.height() - self.icon_label.height())
        return QPoint(
            max(0, min(target_x, max_x)),
            max(0, min(target_y, max_y)),
        )


class MainWindow(QMainWindow):
    """Main application window"""

    PAGE_WELCOME = 0
    PAGE_ERROR = 1
    PAGE_PLUGINS = 2
    PAGE_BROWSER = 3
    HEADER_BUTTON_STYLE = """
        QPushButton {
            background-color: #34495e;
            color: white;
            border: 1px solid #465669;
            border-radius: 4px;
            padding: 5px 12px;
            font-size: 12px;
            font-weight: bold;
        }
        QPushButton:hover {
            background-color: #465669;
        }
        QPushButton:pressed {
            background-color: #2c3e50;
        }
        QPushButton:disabled {
            background-color: #2c3e50;
            color: #7f8c8d;
        }
    """

    def __init__(self):
        super().__init__()

        self._config = load_app_config()                    # persisted desktop settings
        self._saved_window_size = load_main_window_size(self._config)  # preferred main-window size from config.json
        self._saved_gateway_port = load_gateway_port(self._config)      # preferred gateway port from config.json
        self.gateway_manager = GatewayManager(port=self._saved_gateway_port)   # gateway process manager
        self.gateway_manager.status_changed.connect(self._on_status_changed)
        self.gateway_manager.log_message.connect(self._on_log_message)
        self.gateway_manager.process_output.connect(self._on_gateway_process_output)
        self._ui_status = GatewayStatus.STOPPED             # current UI-facing gateway status
        self._window_size_ready = False                    # ignore resize persistence until the initial size is applied
        self._language = self._config.get("language", DEFAULT_LANGUAGE)
        if self._language not in TRANSLATIONS:
            self._language = DEFAULT_LANGUAGE
        self._openclaw_available = self.gateway_manager.is_openclaw_installed()  # whether openclaw is installed
        self._expose_mode = bool(self._config.get('expose_mode', False))
        self._port_visible = False                          # whether the header shows the real port
        cached_plugins, cache_valid = load_plugins_cache()  # cached plugin rows persisted in plugins.json
        self._plugin_dialog = None                          # lazily created "Get More" dialog
        self._settings_dialog = None                        # lazily created settings dialog
        self._plugins_load_thread = None                    # background loader for the plugins page
        self._plugins_rows = cached_plugins                 # last parsed plugin rows
        self._plugins_load_ok = True if cache_valid else None
        self._plugins_output_text = ''                      # raw output from the last plugin load
        self._plugin_row_widgets = {}                       # live widgets keyed by plugin id for local status updates
        self._action_thread = None                          # running gateway action thread, if any
        self._dashboard_open_scheduled = False              # whether auto-open dashboard has been queued
        self._dashboard_navigation_pending = False          # whether a dashboard navigation is in progress
        self._error_info_sticky = False                     # keep error page/button visible until a successful run

        self._setup_ui()
        self._apply_styles()
        self._apply_translations()

        if self._openclaw_available:
            self._apply_openclaw_available_welcome_state()
            self._on_status_changed(self.gateway_manager.get_status())
            if not cache_valid:
                self._load_plugins_page_data(force=True)
        else:
            self._apply_openclaw_missing_state()

    def _run_gateway_action(self, action: str):
        if not self._openclaw_available:
            logger.info("ignored gateway action %s because openclaw is not installed", action)
            self._apply_openclaw_missing_state()
            return
        if self._action_thread and self._action_thread.isRunning():
            logger.info("ignored gateway action %s because another action is running", action)
            return

        logger.info("starting gateway action thread: %s", action)
        if action in ("start", "restart"):
            self._hide_error_card()
            self.gateway_manager.clear_recent_output()
        action_status = {
            "start": (GatewayStatus.STARTING, self._t("message_starting_gateway")),
            "restart": (GatewayStatus.STARTING, self._t("message_restarting_gateway")),
            "stop": (GatewayStatus.STOPPING, self._t("message_stopping_gateway")),
        }
        status, message = action_status[action]
        self._set_ui_status(status, message)

        self._action_thread = GatewayActionThread(self.gateway_manager, action)
        self._action_thread.finished_with_result.connect(self._on_gateway_action_finished)
        self._action_thread.start()

    def _set_ui_status(self, status: GatewayStatus, message: str = None):
        self._ui_status = status
        self.status_indicator.set_status(status, self._language)
        if hasattr(self, "welcome_icon"):
            self.welcome_icon.set_spinning(
                status in (GatewayStatus.STARTING, GatewayStatus.LOADING)
            )
        if message:
            self.status_bar.setText(message)
        self._update_header_buttons()

    def _update_header_buttons(self):
        controls_enabled = self._openclaw_available
        show_error_info = self._error_info_sticky and self._ui_status != GatewayStatus.RUNNING
        if hasattr(self, "header_start_btn"):
            self.header_start_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.STOPPED, GatewayStatus.ERROR))
        if hasattr(self, "header_stop_btn"):
            self.header_stop_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING))
        if hasattr(self, "header_restart_btn"):
            self.header_restart_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING, GatewayStatus.ERROR))
        if hasattr(self, "header_dashboard_btn"):
            self.header_dashboard_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING))
            self.header_dashboard_btn.setVisible(not show_error_info)
        if hasattr(self, "header_error_btn"):
            self.header_error_btn.setVisible(show_error_info)
            self.header_error_btn.setEnabled(show_error_info)
        if hasattr(self, "header_plugins_btn"):
            self.header_plugins_btn.setVisible(controls_enabled)
            self.header_plugins_btn.setEnabled(controls_enabled)
        if hasattr(self, "header_get_more_btn"):
            self.header_get_more_btn.setVisible(controls_enabled)
            self.header_get_more_btn.setEnabled(controls_enabled)
        if hasattr(self, "header_settings_btn"):
            self.header_settings_btn.setVisible(controls_enabled)
            self.header_settings_btn.setEnabled(controls_enabled)

    def _reset_dashboard_navigation(self):
        """Clear deferred dashboard navigation flags when the state changes."""
        self._dashboard_open_scheduled = False
        self._dashboard_navigation_pending = False

    def _set_current_page(self, page_index: int):
        self.content_stack.setCurrentIndex(page_index)

    def _t(self, key: str) -> str:
        return tr_text(self._language, key)

    def set_language(self, language: str):
        if language not in TRANSLATIONS or language == self._language:
            return
        self._language = language
        self._config["language"] = language
        save_app_config(self._config)
        self._apply_translations()

    def _show_themed_warning(self, title: str, body: str):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setText(body)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.setStyleSheet("""
            QMessageBox { background-color: #eef2f6; }
            QLabel { color: #2f3a46; min-width: 280px; }
            QMessageBox QPushButton {
                min-width: 88px; min-height: 34px; padding: 0 14px;
                background-color: #3b526b; color: white; border: 1px solid #50677f;
                border-radius: 10px; font-size: 12px; font-weight: 700;
            }
            QMessageBox QPushButton:hover { background-color: #465f7a; }
            QMessageBox QPushButton:pressed { background-color: #2f4458; }
        """)
        dialog.exec()

    def apply_gateway_port_from_settings(self, port_text: str):
        try:
            port = int(str(port_text).strip())
        except (TypeError, ValueError):
            self._show_themed_warning(self._t('settings_port_invalid_title'), self._t('settings_port_invalid_body'))
            return
        if not 1 <= port <= 65535:
            self._show_themed_warning(self._t('settings_port_invalid_title'), self._t('settings_port_invalid_body'))
            return

        self._config['gateway_port'] = port
        save_app_config(self._config)
        self.gateway_manager.set_port(port)
        if hasattr(self, 'browser_page'):
            self.browser_page.set_port(port)
        self._refresh_port_label()
        if self._settings_dialog is not None:
            self._settings_dialog.refresh_texts()

        if not self._openclaw_available:
            self.status_bar.setText(self._t('settings_port_saved_only'))
            return

        if self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING, GatewayStatus.ERROR):
            self._restart_gateway()
        else:
            self._start_gateway()

    def set_expose_mode(self, enabled: bool):
        enabled = bool(enabled)
        if enabled == getattr(self, '_expose_mode', False):
            return
        self._expose_mode = enabled
        self._config['expose_mode'] = enabled
        save_app_config(self._config)
        if hasattr(self, 'browser_page'):
            self.browser_page.set_expose_mode(enabled)
        self._update_header_buttons()
        if self._settings_dialog is not None:
            self._settings_dialog.refresh_texts()

    def _apply_translations(self):
        self.setWindowTitle(self._t("app_title"))
        if hasattr(self, 'header_title_label'):
            self.header_title_label.setText(self._t("app_title"))
            self.header_welcome_btn.setText(self._t("nav_welcome"))
            self.header_start_btn.setText(self._t("nav_start"))
            self.header_stop_btn.setText(self._t("nav_stop"))
            self.header_restart_btn.setText(self._t("nav_restart"))
            self.header_dashboard_btn.setText(self._t("nav_dashboard"))
            self.header_plugins_btn.setText(self._t("nav_plugins"))
            self.header_error_btn.setText(self._t("nav_error_info"))
            self.header_get_more_btn.setText(self._t("nav_get_more"))
            self.header_settings_btn.setText(self._t("nav_settings"))
        if hasattr(self, 'header_status_label'):
            self.header_status_label.setText(self._t("label_status"))
        if hasattr(self, 'status_indicator'):
            self.status_indicator.set_status(self._ui_status, self._language)
        if hasattr(self, 'status_bar'):
            self.status_bar.setText(self._t("footer_ready"))
        if hasattr(self, 'welcome_instructions_label'):
            self.welcome_instructions_label.setText(self._t("welcome_quick_start_html"))
        if self._openclaw_available:
            self._apply_openclaw_available_welcome_state()
        else:
            self._apply_openclaw_missing_state()
        if self._plugin_dialog is not None:
            self._plugin_dialog.refresh_texts()
        self._refresh_plugins_page_texts()
        if self._settings_dialog is not None:
            self._settings_dialog.refresh_texts()
        self._update_header_buttons()
        if hasattr(self, 'port_toggle_btn'):
            self._refresh_port_label()

    def _apply_openclaw_missing_state(self):
        self._set_current_page(self.PAGE_WELCOME)
        self._set_ui_status(GatewayStatus.ERROR, self._t("message_missing_openclaw_status"))
        self._hide_error_card()
        self.welcome_message_label.setText(self._t("missing_title"))
        self.welcome_message_label.setStyleSheet("color: #c0392b; margin: 20px; font-size: 20px; font-weight: bold;")
        self.welcome_desc_label.hide()
        self.welcome_hint_label.hide()
        self.welcome_instructions_label.hide()
        self.welcome_links_label.setText(
            "<a href='https://github.com/openclaw/openclaw'>https://github.com/openclaw/openclaw</a><br>"
            "<a href='https://docs.openclaw.ai/'>https://docs.openclaw.ai/</a>"
        )
        self.welcome_links_label.show()

    def _apply_openclaw_available_welcome_state(self):
        self.welcome_message_label.setText(self._t("welcome_title"))
        self.welcome_message_label.setStyleSheet("color: #2c3e50; margin: 20px;")
        self.welcome_desc_label.setText(self._t("welcome_desc"))
        self.welcome_desc_label.show()
        self.welcome_hint_label.setText(self._t("welcome_hint"))
        self.welcome_hint_label.show()
        self.welcome_instructions_label.show()
        self.welcome_links_label.hide()

    def _setup_ui(self):
        self.setWindowTitle(self._t("app_title"))
        self.setMinimumSize(1000, 700)
        self.resize(*self._saved_window_size)
        self._window_size_ready = True

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setSpacing(5)
        main_layout.setContentsMargins(15, 10, 15, 10)

        header = self._create_header()
        main_layout.addWidget(header, 0)

        self.content_stack = QStackedWidget()               # switches between welcome and browser pages

        self.welcome_page = self._create_welcome_page()     # landing page shown before browser view
        self.content_stack.addWidget(self.welcome_page)

        self.error_info_page = self._create_error_info_page()  # page showing gateway errors and diagnostics
        self.content_stack.addWidget(self.error_info_page)

        self.plugins_page = self._create_plugins_page()     # page showing parsed plugin rows
        self.content_stack.addWidget(self.plugins_page)

        self.browser_page = BrowserView(port=self.gateway_manager.port)         # embedded dashboard browser page
        self.browser_page.set_expose_mode(self._expose_mode)
        self.browser_page.page_load_started.connect(self._on_page_load_started)
        self.browser_page.page_load_finished.connect(self._on_page_load_finished)
        self.content_stack.addWidget(self.browser_page)

        main_layout.addWidget(self.content_stack, 1)

        self.status_bar = QLabel(self._t("footer_ready"))                   # footer status message label
        self.status_bar.setStyleSheet("color: #666; padding: 5px; border-top: 1px solid #ddd;")
        self.status_bar.setFixedHeight(30)
        main_layout.addWidget(self.status_bar)

    def _on_page_load_started(self):
        if not self._openclaw_available:
            return
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING and self._dashboard_navigation_pending:
            self._set_ui_status(GatewayStatus.LOADING, self._t("message_dashboard_loading"))

    def _on_page_load_finished(self, ok: bool):
        if not self._openclaw_available:
            return
        if not self._dashboard_navigation_pending:
            return
        self._dashboard_navigation_pending = False
        if ok:
            self._set_ui_status(GatewayStatus.RUNNING, self._t("message_dashboard_loaded"))
        else:
            self._set_ui_status(GatewayStatus.ERROR, self._t("message_dashboard_failed"))
            self._show_gateway_error_card(
                self._t("error_dashboard_title"),
                self._t("message_dashboard_failed"),
            )

    def _create_header(self):
        header = QFrame()
        header.setStyleSheet("""
            QFrame {
                background-color: #2c3e50;
                border-radius: 8px;
            }
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 15, 20, 15)

        title = QLabel("OpenClaw Desktop🦞")
        title_font = QFont('Microsoft YaHei UI')
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: white;")
        self.header_title_label = title
        layout.addWidget(title)

        layout.addStretch()

        self.header_welcome_btn = self._create_header_button("Welcome", 90, self._open_welcome_page)
        self.header_start_btn = self._create_header_button("Start", 85, self._start_gateway)
        self.header_stop_btn = self._create_header_button("Stop", 85, self._stop_gateway)
        self.header_restart_btn = self._create_header_button("Restart", 90, self._restart_gateway)
        self.header_dashboard_btn = self._create_header_button("Dashboard", 110, self._open_dashboard)
        self.header_dashboard_btn.setEnabled(False)
        self.header_plugins_btn = self._create_header_button("Plugins", 100, self._open_plugins_page)
        self.header_plugins_btn.hide()
        self.header_error_btn = self._create_header_button("Error Info", 110, self._open_error_info_page)
        self.header_error_btn.hide()
        self.header_get_more_btn = self._create_header_button("Get More", 100, self._open_plugin_dialog)
        self.header_get_more_btn.hide()
        self.header_settings_btn = self._create_header_button("Settings", 100, self._open_settings_dialog)
        self.header_settings_btn.hide()

        for button in (
            self.header_welcome_btn,
            self.header_start_btn,
            self.header_stop_btn,
            self.header_restart_btn,
            self.header_dashboard_btn,
            self.header_plugins_btn,
            self.header_error_btn,
            self.header_get_more_btn,
            self.header_settings_btn,
        ):
            layout.addWidget(button)

        layout.addSpacing(20)

        status_label = QLabel(self._t("label_status"))
        status_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        self.header_status_label = status_label
        layout.addWidget(status_label)

        self.status_indicator = StatusIndicator()               # pill showing current gateway state
        layout.addWidget(self.status_indicator)

        self.port_toggle_btn = PortToggleButton(self.gateway_manager.port)
        self.port_toggle_btn.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                font-size: 11px;
                margin-left: 10px;
                padding: 0;
            }
        """)
        self.port_toggle_btn.clicked.connect(self._toggle_port_visibility)
        self._refresh_port_label()
        layout.addWidget(self.port_toggle_btn)

        return header

    def _refresh_port_label(self):
        self.port_toggle_btn.set_prefix_text(self._t("label_port"))
        self.port_toggle_btn.set_port(self.gateway_manager.port)
        self.port_toggle_btn.set_port_visible(getattr(self, "_port_visible", False))

    def _toggle_port_visibility(self):
        self._port_visible = not self._port_visible
        self._refresh_port_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_error_output()
        self._persist_window_size()

    def _create_welcome_page(self):
        icon_label = RotatingEmojiLabel("🦞")
        icon_font = QFont()
        icon_font.setPointSize(72)
        icon_font.setBold(True)
        icon_label.setFont(icon_font)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.set_text_color("#3498db")
        icon_label.setFixedSize(140, 140)
        self.welcome_icon = icon_label                          # lobster icon shown on the welcome page

        page = WelcomePage(icon_label)

        content = QWidget()
        content.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 0)

        self.welcome_message_label = self._create_welcome_label(
            "Welcome to OpenClaw Desktop",
            "color: #2c3e50; margin: 20px;",
            point_size=16,
            bold=True,
        )
        layout.addWidget(self.welcome_message_label)

        self.welcome_desc_label = self._create_welcome_label(
            "Start the gateway to access the OpenClaw dashboard",
            "color: #7f8c8d; font-size: 14px;",
        )
        layout.addWidget(self.welcome_desc_label)

        self.welcome_hint_label = self._create_welcome_label(
            "Click anywhere with your mouse to guide the lobster around.",
            "color: #5d6d7e; font-size: 13px; margin-top: 8px;",
        )
        layout.addWidget(self.welcome_hint_label)

        instructions = QLabel("""
            <p style='color: #666; margin-top: 30px;'>
            <b>Quick Start:</b><br>
            1. Click <b>Start</b> in the header to launch the gateway<br>
            2. Wait for the status to show <b>Running</b><br>
            3. Click <b>Dashboard</b> to access the web interface
            </p>
        """)
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet("font-size: 13px;")
        instructions.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.welcome_instructions_label = instructions          # quick-start instructions block
        layout.addWidget(instructions)

        links = QLabel("")
        links.setAlignment(Qt.AlignmentFlag.AlignCenter)
        links.setOpenExternalLinks(True)
        links.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        links.setStyleSheet("font-size: 14px; color: #c0392b; margin-top: 10px;")
        links.hide()
        self.welcome_links_label = links                        # install/help links shown when openclaw is missing
        layout.addWidget(links)

        page.set_text_content(content)
        return page

    def _create_welcome_label(
        self,
        text: str,
        style: str,
        *,
        point_size: int | None = None,
        bold: bool = False,
    ) -> QLabel:
        """Build a centered welcome-page label with mouse-transparent text."""
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet(style)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        if point_size is not None or bold:
            font = QFont('Microsoft YaHei UI')
            if point_size is not None:
                font.setPointSize(point_size)
            font.setBold(bold)
            label.setFont(font)
        return label

    def _create_error_info_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        error_card = QFrame()
        error_card.setObjectName("errorInfoCard")
        error_card.setMinimumWidth(630)
        error_card.setMaximumWidth(1140)
        error_card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        error_card.setStyleSheet("""
            QFrame#errorInfoCard {
                background-color: #fff4f4;
                border: 1px solid #f3c5c5;
                border-radius: 16px;
            }
        """)
        error_layout = QVBoxLayout(error_card)
        error_layout.setContentsMargins(0, 0, 0, 18)
        error_layout.setSpacing(8)
        error_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        title_bar = QFrame()
        title_bar.setObjectName("errorInfoTitleBar")
        title_bar.setFixedHeight(46)
        title_bar.setStyleSheet("""
            QFrame#errorInfoTitleBar {
                background-color: #fff0f0;
                border: none;
                border-top-left-radius: 16px;
                border-top-right-radius: 16px;
            }
        """)
        title_bar_layout = QHBoxLayout(title_bar)
        title_bar_layout.setContentsMargins(18, 0, 18, 0)

        error_title = QLabel(self._t("error_gateway_title"))
        error_title.setStyleSheet(
            "color: #b42318; font-size: 16px; font-weight: bold; border: none; background: transparent;"
        )
        self.error_title_label = error_title
        title_bar_layout.addWidget(error_title, 0, Qt.AlignmentFlag.AlignVCenter)
        title_bar_layout.addStretch()
        error_layout.addWidget(title_bar)

        content_wrap = QWidget()
        content_wrap.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        content_layout = QVBoxLayout(content_wrap)
        content_layout.setContentsMargins(18, 8, 18, 0)
        content_layout.setSpacing(8)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)

        error_summary = QLabel("")
        error_summary.hide()
        error_summary.setWordWrap(True)
        error_summary.setTextFormat(Qt.TextFormat.RichText)
        error_summary.setStyleSheet("""
            QLabel {
                background-color: #fffafa;
                color: #7a1f1f;
                border: 1px solid #f0d6d6;
                border-radius: 12px;
                padding: 10px 12px;
                font-size: 12px;
                line-height: 1.35;
            }
        """)
        self.error_summary_label = error_summary
        error_summary.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        content_layout.addWidget(error_summary)

        error_output = QPlainTextEdit()
        error_output.setReadOnly(True)
        error_output.setMinimumHeight(120)
        error_output.setStyleSheet("""
            QPlainTextEdit {
                background-color: #fffafa;
                color: #7a1f1f;
                border: 1px solid #d4dce5;
                border-radius: 12px;
                padding: 10px;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12px;
            }
        """)
        error_output.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        error_output.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        error_output.setVerticalScrollBar(ChromeScrollBar(Qt.Orientation.Vertical, error_output))
        error_output.setHorizontalScrollBar(ChromeScrollBar(Qt.Orientation.Horizontal, error_output))
        self.error_output = error_output
        content_layout.addWidget(error_output)
        error_layout.addWidget(content_wrap)

        layout.addWidget(error_card, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
        self.error_info_card = error_card
        self.error_info_content_wrap = content_wrap
        return page

    def _create_plugins_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 16)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        card = QFrame()
        card.setObjectName("pluginsPageCard")
        card.setMinimumWidth(720)
        card.setMaximumWidth(1180)
        card.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        card.setStyleSheet("""
            QFrame#pluginsPageCard {
                background-color: #f5f7fa;
                border: 1px solid #d4dce5;
                border-radius: 16px;
            }
            QLabel#pluginsPageTitle {
                color: #2f3a46;
                font-size: 16px;
                font-weight: 700;
            }
            QLabel#pluginsPageHint {
                color: #5b6875;
                font-size: 12px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(18, 18, 18, 18)
        card_layout.setSpacing(12)

        header_row = QHBoxLayout()
        self.plugins_page_title_label = QLabel()
        self.plugins_page_title_label.setObjectName('pluginsPageTitle')
        header_row.addWidget(self.plugins_page_title_label)
        header_row.addStretch()
        self.plugins_page_refresh_btn = QPushButton()
        self.plugins_page_refresh_btn.setObjectName('dialogPrimaryButton')
        self.plugins_page_refresh_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: 1px solid #465669;
                border-radius: 8px;
                padding: 8px 14px;
                font-size: 12px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #465669; }
            QPushButton:pressed { background-color: #2c3e50; }
            QPushButton:disabled { background-color: #c7cfd8; color: #7b8794; border-color: #c7cfd8; }
        """)
        self.plugins_page_refresh_btn.clicked.connect(lambda: self._load_plugins_page_data(force=True))
        header_row.addWidget(self.plugins_page_refresh_btn)

        self.plugins_page_add_btn = QPushButton()
        self.plugins_page_add_btn.setObjectName('dialogPrimaryButton')
        refresh_height = self.plugins_page_refresh_btn.sizeHint().height()
        self.plugins_page_add_btn.setFixedSize(refresh_height, refresh_height)
        self.plugins_page_add_btn.setStyleSheet("""
            QPushButton {
                background-color: #34495e;
                color: white;
                border: 1px solid #465669;
                border-radius: 8px;
                padding: 0;
            }
            QPushButton:hover { background-color: #465669; }
            QPushButton:pressed { background-color: #2c3e50; }
        """)
        add_icon_path = resource_base_dir() / 'assets' / 'add.png'
        if add_icon_path.exists():
            self.plugins_page_add_btn.setIcon(QIcon(str(add_icon_path)))
            self.plugins_page_add_btn.setIconSize(QSize(16, 16))
        self.plugins_page_add_btn.clicked.connect(self._open_get_more_plugins)
        header_row.addWidget(self.plugins_page_add_btn)
        card_layout.addLayout(header_row)

        self.plugins_page_hint_label = QLabel()
        self.plugins_page_hint_label.setObjectName('pluginsPageHint')
        self.plugins_page_hint_label.setWordWrap(True)
        card_layout.addWidget(self.plugins_page_hint_label)

        self.plugins_page_scroll = QScrollArea()
        self.plugins_page_scroll.setWidgetResizable(True)
        self.plugins_page_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.plugins_page_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.plugins_page_scroll.setStyleSheet('QScrollArea { border: none; background: transparent; }')

        self.plugins_page_host = QWidget()
        self.plugins_page_list_layout = QVBoxLayout(self.plugins_page_host)
        self.plugins_page_list_layout.setContentsMargins(0, 0, 0, 0)
        self.plugins_page_list_layout.setSpacing(10)
        self.plugins_page_list_layout.addStretch()
        self.plugins_page_scroll.setWidget(self.plugins_page_host)
        card_layout.addWidget(self.plugins_page_scroll, 1)

        layout.addWidget(card, 1)
        return page

    def _clear_plugins_page_rows(self):
        self._plugin_row_widgets = {}
        while self.plugins_page_list_layout.count() > 1:
            item = self.plugins_page_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _plugin_row_enabled(self, plugin: dict[str, str]) -> bool:
        return plugin.get('status', '').strip().lower() in {'loaded', 'enabled', 'active'}

    def _merge_wrapped_identifier(self, value: str) -> str:
        """Undo line-wrap artifacts for identifiers without breaking natural spaces."""
        merged = value.strip()
        merged = merged.replace('/ ', '/')
        merged = merged.replace('- ', '-')
        return merged

    def _split_plugin_source(self, source: str) -> tuple[str, str]:
        """Split `stock:path description...` into a path token and a human description."""
        cleaned = source.strip()
        if not cleaned:
            return '', ''
        head, sep, tail = cleaned.partition(' ')
        if ':' in head:
            prefix, remainder = head.split(':', 1)
            if prefix in {'stock', 'global'} and remainder:
                head = remainder
        return head, tail.strip() if sep else ''

    def _plugin_name_width(self, text: str, font: QFont) -> int:
        metrics = QFontMetrics(font)
        extra = metrics.horizontalAdvance('M' * 5)
        return min(max(metrics.horizontalAdvance(text) + extra, 80), 440)

    def _save_plugins_rows(self):
        save_plugins_cache(self._plugins_rows)

    def _open_plugin_toggle_dialog(self, plugin_id: str):
        plugin = next((row for row in self._plugins_rows if row.get('id', '').strip() == plugin_id), None)
        if not plugin:
            return
        dialog = PluginToggleDialog(self.gateway_manager, plugin, self._plugin_row_enabled(plugin), self)
        dialog.action_completed.connect(self._handle_plugin_toggle_completed)
        dialog.exec()

    def _handle_plugin_switch_clicked(self, plugin_id: str):
        plugin = next((row for row in self._plugins_rows if row.get('id', '').strip() == plugin_id), None)
        widgets = self._plugin_row_widgets.get(plugin_id)
        if widgets and plugin is not None:
            widgets['status_switch'].blockSignals(True)
            widgets['status_switch'].setChecked(self._plugin_row_enabled(plugin))
            widgets['status_switch'].blockSignals(False)
        self._open_plugin_toggle_dialog(plugin_id)

    def _handle_plugin_toggle_completed(self, plugin_id: str, enabled: bool):
        self._update_plugin_row_status(plugin_id, enabled)

    def _update_plugin_row_status(self, plugin_id: str, enabled: bool):
        for plugin in self._plugins_rows:
            if plugin.get('id', '').strip() == plugin_id:
                plugin['status'] = 'enabled' if enabled else 'disabled'
                break
        widgets = self._plugin_row_widgets.get(plugin_id)
        status_text = self._t('plugins_status_enabled') if enabled else self._t('plugins_status_disabled')
        dot_color = '#22c55e' if enabled else '#ef4444'
        if widgets:
            widgets['dot'].setStyleSheet(f'background-color: {dot_color}; border: none; border-radius: 5px;')
            widgets['dot'].setToolTip(status_text)
            widgets['status_button'].setText(status_text)
            widgets['status_switch'].blockSignals(True)
            widgets['status_switch'].setChecked(enabled)
            widgets['status_switch'].blockSignals(False)
        self._save_plugins_rows()

    def _add_plugins_page_row(self, plugin: dict[str, str]):
        enabled = self._plugin_row_enabled(plugin)
        dot_color = '#22c55e' if enabled else '#ef4444'
        status_text = self._t('plugins_status_enabled') if enabled else self._t('plugins_status_disabled')
        plugin_name = self._merge_wrapped_identifier(plugin.get('name', plugin.get('id', '')))
        plugin_id = self._merge_wrapped_identifier(plugin.get('id', ''))
        source_path, source_description = self._split_plugin_source(plugin.get('source', ''))

        row = QFrame()
        row.setObjectName('pluginRow')
        row.setStyleSheet("""
            QFrame#pluginRow {
                background-color: #ffffff;
                border: 1px solid #d6dde5;
                border-radius: 26px;
            }
            QLabel#pluginName {
                color: #2f3a46;
                font-size: 14px;
                font-weight: 700;
                border: none;
                background: transparent;
            }
            QLabel#pluginMeta {
                color: #607080;
                font-size: 11px;
                border: none;
                background: transparent;
            }
            QLabel#pluginSourcePath {
                color: #607080;
                font-size: 11px;
                border: none;
                background: transparent;
            }
            QLabel#pluginSource {
                color: #475467;
                font-size: 12px;
                border: none;
                background: transparent;
            }
            QPushButton#pluginStatusButton {
                color: #607080;
                font-size: 11px;
                font-weight: 600;
                border: none;
                background: transparent;
                padding: 0;
            }
            QPushButton#pluginStatusButton:hover { color: #2f3a46; }
        """)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(26, 12, 16, 12)
        row_layout.setSpacing(14)

        dot_holder = QWidget()
        dot_holder.setFixedWidth(18)
        dot_layout = QHBoxLayout(dot_holder)
        dot_layout.setContentsMargins(2, 0, 6, 0)
        dot_layout.setSpacing(0)
        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f'background-color: {dot_color}; border: none; border-radius: 5px;')
        dot.setToolTip(status_text)
        dot_layout.addWidget(dot, 0, Qt.AlignmentFlag.AlignCenter)
        row_layout.addWidget(dot_holder, 0, Qt.AlignmentFlag.AlignVCenter)

        text_col = QVBoxLayout()
        text_col.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(0)
        top_row.setContentsMargins(0, 0, 0, 0)
        name_label = QLabel(plugin_name)
        name_label.setObjectName('pluginName')
        name_label.setWordWrap(False)
        name_label.setFixedWidth(self._plugin_name_width(plugin_name, name_label.font()))
        top_row.addWidget(name_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        source_path_label = QLabel(source_path)
        source_path_label.setObjectName('pluginSourcePath')
        source_path_label.setWordWrap(False)
        top_row.addWidget(source_path_label, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        top_row.addStretch()
        text_col.addLayout(top_row)

        source_label = QLabel(source_description)
        source_label.setObjectName('pluginSource')
        source_label.setWordWrap(True)
        text_col.addWidget(source_label)
        row_layout.addLayout(text_col, 1)

        meta_parts = [part for part in (plugin_id, plugin.get('version', '')) if part]
        meta_label = QLabel(('  -  ').join(meta_parts))
        meta_label.setObjectName('pluginMeta')
        meta_label.setWordWrap(False)
        meta_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        meta_label.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Preferred)
        row_layout.addWidget(meta_label, 0, Qt.AlignmentFlag.AlignVCenter)

        status_col = QVBoxLayout()
        status_col.setSpacing(6)
        status_col.setContentsMargins(12, 0, 2, 0)
        status_col.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter)
        status_switch = ActionPillSwitch()
        status_switch.setChecked(enabled)
        status_switch.actionRequested.connect(lambda pid=plugin_id: self._handle_plugin_switch_clicked(pid))
        status_button = QPushButton(status_text)
        status_button.setObjectName('pluginStatusButton')
        status_button.setCursor(Qt.CursorShape.PointingHandCursor)
        status_button.clicked.connect(lambda _checked=False, pid=plugin_id: self._open_plugin_toggle_dialog(pid))
        status_col.addWidget(status_switch, 0, Qt.AlignmentFlag.AlignHCenter)
        status_col.addWidget(status_button, 0, Qt.AlignmentFlag.AlignHCenter)
        row_layout.addLayout(status_col, 0)

        self._plugin_row_widgets[plugin_id] = {
            'row': row,
            'dot': dot,
            'status_button': status_button,
            'status_switch': status_switch,
        }
        self.plugins_page_list_layout.insertWidget(self.plugins_page_list_layout.count() - 1, row)

    def _populate_plugins_page(self):
        if not hasattr(self, 'plugins_page_list_layout'):
            return
        self._clear_plugins_page_rows()
        if self._plugins_load_ok is True and self._plugins_rows:
            for plugin in self._plugins_rows:
                self._add_plugins_page_row(plugin)
            enabled_count = sum(1 for plugin in self._plugins_rows if self._plugin_row_enabled(plugin))
            disabled_count = len(self._plugins_rows) - enabled_count
            self.plugins_page_hint_label.setText(
                self._t('plugins_count_summary').format(
                    count=len(self._plugins_rows),
                    enabled=enabled_count,
                    disabled=disabled_count,
                )
            )
            return
        if self._plugins_load_ok is True:
            self.plugins_page_hint_label.setText(self._t('plugins_empty'))
            return
        if self._plugins_load_ok is False:
            self.plugins_page_hint_label.setText(self._t('plugins_failed'))
            row = QFrame()
            row.setStyleSheet('QFrame { background-color: #ffffff; border: 1px solid #d6dde5; border-radius: 14px; }')
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(16, 12, 16, 12)
            output = QPlainTextEdit()
            output.setReadOnly(True)
            output.setPlainText((self._plugins_output_text or self._t('plugins_failed')).strip())
            output.setMaximumHeight(220)
            output.setStyleSheet("QPlainTextEdit { background: transparent; color: #7a1f1f; border: none; font-family: Consolas, 'Courier New', monospace; font-size: 12px; }")
            row_layout.addWidget(output)
            self.plugins_page_list_layout.insertWidget(self.plugins_page_list_layout.count() - 1, row)
            return
        self.plugins_page_hint_label.setText(self._t('plugins_loading'))

    def _refresh_plugins_page_texts(self):
        if not hasattr(self, 'plugins_page_title_label'):
            return
        self.plugins_page_title_label.setText(self._t('plugins_dialog_title'))
        self.plugins_page_refresh_btn.setText(self._t('plugins_refresh'))
        self.plugins_page_add_btn.setToolTip(self._t('plugins_add_tooltip'))
        self._populate_plugins_page()

    def _load_plugins_page_data(self, force: bool = False):
        if not self._openclaw_available:
            return
        if self._plugins_load_thread is not None and self._plugins_load_thread.isRunning():
            return
        if self._plugins_load_ok is True and self._plugins_rows and not force:
            return
        self._plugins_load_ok = None
        self._plugins_output_text = ''
        self._populate_plugins_page()
        self.plugins_page_refresh_btn.setEnabled(False)
        self._plugins_load_thread = PluginListThread(self.gateway_manager)
        self._plugins_load_thread.finished_with_result.connect(self._finish_plugins_page_loading)
        self._plugins_load_thread.start()

    def _finish_plugins_page_loading(self, ok: bool, rows: object, output_text: str):
        self.plugins_page_refresh_btn.setEnabled(True)
        self._plugins_load_thread = None
        self._plugins_output_text = output_text or ''
        self._plugins_rows = rows if isinstance(rows, list) else []
        self._plugins_load_ok = ok and bool(self._plugins_rows)
        if ok and self._plugins_rows:
            self._save_plugins_rows()
        if ok and not self._plugins_rows and any(marker in self._plugins_output_text for marker in ('| Name', '│ Name')):
            self._plugins_load_ok = False
        self._populate_plugins_page()

    def _persist_window_size(self):
        """Store the current main-window size in config.json."""
        if not getattr(self, '_window_size_ready', False):
            return
        width = max(self.minimumWidth(), self.width())
        height = max(self.minimumHeight(), self.height())
        saved = self._config.get('window_size')
        if isinstance(saved, dict) and saved.get('width') == width and saved.get('height') == height:
            return
        self._config['window_size'] = {'width': width, 'height': height}
        save_app_config(self._config)

    def _create_header_button(self, text: str, width: int, handler) -> QPushButton:
        """Create a header button with the shared navigation style."""
        button = QPushButton(text)
        button.setFixedSize(width, 30)
        button.setStyleSheet(self.HEADER_BUTTON_STYLE)
        button.clicked.connect(handler)
        return button

    def _apply_styles(self):
        self.setStyleSheet("""
            QMainWindow {
                background-color: #ecf0f1;
                font-family: 'Microsoft YaHei UI', 'Microsoft YaHei';
            }
            QWidget {
                font-family: 'Microsoft YaHei UI', 'Microsoft YaHei';
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-family: 'Microsoft YaHei UI', 'Microsoft YaHei';
                font-size: 13px;
                font-weight: 700;
            }
            QPushButton:hover {
                background-color: #2980b9;
            }
            QPushButton:pressed {
                background-color: #21618c;
            }
            QPushButton:disabled {
                background-color: #bdc3c7;
                color: #7f8c8d;
            }
            QPushButton#danger {
                background-color: #e74c3c;
            }
            QPushButton#danger:hover {
                background-color: #c0392b;
            }
        """)

    def _on_status_changed(self, status: GatewayStatus):
        if not self._openclaw_available:
            self._apply_openclaw_missing_state()
            return
        self._apply_openclaw_available_welcome_state()
        if status == GatewayStatus.STOPPED:
            self._reset_dashboard_navigation()
            if self._error_info_sticky:
                self._set_ui_status(GatewayStatus.ERROR, self._t("message_gateway_error"))
                self._set_current_page(self.PAGE_ERROR)
            else:
                self._set_ui_status(GatewayStatus.STOPPED, self._t("message_gateway_stopped"))
                if self.content_stack.currentIndex() == self.PAGE_ERROR:
                    self._set_current_page(self.PAGE_WELCOME)
        elif status == GatewayStatus.STARTING:
            self._reset_dashboard_navigation()
            self._set_ui_status(GatewayStatus.STARTING, self._t("message_starting_gateway"))
            if self._error_info_sticky:
                self._set_current_page(self.PAGE_ERROR)
        elif status == GatewayStatus.STOPPING:
            self._reset_dashboard_navigation()
            self._set_ui_status(GatewayStatus.STOPPING, self._t("message_stopping_gateway"))
            if self._error_info_sticky:
                self._set_current_page(self.PAGE_ERROR)
        elif status == GatewayStatus.ERROR:
            self._reset_dashboard_navigation()
            self._error_info_sticky = True
            self._set_current_page(self.PAGE_ERROR)
            self._set_ui_status(GatewayStatus.ERROR, self._t("message_gateway_error"))
            self._show_gateway_error_card(self._t("error_gateway_title"))
        elif status == GatewayStatus.RUNNING:
            self._error_info_sticky = False
            self._hide_error_card()
            if self.content_stack.currentIndex() in (self.PAGE_WELCOME, self.PAGE_ERROR) and not self._dashboard_open_scheduled:
                self._dashboard_open_scheduled = True
                self._set_ui_status(GatewayStatus.LOADING, self._t("message_dashboard_loading"))
                QTimer.singleShot(1000, self._open_dashboard)

    def _on_log_message(self, message: str):
        self.status_bar.setText(message)

    def _on_gateway_process_output(self, stream_name: str, message: str):
        if stream_name != "stderr" or not message.strip():
            return
        if self._ui_status == GatewayStatus.ERROR:
            self._show_gateway_error_card(self._t("error_gateway_title"))

    def _show_gateway_error_card(self, title: str, fallback_message: str = ""):
        self._error_info_sticky = True
        details = self.gateway_manager.get_recent_stderr_text()
        if not details:
            details = fallback_message or self._t("error_no_output")
        self.error_title_label.setText(title)
        self.error_summary_label.setText(self._build_error_summary_html(details))
        self.error_summary_label.show()
        self.error_output.setPlainText(details)
        self._resize_error_output()
        self._set_current_page(self.PAGE_ERROR)

    def _hide_error_card(self):
        if hasattr(self, "error_summary_label"):
            self.error_summary_label.clear()
            self.error_summary_label.hide()
        if hasattr(self, "error_output"):
            self.error_output.clear()

    def _build_error_summary_html(self, details: str) -> str:
        def normalize_summary_line(line: str) -> str:
            cleaned = line.strip()
            if cleaned.startswith("- "):
                cleaned = cleaned[2:].strip()
            return cleaned

        lines = [normalize_summary_line(line) for line in details.splitlines() if line.strip()]
        headline = lines[0] if lines else self._t("error_gateway_reported")

        priority_patterns = (
            "SyntaxError",
            "Error:",
            "Problem:",
            "File:",
            "Run:",
            "failed",
            "invalid",
        )
        picked = []
        for pattern in priority_patterns:
            match = next((line for line in lines if pattern.lower() in line.lower()), None)
            if match and match not in picked and match != headline:
                picked.append(match)
            if len(picked) >= 3:
                break

        summary_lines = [headline, *picked]
        escaped = [
            line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            for line in summary_lines
        ]
        items = "".join(
            f"<div style='margin:0; padding:0;'>• {line}</div>" for line in escaped
        )
        return (
            "<div>"
            "<div style='font-weight:700; margin-bottom:6px;'>Summary</div>"
            "<div style='margin:0; padding:0;'>"
            f"{items}"
            "</div>"
            "</div>"
        )

    def _resize_error_output(self):
        if not hasattr(self, "error_output") or not hasattr(self, "error_summary_label"):
            return

        content_width = max(240, self.error_info_card.width() - 36) if hasattr(self, "error_info_card") else 600
        summary_doc = QTextDocument()
        summary_doc.setDefaultFont(self.error_summary_label.font())
        summary_doc.setHtml(self.error_summary_label.text() or "")
        summary_doc.setTextWidth(max(200, content_width - 28))
        summary_height = int(summary_doc.size().height()) + 24
        if self.error_summary_label.isVisible():
            self.error_summary_label.setFixedHeight(max(52, summary_height))

        document = self.error_output.document()
        block_count = max(1, document.blockCount())
        line_height = self.error_output.fontMetrics().lineSpacing()
        content_height = block_count * line_height + 34

        page_height = self.error_info_page.height() if hasattr(self, "error_info_page") else self.height()
        header_height = self.error_title_label.parentWidget().height()
        layout_overhead = 16 + 18 + 18 + 18 + 8 + 8 + 8
        summary_block_height = self.error_summary_label.height() if self.error_summary_label.isVisible() else 0
        max_height = max(120, page_height - header_height - layout_overhead - summary_block_height)
        self.error_output.setFixedHeight(max(120, min(max_height, content_height)))
        if hasattr(self, "error_info_content_wrap"):
            self.error_info_content_wrap.adjustSize()
        if hasattr(self, "error_info_card"):
            self.error_info_card.adjustSize()
            if self.error_info_card.layout() is not None:
                self.error_info_card.layout().activate()

    def _start_gateway(self):
        self._run_gateway_action("start")

    def _stop_gateway(self):
        self._run_gateway_action("stop")

    def _restart_gateway(self):
        self._run_gateway_action("restart")

    def _open_welcome_page(self):
        self._reset_dashboard_navigation()
        self._set_current_page(self.PAGE_WELCOME)

    def _open_error_info_page(self):
        self._reset_dashboard_navigation()
        self._set_current_page(self.PAGE_ERROR)

    def _open_plugin_dialog(self):
        if self._plugin_dialog is None:
            self._plugin_dialog = PluginInstallDialog(self.gateway_manager, self)
        self._plugin_dialog.show()
        self._plugin_dialog.raise_()
        self._plugin_dialog.activateWindow()

    def _open_get_more_plugins(self):
        self._open_plugin_dialog()
        if self._plugin_dialog is not None:
            self._plugin_dialog.open_plugins_page()

    def _open_plugins_page(self):
        self._reset_dashboard_navigation()
        self._set_current_page(self.PAGE_PLUGINS)
        if self._plugins_load_ok is None and (self._plugins_load_thread is None or not self._plugins_load_thread.isRunning()):
            self._load_plugins_page_data(force=False)

    def _open_settings_dialog(self):
        if self._settings_dialog is None:
            self._settings_dialog = SettingsDialog(self)
        self._settings_dialog.show()
        self._settings_dialog.raise_()
        self._settings_dialog.activateWindow()

    def _open_clawhub_market(self):
        self._reset_dashboard_navigation()
        self._set_current_page(self.PAGE_BROWSER)
        if hasattr(self, 'browser_page'):
            self.browser_page.navigate_to("https://clawhub.ai/")

    def _on_gateway_action_finished(self, action: str, ok: bool):
        if action == "stop":
            self._hide_error_card()
            self._set_ui_status(GatewayStatus.STOPPED, self._t("message_gateway_stopped"))
            self._set_current_page(self.PAGE_WELCOME)
            return

        if not ok:
            self._set_ui_status(GatewayStatus.ERROR, f"{action.capitalize()} failed")
            return

        if action in ("start", "restart"):
            opened = self._open_dashboard()
            if not opened:
                self._set_ui_status(GatewayStatus.RUNNING, self._t("message_dashboard_ready"))

    def _open_dashboard(self):
        if not self._openclaw_available:
            self._apply_openclaw_missing_state()
            return False
        self._dashboard_open_scheduled = False
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING:
            if self.content_stack.currentIndex() == self.PAGE_BROWSER:
                return False
            self._dashboard_navigation_pending = True
            self._set_ui_status(GatewayStatus.LOADING, self._t("message_dashboard_loading"))
            self._set_current_page(self.PAGE_BROWSER)
            self.browser_page.open_home()
            return True

        QMessageBox.warning(
            self,
            self._t("warning_gateway_not_running_title"),
            self._t("warning_gateway_not_running_body")
        )
        return False

    def closeEvent(self, event):
        """Handle window close event - ask user what to do"""
        reply = show_exit_dialog(self, include_cancel=True)

        if reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return

        if reply == QMessageBox.StandardButton.Yes:
            self.gateway_manager.stop()

        self._persist_window_size()
        self.gateway_manager.cleanup()
        event.accept()

    def cleanup(self):
        self._persist_window_size()
        self.gateway_manager.cleanup()
