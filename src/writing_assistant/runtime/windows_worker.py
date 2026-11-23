"""Supervise a Windows adapter and its descendants inside one kernel job."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
                ("flags", wintypes.DWORD), ("min_working_set", ctypes.c_size_t),
                ("max_working_set", ctypes.c_size_t), ("active_processes", wintypes.DWORD),
                ("affinity", ctypes.c_size_t), ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io_counters", ctypes.c_uint64 * 6),
                ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
                ("peak_process_memory", ctypes.c_size_t), ("peak_job_memory", ctypes.c_size_t)]


kernel = ctypes.WinDLL("kernel32", use_last_error=True)


def api(name, result, *parameters):
    f = getattr(kernel, name)
    f.restype, f.argtypes = result, parameters
    return f


new_job = api("CreateJobObjectW", wintypes.HANDLE, ctypes.c_void_p, wintypes.LPCWSTR)
set_limits = api("SetInformationJobObject", wintypes.BOOL, wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
assign = api("AssignProcessToJobObject", wintypes.BOOL, wintypes.HANDLE, wintypes.HANDLE)
open_process = api("OpenProcess", wintypes.HANDLE, wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
close = api("CloseHandle", wintypes.BOOL, wintypes.HANDLE)


def check(value):
    if not value:
        raise ctypes.WinError(ctypes.get_last_error())
    return value


def adapter_entry(runner, request):
    # The parent sends this byte only after assigning this trusted helper to its job.
    if sys.stdin.buffer.read(1) != b"1":
        return 1
    path = Path(runner)
    if path.suffix.lower() == ".exe":
        command = [runner]
    elif path.suffix.lower() == ".py" or path.name == "writing-assistant-provider":
        command = [sys.executable, "-X", "utf8", runner]
    else:
        return 1
    with open(request, "rb") as source:
        return subprocess.run(command, stdin=source).returncode


def run_adapter(runner, request, timeout, limit):
    with tempfile.TemporaryDirectory() as cwd, ThreadPoolExecutor(max_workers=1) as reader:
        source = Path(cwd) / "request.json"
        source.write_bytes(request)
        job = check(new_job(None, None))
        proc = None
        try:
            limits = ExtendedLimits()
            limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            check(set_limits(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)))
            proc = subprocess.Popen([sys.executable, "-I", __file__, runner, str(source)],
                                    cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            handle = check(open_process(0x0101, False, proc.pid))  # SET_QUOTA | TERMINATE
            try:
                check(assign(job, handle))
            finally:
                close(handle)
            deadline = time.monotonic() + timeout
            proc.stdin.write(b"1")
            proc.stdin.close()
            data = reader.submit(proc.stdout.read, limit + 1).result(timeout=timeout)
            if len(data) > limit:
                return {"failure": "response_limit"}
            if proc.wait(timeout=max(0, deadline - time.monotonic())):
                return {"failure": "adapter_failed"}
            return {"response": json.loads(data.decode("utf-8"))}
        except (FutureTimeout, subprocess.TimeoutExpired):
            return {"failure": "adapter_timeout"}
        except (UnicodeError, ValueError, RecursionError):
            return {"failure": "invalid_response"}
        finally:
            close(job)
            if proc is not None:
                # Also covers a failure to assign the waiting helper to its job.
                if proc.poll() is None:
                    proc.kill()
                proc.wait()
                proc.stdin.close()
                proc.stdout.close()


if __name__ == "__main__":
    sys.exit(adapter_entry(*sys.argv[1:]))
