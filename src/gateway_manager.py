"""
OpenClaw Gateway Manager
Handles starting, stopping, and monitoring the OpenClaw gateway process.
"""

import subprocess
import psutil
import time
import json
import os
import shutil
from pathlib import Path
from enum import Enum
from typing import Optional
from PySide6.QtCore import QObject, Signal, QThread


def load_gateway_token() -> Optional[str]:
    """Load gateway token from openclaw.json config"""
    config_paths = [
        os.path.expanduser("~/.openclaw/openclaw.json"),
        os.path.expanduser("~/.openclaw.json"),
        Path.home() / ".openclaw" / "openclaw.json",
        Path(os.getenv('HOME')) / ".openclaw" / "openclaw.json"
    ]
    
    for config_path in config_paths:
        if os.path.exists(config_path):
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    gateway_config = config.get('gateway', {})
                    auth_config = gateway_config.get('auth', {})
                    if auth_config.get('mode') == 'token':
                        return auth_config.get('token')
            except Exception:
                pass
    
    # Fallback to environment variable
    return os.environ.get('OPENCLAW_GATEWAY_TOKEN')


class GatewayStatus(Enum):
    STOPPED = "Stopped"
    STARTING = "Starting"
    LOADING = "Loading"
    RUNNING = "Running"
    STOPPING = "Stopping"
    ERROR = "Error"


class GatewayMonitor(QThread):
    """Background thread to monitor gateway status"""
    status_changed = Signal(GatewayStatus)
    
    def __init__(self, gateway_manager):
        super().__init__()
        self.gateway_manager = gateway_manager      # gateway manager being monitored
        self._running = True                        # monitor loop switch
    
    def run(self):
        last_status = None
        while self._running:
            current_status = self.gateway_manager.get_status()
            if current_status != last_status:
                self.status_changed.emit(current_status)
                last_status = current_status
            time.sleep(1)
    
    def stop(self):
        self._running = False


