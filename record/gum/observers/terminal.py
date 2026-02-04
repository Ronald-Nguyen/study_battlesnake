"""
Terminal Observer for headless mode - MAXIMUM CAPTURE MODE.

Captures ALL terminal activity when GUI input monitoring is unavailable.

Capture methods:
1. /proc monitoring - Captures all new processes system-wide (real-time)
2. PTY monitoring - Reads output from all terminal devices (/dev/pts/*)
3. AI CLI tracking - Special tracking for AI tools (claude, aider, cursor, etc.)
4. Bash history monitoring - Fallback for when /proc isn't available
"""

from __future__ import annotations
import asyncio
import logging
import os
import subprocess
import time
import sys
from pathlib import Path
from typing import Optional, Set, Dict
from datetime import datetime

# fcntl is Unix-only, not available on Windows
# Import conditionally to avoid errors on Windows
HAS_FCNTL = False
if sys.platform != "win32":
    try:
        import fcntl

        HAS_FCNTL = True
    except ImportError:
        HAS_FCNTL = False

from .observer import Observer  # noqa: E402
from ..schemas import Update  # noqa: E402

logger = logging.getLogger("TerminalObserver")

# AI CLI tools to monitor with special handling
AI_CLI_TOOLS = {
    "claude": "Claude CLI",
    "aider": "Aider",
    "sgpt": "Shell GPT",
    "chatgpt": "ChatGPT CLI",
    "copilot": "GitHub Copilot CLI",
    "gh copilot": "GitHub Copilot",
    "cursor": "Cursor CLI",
    "python": "Python (may contain AI)",
    "node": "Node.js (may contain AI)",
}


