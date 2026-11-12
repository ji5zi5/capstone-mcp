# Copyright 2026 Capstone MCP contributors.
"""Persistent native sessions with bounded IPC and no replay after uncertainty."""

from __future__ import annotations

import logging
import subprocess
import sys
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from threading import Lock, Thread
from typing import Final
from uuid import uuid4

import win32api
import win32job
from pydantic import JsonValue, TypeAdapter

from capstone_mcp.automation_models import NativeReply, NativeRequest, RequestPacket
from capstone_mcp.graph_execution import GRAPH_INPUT_OPERATIONS, GraphFailure

TEXT_VALUE: Final = TypeAdapter(str)
LOGGER: Final = logging.getLogger(__name__)
MAX_MESSAGE_BYTES: Final = 64 * 1024 * 1024
CLEANUP_SECONDS: Final = 2
PROCESS_ATTACH_TO_JOB: Final = 0x0101

class NativeSessionError(RuntimeError):
    """The native session failed; an input may already have reached Capstone."""

    def __init__(self, message: str, failure: GraphFailure | None = None) -> None:
        """Keep graph recovery metadata without changing ordinary worker errors."""
        self.failure: GraphFailure | None = failure
        correlation = "" if failure is None else f" [request_id={failure.request_id}]"
        super().__init__(message + correlation)


