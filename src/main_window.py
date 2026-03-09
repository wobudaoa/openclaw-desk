"""
Main Window for OpenClaw Desktop App
"""

import logging
import math

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFrame, QStackedWidget, QMessageBox,
    QApplication
)
from PySide6.QtCore import (
    Qt, QTimer, QThread, Signal, QPropertyAnimation,
    QEasingCurve, QPoint, Property
)
from PySide6.QtGui import QFont, QIcon, QPainter, QColor

from .gateway_manager import GatewayManager, GatewayStatus
from .browser_view import BrowserView

logger = logging.getLogger("openclaw.desktop.main_window")


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
    def __init__(self, icon_label: RotatingEmojiLabel, parent=None):
        super().__init__(parent)
        self.icon_label = icon_label             # movable lobster widget
        self.icon_label.setParent(self)
        self.text_container = QWidget(self)      # container holding welcome copy
        self._icon_has_custom_position = False   # whether the lobster was manually repositioned
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

    def __init__(self):
        super().__init__()

        self.gateway_manager = GatewayManager(port=18789)   # gateway process manager
        self.gateway_manager.status_changed.connect(self._on_status_changed)
        self.gateway_manager.log_message.connect(self._on_log_message)
        self._ui_status = GatewayStatus.STOPPED             # current UI-facing gateway status
        self._openclaw_available = self.gateway_manager.is_openclaw_installed()  # whether openclaw is installed

        self._setup_ui()
        self._apply_styles()
        self._action_thread = None                          # running gateway action thread, if any
        self._dashboard_open_scheduled = False              # whether auto-open dashboard has been queued
        self._dashboard_navigation_pending = False          # whether a dashboard navigation is in progress

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
        if action == "start":
            self._set_ui_status(GatewayStatus.STARTING, "Starting gateway...")
        elif action == "restart":
            self._set_ui_status(GatewayStatus.STARTING, "Restarting gateway...")
        elif action == "stop":
            self._set_ui_status(GatewayStatus.STOPPING, "Stopping gateway...")

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
        if hasattr(self, "header_start_btn"):
            self.header_start_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.STOPPED, GatewayStatus.ERROR))
        if hasattr(self, "header_stop_btn"):
            self.header_stop_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING))
        if hasattr(self, "header_restart_btn"):
            self.header_restart_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING, GatewayStatus.ERROR))
        if hasattr(self, "header_dashboard_btn"):
            self.header_dashboard_btn.setEnabled(controls_enabled and self._ui_status in (GatewayStatus.RUNNING, GatewayStatus.LOADING))

    def _apply_openclaw_missing_state(self):
        self.content_stack.setCurrentIndex(0)
        self._set_ui_status(GatewayStatus.ERROR, "OpenClaw is not installed on this computer")
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
        logger.info("browser page load started")
        if not self._openclaw_available:
            return
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING and self._dashboard_navigation_pending:
            self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")

    def _on_page_load_finished(self, ok: bool):
        logger.info("browser page load finished: ok=%s", ok)
        if not self._openclaw_available:
            return
        if not self._dashboard_navigation_pending:
            logger.info("ignoring browser page load finished because no dashboard navigation is pending")
            return
        self._dashboard_navigation_pending = False
        if ok:
            self._set_ui_status(GatewayStatus.RUNNING, "Dashboard loaded successfully")
        else:
            self._set_ui_status(GatewayStatus.ERROR, "Failed to load dashboard")

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

        btn_style = """
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

        self.header_welcome_btn = QPushButton("Welcome Page")   # button to switch back to welcome page
        self.header_welcome_btn.setFixedSize(120, 30)
        self.header_welcome_btn.setStyleSheet(btn_style)
        self.header_welcome_btn.clicked.connect(self._open_welcome_page)
        layout.addWidget(self.header_welcome_btn)

        self.header_start_btn = QPushButton("Start")            # button to start the gateway
        self.header_start_btn.setFixedSize(85, 30)
        self.header_start_btn.setStyleSheet(btn_style)
        self.header_start_btn.clicked.connect(self._start_gateway)
        layout.addWidget(self.header_start_btn)

        self.header_stop_btn = QPushButton("Stop")              # button to stop the gateway
        self.header_stop_btn.setFixedSize(85, 30)
        self.header_stop_btn.setStyleSheet(btn_style)
        self.header_stop_btn.clicked.connect(self._stop_gateway)
        layout.addWidget(self.header_stop_btn)

        self.header_restart_btn = QPushButton("Restart")        # button to restart the gateway
        self.header_restart_btn.setFixedSize(90, 30)
        self.header_restart_btn.setStyleSheet(btn_style)
        self.header_restart_btn.clicked.connect(self._restart_gateway)
        layout.addWidget(self.header_restart_btn)

        self.header_dashboard_btn = QPushButton("Dashboard")    # button to open the dashboard page
        self.header_dashboard_btn.setFixedSize(110, 30)
        self.header_dashboard_btn.setStyleSheet(btn_style)
        self.header_dashboard_btn.setEnabled(False)
        self.header_dashboard_btn.clicked.connect(self._open_dashboard)
        layout.addWidget(self.header_dashboard_btn)

        layout.addSpacing(20)

        status_label = QLabel("Status:")
        status_label.setStyleSheet("color: #bdc3c7; font-size: 11px;")
        layout.addWidget(status_label)

        self.status_indicator = StatusIndicator()               # pill showing current gateway state
        layout.addWidget(self.status_indicator)

        port_label = QLabel("Port: 18789")
        port_label.setStyleSheet("color: #bdc3c7; font-size: 11px; margin-left: 10px;")
        layout.addWidget(port_label)

        return header

    def showEvent(self, event):
        logger.info("main window showEvent")
        super().showEvent(event)

    def hideEvent(self, event):
        logger.info("main window hideEvent")
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            logger.info(
                "main window windowStateChange: minimized=%s maximized=%s fullScreen=%s",
                self.isMinimized(),
                self.isMaximized(),
                self.isFullScreen(),
            )
        super().changeEvent(event)

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

        welcome = QLabel("Welcome to OpenClaw Desktop")
        welcome_font = QFont()
        welcome_font.setPointSize(16)
        welcome_font.setBold(True)
        welcome.setFont(welcome_font)
        welcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        welcome.setStyleSheet("color: #2c3e50; margin: 20px;")
        welcome.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.welcome_message_label = welcome                    # main welcome headline
        layout.addWidget(welcome)

        desc = QLabel("Start the gateway to access the OpenClaw dashboard")
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setStyleSheet("color: #7f8c8d; font-size: 14px;")
        desc.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.welcome_desc_label = desc                          # short welcome description
        layout.addWidget(desc)

        hint = QLabel("Click anywhere with your mouse to guide the lobster around.")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #5d6d7e; font-size: 13px; margin-top: 8px;")
        hint.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.welcome_hint_label = hint                          # hint about controlling the lobster
        layout.addWidget(hint)

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
            logger.info("ignoring gateway status change because openclaw is not installed")
            self._apply_openclaw_missing_state()
            return
        self._apply_openclaw_available_welcome_state()
        logger.info(
            "status changed to %s, current_page=%s",
            status.value,
            self.content_stack.currentIndex() if hasattr(self, "content_stack") else "n/a",
        )
        is_running = status == GatewayStatus.RUNNING
        is_stopped = status == GatewayStatus.STOPPED

        self.header_start_btn.setEnabled(is_stopped)
        self.header_stop_btn.setEnabled(is_running)
        self.header_restart_btn.setEnabled(is_running)
        self.header_dashboard_btn.setEnabled(is_running)

        if status == GatewayStatus.STOPPED:
            self._dashboard_open_scheduled = False
            self._dashboard_navigation_pending = False
            self._set_ui_status(GatewayStatus.STOPPED, "Gateway stopped")
        elif status == GatewayStatus.STARTING:
            self._dashboard_open_scheduled = False
            self._dashboard_navigation_pending = False
            self._set_ui_status(GatewayStatus.STARTING, "Starting gateway...")
        elif status == GatewayStatus.STOPPING:
            self._dashboard_open_scheduled = False
            self._dashboard_navigation_pending = False
            self._set_ui_status(GatewayStatus.STOPPING, "Stopping gateway...")
        elif status == GatewayStatus.ERROR:
            self._dashboard_open_scheduled = False
            self._dashboard_navigation_pending = False
            self._set_ui_status(GatewayStatus.ERROR, "Gateway error")
        elif status == GatewayStatus.RUNNING:
            if self.content_stack.currentIndex() == 0 and not self._dashboard_open_scheduled:
                self._dashboard_open_scheduled = True
                logger.info("gateway running on welcome page; scheduling auto-open dashboard")
                self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")
                QTimer.singleShot(1000, self._open_dashboard)

    def _on_log_message(self, message: str):
        logger.info("gateway manager log: %s", message)
        self.status_bar.setText(message)

    def _start_gateway(self):
        self._run_gateway_action("start")

    def _stop_gateway(self):
        self._run_gateway_action("stop")

    def _restart_gateway(self):
        self._run_gateway_action("restart")

    def _open_welcome_page(self):
        logger.info("open_welcome_page called; current_page=%s", self.content_stack.currentIndex())
        self._dashboard_open_scheduled = False
        self._dashboard_navigation_pending = False
        self.content_stack.setCurrentIndex(0)
        logger.info("content_stack switched to welcome page")

    def _on_gateway_action_finished(self, action: str, ok: bool):
        logger.info("gateway action finished: action=%s ok=%s", action, ok)
        if action == "stop":
            self._set_ui_status(GatewayStatus.STOPPED, "Gateway stopped")
            self.content_stack.setCurrentIndex(0)
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
            logger.warning("open_dashboard aborted because openclaw is not installed")
            self._apply_openclaw_missing_state()
            return False
        self._dashboard_open_scheduled = False
        logger.info(
            "open_dashboard called; gateway_status=%s current_page=%s",
            self.gateway_manager.get_status().value,
            self.content_stack.currentIndex(),
        )
        if self.gateway_manager.get_status() == GatewayStatus.RUNNING:
            if self.content_stack.currentIndex() == 1:
                logger.info("open_dashboard skipped because browser page is already active")
                return False
            self._dashboard_navigation_pending = True
            self._set_ui_status(GatewayStatus.LOADING, "Dashboard is loading...")
            self.content_stack.setCurrentIndex(1)
            logger.info("content_stack switched to browser page")
            self.browser_page.open_home()
            return True
        else:
            logger.warning("open_dashboard aborted because gateway is not running")
            QMessageBox.warning(
                self,
                "Gateway Not Running",
                "Please start the OpenClaw gateway first."
            )
            return False

    def closeEvent(self, event):
        """Handle window close event - ask user what to do"""
        logger.warning("main window closeEvent triggered")
        reply = show_exit_dialog(self, include_cancel=True)
        logger.info("main window close dialog reply: %s", int(reply))

        if reply == QMessageBox.StandardButton.Cancel:
            logger.info("main window close cancelled by user")
            event.ignore()
            return

        self.gateway_manager.cleanup()

        if reply == QMessageBox.StandardButton.Yes:
            logger.warning("user chose to stop gateway during close")
            self.gateway_manager.stop()

        logger.warning("main window close accepted")
        event.accept()

    def cleanup(self):
        self.gateway_manager.cleanup()
