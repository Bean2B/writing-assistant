"""Supervise exactly one explicitly requested local adapter process on the local platform."""
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time

MAX_RESPONSE = 2 * 1024 * 1024


def run_adapter(runner, request, timeout):
    """Bound both running time and stdout before decoding the adapter response."""
    if os.name == "nt":
        from writing_assistant.runtime import windows_worker
        return windows_worker.run_adapter(runner, request, timeout, MAX_RESPONSE)
    with tempfile.TemporaryDirectory() as cwd, tempfile.TemporaryFile() as inp:
        inp.write(request)
        inp.seek(0)
        proc = subprocess.Popen([runner], stdin=inp, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, cwd=cwd, start_new_session=True)
        deadline = time.monotonic() + timeout
        result = bytearray()
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(proc.stdout, selectors.EVENT_READ)
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        return {"failure": "adapter_timeout"}
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    result.extend(chunk)
                    if len(result) > MAX_RESPONSE:
                        return {"failure": "response_limit"}
            remaining = max(0, deadline - time.monotonic())
            if proc.wait(timeout=remaining) != 0:
                return {"failure": "adapter_failed"}
            response = json.loads(result.decode("utf-8"))
            return {"response": response}
        except subprocess.TimeoutExpired:
            return {"failure": "adapter_timeout"}
        except (UnicodeError, ValueError, RecursionError):
            return {"failure": "invalid_response"}
        finally:
            # Close descendants' inherited descriptors as well on exit or timeout.
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.wait()
            proc.stdout.close()


def main():
    runner, destination, timeout = sys.argv[1:]
    try:
        result = run_adapter(runner, sys.stdin.buffer.read(), int(timeout))
    except OSError:
        result = {"failure": "adapter_os_error"}
    path = Path(destination)
    fd, temp_name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(result, out, ensure_ascii=True, allow_nan=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    main()
