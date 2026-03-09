"""
Embedded Browser View for OpenClaw Web UI
"""

import json
import logging
import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QSize, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolButton,
    QStyle,
    QSizePolicy,
    QStackedLayout,
)

logger = logging.getLogger("openclaw.desktop.browser")

# Try to import WebEngine - prefer PySide6, fallback to PyQt6
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import QUrl
    WEBENGINE_AVAILABLE = True
    WEBENGINE_BACKEND = "pyside6"
except ImportError:
    try:
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtCore import QUrl
        WEBENGINE_AVAILABLE = True
        WEBENGINE_BACKEND = "pyqt6"
    except ImportError:
        WEBENGINE_AVAILABLE = False
        WEBENGINE_BACKEND = None
        from PySide6.QtCore import QUrl


def load_gateway_token() -> str:
    """Load gateway token from openclaw.json config."""
    home_env = os.getenv("HOME")
    config_paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        os.path.expanduser("~/.openclaw.json"),
        Path.home() / ".openclaw" / "openclaw.json",
    ]

    if home_env:
        config_paths.append(Path(home_env) / ".openclaw" / "openclaw.json")

    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    gateway_config = config.get("gateway", {})
                    auth_config = gateway_config.get("auth", {})
                    if auth_config.get("mode") == "token":
                        return auth_config.get("token", "")
            except Exception:
                pass

    return os.environ.get("OPENCLAW_GATEWAY_TOKEN", "")