class TerminalObserver(Observer):
    """
    Observer for terminal activity in headless mode.

    Monitors shell history and terminal activity when GUI input is unavailable.
    """

    def __init__(
        self,
        poll_interval: float = 2.0,
        proc_poll_interval: float = 0.1,  # Fast polling for /proc (100ms)
        history_file: Optional[str] = None,
        screenshots_dir: Optional[str] = None,
        debug: bool = False,
    ):
        """
        Initialize terminal observer.

        Parameters
        ----------
        poll_interval : float
            How often to check for new terminal activity (seconds)
        history_file : str, optional
            Path to shell history file (auto-detected if None)
        screenshots_dir : str, optional
            Directory where screenshots are saved. AI session logs will be saved here.
            If None, defaults to ~/.gum/ai_sessions/
        debug : bool
            Enable debug logging
        """
        super().__init__(name="TerminalObserver")
        self.poll_interval = poll_interval
        self.proc_poll_interval = proc_poll_interval  # Faster polling for /proc
        self.debug = debug

        # Platform detection (needed for history file detection)
        import platform

        self._is_macos = platform.system() == "Darwin"
        self._is_linux = platform.system() == "Linux"
        self._is_windows = platform.system() == "Windows"

        # Detect shell history file
        if history_file:
            self.history_file = Path(history_file)
        else:
            if self._is_windows:
                # Windows: PowerShell history or CMD history
                # PowerShell history is in: $env:APPDATA\Microsoft\Windows\PowerShell\PSReadLine\ConsoleHost_history.txt
                # CMD history is harder to access, but we can try PowerShell
                ps_history = (
                    Path(os.environ.get("APPDATA", ""))
                    / "Microsoft"
                    / "Windows"
                    / "PowerShell"
                    / "PSReadLine"
                    / "ConsoleHost_history.txt"
                )
                if ps_history.exists():
                    self.history_file = ps_history
                else:
                    self.history_file = None
            else:
                shell = os.environ.get("SHELL", "/bin/bash")
                if "bash" in shell:
                    self.history_file = Path.home() / ".bash_history"
                elif "zsh" in shell:
                    self.history_file = Path.home() / ".zsh_history"
                else:
                    self.history_file = None

        # Check if script command is available (hypothesis E)
        self._script_available = False
        try:
            result = subprocess.run(["which", "script"], capture_output=True, timeout=2)
            self._script_available = result.returncode == 0
        except Exception:
            pass

        # Check history file permissions (hypothesis C)
        self._history_writable = False
        if self.history_file and self.history_file.exists():
            try:
                self._history_writable = os.access(self.history_file, os.W_OK)
            except Exception:
                pass

        self._last_history_size = 0
        self._last_check_time = time.time()

        # Platform detection already done above for history file detection

        # /proc monitoring state (Linux) or ps command (macOS) or PowerShell (Windows)
        self._proc_available = Path("/proc").exists()
        self._ps_available = (
            self._check_ps_available() if (self._is_macos or self._is_windows) else False
        )
        self._powershell_available = (
            self._check_powershell_available() if self._is_windows else False
        )
        self._seen_pids: Set[int] = set()
        self._our_pid = os.getpid()
        # Only ignore our own processes and very common system utilities
        # Keep the filter minimal to capture more user commands
        self._ignored_commands = {
            "gum",  # Our own process
            "sleep",
            "watch",  # Background/monitoring
            "ps",
            "grep",  # Our monitoring commands
        }

        # AI CLI monitoring state
        self._ai_cli_sessions: Dict[int, dict] = {}  # pid -> session info
        # Store AI session logs in the same directory as screenshots
        if screenshots_dir:
            screenshots_path = Path(os.path.abspath(os.path.expanduser(screenshots_dir)))
            self._ai_sessions_dir = screenshots_path / "ai_sessions"
        else:
            # Fallback to home directory if screenshots_dir not provided
            self._ai_sessions_dir = Path.home() / ".gum" / "ai_sessions"
        self._ai_sessions_dir.mkdir(parents=True, exist_ok=True)

        # PTY monitoring state for maximum capture
        self._pty_buffers: Dict[str, str] = {}  # pty path -> accumulated output
        self._pty_last_read: Dict[str, float] = {}  # pty path -> last read time
        self._monitored_ptys: Set[str] = set()

        # Process output capture (read from /proc/[pid]/fd/*)
        self._process_outputs: Dict[int, dict] = {}  # pid -> output info

        if self._proc_available:
            # Initialize seen PIDs with current processes (Linux)
            self._seen_pids = self._get_current_pids()
            logger.info("Monitoring /proc for new processes (real-time capture)")
        elif self._is_windows:
            # Initialize seen PIDs with current processes (Windows)
            # Try even if PowerShell check failed
            self._seen_pids = self._get_current_pids_windows()
            if self._seen_pids:
                logger.info(
                    f"Monitoring PowerShell for new processes (Windows mode) - {len(self._seen_pids)} processes found"
                )
            else:
                logger.warning("Windows: Could not get initial PIDs, will retry during monitoring")
        elif self._ps_available:
            # Initialize seen PIDs with current processes (macOS)
            self._seen_pids = self._get_current_pids_macos()
            logger.info("Monitoring ps for new processes (macOS mode)")

        if self.history_file and self.history_file.exists():
            self._last_history_size = self.history_file.stat().st_size
            logger.info(f"Also monitoring terminal history: {self.history_file}")
        else:
            logger.warning(f"Terminal history file not found: {self.history_file}")
            if not self._proc_available:
                logger.info("Terminal activity logging will be limited")

    async def _worker(self) -> None:
        """Main monitoring loop."""
        log = logging.getLogger("TerminalObserver")
        if self.debug:
            log.setLevel(logging.INFO)

        log.info("Terminal observer started (headless mode)")

        if self._proc_available:
            log.info(
                f"[OK] /proc monitoring enabled - polling every {self.proc_poll_interval}s for real-time capture"
            )
        else:
            # Warn about bash history limitation only if /proc isn't available
            if self.history_file and "bash" in str(self.history_file):
                log.warning(
                    "[!] Terminal capture limitation: Bash history is only written when shell sessions end, "
                    "not in real-time. Commands run in other terminal sessions won't be captured until "
                    "those sessions exit."
                )

        # Use separate counters for /proc (fast) and history (slow) polling
        history_check_counter = 0
        history_check_interval = int(
            self.poll_interval / self.proc_poll_interval
        )  # e.g., 20 for 2s/0.1s

        # MAXIMUM CAPTURE MODE - check everything frequently
        ai_check_counter = 0
        ai_check_interval = 5  # Every 0.5 seconds (5 * 0.1s)

        pty_check_counter = 0
        pty_check_interval = 10  # Every 1 second

        while self._running:
            try:
                # Check /proc (Linux) or ps (macOS) or PowerShell (Windows) for process monitoring
                if self._proc_available:
                    await self._check_proc_activity()
                elif self._is_windows:
                    # On Windows, try PowerShell monitoring (even if check failed, try anyway)
                    if self._powershell_available:
                        await self._check_powershell_activity_windows()
                    else:
                        # PowerShell check failed, but try anyway as fallback
                        await self._check_powershell_activity_windows()
                elif self._ps_available:
                    await self._check_ps_activity_macos()

                # Check AI CLI sessions frequently for output capture
                ai_check_counter += 1
                if ai_check_counter >= ai_check_interval:
                    if self._ai_cli_sessions:
                        await self._check_ai_cli_sessions()
                    ai_check_counter = 0

                # Try PTY/process output capture periodically
                pty_check_counter += 1
                if pty_check_counter >= pty_check_interval:
                    await self._capture_pty_output()
                    pty_check_counter = 0

                # Check history less frequently (fallback)
                history_check_counter += 1
                if history_check_counter >= history_check_interval:
                    await self._check_history_activity()
                    history_check_counter = 0

            except Exception as e:
                log.error(f"Error checking terminal activity: {e}", exc_info=True)

            # Use fast polling interval
            await asyncio.sleep(
                self.proc_poll_interval if self._proc_available else self.poll_interval
            )

        log.info("Terminal observer stopped")

    def _check_ps_available(self) -> bool:
        """Check if ps command is available (for macOS only)."""
        if self._is_windows:
            # Don't check for ps on Windows
            return False
        try:
            result = subprocess.run(["which", "ps"], capture_output=True, timeout=2)
            return result.returncode == 0
        except Exception:
            return False

    def _check_powershell_available(self) -> bool:
        """Check if PowerShell is available (for Windows)."""

        if not self._is_windows:
            return False

        # Try multiple methods to check PowerShell availability
        methods = [
            # Method 1: Simple exit command
            (["powershell", "-Command", "exit"], "exit"),
            # Method 2: Check if PowerShell exists
            (["powershell", "-NoProfile", "-Command", "$PSVersionTable"], "version"),
            # Method 3: Try pwsh (PowerShell Core) if regular PowerShell fails
            (["pwsh", "-Command", "exit"], "pwsh_exit"),
        ]

        for cmd, method_name in methods:
            try:

                result = subprocess.run(
                    cmd, capture_output=True, timeout=5, text=True  # Increased timeout
                )

                if result.returncode == 0:
                    return True
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue
        return False

    def _get_current_pids(self) -> Set[int]:
        """Get set of currently running process IDs (Linux /proc)."""
        pids = set()
        try:
            for entry in os.listdir("/proc"):
                if entry.isdigit():
                    pids.add(int(entry))
        except Exception:
            pass
        return pids

    def _get_current_pids_macos(self) -> Set[int]:
        """Get set of currently running process IDs (macOS ps command)."""
        pids = set()
        try:
            # Get all process IDs
            result = subprocess.run(
                ["ps", "-axo", "pid"], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n")[1:]:  # Skip header
                    line = line.strip()
                    if line.isdigit():
                        pids.add(int(line))
        except Exception:
            pass
        return pids

    def _get_process_cmdline_macos(self, pid: int) -> Optional[str]:
        """Get command line for a process (macOS)."""
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "command="], capture_output=True, text=True, timeout=2
            )
            if result.returncode == 0:
                cmdline = result.stdout.strip()
                if cmdline:
                    return cmdline
        except Exception:
            pass
        return None

    def _get_process_cmdline(self, pid: int) -> Optional[str]:
        """Get command line for a process."""
        try:
            cmdline_path = Path(f"/proc/{pid}/cmdline")
            if cmdline_path.exists():
                with open(cmdline_path, "rb") as f:
                    cmdline = f.read()
                    # cmdline is null-separated
                    args = cmdline.decode("utf-8", errors="ignore").split("\x00")
                    # Filter empty strings and join
                    args = [a for a in args if a]
                    if args:
                        return " ".join(args)
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            pass
        return None

    def _is_user_command(self, cmdline: str) -> bool:
        """Check if this looks like a user-initiated command."""
        if not cmdline:
            return False

        # Get the base command name
        parts = cmdline.split()
        if not parts:
            return False

        base_cmd = Path(parts[0]).name

        # Skip our own processes and common system utilities
        if base_cmd in self._ignored_commands:
            return False

        # Skip kernel threads and system processes (Linux)
        if cmdline.startswith("[") or cmdline.startswith("/usr/lib/systemd"):
            return False

        # Skip macOS system processes - filter out system framework paths
        macos_system_prefixes = (
            "/System/Library/",
            "/usr/libexec/",
            "/usr/sbin/",
            "/Library/Apple/",
            "/System/Volumes/Preboot/",
            "/System/Applications/",  # System app extensions
            "/Library/Developer/",
            "/Applications/Xcode.app/",
        )
        if cmdline.startswith(macos_system_prefixes):
            return False

        # Skip Windows system processes - filter out system paths
        windows_system_prefixes = (
            "C:\\Windows\\System32\\",
            "C:\\Windows\\SysWOW64\\",
            "C:\\Program Files\\WindowsApps\\",
            "C:\\Windows\\WinSxS\\",
            "C:\\ProgramData\\",
        )
        if any(cmdline.startswith(prefix) for prefix in windows_system_prefixes):
            return False

        # Skip common macOS system commands by name
        macos_system_commands = {
            "cfprefsd",
            "deleted",
            "deleted_helper",
            "installd",
            "system_installd",
            "trustd",
            "trustdFileHelper",
            "secinitd",
            "containermanagerd",
            "containermanagerd_system",
            "pkd",
            "usermanagerd",
            "feedbackd",
            "mdworker",
            "mdworker_shared",
            "mds",
            "mds_stores",
            "triald_system",
            "sysmond",
            "logd_helper",
            "coresymbolicationd",
            "ReportCrash",
            "ReportMemoryException",
            "aneuserd",
            "geodMachServiceBridge",
            "backupd-helper",
            "AssetCache",
            "cloudd",
            "cdpd",
        }
        if base_cmd in macos_system_commands:
            return False

        # Skip common Windows system commands by name
        windows_system_commands = {
            "svchost",
            "dwm",
            "csrss",
            "winlogon",
            "services",
            "lsass",
            "smss",
            "spoolsv",
            "explorer",
            "conhost",
            "RuntimeBroker",
            "SearchIndexer",
            "SearchProtocolHost",
            "SearchFilterHost",
            "WmiPrvSE",
            "dllhost",
            "taskhostw",
            "sihost",
            "audiodg",
            "WUDFHost",
            "ApplicationFrameHost",
            "SystemSettings",
        }
        if base_cmd.lower() in windows_system_commands:
            return False

        # Skip very short commands that are likely internal
        if len(cmdline) < 2:
            return False

        return True

    def _is_ai_cli(self, cmdline: str) -> Optional[str]:
        """Check if command is an AI CLI tool. Returns tool name if matched."""
        if not cmdline:
            return None

        cmdline_lower = cmdline.lower()
        parts = cmdline.split()
        if not parts:
            return None

        base_cmd = Path(parts[0]).name.lower()

        # Check if the base command matches any AI CLI tool
        for tool_cmd, tool_name in AI_CLI_TOOLS.items():
            if base_cmd == tool_cmd or tool_cmd in cmdline_lower:
                return tool_name

        return None

    def _get_process_tty(self, pid: int) -> Optional[str]:
        """Get the TTY device for a process."""
        try:
            stat_path = Path(f"/proc/{pid}/stat")
            if stat_path.exists():
                with open(stat_path, "r") as f:
                    stat = f.read()
                    # Field 7 is tty_nr
                    parts = stat.split()
                    if len(parts) > 6:
                        tty_nr = int(parts[6])
                        if tty_nr > 0:
                            # Convert tty_nr to device path
                            major = (tty_nr >> 8) & 0xFF
                            minor = tty_nr & 0xFF
                            if major == 136:  # pts
                                return f"/dev/pts/{minor}"
        except Exception:
            pass
        return None

    async def _start_ai_cli_capture(self, pid: int, tool_name: str, cmdline: str) -> None:
        """Start capturing output from an AI CLI process."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        session_file = (
            self._ai_sessions_dir / f"{tool_name.lower().replace(' ', '_')}_{timestamp}_{pid}.log"
        )

        session_info = {
            "pid": pid,
            "tool": tool_name,
            "cmdline": cmdline,
            "start_time": time.time(),
            "log_file": str(session_file),
            "last_read_pos": 0,
        }
        self._ai_cli_sessions[pid] = session_info

        # Write header to session file
        with open(session_file, "w") as f:
            f.write(f"=== {tool_name} Session ===\n")
            f.write(f"Command: {cmdline}\n")
            f.write(f"Started: {datetime.now().isoformat()}\n")
            f.write(f"PID: {pid}\n")
            f.write("=" * 50 + "\n\n")

        # Send notification about AI CLI session start
        await self.update_queue.put(
            Update(
                content=f"ai_cli_session_start: {tool_name} (PID: {pid}) - {cmdline}",
                content_type="ai_activity",
            )
        )

        logger.info(f"[AI] Started monitoring {tool_name} session (PID: {pid})")
        logger.info(f"   Session log: {session_file}")

    async def _capture_ai_cli_output(self, pid: int) -> Optional[str]:
        """Try to capture recent output from an AI CLI process."""
        if pid not in self._ai_cli_sessions:
            return None

        session = self._ai_cli_sessions[pid]

        try:
            # Try to read from the process's stdout fd
            stdout_path = Path(f"/proc/{pid}/fd/1")
            if stdout_path.exists():
                # Check if it's a pipe or regular file we can read
                try:
                    # Read what we can (this is limited and may not work for all cases)
                    real_path = stdout_path.resolve()
                    if real_path.is_file():
                        with open(real_path, "r", errors="ignore") as f:
                            f.seek(session["last_read_pos"])
                            new_content = f.read()
                            if new_content:
                                session["last_read_pos"] = f.tell()
                                return new_content
                except (PermissionError, OSError):
                    pass
        except Exception:
            pass

        return None

    async def _check_ai_cli_sessions(self) -> None:
        """Check on active AI CLI sessions and capture output (MAXIMUM CAPTURE)."""
        ended_sessions = []

        for pid, session in self._ai_cli_sessions.items():
            # Check if process is still running
            if not Path(f"/proc/{pid}").exists():
                ended_sessions.append(pid)
                continue

            # Try multiple capture methods
            output = await self._capture_ai_cli_output(pid)
            aggressive_output = await self._monitor_ai_process_output(pid, session["tool"])

            combined_output = []
            if output:
                combined_output.append(output)
            if aggressive_output:
                combined_output.append(aggressive_output)

            if combined_output:
                full_output = "\n".join(combined_output)
                # Append to session log
                with open(session["log_file"], "a") as f:
                    f.write(f"[{datetime.now().isoformat()}]\n{full_output}\n\n")

                # Send update with captured content
                await self.update_queue.put(
                    Update(
                        content=f"ai_cli_output: [{session['tool']}] {full_output[:1000]}",
                        content_type="ai_activity",
                    )
                )

        # Clean up ended sessions
        for pid in ended_sessions:
            session = self._ai_cli_sessions.pop(pid)
            duration = time.time() - session["start_time"]

            # Finalize session log
            with open(session["log_file"], "a") as f:
                f.write(f"\n{'=' * 50}\n")
                f.write(f"Session ended: {datetime.now().isoformat()}\n")
                f.write(f"Duration: {duration:.1f}s\n")

            # Send notification about session end
            await self.update_queue.put(
                Update(
                    content=(
                        f"ai_cli_session_end: {session['tool']} (PID: {pid}) - "
                        f"Duration: {duration:.1f}s - Log: {session['log_file']}"
                    ),
                    content_type="ai_activity",
                )
            )

            logger.info(
                f"[AI] {session['tool']} session ended (PID: {pid}, Duration: {duration:.1f}s)"
            )

    def _get_process_ptys(self) -> Dict[int, str]:
        """Get all processes and their associated PTY devices."""
        process_ptys = {}
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                if pid == self._our_pid:
                    continue

                # Check /proc/[pid]/fd/0 (stdin) to find the PTY
                try:
                    fd0_path = Path(f"/proc/{pid}/fd/0")
                    if fd0_path.exists():
                        real_path = os.readlink(fd0_path)
                        if "/dev/pts/" in real_path:
                            process_ptys[pid] = real_path
                except (PermissionError, FileNotFoundError, OSError):
                    pass
        except Exception:
            pass
        return process_ptys

    async def _capture_pty_output(self) -> None:
        """Capture output from all active PTY devices."""
        try:
            pts_dir = Path("/dev/pts")
            if not pts_dir.exists():
                return

            # Get all pts devices
            for pty_entry in pts_dir.iterdir():
                if pty_entry.name == "ptmx":
                    continue

                pty_path = str(pty_entry)

                # Try to read from /proc to find processes using this PTY
                # and capture their output
                await self._try_capture_from_pty(pty_path)

        except Exception as e:
            if self.debug:
                logger.debug(f"PTY capture error: {e}")

    async def _try_capture_from_pty(self, pty_path: str) -> None:
        """Try to capture output associated with a PTY."""
        # Find processes using this PTY and capture their output
        try:
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                pid = int(entry)
                if pid == self._our_pid:
                    continue

                # Check if this process uses the PTY
                try:
                    fd0_link = os.readlink(f"/proc/{pid}/fd/0")
                    if fd0_link != pty_path:
                        continue

                    # Try to read stdout (fd/1) - this is where output goes
                    await self._capture_process_output(pid)

                except (PermissionError, FileNotFoundError, OSError):
                    pass
        except Exception:
            pass

    async def _capture_process_output(self, pid: int) -> None:
        """Try to capture stdout/stderr from a process."""
        # Read from /proc/[pid]/fd/1 (stdout) and /proc/[pid]/fd/2 (stderr)
        for fd_num, fd_name in [(1, "stdout"), (2, "stderr")]:
            try:
                fd_path = f"/proc/{pid}/fd/{fd_num}"
                real_path = os.readlink(fd_path)

                # Skip if it's a PTY (we can't read PTY output directly like this)
                if "/dev/pts/" in real_path:
                    continue

                # If it's a pipe or file, try to read
                if real_path.startswith("pipe:") or os.path.isfile(real_path):
                    try:
                        # Try non-blocking read (Unix only - fcntl not available on Windows)
                        with open(fd_path, "r", errors="ignore") as f:
                            if HAS_FCNTL:
                                # Set non-blocking mode (Unix)
                                fd = f.fileno()
                                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

                            try:
                                # Read content (may block on Windows, but that's okay)
                                content = f.read(4096)
                                if content:
                                    await self.update_queue.put(
                                        Update(
                                            content=f"process_output: [PID:{pid}:{fd_name}] {content[:500]}",
                                            content_type="terminal_output",
                                        )
                                    )
                            except (BlockingIOError, IOError):
                                # Expected on Unix when no data available
                                pass
                    except Exception:
                        pass
            except (PermissionError, FileNotFoundError, OSError):
                pass

    async def _monitor_ai_process_output(self, pid: int, tool_name: str) -> Optional[str]:
        """
        Aggressively try to capture AI process output using multiple methods.
        """
        output_parts = []

        # Method 1: Read from /proc/[pid]/fd/*
        for fd_num in [1, 2]:  # stdout, stderr
            try:
                fd_path = f"/proc/{pid}/fd/{fd_num}"
                if not os.path.exists(fd_path):
                    continue

                real_path = os.readlink(fd_path)

                # If redirected to a file, read from it
                if os.path.isfile(real_path):
                    try:
                        with open(real_path, "r", errors="ignore") as f:
                            content = f.read()
                            if content:
                                output_parts.append(f"[fd{fd_num}] {content}")
                    except Exception:
                        pass
            except Exception:
                pass

        # Method 2: Check /proc/[pid]/environ for any output files
        try:
            env_path = f"/proc/{pid}/environ"
            if os.path.exists(env_path):
                with open(env_path, "r", errors="ignore") as f:
                    environ = f.read()
                    # Look for log files or output files in environment
                    for var in environ.split("\x00"):
                        if "LOG" in var or "OUTPUT" in var:
                            output_parts.append(f"[env] {var}")
        except Exception:
            pass

        # Method 3: Check /proc/[pid]/cwd for recent files
        try:
            cwd_path = f"/proc/{pid}/cwd"
            if os.path.exists(cwd_path):
                cwd = os.readlink(cwd_path)
                # Look for recent log files in cwd
                cwd_dir = Path(cwd)
                if cwd_dir.exists():
                    for log_file in cwd_dir.glob("*.log"):
                        try:
                            mtime = log_file.stat().st_mtime
                            if time.time() - mtime < 60:  # Modified in last minute
                                with open(log_file, "r", errors="ignore") as f:
                                    content = f.read()[-1000:]  # Last 1000 chars
                                    if content:
                                        output_parts.append(f"[log:{log_file.name}] {content}")
                        except Exception:
                            pass
        except Exception:
            pass

        return "\n".join(output_parts) if output_parts else None

    async def _check_proc_activity(self) -> int:
        """Check /proc for new processes. Returns count of new commands captured."""
        if not self._proc_available:
            return 0

        captured_count = 0
        current_pids = self._get_current_pids()
        new_pids = current_pids - self._seen_pids

        for pid in new_pids:
            if pid == self._our_pid:
                continue

            cmdline = self._get_process_cmdline(pid)

            if cmdline and self._is_user_command(cmdline):

                # Check if this is an AI CLI tool - start special monitoring
                ai_tool = self._is_ai_cli(cmdline)
                if ai_tool:
                    if pid not in self._ai_cli_sessions:
                        await self._start_ai_cli_capture(pid, ai_tool, cmdline)

                update = Update(content=f"terminal_command: {cmdline}", content_type="input_text")
                await self.update_queue.put(update)

                captured_count += 1
                if self.debug:
                    logger.info(f"Captured process: {cmdline[:50]}...")

        # Update seen PIDs (keep only currently existing ones to avoid memory growth)
        self._seen_pids = current_pids
        return captured_count

    async def _check_ps_activity_macos(self) -> int:
        """Check for new processes using ps command (macOS). Returns count of new commands captured."""
        if not self._ps_available:
            return 0

        captured_count = 0
        current_pids = self._get_current_pids_macos()
        new_pids = current_pids - self._seen_pids

        for pid in new_pids:
            if pid == self._our_pid:
                continue

            cmdline = self._get_process_cmdline_macos(pid)

            if cmdline and self._is_user_command(cmdline):
                # Check if this is an AI CLI tool - start special monitoring
                ai_tool = self._is_ai_cli(cmdline)
                if ai_tool:
                    if pid not in self._ai_cli_sessions:
                        await self._start_ai_cli_capture(pid, ai_tool, cmdline)

                update = Update(content=f"terminal_command: {cmdline}", content_type="input_text")
                await self.update_queue.put(update)

                captured_count += 1
                if self.debug:
                    logger.info(f"Captured process (macOS): {cmdline[:50]}...")

        # Update seen PIDs
        self._seen_pids = current_pids
        return captured_count

    def _get_current_pids_windows(self) -> Set[int]:
        """Get set of currently running process IDs (Windows PowerShell)."""
        pids = set()

        # Try both powershell and pwsh
        for ps_cmd in ["powershell", "pwsh"]:
            try:
                # Use PowerShell to get all process IDs
                ps_script = "Get-Process | Select-Object -ExpandProperty Id"
                result = subprocess.run(
                    [ps_cmd, "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )

                if result.returncode == 0:
                    for line in result.stdout.strip().split("\n"):
                        line = line.strip()
                        if line.isdigit():
                            pids.add(int(line))
                    # Success, return immediately
                    return pids
            except subprocess.TimeoutExpired:
                continue
            except Exception:
                continue

        return pids

    def _get_process_cmdline_windows(self, pid: int) -> Optional[str]:
        """Get command line for a process (Windows PowerShell)."""

        # Try both WMI and Get-CimInstance (newer method)
        methods = [
            (f'(Get-WmiObject Win32_Process -Filter "ProcessId = {pid}").CommandLine', "WMI"),
            (
                f'(Get-CimInstance Win32_Process -Filter "ProcessId = {pid}").CommandLine',
                "CimInstance",
            ),
        ]

        for ps_cmd in ["powershell", "pwsh"]:
            for ps_script, method_name in methods:
                try:
                    result = subprocess.run(
                        [ps_cmd, "-NoProfile", "-Command", ps_script],
                        capture_output=True,
                        text=True,
                        timeout=3,
                    )

                    if result.returncode == 0:
                        cmdline = result.stdout.strip()
                        if cmdline and cmdline != "":
                            return cmdline
                except subprocess.TimeoutExpired:
                    continue
                except Exception:
                    continue

        return None

    async def _check_powershell_activity_windows(self) -> int:
        """Check for new processes using PowerShell (Windows). Returns count of new commands captured."""
        # Try even if check failed - the check might have been too strict

        captured_count = 0
        current_pids = self._get_current_pids_windows()
        new_pids = current_pids - self._seen_pids

        for pid in new_pids:
            if pid == self._our_pid:
                continue

            cmdline = self._get_process_cmdline_windows(pid)

            if cmdline and self._is_user_command(cmdline):
                # Check if this is an AI CLI tool - start special monitoring
                ai_tool = self._is_ai_cli(cmdline)
                if ai_tool:
                    if pid not in self._ai_cli_sessions:
                        await self._start_ai_cli_capture(pid, ai_tool, cmdline)

                update = Update(content=f"terminal_command: {cmdline}", content_type="input_text")
                await self.update_queue.put(update)

                captured_count += 1
                if self.debug:
                    logger.info(f"Captured process (Windows): {cmdline[:50]}...")

        # Update seen PIDs
        self._seen_pids = current_pids
        return captured_count

    async def _check_history_activity(self) -> None:
        """Check for new terminal commands in bash history (fallback method)."""

        # Try to force history flush from all active bash sessions (hypothesis D)
        shell = os.environ.get("SHELL", "/bin/bash")
        if "bash" in shell:
            try:
                # Try to flush history from all active bash sessions
                # This only works if we can send commands to those sessions, which we can't
                # But we try anyway in case it helps
                subprocess.run(["bash", "-c", "history -a"], timeout=1, capture_output=True)

                # Also try to find and flush from other bash sessions via their history files
                # This is a workaround: try to trigger history write by checking if any
                # terminal devices are active and attempting to send history flush command
                try:
                    # Find active terminal devices
                    result = subprocess.run(["who"], capture_output=True, timeout=1, text=True)
                    if result.returncode == 0:
                        # For each active terminal, we could try to send a command, but that's complex
                        # Instead, we'll just note that there are active terminals
                        pass
                except Exception:
                    pass
            except Exception:
                pass

        if not self.history_file or not self.history_file.exists():
            return

        try:
            current_size = self.history_file.stat().st_size

            # Check for active shell sessions (hypothesis B)
            try:
                # Count processes with shell in name
                result = subprocess.run(
                    ["pgrep", "-f", shell.split("/")[-1]], capture_output=True, timeout=1
                )
                active_shells = (
                    len(result.stdout.decode().strip().split("\n")) if result.stdout else 0
                )
            except Exception:
                active_shells = -1

            # If file grew, read new lines
            if current_size > self._last_history_size:
                with open(self.history_file, "r", encoding="utf-8", errors="ignore") as f:
                    # Seek to last known position
                    f.seek(self._last_history_size)
                    new_lines = f.readlines()

                    for line in new_lines:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            # Send command as update
                            await self.update_queue.put(
                                Update(
                                    content=f"terminal_command: {line}", content_type="input_text"
                                )
                            )
                            if self.debug:
                                logger.info(f"Captured terminal command: {line[:50]}...")

                    self._last_history_size = current_size
            else:
                # Check if history file modification time changed (might indicate activity)
                # even if size didn't change (could be overwritten)
                try:
                    current_mtime = self.history_file.stat().st_mtime
                    if not hasattr(self, "_last_history_mtime"):
                        self._last_history_mtime = current_mtime

                    # If mtime changed but size didn't, history might have been rewritten
                    if current_mtime != self._last_history_mtime:
                        # Re-read the entire file to see if content changed
                        with open(self.history_file, "r", encoding="utf-8", errors="ignore") as f:
                            all_lines = f.readlines()
                            # Compare with what we've seen (simplified: just check if we missed anything)
                            # This is a fallback for when history is rewritten rather than appended
                            pass  # For now, just track mtime changes
                        self._last_history_mtime = current_mtime
                except Exception:
                    pass

                # Send periodic activity indicator even if no new commands
                time_since_check = time.time() - self._last_check_time
                if time_since_check >= 30:  # Every 30 seconds
                    await self.update_queue.put(
                        Update(
                            content=f"terminal_activity: system_active (no new commands in last {int(time_since_check)}s). "
                            f"Note: Bash history is only written when shell sessions end. "
                            f"Active shell sessions: {active_shells if 'active_shells' in locals() else 'unknown'}",
                            content_type="input_text",
                        )
                    )
                    self._last_check_time = time.time()
        except Exception as e:
            logger.debug(f"Error reading history: {e}")