class AutomationWorker:
    """Serialize one session's requests; retire its process on uncertain results."""

    def __init__(self, *, timeout: float = 60) -> None:
        """Start lazily so importing the MCP does not launch a worker."""
        self.timeout: float = timeout
        self.lock: Lock = Lock()
        self.cleanup_lock: Lock = Lock()
        self.process: subprocess.Popen[str] | None = None
        self.job: win32job.Handle | None = None
        self.transport: Thread | None = None
        self.retired: bool = False
        self.uncertain: bool = False
        self.last_graph_failure: GraphFailure | None = None

    def _spawn(self) -> subprocess.Popen[str]:
        """Launch the fixed native bootstrap; test backends replace this boundary."""
        return subprocess.Popen(
            [sys.executable, "-X", "utf8", "-u", "-m", "capstone_mcp.native_main"],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8",
        )

    def _start(self) -> subprocess.Popen[str]:
        if self.retired:
            msg = "Native session was retired; attach a new session before more input."
            raise NativeSessionError(msg)
        if self.process is not None:
            return self.process
        self.job = win32job.CreateJobObject(None, "capstone-mcp-" + uuid4().hex)
        limits = win32job.QueryInformationJobObject(
            self.job, win32job.JobObjectExtendedLimitInformation,
        )
        limits["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            | win32job.JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK
        )
        win32job.SetInformationJobObject(
            self.job, win32job.JobObjectExtendedLimitInformation, limits,
        )
        process = self._spawn()
        self.process = process
        if self.retired:
            process.kill()
            msg = "Worker startup finished after its session was retired."
            raise NativeSessionError(msg)
        process_handle = win32api.OpenProcess(
            PROCESS_ATTACH_TO_JOB, 0, process.pid,
        )
        try:
            win32job.AssignProcessToJobObject(self.job, process_handle)
        finally:
            process_handle.Close()
        if process.stdin is None:
            msg = "Native worker input stream is unavailable."
            raise NativeSessionError(msg)
        _ = process.stdin.write("INITIALIZE\n")
        process.stdin.flush()
        return process

    def _exchange(self, request: NativeRequest, identifier: str) -> NativeReply:
        process = self._start()
        if self.retired:
            msg = "Native session was retired before input delivery."
            raise NativeSessionError(msg)
        if process.stdin is None or process.stdout is None:
            msg = "Native worker IPC streams are unavailable."
            raise NativeSessionError(msg)
        packet = RequestPacket(identifier=identifier, command=request)
        _ = process.stdin.write(packet.model_dump_json() + "\n")
        process.stdin.flush()
        line = TEXT_VALUE.validate_python(
            process.stdout.readline(MAX_MESSAGE_BYTES + 1),
        )
        if not line.endswith("\n") or len(line) > MAX_MESSAGE_BYTES:
            msg = "Native worker returned an incomplete or oversized reply."
            raise NativeSessionError(msg)
        reply = NativeReply.model_validate_json(line)
        if reply.identifier != identifier:
            msg = "Native worker returned a reply for a different request."
            raise NativeSessionError(msg)
        return reply

    def call(self, request: NativeRequest) -> JsonValue:
        """Cover startup, write, complete read, and parsing with one absolute budget."""
        if self.retired:
            msg = "Native session was retired; create a new session before more input."
            raise NativeSessionError(msg)
        if not self.lock.acquire(blocking=False):
            msg = "A native request is already active; it was not queued or replayed."
            raise NativeSessionError(msg)
        deadline = time.monotonic() + self.timeout
        identifier = uuid4().hex
        future: Future[NativeReply] = Future()

        def exchange() -> None:
            try:
                reply = self._exchange(request, identifier)
            except Exception as error:
                LOGGER.exception("Native worker transport failed")
                future.set_exception(error)
            else:
                future.set_result(reply)

        self.transport = Thread(target=exchange, daemon=True)
        self.transport.start()
        try:
            reply = future.result(timeout=max(0, deadline - time.monotonic()))
        except FutureTimeout as error:
            self.uncertain = True
            self._retire()
            msg = (
                "Native operation timed out; its outcome is unknown. The worker was "
                "retired without replay. Capstone was not terminated. Reattach and "
                "inspect the application before further input."
            )
            failure = self._graph_transport_failure(
                request, identifier, "WORKER_TIMEOUT", msg,
            )
            raise NativeSessionError(msg, failure) from error
        except Exception as error:
            self.uncertain = True
            self._retire()
            msg = f"Native transport failed; outcome is unknown: {error}"
            failure = self._graph_transport_failure(
                request, identifier, "TRANSPORT_FAILURE", msg,
            )
            raise NativeSessionError(msg, failure) from error
        finally:
            self.lock.release()
        if reply.error is not None:
            if reply.graph_failure is not None:
                self.last_graph_failure = reply.graph_failure
            raise NativeSessionError(reply.error, reply.graph_failure)
        return reply.result

    def _graph_transport_failure(
        self, request: NativeRequest, identifier: str, code: str, detail: str,
    ) -> GraphFailure | None:
        if request.operation not in GRAPH_INPUT_OPERATIONS | {
            "read_graph", "observe_graph", "create_graph",
        }:
            return None
        failure = GraphFailure(
            code=code, request_id=identifier, operation=request.operation,
            stage="transport",
            graph_input_may_have_been_sent=request.operation in
            GRAPH_INPUT_OPERATIONS | {"create_graph"},
            next_action="reattach_and_inspect", detail=detail,
        )
        self.last_graph_failure = failure
        return failure

    def _retire(self) -> None:
        """Terminate only the automation worker, with bounded reaping."""
        self.retired = True
        if not self.cleanup_lock.acquire(timeout=CLEANUP_SECONDS):
            msg = "Worker retirement is already in progress; replacement is prohibited."
            raise NativeSessionError(msg)
        try:
            self._dispose_resources()
        finally:
            self.cleanup_lock.release()

    def _dispose_resources(self) -> None:
        process = self.process
        if process is not None:
            if process.poll() is None:
                process.kill()
            try:
                _ = process.wait(timeout=CLEANUP_SECONDS)
            except subprocess.TimeoutExpired as error:
                msg = "Worker termination is unconfirmed; replacement is prohibited."
                raise NativeSessionError(msg) from error
        if self.transport is not None:
            self.transport.join(CLEANUP_SECONDS)
            if self.transport.is_alive():
                msg = "Worker transport did not retire; no replacement may be started."
                raise NativeSessionError(msg)
        if process is not None:
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()
        if self.job is not None:
            self.job.Close()
            self.job = None

    def reset(self) -> None:
        """Prepare a fresh session only for an explicit attach after worker loss."""
        if not self.lock.acquire(blocking=False):
            msg = "A native request is still active; reattachment was not queued."
            raise NativeSessionError(msg)
        try:
            self._retire()
            self.process = None
            self.transport = None
            self.retired = False
            self.uncertain = False
        finally:
            self.lock.release()

    def close(self) -> None:
        """Retire without attempting to repeat or undo an uncertain native action."""
        self._retire()
