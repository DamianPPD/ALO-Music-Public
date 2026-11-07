"""External, opt-in observer for the unchanged restart-regression child.

Put this directory on PYTHONPATH and call ``install()`` from sitecustomize.
ALO_RESTART_TRACE_DIR enables the observer. ALO_RESTART_CHILD_SCRIPT points to
the exact source passed to ``python -c``; its hash is compared with orig_argv.
ALO_RESTART_TRACE_INTERVAL controls repeated native faulthandler dumps (10s).
ALO_RESTART_TRACE_AUDIT=0 disables sqlite/subprocess audit observations.

Designed for CPython 3.12, including the target 3.12.10. This module never
wraps application functions/Qt slots, changes Qt connections, touches music,
changes safety settings, creates a Python thread, or writes to stdout/stderr.
Every JSONL record is flushed to the OS for recovery after process termination. Trace I/O and monitoring do affect
timing; a traced success is not evidence that an intermittent hang is fixed.
No locals, SQL, command arguments, exception messages, tags, or audio bytes
are dumped. File locators are represented only by a stable truncated hash.
"""

from __future__ import annotations

import ast
import atexit
import faulthandler
import gc
import hashlib
import os
from pathlib import Path
import re
import sys
import threading
import time
import weakref


_state = None
_MISSING = object()


def _plain_fields(obj):
    """Read a real instance dictionary without invoking a custom __getattr__."""
    try:
        value = object.__getattribute__(obj, "__dict__")
        return value if type(value) is dict else {}
    except BaseException:
        return {}


def _code_word(value):
    return (value if type(value) is str and len(value) <= 100
            and re.fullmatch(r"[A-Z][A-Z0-9_]*", value) else None)


def _summary(obj):
    """An allowlist: never stringify an application value or exception."""
    result = {"type": type(obj).__name__}
    if obj is None or type(obj) in (bool, int):
        result["value"] = obj
    elif type(obj) in (tuple, list, dict):
        result["count"] = len(obj)
    elif type(obj) is str:
        word = _code_word(obj)
        if word is not None:
            result["code"] = word
    elif type(obj).__module__.startswith("audio_library_organizer."):
        # The relevant result classes are application dataclasses; descriptors
        # below are their plain slots/fields, not application properties.
        for name in ("status", "reason", "cancelled", "is_confirmed"):
            try:
                value = object.__getattribute__(obj, name)
            except BaseException:
                continue
            if type(value) is bool:
                result[name] = value
            elif (word := _code_word(value)) is not None:
                result[name] = word
            elif name == "reason" and type(value) is str and value:
                result["reason_present"] = True
    return result


def _locator(value):
    if not isinstance(value, (str, bytes, os.PathLike)):
        return {"type": type(value).__name__}
    try:
        encoded = os.fsencode(value)
        return {"locator_id": hashlib.sha256(encoded).hexdigest()[:16],
                "mp3": encoded.lower().endswith(b".mp3")}
    except BaseException:
        return {"type": type(value).__name__}


def _call_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return (prefix + "." if prefix else "") + node.attr
    return ""


def _child_markers(source):
    markers = {}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.stmt):
            continue
        label = type(node).__name__
        calls = [_call_name(part.func) for part in ast.walk(node)
                 if isinstance(part, ast.Call)]
        if calls:
            label += ":" + ",".join(dict.fromkeys(filter(None, calls)))[:200]
        markers.setdefault(node.lineno, label)
    return markers


