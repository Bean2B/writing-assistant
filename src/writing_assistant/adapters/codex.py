"""One bounded local Codex process. Authentication stays inside the CLI."""

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import stat
import subprocess
import tempfile
import time
from urllib.parse import unquote, urlsplit

from ..core.errors import AssistantError, require
from ..core.jsonio import canonical, decode

# Supported Codex exec versions and required flags.
QUALIFIED = frozenset({"0.164.0-alpha.11.1", "0.166.0-alpha.6"})
REQUIRED_FLAGS = ("--ephemeral", "--ignore-user-config", "--json", "--output-last-message",
                  "--sandbox", "--skip-git-repo-check", "--strict-config", "--cd")
DISABLED = ("apps", "plugins", "hooks", "memories", "shell_tool", "multi_agent",
            "browser_use", "computer_use", "in_app_browser", "image_generation",
            "code_mode_host", "skill_search", "tool_suggest", "workspace_dependencies",
            "view_image", "sleep_tool", "goals")
CODES = frozenset({"codex_missing", "capability_unsupported", "codex_model_failure",
                   "codex_timeout", "codex_cancelled", "codex_malformed", "codex_unknown"})
STREAM_LIMIT = 4 * 1024 * 1024
FINAL_LIMIT = 1024 * 1024
PROBE_LIMIT = 128 * 1024
REASONING_EFFORTS = ("low", "medium", "high", "xhigh", "max", "ultra")
LAUNCH_SETTINGS = ('project_doc_max_bytes=0', 'web_search="disabled"', 'notify=[]',
                   'skills.include_instructions=false', 'skills.bundled.enabled=false',
                   'features.code_mode.enabled=false')