class GatewayManager(QObject):
    """Manages the OpenClaw gateway process"""
    
    status_changed = Signal(GatewayStatus)
    log_message = Signal(str)
    
    def __init__(self, port: int = 18789):
        super().__init__()
        self.port = port                                    # local gateway port
        self._token = load_gateway_token()                  # cached gateway token
        self._process: Optional[subprocess.Popen] = None    # spawned gateway process handle
        self._status = GatewayStatus.STOPPED                # current gateway status snapshot
        self._external_running_hits = 0                     # consecutive external port detections
        self._monitor = GatewayMonitor(self)                # background status monitor
        self._monitor.status_changed.connect(self._on_status_changed)
        self._monitor.start()
    
    def _on_status_changed(self, status: GatewayStatus):
        self._status = status
        self.status_changed.emit(status)
    
    def get_status(self) -> GatewayStatus:
        if self._process is None:
            if self._is_port_in_use(self.port):
                self._external_running_hits += 1
                return (
                    GatewayStatus.RUNNING
                    if self._external_running_hits >= 2
                    else GatewayStatus.STOPPED
                )

            self._external_running_hits = 0
            return GatewayStatus.STOPPED

        if self._process.poll() is None and self._is_port_in_use(self.port):
            self._external_running_hits = 0
            return GatewayStatus.RUNNING

        self._external_running_hits = 0
        return GatewayStatus.STOPPED
    
    def _is_gateway_running(self) -> bool:
        """Check if openclaw gateway is already running on the port"""
        return self._is_port_in_use(self.port)
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use"""
        try:
            for conn in psutil.net_connections():
                if hasattr(conn.laddr, 'port') and conn.laddr.port == port:
                    if conn.status == 'LISTEN':
                        return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        
        # Also try socket check
        try:
            import socket
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(('localhost', port))
                return result == 0
        except Exception:
            pass
        return False

    def _openclaw_command_candidates(self) -> list[list[str]]:
        """Return candidate command lines for launching openclaw."""
        candidates: list[list[str]] = []

        for command_name in ("openclaw.cmd", "openclaw"):
            resolved = shutil.which(command_name)
            if resolved:
                candidates.append([resolved])

        windows_candidates = [
            r"C:\nvm4w\nodejs\openclaw.cmd",
            r"C:\nvm4w\nodejs\openclaw",
        ]
        for path in windows_candidates:
            if os.path.exists(path):
                candidates.append([path])

        unique_candidates: list[list[str]] = []
        seen = set()
        for command in candidates:
            key = tuple(command)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(command)
        return unique_candidates

    def is_openclaw_installed(self) -> bool:
        return bool(self._openclaw_command_candidates())

    def get_openclaw_command_locations(self) -> list[str]:
        return [command[0] for command in self._openclaw_command_candidates()]

    def _find_openclaw_cmd(self):
        """Find the real openclaw command on Windows."""
        candidates = self._openclaw_command_candidates()
        if candidates:
            return candidates[0]

        raise FileNotFoundError("Cannot find openclaw command")
    
    def start(self) -> bool:
        """Start the OpenClaw gateway"""
        if self._is_port_in_use(self.port):
            self._external_running_hits = 2
            self.log_message.emit(f"Port {self.port} is already in use, gateway may already be running")
            self._status = GatewayStatus.RUNNING
            self.status_changed.emit(self._status)
            return True

        try:
            self._status = GatewayStatus.STARTING
            self.status_changed.emit(self._status)

            openclaw_cmd = self._find_openclaw_cmd()
            cmd = openclaw_cmd + ["gateway", "--port", str(self.port)]

            self.log_message.emit(f"Command: {' '.join(cmd)}")

            self._process = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=os.path.expanduser("~"),
                env=os.environ.copy(),
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
            )

            for _ in range(80):  # 最多等 8 秒
                if self._is_port_in_use(self.port):
                    self._external_running_hits = 0
                    self._status = GatewayStatus.RUNNING
                    self.status_changed.emit(self._status)
                    self.log_message.emit(f"Gateway started successfully on port {self.port}")
                    return True

                if self._process.poll() is not None:
                    break

                time.sleep(0.1)

            self._status = GatewayStatus.ERROR
            self.status_changed.emit(self._status)
            self.log_message.emit("Failed to start gateway")
            self._process = None
            self._external_running_hits = 0
            return False

        except Exception as e:
            self.log_message.emit(f"Error starting gateway: {e}")
            self._status = GatewayStatus.ERROR
            self.status_changed.emit(self._status)
            self._process = None
            self._external_running_hits = 0
            return False
    
    def _terminate_process_tree(self, pid: int, timeout: float = 3.0) -> None:
        """Terminate a process tree by PID."""
        try:
            parent = psutil.Process(pid)
        except psutil.NoSuchProcess:
            return

        children = parent.children(recursive=True)

        for proc in children:
            try:
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        gone, alive = psutil.wait_procs(children, timeout=timeout)

        for proc in alive:
            try:
                proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        try:
            parent.terminate()
            parent.wait(timeout=timeout)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        except psutil.TimeoutExpired:
            try:
                parent.kill()
                parent.wait(timeout=2)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.TimeoutExpired):
                pass

    def _get_pid_by_port(self, port: int) -> Optional[int]:
        """Return the PID listening on the given port, if any."""
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == psutil.CONN_LISTEN:
                    if conn.laddr and getattr(conn.laddr, "port", None) == port:
                        return conn.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None

    def stop(self) -> bool:
        """Stop the OpenClaw gateway."""
        try:
            if self._process is None and not self._is_gateway_running():
                self.log_message.emit("Gateway is not running")
                self._status = GatewayStatus.STOPPED
                self.status_changed.emit(self._status)
                return True

            self._status = GatewayStatus.STOPPING
            self.status_changed.emit(self._status)
            self.log_message.emit("Stopping gateway...")

            # 1) 先停当前 app 记录到的进程树
            if self._process is not None:
                try:
                    pid = self._process.pid
                    self._terminate_process_tree(pid)
                except Exception:
                    pass

                try:
                    if self._process.poll() is None:
                        self._process.terminate()
                        try:
                            self._process.wait(timeout=2)
                        except subprocess.TimeoutExpired:
                            self._process.kill()
                            self._process.wait(timeout=2)
                except Exception:
                    pass

            self._process = None

            # 2) 如果端口还在，精准找到监听 18789 的 PID，再停一次
            if self._is_gateway_running():
                port_pid = self._get_pid_by_port(self.port)
                if port_pid:
                    self.log_message.emit(f"Port {self.port} is still in use by PID {port_pid}, forcing cleanup...")
                    self._terminate_process_tree(port_pid)
                    time.sleep(0.3)

            # 3) 最终验收
            if self._is_gateway_running():
                self.log_message.emit("Stop failed: gateway is still listening on the port")
                self._status = GatewayStatus.ERROR
                self.status_changed.emit(self._status)
                return False

            self._process = None
            self._status = GatewayStatus.STOPPED
            self.status_changed.emit(self._status)
            self.log_message.emit("Gateway stopped")
            self._external_running_hits = 0
            return True

        except Exception as e:
            self.log_message.emit(f"Error stopping gateway: {e}")
            self._status = GatewayStatus.ERROR
            self.status_changed.emit(self._status)
            self._external_running_hits = 0
            return False
    
    def restart(self) -> bool:
        """Restart the OpenClaw gateway"""
        self.log_message.emit("Restarting gateway...")
        self.stop()
        time.sleep(0.3)
        return self.start()
    
    def cleanup(self):
        """Clean up resources"""
        self._monitor.stop()
        self._monitor.wait()
