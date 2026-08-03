"""OS-level sandbox for the Angelus shell tool.

A lightweight, dependency-free container-style sandbox built directly on Linux
namespaces (no Docker, no bubblewrap):

* ``CLONE_NEWUSER`` - unprivileged user namespace: the sandbox believes it is
  root but maps to the real OS user, so it holds no real privileges.
* ``CLONE_NEWNS``   - private mount namespace: the whole root filesystem is
  remounted read-only and only the session working directory is bind-mounted
  writable.  Anything the command does can never touch the host filesystem.
* ``CLONE_NEWNET``  - optional network namespace (``no_network``): the command
  sees only the loopback device; no host network access.

``os.unshare`` requires Python 3.12+ and a Linux kernel with unprivileged user
namespaces enabled (default on Ubuntu/WSL2/Arch; disabled on some hardened
distros).  ``mount(2)`` is invoked through ``ctypes`` because this Python build
does not expose ``os.mount``.
"""

from __future__ import annotations

import ctypes
import os
import signal
import time
from typing import Any, Callable, Optional

# mount(2) flag constants (stable across Linux kernels).
MS_RDONLY = 1
MS_NOSUID = 2
MS_NODEV = 4
MS_NOEXEC = 8
MS_BIND = 4096
MS_REMOUNT = 32

_libc = ctypes.CDLL(None, use_errno=True)
_libc.mount.argtypes = [
    ctypes.c_char_p, ctypes.c_char_p, ctypes.c_char_p,
    ctypes.c_ulong, ctypes.c_char_p,
]
_libc.mount.restype = ctypes.c_int


def _mount(source: str, target: str, flags: int) -> None:
    """Thin wrapper around mount(2); raises OSError with the errno text."""
    result = _libc.mount(
        source.encode(), target.encode(), None, flags, None,
    )
    if result != 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), target)


def _workspace_path() -> str:
    return "/tmp/angelus-sbx-ws"


def _write_id_maps(uid: int, gid: int) -> None:
    """Map sandbox uid 0 to the real OS user inside the new user namespace."""
    with open("/proc/self/setgroups", "w", encoding="utf-8") as handle:
        try:
            handle.write("deny\n")
        except OSError:
            pass
    with open("/proc/self/gid_map", "w", encoding="utf-8") as handle:
        handle.write(f"0 {gid} 1\n")
    with open("/proc/self/uid_map", "w", encoding="utf-8") as handle:
        handle.write(f"0 {uid} 1\n")


def _setup_sandbox(workdir: str, no_network: bool) -> None:
    """Run inside the forked child: create namespaces + mounts, then chdir."""
    real_uid = os.getuid()
    real_gid = os.getgid()

    # 1. User namespace first, so all later steps need no real privilege.
    os.unshare(os.CLONE_NEWUSER)
    _write_id_maps(real_uid, real_gid)
    os.unshare(os.CLONE_NEWNS)
    if no_network:
        os.unshare(os.CLONE_NEWNET)

    # 2. Writable workspace, then lock the rest of the filesystem read-only.
    #    Order matters: bind the writable workspace BEFORE remounting the root
    #    read-only, otherwise the bind inherits the read-only state.
    ws = _workspace_path()
    try:
        os.mkdir(ws)
    except FileExistsError:
        pass
    _mount(workdir, ws, MS_BIND | MS_NOSUID | MS_NODEV)
    _mount("/", "/", MS_BIND | MS_REMOUNT | MS_RDONLY | MS_NOSUID | MS_NODEV)

    # 3. Confine the default working directory to the session workspace.
    os.chdir(ws)


def _sanitised_env() -> dict[str, str]:
    """Return a copy of the environment with agent secrets removed."""
    env = dict(os.environ)
    for key in ("SSH_AUTH_SOCK", "GPG_AGENT_INFO"):
        env.pop(key, None)
    return env


def run_in_sandbox(
    command: str,
    workdir: str,
    timeout: float,
    *,
    no_network: bool = False,
    force_stop_event: Any = None,
    register_process: Optional[Callable[[int], None]] = None,
    unregister_process: Optional[Callable[[int], None]] = None,
    extra_env: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Execute ``command`` inside the OS-level sandbox.

    Returns a result dict with ``stdout``, ``stderr``, ``returncode`` and an
    optional ``error`` describing a timeout or force-stop.
    """
    out_read, out_write = os.pipe()
    err_read, err_write = os.pipe()
    pid = os.fork()
    if pid == 0:
        # -- child: build the sandbox and exec the command --
        try:
            os.close(out_read)
            os.close(err_read)
            os.dup2(out_write, 1)
            os.dup2(err_write, 2)
            os.close(out_write)
            os.close(err_write)
            os.setsid()
            _setup_sandbox(workdir, no_network)
            env = _sanitised_env()
            if extra_env:
                env.update(extra_env)
            os.execve("/bin/bash", ["bash", "-c", command], env)
        except BaseException:
            os._exit(127)

    # -- parent: monitor and collect output --
    os.close(out_write)
    os.close(err_write)
    if register_process:
        register_process(pid)

    stdout_chunks: list[bytes] = []
    stderr_chunks: list[bytes] = []
    deadline = time.time() + timeout
    error = ""
    finished = False
    try:
        while True:
            # Drain available output first.
            for fd, chunks in ((out_read, stdout_chunks), (err_read, stderr_chunks)):
                try:
                    chunk = os.read(fd, 65536)
                    if chunk:
                        chunks.append(chunk)
                except OSError:
                    pass

            waited, status = os.waitpid(pid, os.WNOHANG)
            if waited == pid:
                finished = True
                returncode = os.waitstatus_to_exitcode(status)
                break

            if force_stop_event is not None and force_stop_event.is_set():
                error = "sandbox command force-stopped"
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass
                _, _ = os.waitpid(pid, 0)
                returncode = -signal.SIGKILL
                finished = True
                break

            if time.time() >= deadline:
                error = f"command timed out after {timeout} seconds"
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass
                _, _ = os.waitpid(pid, 0)
                returncode = -signal.SIGKILL
                finished = True
                break

            time.sleep(0.05)
    finally:
        os.close(out_read)
        os.close(err_read)
        if unregister_process:
            unregister_process(pid)

    return {
        "stdout": b"".join(stdout_chunks).decode("utf-8", errors="replace"),
        "stderr": b"".join(stderr_chunks).decode("utf-8", errors="replace"),
        "returncode": returncode if finished else -1,
        "error": error or None,
    }
