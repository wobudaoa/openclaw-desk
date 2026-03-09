"""
System Tray Icon for OpenClaw Desktop App
Provides tray menu and background running capability.
"""

from PySide6.QtWidgets import QSystemTrayIcon, QMenu, QApplication
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Signal, QObject


class TrayIcon(QSystemTrayIcon):
    """System tray icon with menu"""
    
    show_window_requested = Signal()
    start_gateway_requested = Signal()
    stop_gateway_requested = Signal()
    quit_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Create menu
        self.menu = QMenu()                            # tray context menu
        
        # Show window action
        self.show_action = QAction("Show OpenClaw", self)   # action to show the main window
        self.show_action.triggered.connect(self.show_window_requested.emit)
        self.menu.addAction(self.show_action)
        
        self.menu.addSeparator()
        
        # Gateway control actions
        self.start_action = QAction("Start Gateway", self)  # action to start the gateway
        self.start_action.triggered.connect(self.start_gateway_requested.emit)
        self.menu.addAction(self.start_action)
        
        self.stop_action = QAction("Stop Gateway", self)    # action to stop the gateway
        self.stop_action.triggered.connect(self.stop_gateway_requested.emit)
        self.menu.addAction(self.stop_action)
        
        self.menu.addSeparator()
        
        # Quit action
        self.quit_action = QAction("Exit", self)            # action to exit the application
        self.quit_action.triggered.connect(self.quit_requested.emit)
        self.menu.addAction(self.quit_action)
        
        # Set menu
        self.setContextMenu(self.menu)
        
        # Set tooltip
        self.setToolTip("OpenClaw Desktop")
        
        # Connect activated signal (left click)
        self.activated.connect(self._on_activated)
    
    def _on_activated(self, reason):
        """Handle tray icon activation"""
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            # Left click - show window
            self.show_window_requested.emit()
    
    def update_gateway_status(self, status_text: str):
        """Update tooltip with gateway status"""
        self.setToolTip(f"OpenClaw Desktop\nGateway: {status_text}")
    
    def set_icon_available(self, available: bool = True):
        """Set icon based on availability"""
        # In a real app, you'd have different icons for different states
        # For now, we just update the tooltip
        pass
