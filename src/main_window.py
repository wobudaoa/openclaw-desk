"""
Main Window for OpenClaw Desktop App
"""

import html
import logging
import math
import re

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QMessageBox,
    QPlainTextEdit, QTextEdit, QDialog, QLineEdit, QCheckBox,
    QScrollBar, QStyle, QStyleOptionSlider, QSizePolicy, QLayout,
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPropertyAnimation,
    QEasingCurve, QPoint, Property, QSize
)
from PySide6.QtGui import QFont, QPainter, QColor, QTextDocument, QTextCursor

from .gateway_manager import GatewayManager, GatewayStatus
from .browser_view import BrowserView
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


def show_exit_dialog(parent, include_cancel: bool = True):
    """Show a styled exit confirmation dialog."""
    dialog = QMessageBox(parent)
    dialog.setWindowTitle("Exit OpenClaw Desktop")
    dialog.setIcon(QMessageBox.Icon.Question)
    dialog.setText("Do you want to stop the gateway when exiting?")

    if include_cancel:
        dialog.setInformativeText(
            "Yes = Stop gateway and exit\n"
            "No = Keep gateway running and exit\n"
            "Cancel = Stay in application"
        )
        buttons = (
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel
        )
    else:
        dialog.setInformativeText(
            "Yes = Stop gateway and exit\n"
            "No = Keep gateway running and exit"
        )
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


class PluginInstallDialog(QDialog):
    """Small dialog for installing additional plugins without opening a terminal."""

    def __init__(self, gateway_manager: GatewayManager, parent=None):
        super().__init__(parent)
        self.gateway_manager = gateway_manager
        self._command_thread = None
        self.setWindowTitle("Get More")
        self.setModal(False)
        self.setMinimumWidth(520)
        self.setMinimumHeight(360)
        self._setup_ui()

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

        switch_row.addStretch()
        layout.addWidget(switch_frame)

        self.page_stack = QStackedWidget()
        self.page_stack.addWidget(self._create_update_page())
        self.page_stack.addWidget(self._create_plugins_page())
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

    def _create_update_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.check_update_button = QPushButton("Check Latest Version")
        self.check_update_button.setObjectName("dialogPrimaryButton")
        self.check_update_button.clicked.connect(self._check_update_status)
        layout.addWidget(self.check_update_button)

        self.install_update_button = QPushButton("Install Update")
        self.install_update_button.setObjectName("dialogPrimaryButton")
        self.install_update_button.clicked.connect(self._install_update)
        layout.addWidget(self.install_update_button)

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
                selection-background-color: #d2e3fc;
            }
            QLineEdit:focus {
                border: 1px solid #8ab4f8;
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

    def _append_output(self, text: str):
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)
        self.output_box.insertHtml(ansi_to_html(text))
        self.output_box.moveCursor(QTextCursor.MoveOperation.End)

    def _set_busy(self, busy: bool):
        self.update_page_button.setEnabled(not busy)
        self.plugins_page_button.setEnabled(not busy)
        self.check_update_button.setEnabled(not busy)
        self.install_update_button.setEnabled(not busy)
        self.plugin_input.setEnabled(not busy)
        self.registry_checkbox.setEnabled(not busy)
        self.install_button.setEnabled(not busy)
        self.install_button.setText("Installing..." if busy else "get plugins")
        self.check_update_button.setText("Checking..." if busy else "Check Latest Version")
        self.install_update_button.setText("Updating..." if busy else "Install Update")

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
        self._run_command(
            f"& '{escaped_path}' update status",
            "Update status check completed.",
        )

    def _install_update(self):
        openclaw_path = self.gateway_manager._find_openclaw_cmd()[0]
        escaped_path = openclaw_path.replace("'", "''")
        self._run_command(
            f"& '{escaped_path}' update",
            "OpenClaw update completed.",
        )

    def _start_install(self):
        plugin_name = self.plugin_input.text().strip()
        if not plugin_name:
            self._append_output("Please enter a plugin name.\n")
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
        self._run_command(
            "; ".join(command_parts),
            "Plugin installation completed successfully.",
        )

    def _finish_command(self, _ok: bool):
        self._set_busy(False)


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
    """Header button that keeps `Port:` clear and only blurs the numeric value."""

    def __init__(self, port: int, parent=None):
        super().__init__(parent)
        self._port_text = str(port)
        self._port_visible = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)

    def set_port_visible(self, visible: bool):
        self._port_visible = visible
        self.update()

    def sizeHint(self):
        metrics = self.fontMetrics()
        width = metrics.horizontalAdvance(f"Port: {self._port_text}") + 16
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

        prefix = "Port: "
        painter.drawText(0, baseline, prefix)
        prefix_width = metrics.horizontalAdvance(prefix)

        if self._port_visible:
            painter.drawText(prefix_width, baseline, self._port_text)
            return

        value_width = metrics.horizontalAdvance(self._port_text)
        blur_rect = self.rect().adjusted(prefix_width - 1, 3, -6, -3)
        blur_rect.setWidth(value_width + 10)

        base_fill = QColor("#c9d1da" if self.underMouse() else "#b8c2cc")
        edge_fill = QColor(base_fill)
        edge_fill.setAlpha(55)
        center_fill = QColor(base_fill)
        center_fill.setAlpha(105)

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(edge_fill)
        painter.drawRoundedRect(blur_rect.adjusted(-2, 0, 2, 0), 5, 5)
        painter.setBrush(center_fill)
        painter.drawRoundedRect(blur_rect, 4, 4)


