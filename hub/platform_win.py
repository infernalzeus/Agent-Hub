"""Windows Job Object — guarantees spawned children die with the Hub,
even on force-kill. Single orphan-prevention seam for the whole app."""
from __future__ import annotations

import sys

from .config import logger


# ── Orphan prevention (Windows Job Object) ────────────────────────────────────
# Graceful shutdown (on_cleanup killing tracked processes) only covers the case
# where Hub exits cleanly. It does NOT cover being force-killed (Task Manager,
# `Stop-Process -Force`, a crash) — in that case children just keep running
# with no parent, which is exactly the orphaned-process problem. A Windows Job
# Object with KILL_ON_JOB_CLOSE fixes this at the OS level: every subprocess we
# spawn gets assigned to this job, and Windows kills all of them the instant
# Hub's process handle closes, no matter how Hub itself went down.

_JOB_HANDLE = None

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class _IO_COUNTERS(ctypes.Structure):
        _fields_ = [(n, ctypes.c_uint64) for n in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", _JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", _IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _JobObjectExtendedLimitInformation = 9
    _PROCESS_ALL_ACCESS = 0x1F0FFF

    def _create_kill_on_close_job():
        kernel32 = ctypes.windll.kernel32
        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None
        info = _JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        kernel32.SetInformationJobObject(
            job, _JobObjectExtendedLimitInformation, ctypes.byref(info), ctypes.sizeof(info)
        )
        return job

    def _assign_to_job(pid: int) -> None:
        if not _JOB_HANDLE:
            return
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(_PROCESS_ALL_ACCESS, False, pid)
        if handle:
            kernel32.AssignProcessToJobObject(_JOB_HANDLE, handle)
            kernel32.CloseHandle(handle)

    _JOB_HANDLE = _create_kill_on_close_job()
    if _JOB_HANDLE:
        logger.info("Orphan-prevention job object created — child processes die with Hub, always")
    else:
        logger.warning("Could not create job object — orphaned child processes are possible if Hub is force-killed")
else:
    def _assign_to_job(pid: int) -> None:
        pass