# Existing CLI auth stays in HOME/CODEX_HOME and the OS credential store. Do not
# forward API keys, caller bridges, shell/loader controls or arbitrary prefixes.
CHILD_ENV_ALLOWLIST = frozenset({
    "PATH", "HOME", "CODEX_HOME",
    "LANG", "LANGUAGE", "LC_ALL", "LC_COLLATE", "LC_CTYPE", "LC_MESSAGES",
    "LC_MONETARY", "LC_NUMERIC", "LC_TIME",
    "TMPDIR", "TMP", "TEMP",
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "CODEX_CA_CERTIFICATE", "SSL_CERT_FILE",
})
# Routing may contain credentials; trust paths may identify private local files.
PRIVATE_CHILD_ENV = frozenset({
    "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
    "CODEX_CA_CERTIFICATE", "SSL_CERT_FILE",
})
PROXY_AUTH_ENV = frozenset({"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                            "http_proxy", "https_proxy", "all_proxy"})
UNSUPPORTED_ACTIVITY = frozenset({
    "command_execution", "file_change", "mcp_tool_call", "web_search",
    "collab_tool_call",
})


def _private_environment_fragments(child_environment):
    """Snapshot routing credentials from the exact launch mapping, not globals."""
    fragments = set()
    for name in PRIVATE_CHILD_ENV:
        value = child_environment.get(name)
        if not value:
            continue
        fragments.add(value)
        if name in PROXY_AUTH_ENV:
            try:
                proxy = urlsplit(value if "://" in value else "//" + value)
                userinfo = proxy.netloc.rsplit("@", 1)[0] if "@" in proxy.netloc else ""
                for fragment in (userinfo, proxy.username, proxy.password):
                    if fragment:
                        fragments.update((fragment, unquote(fragment)))
                if userinfo:
                    fragments.add(base64.b64encode(unquote(userinfo).encode("utf-8")).decode("ascii"))
            except ValueError:
                # Malformed routing is not permission to collect another source.
                pass
    encoded = set()
    for part in fragments:
        for variant in (part, json.dumps(part, ensure_ascii=True)[1:-1],
                        json.dumps(part, ensure_ascii=False)[1:-1]):
            encoded.add(variant.encode("utf-8", "backslashreplace"))
    return tuple(sorted(encoded, key=len, reverse=True))


def _diagnostic_bytes(raw, *, private_fragments):
    """Redact recognized environment fragments from diagnostic bytes only."""
    if not private_fragments:
        return raw, False
    # One pass removes fragments without reprocessing replacements or expanding
    # bounded process streams when a configured credential is very short.
    retained, count = re.subn(b"|".join(re.escape(part) for part in private_fragments), b"", raw)
    return retained, bool(count)


def _diagnostic(stage, error, *, private_fragments):
    complete = True
    try:
        raw = str(error).encode("utf-8", "backslashreplace")
    except Exception:
        raw, complete = b"exception_message_unavailable", False
    try:
        number = error.errno
    except Exception:
        number = None
    _, redacted = _diagnostic_bytes(raw, private_fragments=private_fragments)
    diagnostic = {"stage": stage, "type": type(error).__name__[:128],
                  "errno": number if type(number) is int else None,
                  "message": "environment_value_redacted" if redacted else raw[:8192].decode("utf-8", "ignore"),
                  "message_complete": complete and len(raw) <= 8192 and not redacted}
    if redacted:
        diagnostic["message_redacted"] = True
    return diagnostic


def _probe_bytes(raw, *, private_fragments, complete=True):
    raw, redacted = _diagnostic_bytes(raw or b"", private_fragments=private_fragments)
    observed = {"base64": base64.b64encode(raw[:PROBE_LIMIT]).decode("ascii"),
                "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "complete": complete and len(raw) <= PROBE_LIMIT and not redacted}
    if redacted:
        observed["redacted"] = True
    return observed


def environment():
    """Forward only CLI location, existing auth, locale, temp and proxy/CA inputs.

    Do not attach this mapping to observations or summaries.
    This limits inherited environment data, not the child's OS/provider access.
    """
    return {name: os.environ[name] for name in CHILD_ENV_ALLOWLIST if name in os.environ}


def _configuration_args():
    args = []
    for setting in LAUNCH_SETTINGS:
        args += ["-c", setting]
    for feature in DISABLED:
        args += ["--disable", feature]
    return args


def doctor(executable="codex", *, _diagnostics=None):
    scope = {"probe_scope": "local-version-help-and-feature-flags",
             "runtime_readiness": "not_checked"}
    binary = shutil.which(executable)
    if binary is None:
        if _diagnostics is not None:
            _diagnostics.append({"stage": "locate", "code": "codex_missing",
                                 "executable": executable, "launched": False})
        return {**scope, "status": "missing", "code": "codex_missing", "live_supported": False}

    def probe(tokens, stage, *, configuration_home=None):
        item = {"stage": stage, "argv": [binary, *tokens], "returncode": None}
        child_environment = environment()
        if configuration_home is not None:
            # features list has no --ignore-user-config. Its private, empty
            # config root reproduces exec's ignored user config without reading
            # or changing the user's settings or authentication store.
            child_environment["CODEX_HOME"] = str(configuration_home)
        private_fragments = _private_environment_fragments(child_environment)
        try:
            result = subprocess.run(item["argv"], capture_output=True, timeout=5,
                                    env=child_environment, check=False,
                                    **({"cwd": configuration_home} if configuration_home is not None else {}))
            item.update(returncode=result.returncode,
                        stdout=_probe_bytes(result.stdout, private_fragments=private_fragments),
                        stderr=_probe_bytes(result.stderr, private_fragments=private_fragments))
            return result, private_fragments
        except (OSError, subprocess.TimeoutExpired) as error:
            complete = not isinstance(error, subprocess.TimeoutExpired)
            item.update(diagnostic=_diagnostic(stage, error, private_fragments=private_fragments),
                        stdout=_probe_bytes(getattr(error, "stdout", None), complete=complete,
                                            private_fragments=private_fragments),
                        stderr=_probe_bytes(getattr(error, "stderr", None), complete=complete,
                                            private_fragments=private_fragments))
            raise
        finally:
            if _diagnostics is not None:
                _diagnostics.append(item)

    try:
        version, version_fragments = probe(["--version"], "version")
        help_result, _ = probe(["exec", "--help"], "exec-help")
    except (OSError, subprocess.TimeoutExpired):
        return {**scope, "status": "unknown", "code": "capability_unsupported", "live_supported": False}
    # Qualification is decided from original protocol bytes, never redacted text.
    match = re.fullmatch(rb"codex-cli ([A-Za-z0-9.+_-]+)\s*", version.stdout)
    if match is None or version.returncode or help_result.returncode:
        return {**scope, "status": "unsupported", "code": "capability_unsupported", "live_supported": False}
    found = match[1].decode()
    missing = [f for f in REQUIRED_FLAGS if f.encode() not in help_result.stdout]
    supported = found in QUALIFIED and not missing
    configuration = "not_checked"
    if supported:
        try:
            with tempfile.TemporaryDirectory(prefix="writing-assistant-config-", dir="/tmp") as temporary:
                features, _ = probe(["features", "list", *_configuration_args()], "launch-configuration",
                                    configuration_home=Path(temporary).resolve())
            states = {}
            for line in features.stdout.splitlines():
                match_feature = re.fullmatch(rb"(code_mode|code_mode_host)\s+.+?\s+(true|false)\s*", line)
                if match_feature:
                    name = match_feature[1].decode()
                    if name in states:
                        states[name] = "unknown"
                    else:
                        states[name] = match_feature[2].decode()
            configuration = ("feature_flags_verified" if features.returncode == 0 and len(features.stdout) <= PROBE_LIMIT
                             and states == {"code_mode": "false", "code_mode_host": "false"}
                             else "unsupported" if features.returncode == 0
                             and any(value == "true" for value in states.values()) else "unknown")
        except (OSError, subprocess.TimeoutExpired):
            configuration = "unknown"
        supported = configuration == "feature_flags_verified"
    _, version_redacted = _diagnostic_bytes(match[1], private_fragments=version_fragments)
    observed = {**scope, "status": "supported" if supported else "unknown" if configuration == "unknown" else "unsupported",
                "version": None if version_redacted else found,
                "surface": "codex-exec", "missing_flags": missing, "live_supported": supported,
                "launch_configuration": configuration,
                "code": None if supported else "capability_unsupported", "model_observed": None}
    if version_redacted:
        observed["version_redacted"] = True
    return observed


def qualify(executable="codex"):
    probes = []
    observed = doctor(executable, _diagnostics=probes)
    if not observed["live_supported"]:
        error = AssistantError(observed["code"])
        error.qualification = {"capability": observed, "probes": probes}
        raise error
    return observed


def validate_options(model, timeout, cancelled=None, *, reasoning_effort=None):
    require(type(timeout) in (int, float) and 0 < timeout <= 600, "invalid_timeout")
    require(cancelled is None or callable(cancelled), "invalid_request")
    require(model is None or (type(model) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", model)),
            "invalid_model")
    require(reasoning_effort is None or (type(reasoning_effort) is str
            and reasoning_effort in REASONING_EFFORTS), "invalid_reasoning_effort")


def command(binary, cwd, output, model=None, *, reasoning_effort=None):
    args = [binary, "exec", "--strict-config", "--ignore-user-config", "--ephemeral",
            "--skip-git-repo-check", "--sandbox", "read-only", "--cd", str(cwd),
            "--json", "--color", "never", "--output-last-message", str(output)]
    args += _configuration_args()
    if model is not None:
        args += ["--model", model]
    if reasoning_effort is not None:
        args += ["-c", "model_reasoning_effort=" + json.dumps(reasoning_effort)]
    return args + ["-"]


def _final(path):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return b"", False, False
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid():
            return b"", False, False
        raw = os.read(fd, FINAL_LIMIT + 1)
        return raw[:FINAL_LIMIT], True, len(raw) <= FINAL_LIMIT
    finally:
        os.close(fd)


def _terminal_error(event):
    """Only a failed turn establishes a terminal protocol failure.

    An item.completed/error can precede a successful text turn, including the
    Code Mode host-disabled diagnostic. Retain it without stopping the process
    or overriding the eventual turn result.
    """
    if event.get("type") == "turn.failed":
        return "codex_model_failure", {"type": "turn.failed", "code": "turn_failed"}
    return None


def _interpret(result):
    events = []
    try:
        for line in result["stdout"].splitlines():
            require(len(line) <= 2 * FINAL_LIMIT and len(events) < 8192, "codex_malformed")
            event = decode(line)
            require(type(event) is dict and type(event.get("type")) is str, "codex_malformed")
            events.append(event)
    except (AssistantError, UnicodeError, ValueError, RecursionError):
        return "codex_malformed"
    completed = [e for e in events if e["type"] == "turn.completed"]
    failed = [e for e in events if e["type"] == "turn.failed"]
    result["usage"] = completed[0].get("usage") if len(completed) == 1 else None
    result["tool_activity_observed"] = any(
        e["item"].get("type") in UNSUPPORTED_ACTIVITY
        for e in events if isinstance(e.get("item"), dict))
    if result["tool_activity_observed"]:
        return "capability_unsupported"
    if len(completed) > 1 or len(failed) > 1 or (completed and failed):
        return "codex_unknown"
    for event in events:
        terminal = _terminal_error(event)
        if terminal is not None:
            result["terminal_event"] = terminal[1]
            return terminal[0]
    if failed or (result["returncode"] != 0 and not completed):
        return "codex_model_failure"
    if result["returncode"] != 0 or not completed:
        return "codex_unknown"
    try:
        result["output"].decode("utf-8")
    except UnicodeError:
        return "codex_malformed"
    return "completed" if result["output_exists"] and result["output_complete"] and result["output"] else "codex_malformed"


def execute(prompt, *, executable="codex", model=None, reasoning_effort=None, timeout=120, cancelled=None):
    """Return exact final bytes and filtered diagnostics. Never retry or adopt."""
    require(type(prompt) is bytes and len(prompt) <= 6 * 1024 * 1024, "input_limit")
    validate_options(model, timeout, cancelled, reasoning_effort=reasoning_effort)
    qualify(executable)
    started = time.monotonic()
    result = {"status": "codex_unknown", "stdout": b"", "stderr": b"", "output": b"",
              "returncode": None, "usage": None, "model_observed": None, "model_requested": model,
              "model_selection_source": "explicit-command" if model is not None else "codex-cli-default-user-config-ignored",
              "reasoning_effort_requested": reasoning_effort, "reasoning_effort_observed": None,
              "reasoning_effort_selection_source": "explicit-command" if reasoning_effort is not None else "codex-cli-default-user-config-ignored",
              "local_process_stopped": True, "backend_stop_confirmed": False,
              "signals": [], "streams_complete": True, "output_exists": False,
              "output_complete": False, "tool_activity_observed": False,
              "local_diagnostics": []}
    if cancelled is not None and cancelled():
        return {**result, "status": "codex_cancelled", "launched": False, "elapsed_seconds": 0}
    with tempfile.TemporaryDirectory(prefix="writing-assistant-codex-", dir="/tmp") as temporary:
        cwd = Path(temporary).resolve()
        output = cwd / "final.txt"
        binary = shutil.which(executable)
        if binary is None:
            return {**result, "status": "codex_missing", "launched": False,
                    "elapsed_seconds": time.monotonic() - started,
                    "local_diagnostics": [{"stage": "locate-before-spawn", "code": "codex_missing"}]}
        args = command(binary, cwd, output, model, reasoning_effort=reasoning_effort)
        result["argv"] = args
        child_environment = environment()
        private_fragments = _private_environment_fragments(child_environment)
        try:
            process = subprocess.Popen(args, cwd=cwd, env=child_environment, stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        except OSError as error:
            return {**result, "status": "codex_missing" if isinstance(error, FileNotFoundError) else "codex_unknown",
                    "launched": False, "elapsed_seconds": time.monotonic() - started,
                    "local_diagnostics": [_diagnostic("spawn", error, private_fragments=private_fragments)]}
        result["launched"] = True
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        reason, sent, signal_time, offset = None, 0, 0.0, 0
        stdout_scanned, event_count = 0, 0
        try:
            with selectors.DefaultSelector() as selector:
                for stream, name, event in ((process.stdout, "stdout", selectors.EVENT_READ),
                                            (process.stderr, "stderr", selectors.EVENT_READ),
                                            (process.stdin, "stdin", selectors.EVENT_WRITE)):
                    os.set_blocking(stream.fileno(), False)
                    selector.register(stream, event, name)
                while selector.get_map() or process.poll() is None:
                    now = time.monotonic()
                    if reason is None:
                        if cancelled is not None and cancelled():
                            reason = "codex_cancelled"
                        elif now - started >= timeout:
                            reason = "codex_timeout"
                    if reason and (sent == 0 or now - signal_time >= 1):
                        if sent >= 3:
                            result["streams_complete"] = False
                            break
                        sig = (signal.SIGINT, signal.SIGTERM, signal.SIGKILL)[sent]
                        try:
                            os.killpg(process.pid, sig)
                            result["signals"].append({"signal": sig.name, "sent": True})
                        except (ProcessLookupError, PermissionError):
                            result["signals"].append({"signal": sig.name, "sent": False})
                        sent += 1
                        signal_time = now
                    for key, _ in selector.select(0.05):
                        stream, name = key.fileobj, key.data
                        if name == "stdin":
                            try:
                                offset += os.write(stream.fileno(), prompt[offset:offset + 65536])
                            except BrokenPipeError:
                                offset = len(prompt)
                            if offset == len(prompt):
                                selector.unregister(stream)
                                stream.close()
                        else:
                            raw = os.read(stream.fileno(), 65536)
                            if not raw:
                                selector.unregister(stream)
                                stream.close()
                                continue
                            room = STREAM_LIMIT - len(buffers[name])
                            buffers[name].extend(raw[:room])
                            if len(raw) > room:
                                reason = reason or "codex_malformed"
                                result["streams_complete"] = False
                            if name == "stdout" and reason is None:
                                while True:
                                    end = buffers[name].find(b"\n", stdout_scanned)
                                    if end < 0:
                                        if len(buffers[name]) - stdout_scanned > 2 * FINAL_LIMIT:
                                            reason = "codex_malformed"
                                        break
                                    line = bytes(buffers[name][stdout_scanned:end])
                                    stdout_scanned = end + 1
                                    event_count += 1
                                    try:
                                        require(len(line) <= 2 * FINAL_LIMIT and event_count <= 8192,
                                                "codex_malformed")
                                        event = decode(line)
                                        require(type(event) is dict and type(event.get("type")) is str,
                                                "codex_malformed")
                                    except (AssistantError, UnicodeError, ValueError, RecursionError):
                                        reason = "codex_malformed"
                                        break
                                    terminal = _terminal_error(event)
                                    if terminal is not None:
                                        reason, result["terminal_event"] = terminal
                                        break
        except KeyboardInterrupt as error:
            result["local_diagnostics"].append(_diagnostic("process-io", error, private_fragments=private_fragments))
            reason = "codex_cancelled"
            result["streams_complete"] = False
        except Exception as error:
            result["local_diagnostics"].append(_diagnostic("process-io", error, private_fragments=private_fragments))
            reason = reason or "codex_unknown"
            result["streams_complete"] = False
        finally:
            # Covers selector construction/setup as well as draining and control flow.
            if reason is not None or process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    result["signals"].append({"signal": "SIGKILL", "sent": True})
                except (ProcessLookupError, PermissionError):
                    pass
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                result["local_process_stopped"] = False
            for stream in (process.stdin, process.stdout, process.stderr):
                stream.close()
        result.update({name: bytes(raw) for name, raw in buffers.items()})
        result["returncode"] = process.returncode
        try:
            result["output"], result["output_exists"], result["output_complete"] = _final(output)
        except OSError as error:
            result["local_diagnostics"].append(_diagnostic("read-final", error, private_fragments=private_fragments))
            reason = reason or "codex_unknown"
        result["elapsed_seconds"] = time.monotonic() - started
        interpreted = _interpret(result)
        result["status"] = reason or interpreted
        if not result["local_process_stopped"]:
            result["status"] = "codex_unknown"
        # Interpret the original protocol before filtering diagnostic streams.
        # The authorized final message is a separate exact-byte user artifact.
        for name in ("stdout", "stderr"):
            result[name], redacted = _diagnostic_bytes(result[name], private_fragments=private_fragments)
            if redacted:
                result[name + "_redacted"] = True
                result["streams_complete"] = False
        if result["usage"] is not None and _diagnostic_bytes(
                canonical(result["usage"]), private_fragments=private_fragments)[1]:
            result["usage"] = None
            result["usage_redacted"] = True
        return result