class _Observer:
    def __init__(self, directory):
        self.pid = os.getpid()
        self.main_ident = threading.get_ident()
        self.lock = threading.RLock()
        self.enabled = True
        self.sequence = 0
        self.next_call = 0
        self.active = {}
        self.selected = {}
        self.line_counts = {}
        self.native_counts = {}
        self.qt_threads = {}
        self.qt_pool = None
        self.last_qt = {"pool": "not_observed"}
        self.last_snapshot_ns = 0
        self.main_code = None
        self.markers = {}
        self.child_expected = False
        self.child_matches = None
        self.tool_id = None
        self.events = sys.monitoring.events
        directory.mkdir(parents=True, exist_ok=True)
        self.output = (directory / f"child-{self.pid}.jsonl").open(
            "a", encoding="utf-8", buffering=1)
        self.fault_output = (directory / f"child-{self.pid}.faulthandler.log").open(
            "a", encoding="utf-8", buffering=1)
        try:
            self.interval = max(1.0, float(os.environ.get("ALO_RESTART_TRACE_INTERVAL", "10")))
            if not self.interval < float("inf"):
                self.interval = 10.0
        except (ValueError, OverflowError):
            self.interval = 10.0
        source_path = os.environ.get("ALO_RESTART_CHILD_SCRIPT")
        if source_path:
            source = Path(source_path).read_text(encoding="utf-8")
            self.child_expected = True
            arguments = getattr(sys, "orig_argv", ())
            command = next((arguments[i + 1] for i, value in enumerate(arguments[:-1])
                            if value == "-c"), None)
            self.child_matches = source == command
            self.child_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
            self.markers = _child_markers(source)
            expected = compile(source, "<string>", "exec")
            self.main_code = (expected.co_code, expected.co_names)
        else:
            self.child_hash = None

    def emit(self, stage, event, **fields):
        if not self.enabled:
            return
        try:
            import json
            with self.lock:
                self.sequence += 1
                record = {**fields, "pid": self.pid, "python_thread_id": threading.get_ident(),
                          "native_thread_id": threading.get_native_id(),
                          "monotonic_ns": time.monotonic_ns(), "seq": self.sequence,
                          "stage": stage, "event": event}
                self.output.write(json.dumps(record, ensure_ascii=True,
                                             separators=(",", ":")) + "\n")
                self.output.flush()
        except BaseException:
            # An observer failure must not change the application's result.
            self.enabled = False

    def location(self, code):
        filename = code.co_filename.replace("\\", "/")
        if "/audio_library_organizer/" in filename:
            filename = "audio_library_organizer/" + filename.split("/audio_library_organizer/", 1)[1]
        elif filename != "<string>":
            filename = Path(filename).name
        return {"file": filename, "function": code.co_qualname,
                "first_line": code.co_firstlineno}

    def kind(self, code):
        filename = code.co_filename.replace("\\", "/")
        name, qual = code.co_name, code.co_qualname
        if name.startswith("<") and not (filename == "<string>" and name == "<module>"):
            return None
        if filename == "<string>" and name == "<module>":
            if self.main_code is None or (code.co_code, code.co_names) == self.main_code:
                return "child"
        if filename.endswith("/threading.py") and name == "_shutdown":
            return "shutdown"
        if filename.endswith("/subprocess.py") and qual.startswith("Popen."):
            if name in {"__init__", "_execute_child", "communicate", "_communicate",
                        "wait", "_wait", "kill", "terminate", "__del__"}:
                return "subprocess"
        if "/audio_library_organizer/" not in filename:
            return None
        relative = filename.split("/audio_library_organizer/", 1)[1]
        if relative == "ui/main_window.py":
            if qual == "MainWindow.__init__" or (qual.startswith("MainWindow.") and (
                    any(part in name for part in ("file_check", "output", "check_library"))
                    or name in {"closeEvent", "_thread_done", "_job_failed", "refresh_data",
                                "_open_review", "_rebind_active_profile", "_select_saved_track"})):
                return "application"
        elif relative in {"ui/library_page.py", "ui/player.py"}:
            if name == "__init__" or any(part in name for part in (
                    "select_track", "show_detail", "cover", "cancel_context", "read_context")):
                return "application"
        elif relative == "ui/workers.py":
            if name in {"run", "cancel", "__init__", "forward_finished", "forward_failed"}:
                return "application"
        elif relative == "audio/identity.py":
            if name in {"inspect_audio", "_decode", "_decode_windows", "_find_decoder"}:
                return "application"
        elif relative == "safety/windows_output_lease.py":
            if name not in {"active", "accepted", "reason", "owned_count", "failed_handles",
                            "active_for", "cancelled", "_live_locked", "_adopt_handle"}:
                return "application"
        elif relative == "safety/windows_file_identity.py":
            if name in {"_open_path", "open", "close", "material_pair", "locator_proof"}:
                return "application"
        elif relative in {"storage/database.py", "storage/migrations.py"}:
            if name not in {"quoted", "create_tracks_sql"}:
                return "application"
        elif relative == "storage/repository.py":
            if name in {"__init__", "initialize", "list_managed_bindings", "read_context",
                        "adopted_assessment_snapshot", "file_check_snapshot", "get_track",
                        "library_id", "sync_availability"}:
                return "application"
        elif relative == "storage/managed_bindings.py":
            if name in {"read_managed_bindings", "create_managed_schema", "validate_managed_schema"}:
                return "application"
        elif relative in {"jobs/file_reconciliation.py", "jobs/output_session.py",
                          "jobs/managed_files.py"}:
            if name in {"check_library", "_pending_output_check", "prepare_delivery",
                        "context_matches", "material_matches", "database_safe",
                        "read_material", "recheck_read_path", "resolve_read_path"}:
                return "application"
        elif "cover" in name:
            return "application"
        return None

    def frame(self, code):
        frame = sys._getframe(1)
        for _ in range(8):
            if frame is None or frame.f_code is code:
                return frame
            frame = frame.f_back
        return None

    def details(self, code, frame):
        if frame is None:
            return {}
        local = frame.f_locals
        result = {}
        if code.co_name in {"inspect_audio", "_decode", "connect", "__init__"}:
            for field in ("path", "database_path"):
                if field in local:
                    result[field] = _locator(local[field])
        owner = local.get("self")
        fields = _plain_fields(owner)
        if code.co_filename.replace("\\", "/").endswith("/subprocess.py"):
            for field in ("pid", "returncode"):
                value = fields.get(field)
                if value is None or type(value) is int:
                    result["process_" + field] = value
        if type(owner).__name__ == "WindowsOutputLease":
            # Do not acquire the lease's lock or call any of its properties.
            for field in ("_owner", "_active", "_revoked", "_close_attempted", "_acked", "_claimed"):
                value = fields.get(field, _MISSING)
                if type(value) in (bool, int):
                    result[field] = value
            if (reason := _code_word(fields.get("_reason"))) is not None:
                result["lease_reason"] = reason
            result["owned_handle_count"] = len(fields.get("_handles", ()))
        thread = fields.get("_thread")
        if thread is not None and type(thread).__name__ == "QThread":
            try:
                self.qt_threads[id(thread)] = weakref.ref(thread)
            except TypeError:
                pass
        for field in ("result", "checked", "assessment"):
            if field in local:
                result["local_" + field] = _summary(local[field])
        return result

    def qt_snapshot(self):
        # Never construct a pool/app, import Qt, process events, or wait here.
        core = sys.modules.get("PySide6.QtCore")
        shiboken = sys.modules.get("shiboken6")
        if core is None or shiboken is None:
            return {"available": False}
        try:
            app = core.QCoreApplication.instance()
            if app is None or not shiboken.isValid(app) or core.QCoreApplication.closingDown():
                return {"available": False, "closing_or_no_app": True,
                        "last_observation": self.last_qt}
            result = {"available": True, "threads": []}
            pool = self.qt_pool() if self.qt_pool is not None else None
            if pool is not None and shiboken.isValid(pool):
                result["pool"] = {"active": pool.activeThreadCount(),
                                  "max": pool.maxThreadCount(),
                                  "expiry_timeout_ms": pool.expiryTimeout()}
            else:
                result["pool"] = "not_observed_or_deleted"
            for key, reference in list(self.qt_threads.items()):
                thread = reference()
                if thread is None or not shiboken.isValid(thread):
                    self.qt_threads.pop(key, None)
                    continue
                result["threads"].append({"object_id": key,
                                          "running": thread.isRunning(),
                                          "finished": thread.isFinished()})
            self.last_qt = result
            return result
        except BaseException as exc:
            return {"snapshot_error_type": type(exc).__name__, "last_observation": self.last_qt}

    def snapshot(self, reason, *, qt=True):
        try:
            frames = sys._current_frames()
            threads = []
            # enumerate() does not manufacture a DummyThread for the caller.
            for thread in threading.enumerate():
                fields = _plain_fields(thread)
                ident = fields.get("_ident")
                frame = frames.get(ident)
                entry = {"python_thread_id": ident,
                         "native_thread_id": fields.get("_native_id"),
                         "type": type(thread).__name__, "daemon": fields.get("_daemonic"),
                         "stopped": fields.get("_is_stopped"), "main": ident == self.main_ident}
                if frame is not None:
                    entry["frame"] = {**self.location(frame.f_code), "line": frame.f_lineno}
                threads.append(entry)
            # Qt-created native threads may have Python frames without any
            # threading.Thread registry entry. Log those without registering them.
            registered = {entry["python_thread_id"] for entry in threads}
            for ident, frame in frames.items():
                if ident not in registered:
                    threads.append({"python_thread_id": ident, "type": "unregistered_native",
                                    "frame": {**self.location(frame.f_code), "line": frame.f_lineno}})
            del frames
            self.emit("RESULT", "thread_snapshot", reason=reason, python_threads=threads,
                      qt=(self.qt_snapshot() if qt and threading.get_ident() == self.main_ident
                          else {"cached": True, "last_observation": self.last_qt}))
            if reason in {"natural_atexit", "child_module_returned", "shutdown_start"}:
                self.sqlite_snapshot(reason)
            self.fault_output.flush()
            os.fsync(self.fault_output.fileno())
        except BaseException as exc:
            self.emit("RESULT", "snapshot_error", exception_type=type(exc).__name__)

    def sqlite_snapshot(self, reason):
        sqlite = sys.modules.get("sqlite3")
        if sqlite is None:
            return
        counts = {"open": 0, "closed": 0, "in_transaction": 0, "unreadable": 0}
        # Inspect connection state only. Never execute SQL, close a connection,
        # force garbage collection, or retain the discovered objects.
        for obj in gc.get_objects():
            if not isinstance(obj, sqlite.Connection):
                continue
            try:
                transaction = obj.in_transaction
                counts["open"] += 1
                counts["in_transaction"] += bool(transaction)
            except sqlite.ProgrammingError:
                counts["closed"] += 1
            except BaseException:
                counts["unreadable"] += 1
        self.emit("RESULT", "sqlite_connection_snapshot", reason=reason, **counts)

    def on_start(self, code, offset):
        try:
            kind = self.selected.get(code, _MISSING)
            if kind is _MISSING:
                kind = self.kind(code)
                self.selected[code] = kind
            if kind is None:
                return sys.monitoring.DISABLE
            events = self.events.PY_RETURN
            if kind == "child":
                events |= self.events.LINE
            if kind in {"application", "child"}:
                events |= self.events.CALL | self.events.C_RETURN | self.events.C_RAISE
            sys.monitoring.set_local_events(self.tool_id, code, events)
            frame = self.frame(code)
            self.next_call += 1
            call_id = self.next_call
            self.active[(threading.get_ident(), id(frame))] = call_id
            self.emit("START", "python_function", call_id=call_id,
                      **self.location(code), **self.details(code, frame))
            if kind in {"child", "shutdown"}:
                self.snapshot(kind + "_start", qt=kind != "shutdown")
        except BaseException as exc:
            self.emit("RESULT", "observer_callback_error", callback="start",
                      exception_type=type(exc).__name__)

    def on_line(self, code, line):
        try:
            now = time.monotonic_ns()
            key = (threading.get_ident(), code, line)
            count, previous = self.line_counts.get(key, (0, 0))
            self.line_counts[key] = (count + 1, previous)
            # Tight event/decode loops stay visible without fsync on each spin.
            if count >= 2 and now - previous < 1_000_000_000:
                return
            self.line_counts[key] = (count + 1, now)
            frame = self.frame(code)
            self.emit("LINE", "python_line", line=line, visits=count + 1,
                      marker=self.markers.get(line) if self.selected.get(code) == "child" else None,
                      **self.location(code), **self.details(code, frame))
            if threading.get_ident() == self.main_ident and now - self.last_snapshot_ns >= int(self.interval * 1e9):
                self.last_snapshot_ns = now
                self.snapshot("active_python")
        except BaseException as exc:
            self.emit("RESULT", "observer_callback_error", callback="line",
                      exception_type=type(exc).__name__)

    def on_return(self, code, offset, value):
        try:
            frame = self.frame(code)
            call_id = self.active.pop((threading.get_ident(), id(frame)), None)
            self.emit("END", "python_function", call_id=call_id, result=_summary(value),
                      **self.location(code), **self.details(code, frame))
            if self.selected.get(code) == "child":
                self.snapshot("child_module_returned")
        except BaseException as exc:
            self.emit("RESULT", "observer_callback_error", callback="return",
                      exception_type=type(exc).__name__)

    def on_unwind(self, code, offset, exception):
        if not self.selected.get(code):
            return
        try:
            frame = self.frame(code)
            call_id = self.active.pop((threading.get_ident(), id(frame)), None)
            self.emit("END", "python_unwind", call_id=call_id,
                      exception_type=type(exception).__name__,
                      **self.location(code), **self.details(code, frame))
        except BaseException:
            pass

    def on_yield(self, code, offset, value):
        self.emit("YIELD", "python_generator", **self.location(code))

    def on_resume(self, code, offset):
        self.emit("RESUME", "python_generator", **self.location(code))

    def on_call(self, code, offset, callable_object, argument):
        try:
            name = getattr(callable_object, "__name__", "")
            if name in {"emit", "wait", "start", "quit", "close", "processEvents"}:
                self.native_marker("START", "native_call_start", code, offset, name)
        except BaseException:
            pass

    def on_c_return(self, code, offset, callable_object, argument):
        try:
            name = getattr(callable_object, "__name__", "")
            owner = getattr(callable_object, "__self__", None)
            if name == "globalInstance" and getattr(owner, "__name__", "") == "QThreadPool":
                # The original call just succeeded: this only retrieves the
                # existing singleton, and a weakref preserves its ownership.
                self.qt_pool = weakref.ref(callable_object())
                self.snapshot("qt_pool_observed")
            elif name in {"emit", "wait", "start", "quit", "close", "processEvents"}:
                # Return markers distinguish a line entered from a C++ call
                # that actually returned. No call arguments are inspected.
                self.native_marker("END", "native_call", code, offset, name)
        except BaseException:
            pass

    def on_c_raise(self, code, offset, callable_object, argument):
        try:
            name = getattr(callable_object, "__name__", "")
            if name in {"emit", "wait", "start", "quit", "close", "processEvents"}:
                self.native_marker("END", "native_call_raised", code, offset, name)
        except BaseException:
            pass

    def native_marker(self, stage, event, code, offset, name):
        now = time.monotonic_ns()
        key = (threading.get_ident(), code, offset, event)
        count, previous = self.native_counts.get(key, (0, 0))
        self.native_counts[key] = (count + 1, previous)
        if count >= 2 and now - previous < 1_000_000_000:
            return
        self.native_counts[key] = (count + 1, now)
        self.emit(stage, event, native_function=name, instruction_offset=offset,
                  visits=count + 1, **self.location(code))

    def audit(self, event, args):
        try:
            if event == "sqlite3.connect":
                self.emit("START", "sqlite_connect", database=_locator(args[0]))
            elif event == "sqlite3.connect/handle":
                self.emit("END", "sqlite_connect", result_type=type(args[0]).__name__)
            elif event == "subprocess.Popen":
                executable, arguments = args[:2]
                executable = os.fsdecode(executable).replace("\\", "/").rsplit("/", 1)[-1].lower()
                tool = ("ffmpeg" if executable in {"ffmpeg", "ffmpeg.exe"}
                        else "python" if executable.startswith("python") else "other")
                self.emit("START", "subprocess_spawn", executable_kind=tool,
                          argument_count=len(arguments) if isinstance(arguments, (tuple, list)) else None)
        except BaseException:
            pass

    def natural_exit(self):
        self.emit("START", "natural_atexit")
        self.snapshot("natural_atexit")
        repeated = sorted(((count, code, line) for (_, code, line), (count, _) in self.line_counts.items()
                           if count > 2), key=lambda item: item[0], reverse=True)
        self.emit("RESULT", "observer_counters", records_before_counters=self.sequence,
                  line_visits=sum(item[0] for item in self.line_counts.values()),
                  native_call_visits=sum(item[0] for item in self.native_counts.values()),
                  repeated_lines=[{**self.location(code), "line": line, "visits": count}
                                  for count, code, line in repeated[:50]])
        try:
            faulthandler.dump_traceback(file=self.fault_output, all_threads=True)
            self.fault_output.flush()
            os.fsync(self.fault_output.fileno())
        except BaseException:
            pass
        self.emit("END", "natural_atexit")
        # Keep the native watchdog armed during later interpreter/Qt teardown.
        # Keep files open: closing a descriptor used by faulthandler is unsafe.

    def install(self):
        monitoring = sys.monitoring
        for tool_id in (3, 4, 5):
            if monitoring.get_tool(tool_id) is None:
                monitoring.use_tool_id(tool_id, "alo-restart-diagnostic")
                self.tool_id = tool_id
                break
        if self.tool_id is None:
            self.emit("RESULT", "install_failed", reason="NO_FREE_MONITORING_TOOL")
            return False
        callbacks = {self.events.PY_START: self.on_start, self.events.LINE: self.on_line,
                     self.events.PY_RETURN: self.on_return, self.events.PY_UNWIND: self.on_unwind,
                     self.events.PY_YIELD: self.on_yield, self.events.PY_RESUME: self.on_resume,
                     self.events.CALL: self.on_call, self.events.C_RETURN: self.on_c_return,
                     self.events.C_RAISE: self.on_c_raise}
        for event, callback in callbacks.items():
            monitoring.register_callback(self.tool_id, event, callback)
        self.emit("START", "observer_installed", python_version=sys.version.split()[0],
                  target_python_version="3.12.10", tool_id=self.tool_id,
                  child_source_sha256=self.child_hash, child_source_supplied=self.child_expected,
                  child_source_matches_command=self.child_matches,
                  faulthandler_interval_seconds=self.interval,
                  audit_enabled=os.environ.get("ALO_RESTART_TRACE_AUDIT", "1") != "0")
        faulthandler.enable(file=self.fault_output, all_threads=True)
        faulthandler.dump_traceback_later(self.interval, repeat=True, file=self.fault_output)
        if os.environ.get("ALO_RESTART_TRACE_AUDIT", "1") != "0":
            sys.addaudithook(self.audit)
        atexit.register(self.natural_exit)
        monitoring.set_events(self.tool_id, self.events.PY_START | self.events.PY_UNWIND)
        return True


def install():
    """Install once when opted in; observer failures never fail the child."""
    global _state
    if _state is not None:
        return _state.enabled
    directory = os.environ.get("ALO_RESTART_TRACE_DIR")
    if not directory:
        return False
    if not hasattr(sys, "monitoring"):
        return False
    try:
        observer = _Observer(Path(directory))
        _state = observer
        return observer.install()
    except BaseException as exc:
        if _state is not None:
            _state.emit("RESULT", "install_failed", exception_type=type(exc).__name__)
        return False
