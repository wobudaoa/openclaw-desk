"""Start, stop, and monitor the local OpenClaw gateway process."""

import logging
import locale
import os
import shutil
import subprocess
import threading
import time
from collections import deque
from enum import Enum
from typing import Optional

import psutil
from PySide6.QtCore import QObject, QThread, Signal

logger = logging.getLogger("openclaw.desktop.gateway_manager")


class GatewayStatus(Enum):
    STOPPED = "Stopped"
    STARTING = "Starting"
    LOADING = "Loading"
    RUNNING = "Running"
    STOPPING = "Stopping"
    ERROR = "Error"


class GatewayMonitor(QThread):
    """Background thread to monitor gateway status."""

    status_changed = Signal(GatewayStatus)

    def __init__(self, gateway_manager):
        super().__init__()
        self.gateway_manager = gateway_manager
        self._running = True

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
    """Thin process wrapper around the `openclaw gateway` CLI."""

    status_changed = Signal(GatewayStatus)
    log_message = Signal(str)
    process_output = Signal(str, str)

    def __init__(self, port: int = 18789):
        super().__init__()
        self.port = port
        self._process: Optional[subprocess.Popen] = None
        self._status = GatewayStatus.STOPPED
        self._external_running_hits = 0
        self._recent_stderr_output = deque(maxlen=80)
        self._reported_process_exit = False
        self._monitor = GatewayMonitor(self)
        self._monitor.status_changed.connect(self._on_status_changed)
        self._monitor.start()

    def _on_status_changed(self, status: GatewayStatus):
        self._status = status
        self.status_changed.emit(status)

    def _set_status(self, status: GatewayStatus):
        self._status = status
        self.status_changed.emit(status)

    def _reset_runtime_state(self):
        """Clear transient runtime flags before a fresh start/after a clean stop."""
        self._external_running_hits = 0
        self._reported_process_exit = False

    def _clear_process(self):
        """Forget the tracked child process after it exits or is terminated."""
        self._process = None

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

        process_exit_code = self._process.poll()
        if process_exit_code is None and self._is_port_in_use(self.port):
            self._external_running_hits = 0
            return GatewayStatus.RUNNING

        if process_exit_code is not None:
            if not self._reported_process_exit and self._status not in (
                GatewayStatus.STOPPING,
                GatewayStatus.STOPPED,
            ):
                self._reported_process_exit = True
                self._record_process_output(
                    "stderr",
                    f"Gateway process exited with code {process_exit_code}",
                )
            self._external_running_hits = 0
            if self._status == GatewayStatus.STOPPING:
                return GatewayStatus.STOPPED
            if self._status in (
                GatewayStatus.STARTING,
                GatewayStatus.LOADING,
                GatewayStatus.RUNNING,
                GatewayStatus.ERROR,
            ):
                return GatewayStatus.ERROR

        self._external_running_hits = 0
        return GatewayStatus.STOPPED

    def _is_port_in_use(self, port: int) -> bool:
        try:
            for conn in psutil.net_connections():
                if hasattr(conn.laddr, "port") and conn.laddr.port == port:
                    if conn.status == "LISTEN":
                        return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

        try:
            import socket

            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("localhost", port))
                return result == 0
        except Exception:
            pass
        return False

    def _openclaw_command_candidates(self) -> list[list[str]]:
        candidates = []
        for command_name in ("openclaw.cmd", "openclaw"):
            resolved = shutil.which(command_name)
            if resolved:
                candidates.append([resolved])

        for path in (r"C:\nvm4w\nodejs\openclaw.cmd", r"C:\nvm4w\nodejs\openclaw"):
            if os.path.exists(path):
                candidates.append([path])

        seen = set()
        unique_candidates = []
        for command in candidates:
            key = tuple(command)
            if key not in seen:
                seen.add(key)
                unique_candidates.append(command)
        return unique_candidates

    def is_openclaw_installed(self) -> bool:
        return bool(self._openclaw_command_candidates())

    def get_openclaw_command_locations(self) -> list[str]:
        return [command[0] for command in self._openclaw_command_candidates()]

    def _find_openclaw_cmd(self) -> list[str]:
        candidates = self._openclaw_command_candidates()
        if candidates:
            return candidates[0]
        raise FileNotFoundError("Cannot find openclaw command")

    def clear_recent_output(self):
        self._recent_stderr_output.clear()

    def get_recent_stderr_text(self, limit: int = 80) -> str:
        lines = list(self._recent_stderr_output)[-limit:]
        cleaned_lines = [
            line[len("[stderr] ") :] if line.startswith("[stderr] ") else line
            for line in lines
        ]
        return "\n".join(cleaned_lines)

    def _decode_process_output(self, message) -> str:
        if isinstance(message, str):
            return message

        preferred_encoding = locale.getpreferredencoding(False) or "utf-8"
        encodings = [
            "utf-8",
            preferred_encoding,
            "gb18030",
            "cp936",
            "utf-16-le",
            "latin-1",
        ]

        for encoding in encodings:
            try:
                return message.decode(encoding)
            except UnicodeDecodeError:
                continue

        return message.decode("utf-8", errors="replace")

    def _record_process_output(self, stream_name: str, message):
        line = self._decode_process_output(message).rstrip()
        if not line:
            return
        prefixed_line = f"[{stream_name}] {line}"
        if stream_name == "stderr":
            self._recent_stderr_output.append(prefixed_line)
        if stream_name == "stderr":
            logger.error("gateway %s", line)
        else:
            logger.info("gateway %s", line)
        self.process_output.emit(stream_name, line)

    def _read_process_pipe(self, stream_name: str, pipe):
        try:
            for raw_line in iter(pipe.readline, b""):
                self._record_process_output(stream_name, raw_line)
        except Exception as exc:
            logger.exception("failed to read gateway %s: %s", stream_name, exc)
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _popen_kwargs(self) -> dict:
        """Use the same detached console-less launch settings everywhere."""
        return {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "cwd": os.path.expanduser("~"),
            "env": os.environ.copy(),
            "creationflags": (
                subprocess.CREATE_NO_WINDOW
                if hasattr(subprocess, "CREATE_NO_WINDOW")
                else 0
            ),
            "bufsize": 1,
        }

    def _start_output_readers(self):
        if self._process is None:
            return

        for stream_name, pipe in (
            ("stdout", self._process.stdout),
            ("stderr", self._process.stderr),
        ):
            if pipe is None:
                continue
            threading.Thread(
                target=self._read_process_pipe,
                args=(stream_name, pipe),
                daemon=True,
            ).start()

    def _start_command(self) -> list[str]:
        """Build the exact CLI command used to launch the gateway."""
        return self._find_openclaw_cmd() + ["gateway", "--port", str(self.port)]

    def _mark_start_failure(self, message: str) -> bool:
        self._set_status(GatewayStatus.ERROR)
        self.log_message.emit(message)
        self._clear_process()
        self._external_running_hits = 0
        return False

    def start(self) -> bool:
        if self._is_port_in_use(self.port):
            self._external_running_hits = 2
            self.log_message.emit(
                f"Port {self.port} is already in use, gateway may already be running"
            )
            self._set_status(GatewayStatus.RUNNING)
            return True

        try:
            self._set_status(GatewayStatus.STARTING)
            self.clear_recent_output()
            self._reset_runtime_state()

            cmd = self._start_command()
            self.log_message.emit(f"Command: {' '.join(cmd)}")

            self._process = subprocess.Popen(cmd, **self._popen_kwargs())
            self._start_output_readers()

            for _ in range(80):
                if self._is_port_in_use(self.port):
                    self._external_running_hits = 0
                    self._set_status(GatewayStatus.RUNNING)
                    self.log_message.emit(
                        f"Gateway started successfully on port {self.port}"
                    )
                    return True

                if self._process.poll() is not None:
                    break

                time.sleep(0.1)

            return self._mark_start_failure("Failed to start gateway")

        except Exception as exc:
            self._record_process_output("stderr", str(exc))
            self.log_message.emit(f"Error starting gateway: {exc}")
            return self._mark_start_failure(f"Error starting gateway: {exc}")

    def _terminate_process_tree(self, pid: int, timeout: float = 3.0) -> None:
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
        try:
            for conn in psutil.net_connections(kind="inet"):
                if conn.status == psutil.CONN_LISTEN:
                    if conn.laddr and getattr(conn.laddr, "port", None) == port:
                        return conn.pid
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        return None

    def stop(self) -> bool:
        try:
            if self._process is None and not self._is_port_in_use(self.port):
                self.log_message.emit("Gateway is not running")
                self._set_status(GatewayStatus.STOPPED)
                return True

            self._set_status(GatewayStatus.STOPPING)
            self.log_message.emit("Stopping gateway...")

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

            self._clear_process()

            if self._is_port_in_use(self.port):
                port_pid = self._get_pid_by_port(self.port)
                if port_pid:
                    self.log_message.emit(
                        f"Port {self.port} is still in use by PID {port_pid}, forcing cleanup..."
                    )
                    self._terminate_process_tree(port_pid)
                    time.sleep(0.3)

            if self._is_port_in_use(self.port):
                self.log_message.emit(
                    "Stop failed: gateway is still listening on the port"
                )
                self._set_status(GatewayStatus.ERROR)
                return False

            self._clear_process()
            self._set_status(GatewayStatus.STOPPED)
            self.log_message.emit("Gateway stopped")
            self._reset_runtime_state()
            return True

        except Exception as exc:
            self._record_process_output("stderr", str(exc))
            self.log_message.emit(f"Error stopping gateway: {exc}")
            self._set_status(GatewayStatus.ERROR)
            self._external_running_hits = 0
            return False

    def restart(self) -> bool:
        self.log_message.emit("Restarting gateway...")
        self.stop()
        time.sleep(0.3)
        return self.start()

    def cleanup(self):
        self._monitor.stop()
        self._monitor.wait()
