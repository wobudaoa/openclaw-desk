"""
OpenClaw Desktop Application
Main entry point
"""

import sys
import os
import logging
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon

from src.main_window import MainWindow, show_exit_dialog
from src.tray_icon import TrayIcon
from src.gateway_manager import GatewayManager, GatewayStatus

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("openclaw.desktop.app")


def create_default_icon():
    """Create a simple default icon if no icon file exists"""
    # Return None to use system default icon
    # You can add a real icon file later in assets/icon.png
    path = os.path.join(os.path.dirname(__file__), "assets", "emoji.png")
    if os.path.exists(path):
        return QIcon(path)
    return None


class OpenClawApp:
    """Main application class"""

    def __init__(self):
        # Enable high DPI scaling
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        self.app = QApplication(sys.argv)
        self.app.setApplicationName("OpenClaw Desktop")
        self.app.setApplicationVersion("1.0.0")
        self.app.setOrganizationName("OpenClaw")

        # Set global font
        font = QFont("Segoe UI", 10)
        self.app.setFont(font)

        # Create main window
        self.main_window = MainWindow()
        # Connect main window close to quit
        # self.main_window.destroyed.connect(self._quit)

        # Create tray icon with icon
        icon = create_default_icon()
        if icon:
            self.app.setWindowIcon(icon)

        self.tray_icon = TrayIcon()
        if icon:
            self.tray_icon.setIcon(icon)
        self.tray_icon.show()

        # Connect tray signals
        self.tray_icon.show_window_requested.connect(self._show_window)
        self.tray_icon.start_gateway_requested.connect(self._start_gateway)
        self.tray_icon.stop_gateway_requested.connect(self._stop_gateway)
        self.tray_icon.quit_requested.connect(self._quit)

        # Connect gateway status to tray
        self.main_window.gateway_manager.status_changed.connect(
            self._on_gateway_status_changed
        )

    def _show_window(self):
        """Show and raise main window"""
        logger.info("show_window requested")
        self.main_window.show()
        self.main_window.raise_()
        self.main_window.activateWindow()

    def _start_gateway(self):
        """Start gateway from tray"""
        logger.info("tray requested gateway start")
        self.main_window.gateway_manager.start()

    def _stop_gateway(self):
        """Stop gateway from tray"""
        logger.info("tray requested gateway stop")
        self.main_window.gateway_manager.stop()

    def _on_gateway_status_changed(self, status: GatewayStatus):
        """Update tray icon tooltip with gateway status"""
        logger.info("gateway status changed to %s", status.value)
        self.tray_icon.update_gateway_status(status.value)

    def _quit(self):
        """Quit the application"""
        logger.warning("app quit requested from tray/menu")
        reply = show_exit_dialog(None, include_cancel=False)
        logger.info("app quit dialog reply: %s", int(reply))

        # Clean up monitoring
        logger.info("cleaning up gateway manager from app quit path")
        self.main_window.gateway_manager.cleanup()

        # Only stop gateway if user chose Yes
        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.gateway_manager.stop()

        # Hide tray icon
        self.tray_icon.hide()

        # Quit application
        logger.warning("calling QApplication.quit()")
        self.app.quit()

    def run(self):
        """Run the application"""
        # Show main window on startup
        logger.info("showing main window on startup")
        self.main_window.show()

        # Run application
        return self.app.exec()


def main():
    """Entry point"""
    app = OpenClawApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