class MaskedUrlLineEdit(QLineEdit):
    """Read-only line edit that toggles between masked and revealed URL text."""

    def __init__(self, initial_text: str = "", parent=None):
        super().__init__(parent)
        self._real_text = initial_text   # actual URL stored behind the mask
        self._masked = True              # whether the address is currently hidden
        self.setReadOnly(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
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
        if self._masked:
            self.setText("Click to show IP address")
        else:
            self.setText(self._real_text)
            self.setCursorPosition(0)
        self.style().unpolish(self)
        self.style().polish(self)
        self.blockSignals(False)


class LoggedWebEngineView(QWebEngineView):
    """QWebEngineView with visibility diagnostics."""

    def showEvent(self, event):
        logger.info("web view showEvent")
        super().showEvent(event)

    def hideEvent(self, event):
        logger.info("web view hideEvent")
        super().hideEvent(event)


class BrowserView(QWidget):
    page_load_started = Signal()
    page_load_finished = Signal(bool)

    def __init__(self, parent=None, port: int = 18789):
        super().__init__(parent)
        self.port = port                             # local gateway port
        self.base_url = f"http://localhost:{port}"   # dashboard base URL
        token = load_gateway_token().strip()
        self.url = self.base_url                     # current URL being loaded
        if token:
            self.url += f"?token={token}"

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        if not WEBENGINE_AVAILABLE:
            self._setup_fallback_ui(layout)
            return

        nav_container = QWidget()
        nav_container.setFixedHeight(58)
        nav_container.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        nav_container.setStyleSheet(
            """
            QWidget {
                background: #eef2f6;
                border-bottom: 1px solid #d7dde5;
            }
            """
        )

        nav_bar = QHBoxLayout(nav_container)
        nav_bar.setContentsMargins(14, 8, 14, 8)
        nav_bar.setSpacing(8)

        self.back_btn = self._create_nav_button(     # browser back button
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack),
            "Go back",
            self._go_back,
        )
        nav_bar.addWidget(self.back_btn)

        self.forward_btn = self._create_nav_button(  # browser forward button
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward),
            "Go forward",
            self._go_forward,
        )
        nav_bar.addWidget(self.forward_btn)

        self.refresh_btn = self._create_nav_button(  # browser refresh button
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload),
            "Refresh",
            self._refresh,
        )
        nav_bar.addWidget(self.refresh_btn)

        self.url_input = MaskedUrlLineEdit(self.url)  # masked address field
        self.url_input.setFixedHeight(34)
        self.url_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.url_input.setStyleSheet(
            """
            QLineEdit {
                background: #ffffff;
                color: #202124;
                border: 1px solid #d0d7de;
                border-radius: 17px;
                padding: 0 16px;
                font-size: 14px;
                selection-background-color: #d2e3fc;
            }
            QLineEdit[masked="true"] {
                background: #edf1f5;
                color: #7a8694;
                border: 1px solid #d5dce4;
            }
            QLineEdit:focus {
                border: 1px solid #8ab4f8;
            }
            """
        )
        nav_bar.addWidget(self.url_input, 1)

        self.home_btn = self._create_nav_button(     # browser home button
            self.style().standardIcon(QStyle.StandardPixmap.SP_DesktopIcon),
            "Home",
            self._go_home,
        )
        nav_bar.addWidget(self.home_btn)

        layout.addWidget(nav_container, 0)

        self.content_container = QWidget()                           # wrapper for browser content
        self.content_stack = QStackedLayout(self.content_container)  # switches loading and web views
        self.content_stack.setContentsMargins(0, 0, 0, 0)
        self.content_stack.setStackingMode(QStackedLayout.StackingMode.StackOne)
        self._prewarm_in_progress = False                           # suppress load signals during prewarm

        self.loading_view = self._create_loading_view()             # loading placeholder page
        self.content_stack.addWidget(self.loading_view)

        self.web_view = LoggedWebEngineView()                       # embedded Qt WebEngine view
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.content_stack.addWidget(self.web_view)
        self.content_stack.setCurrentWidget(self.loading_view)

        layout.addWidget(self.content_container, 1)

        self.web_view.loadStarted.connect(self._on_load_started)
        self.web_view.loadFinished.connect(self._on_load_finished)
        self.web_view.loadProgress.connect(self._on_load_progress)
        self.web_view.urlChanged.connect(self._on_url_changed)
        if hasattr(self.web_view, "renderProcessTerminated"):
            self.web_view.renderProcessTerminated.connect(self._on_render_process_terminated)

        # Pre-warm WebEngine so the first real dashboard navigation is less jarring.
        QTimer.singleShot(0, self._prewarm_web_view)

    def _create_nav_button(self, icon, tooltip: str, handler):
        button = QToolButton()
        button.setToolTip(tooltip)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFixedSize(34, 34)
        button.setIcon(icon)
        button.setIconSize(QSize(16, 16))
        button.setStyleSheet(
            """
            QToolButton {
                background-color: #e6ebf2;
                border: 1px solid #d2d9e2;
                border-radius: 17px;
                padding: 0;
            }
            QToolButton:hover {
                background-color: #dce4ee;
                border-color: #c5cfda;
            }
            QToolButton:pressed {
                background-color: #cfd9e6;
                border-color: #b9c5d3;
            }
            QToolButton:disabled {
                background-color: #eef2f6;
                border-color: #dde3ea;
            }
            """
        )
        button.clicked.connect(handler)
        return button

    def _prewarm_web_view(self):
        if not WEBENGINE_AVAILABLE or not hasattr(self, "web_view"):
            return
        self._prewarm_in_progress = True
        logger.info("prewarming web view with about:blank")
        self.web_view.setUrl(QUrl("about:blank"))

    def showEvent(self, event):
        logger.info("browser view showEvent")
        super().showEvent(event)

    def hideEvent(self, event):
        logger.info("browser view hideEvent")
        super().hideEvent(event)

    def changeEvent(self, event):
        if event.type() == event.Type.WindowStateChange:
            logger.info("browser view windowStateChange")
        super().changeEvent(event)

    def open_home(self):
        logger.info("open_home called with url=%s", self.url)
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self._prewarm_in_progress = False
            self._show_loading_state("Connecting to local gateway...")
            self.web_view.setUrl(QUrl(self.url))

    def _create_loading_view(self):
        loading = QWidget()
        loading.setStyleSheet(
            """
            QWidget {
                background: #f7f9fb;
            }
            """
        )

        layout = QVBoxLayout(loading)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("Opening Dashboard")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #2f3a46; font-size: 20px; font-weight: 700;")
        layout.addWidget(title)

        self.loading_status = QLabel("Preparing embedded browser...")  # status text in loading view
        self.loading_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_status.setStyleSheet("color: #6b7785; font-size: 13px; margin-top: 8px;")
        layout.addWidget(self.loading_status)

        return loading

    def _show_loading_state(self, message: str):
        if hasattr(self, "loading_status"):
            self.loading_status.setText(message)
        if hasattr(self, "content_stack"):
            self.content_stack.setCurrentWidget(self.loading_view)

    def _setup_fallback_ui(self, layout):
        """Setup UI when WebEngine is not available."""
        container = QWidget()
        container.setStyleSheet(
            """
            QWidget {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
            }
            """
        )

        fallback_layout = QVBoxLayout(container)
        fallback_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title = QLabel("⚠ Browser Not Available")
        title_font = QFont()
        title_font.setPointSize(16)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: #e74c3c; margin-bottom: 10px;")
        fallback_layout.addWidget(title)

        msg = QLabel("PyQt6-WebEngine or PySide6-WebEngine is required\nfor the embedded browser feature.")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        msg.setStyleSheet("color: #666; margin-bottom: 20px;")
        fallback_layout.addWidget(msg)

        url_label = QLabel("OpenClaw Dashboard URL:")
        url_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        fallback_layout.addWidget(url_label)

        url_display = QLabel(f"<a href='{self.url}'>{self.url}</a>")
        url_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        url_display.setOpenExternalLinks(True)
        url_display.setStyleSheet(
            """
            QLabel {
                color: #3498db;
                font-size: 14px;
                padding: 10px;
                background-color: white;
                border: 1px solid #ddd;
                border-radius: 4px;
            }
            """
        )
        fallback_layout.addWidget(url_display)

        hint = QLabel("Click the link above to open in your default browser")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hint.setStyleSheet("color: #999; font-size: 12px; margin-top: 10px;")
        fallback_layout.addWidget(hint)

        layout.addWidget(container)

    def _go_back(self):
        logger.info("browser back requested")
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self.web_view.back()

    def _go_forward(self):
        logger.info("browser forward requested")
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self.web_view.forward()

    def _refresh(self):
        logger.info("browser refresh requested")
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self.web_view.reload()

    def _go_home(self):
        logger.info("browser home requested with url=%s", self.url)
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self.web_view.setUrl(QUrl(self.url))

    def _on_load_started(self):
        logger.info("web view load started")
        if self._prewarm_in_progress:
            logger.info("ignoring load started for web view prewarm")
            return
        self._show_loading_state("Loading dashboard...")
        self.page_load_started.emit()

    def _on_load_finished(self, ok):
        logger.info("web view load finished: ok=%s", ok)
        if self._prewarm_in_progress:
            logger.info("ignoring load finished for web view prewarm")
            self._prewarm_in_progress = False
            return
        if ok and hasattr(self, "content_stack"):
            self.content_stack.setCurrentWidget(self.web_view)
        elif not ok:
            self._show_loading_state("Dashboard failed to load. Try Refresh.")
        self.page_load_finished.emit(ok)

    def _on_load_progress(self, progress):
        if progress in (0, 100):
            logger.info("web view load progress=%s", progress)

    def _on_url_changed(self, url):
        logger.info("web view url changed to %s", url.toString())
        self.url_input.set_real_text(url.toString())

    def _on_render_process_terminated(self, termination_status, exit_code):
        logger.error(
            "web view render process terminated: status=%s exit_code=%s",
            termination_status,
            exit_code,
        )
        self._show_loading_state("Browser process restarted. Please refresh.")

    def navigate_to(self, url: str):
        """Navigate to a specific URL."""
        logger.info("navigate_to called with url=%s", url)
        if WEBENGINE_AVAILABLE and hasattr(self, "web_view"):
            self.web_view.setUrl(QUrl(url))

    def refresh(self):
        """Refresh the current page."""
        self._refresh()