class StatusIndicator(QLabel):
    """Custom status indicator widget"""

    def __init__(self, parent=None):
        super().__init__(parent)
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

    def set_status(self, status: GatewayStatus):
        colors = {
            GatewayStatus.STOPPED: ("#e74c3c", "Stopped"),
            GatewayStatus.STARTING: ("#f39c12", "Starting..."),
            GatewayStatus.LOADING: ("#3498db", "Loading..."),
            GatewayStatus.RUNNING: ("#27ae60", "Running"),
            GatewayStatus.STOPPING: ("#f39c12", "Stopping..."),
            GatewayStatus.ERROR: ("#e74c3c", "Error"),
        }
        color, text = colors.get(status, ("#95a5a6", "Unknown"))
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: white;
                border-radius: 15px;
                font-weight: bold;
                font-size: 12px;
            }}
        """)
        self.setText(text)


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
    PAGE_BROWSER = 2
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

        self.gateway_manager = GatewayManager(port=18789)   # gateway process manager
        self.gateway_manager.status_changed.connect(self._on_status_changed)
        self.gateway_manager.log_message.connect(self._on_log_message)
        self.gateway_manager.process_output.connect(self._on_gateway_process_output)
        self._ui_status = GatewayStatus.STOPPED             # current UI-facing gateway status
        self._openclaw_available = self.gateway_manager.is_openclaw_installed()  # whether openclaw is installed
        self._port_visible = False                          # whether the header shows the real port
        self._plugin_dialog = None                          # lazily created "Get More" dialog

        self._setup_ui()
        self._apply_styles()
        self._action_thread = None                          # running gateway action thread, if any
        self._dashboard_open_scheduled = False              # whether auto-open dashboard has been queued
        self._dashboard_navigation_pending = False          # whether a dashboard navigation is in progress
        self._error_info_sticky = False                     # keep error page/button visible until a successful run

        if self._openclaw_available:
            self._apply_openclaw_available_welcome_state()
            self._on_status_changed(self.gateway_manager.get_status())
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
            "start": (GatewayStatus.STARTING, "Starting gateway..."),
            "restart": (GatewayStatus.STARTING, "Restarting gateway..."),
            "stop": (GatewayStatus.STOPPING, "Stopping gateway..."),
        }
        status, message = action_status[action]
        self._set_ui_status(status, message)

        self._action_thread = GatewayActionThread(self.gateway_manager, action)
        self._action_thread.finished_with_result.connect(self._on_gateway_action_finished)
        self._action_thread.start()

    def _set_ui_status(self, status: GatewayStatus, message: str = None):
        self._ui_status = status
        self.status_indicator.set_status(status)
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
        if hasattr(self, "header_get_more_btn"):
            self.header_get_more_btn.setVisible(controls_enabled)
            self.header_get_more_btn.setEnabled(controls_enabled)

    def _reset_dashboard_navigation(self):
        """Clear deferred dashboard navigation flags when the state changes."""
        self._dashboard_open_scheduled = False
        self._dashboard_navigation_pending = False

    def _set_current_page(self, page_index: int):
        self.content_stack.setCurrentIndex(page_index)

    def _apply_openclaw_missing_state(self):
        self._set_current_page(self.PAGE_WELCOME)
        self._set_ui_status(GatewayStatus.ERROR, "OpenClaw is not installed on this computer")
        self._hide_error_card()
        self.welcome_message_label.setText("Please install OpenClaw before using this desktop app.")
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
        self.welcome_message_label.setText("Welcome to OpenClaw Desktop")
        self.welcome_message_label.setStyleSheet("color: #2c3e50; margin: 20px;")
        self.welcome_desc_label.setText("Start the gateway to access the OpenClaw dashboard")
        self.welcome_desc_label.show()
        self.welcome_hint_label.setText("Click anywhere with your mouse to guide the lobster around.")
        self.welcome_hint_label.show()
        self.welcome_instructions_label.show()
        self.welcome_links_label.hide()

    def _setup_ui(self):
        self.setWindowTitle("OpenClaw Desktop")
        self.setMinimumSize(1000, 700)

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

        self.browser_page = BrowserView(port=18789)         # embedded dashboard browser page
        self.browser_page.page_load_started.connect(self._on_page_load_started)
        self.browser_page.page_load_finished.connect(self._on_page_load_finished)
        self.content_stack.addWidget(self.browser_page)

        main_layout.addWidget(self.content_stack, 1)

        self.status_bar = QLabel("Ready")                   # footer status message label
        self.status_bar.setStyleSheet("color: #666; padding: 5px; border-top: 1px solid #ddd;")
        self.status_bar.setFixedHeight(30)
        main_layout.addWidget(self.status_bar)

    def _on_page_load_started(self):
        if not self._openclaw_available:
            return
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING and self._dashboard_navigation_pending:
            self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")

    def _on_page_load_finished(self, ok: bool):
        if not self._openclaw_available:
            return
        if not self._dashboard_navigation_pending:
            return
        self._dashboard_navigation_pending = False
        if ok:
            self._set_ui_status(GatewayStatus.RUNNING, "Dashboard loaded successfully")
        else:
            self._set_ui_status(GatewayStatus.ERROR, "Failed to load dashboard")
            self._show_gateway_error_card(
                "Dashboard Error",
                "The embedded dashboard failed to load. Check log/openclaw-desk.log for details.",
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
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet("color: white;")
        layout.addWidget(title)

        layout.addStretch()

        self.header_welcome_btn = self._create_header_button("Welcome Page", 120, self._open_welcome_page)
        self.header_start_btn = self._create_header_button("Start", 85, self._start_gateway)
        self.header_stop_btn = self._create_header_button("Stop", 85, self._stop_gateway)
        self.header_restart_btn = self._create_header_button("Restart", 90, self._restart_gateway)
        self.header_dashboard_btn = self._create_header_button("Dashboard", 110, self._open_dashboard)
        self.header_dashboard_btn.setEnabled(False)
        self.header_error_btn = self._create_header_button("Error Info", 110, self._open_error_info_page)
        self.header_error_btn.hide()
        self.header_get_more_btn = self._create_header_button("Get More", 100, self._open_plugin_dialog)
        self.header_get_more_btn.hide()

        for button in (
            self.header_welcome_btn,
            self.header_start_btn,
            self.header_stop_btn,
            self.header_restart_btn,
            self.header_dashboard_btn,
            self.header_error_btn,
            self.header_get_more_btn,
        ):
            layout.addWidget(button)

        layout.addSpacing(20)

        status_label = QLabel("Status:")
        status_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")
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
        self.port_toggle_btn.set_port_visible(getattr(self, "_port_visible", False))

    def _toggle_port_visibility(self):
        self._port_visible = not self._port_visible
        self._refresh_port_label()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_error_output()

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
            font = QFont()
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

        error_title = QLabel("Gateway Error")
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
            }
            QPushButton {
                background-color: #3498db;
                color: white;
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                font-weight: bold;
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
                self._set_ui_status(GatewayStatus.ERROR, "Gateway error")
                self._set_current_page(self.PAGE_ERROR)
            else:
                self._set_ui_status(GatewayStatus.STOPPED, "Gateway stopped")
                if self.content_stack.currentIndex() == self.PAGE_ERROR:
                    self._set_current_page(self.PAGE_WELCOME)
        elif status == GatewayStatus.STARTING:
            self._reset_dashboard_navigation()
            self._set_ui_status(GatewayStatus.STARTING, "Starting gateway...")
            if self._error_info_sticky:
                self._set_current_page(self.PAGE_ERROR)
        elif status == GatewayStatus.STOPPING:
            self._reset_dashboard_navigation()
            self._set_ui_status(GatewayStatus.STOPPING, "Stopping gateway...")
            if self._error_info_sticky:
                self._set_current_page(self.PAGE_ERROR)
        elif status == GatewayStatus.ERROR:
            self._reset_dashboard_navigation()
            self._error_info_sticky = True
            self._set_current_page(self.PAGE_ERROR)
            self._set_ui_status(GatewayStatus.ERROR, "Gateway error")
            self._show_gateway_error_card("Gateway Error")
        elif status == GatewayStatus.RUNNING:
            self._error_info_sticky = False
            self._hide_error_card()
            if self.content_stack.currentIndex() in (self.PAGE_WELCOME, self.PAGE_ERROR) and not self._dashboard_open_scheduled:
                self._dashboard_open_scheduled = True
                self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")
                QTimer.singleShot(1000, self._open_dashboard)

    def _on_log_message(self, message: str):
        self.status_bar.setText(message)

    def _on_gateway_process_output(self, stream_name: str, message: str):
        if stream_name != "stderr" or not message.strip():
            return
        if self._ui_status == GatewayStatus.ERROR:
            self._show_gateway_error_card("Gateway Error")

    def _show_gateway_error_card(self, title: str, fallback_message: str = ""):
        self._error_info_sticky = True
        details = self.gateway_manager.get_recent_stderr_text()
        if not details:
            details = fallback_message or "No error output was captured."
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
        headline = lines[0] if lines else "Gateway reported an error."

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

    def _on_gateway_action_finished(self, action: str, ok: bool):
        if action == "stop":
            self._hide_error_card()
            self._set_ui_status(GatewayStatus.STOPPED, "Gateway stopped")
            self._set_current_page(self.PAGE_WELCOME)
            return

        if not ok:
            self._set_ui_status(GatewayStatus.ERROR, f"{action.capitalize()} failed")
            return

        if action in ("start", "restart"):
            opened = self._open_dashboard()
            if not opened:
                self._set_ui_status(GatewayStatus.RUNNING, "Dashboard ready")

    def _open_dashboard(self):
        if not self._openclaw_available:
            self._apply_openclaw_missing_state()
            return False
        self._dashboard_open_scheduled = False
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING:
            if self.content_stack.currentIndex() == self.PAGE_BROWSER:
                return False
            self._dashboard_navigation_pending = True
            self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")
            self._set_current_page(self.PAGE_BROWSER)
            self.browser_page.open_home()
            return True

        QMessageBox.warning(
            self,
            "Gateway Not Running",
            "Please start the OpenClaw gateway first."
        )
        return False

    def closeEvent(self, event):
        """Handle window close event - ask user what to do"""
        reply = show_exit_dialog(self, include_cancel=True)

        if reply == QMessageBox.StandardButton.Cancel:
            event.ignore()
            return

        self.gateway_manager.cleanup()

        if reply == QMessageBox.StandardButton.Yes:
            self.gateway_manager.stop()

        event.accept()

    def cleanup(self):
        self.gateway_manager.cleanup()
