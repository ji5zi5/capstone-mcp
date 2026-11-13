# Copyright 2026 Capstone MCP contributors.
"""Cancellable repeated acquisition using native start/stop event confirmation."""

import logging
import time
from collections.abc import Callable, Generator
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from threading import Event, RLock, Thread
from typing import Annotated, Final, Literal, Protocol
from uuid import uuid4

from pydantic import Field, FiniteFloat, JsonValue, TypeAdapter, ValidationError

from capstone_mcp.acquisition import (
    RecordingStatus,
    observe_recording,
    request_recording,
)
from capstone_mcp.automation_models import NativeRequest
from capstone_mcp.automation_worker import AutomationWorker, NativeSessionError
from capstone_mcp.desktop import AutomationError, Capstone
from capstone_mcp.file_workflows import FileArtifact
from capstone_mcp.models import Model
from capstone_mcp.record_events import (
    arm_transition,
    await_transition,
    dispose_transition,
    verify_debug_process,
)
from capstone_mcp.runs import CapturePlan, CaptureResult, CaptureSession

LOGGER: Final = logging.getLogger(__name__)
MAX_JOB_HISTORY: Final = 16
JSON_VALUE: Final = TypeAdapter(JsonValue)


class RepeatPlan(Model):
    """Explicit acquisition timing; no samplerate or sensor settings are changed."""

    process_id: Annotated[int, Field(gt=0)]
    window_handle: Annotated[int, Field(gt=0)]
    debug_port: Annotated[int, Field(ge=1024, le=65535)] = 9223
    repetitions: Annotated[int, Field(ge=1, le=100)] = 1
    duration_seconds: Annotated[FiniteFloat, Field(gt=0, le=3600)]
    pause_seconds: Annotated[FiniteFloat, Field(ge=0, le=3600)] = 0
    allow_foreground: bool = True
    capture: CapturePlan | None = None


class RunReceipt(Model):
    """Host-observed cycle timing; not a hardware sampling timestamp."""

    ordinal: int
    elapsed_seconds: float
    interrupted: bool = False


class RepeatOutcome(Model):
    """Recorded cycles are retained in Capstone, not deleted or overwritten."""

    state: Literal["completed", "cancelled", "failed"]
    runs: list[RunReceipt] | None
    error: str | None = None
    capture: CaptureResult | None = None


class JobStatus(Model):
    """Background job receipt; callers use its ID to inspect or cancel."""

    job_id: str
    state: Literal["running", "completed", "cancelled", "failed"]
    result: RepeatOutcome | None


class RecordingBackend(Protocol):
    """Native boundary used by the deterministic acquisition sequencer."""

    def observe(self) -> RecordingStatus:
        """Read current recording state."""
        ...

    def change(self, *, recording: bool) -> RecordingStatus:
        """Request and confirm a native recording transition."""
        ...


class Cancellation(Protocol):
    """Interruptible acquisition timer; duration itself is intended behavior."""

    def is_set(self) -> bool:
        """Report whether cancellation was requested."""
        ...

    def wait(self, timeout: float) -> bool:
        """Wait the specified acquisition time, interrupting on cancellation."""
        ...


class JobRecordingBackend(RecordingBackend, Protocol):
    """Lifecycle boundary used by the job, independent of the process implementation."""

    @property
    def uncertain(self) -> bool:
        """Whether a native operation lost its confirmed outcome."""
        ...

    def save(self, path: str) -> FileArtifact:
        """Save a confirmed stopped experiment to a new path."""
        ...

    def close(self) -> None:
        """Release native resources with a bounded wait."""
        ...


class NativeRecordingBackend:
    """Own UIA objects on the worker's COM apartment rather than sharing APP refs."""

    def __init__(self, plan: RepeatPlan) -> None:
        """Bind independently to the validated process and native event endpoint."""
        verify_debug_process(plan.debug_port, plan.process_id)
        self.app: Capstone = Capstone()
        _ = self.app.attach(process_id=plan.process_id)
        self.plan: RepeatPlan = plan

    def observe(self) -> RecordingStatus:
        """Read the current native control state."""
        state, _ = observe_recording(self.app, self.plan.window_handle)
        return state

    def change(self, *, recording: bool) -> RecordingStatus:
        """Arm the event before input, and require the actual native transition."""
        state = self.observe()
        if state.recording == recording:
            return state
        token = arm_transition(self.plan.debug_port, recording=recording)
        try:
            _ = request_recording(
                self.app, self.plan.window_handle, recording=recording,
                allow_foreground=self.plan.allow_foreground,
            )
            await_transition(self.plan.debug_port, token, recording=recording)
        finally:
            dispose_transition(self.plan.debug_port, token)
        observed = self.observe()
        if observed.recording != recording:
            msg = "Native event and observed recording control state disagree."
            raise AutomationError(msg)
        return observed


class RemoteRecordingBackend:
    """Own a recording worker; every native observation and transition is bounded."""

    def __init__(self, plan: RepeatPlan) -> None:
        """Initialize and validate readiness in the same worker used for acquisition."""
        self.worker: AutomationWorker = AutomationWorker()
        self.handle: int = plan.window_handle
        try:
            self.initial: RecordingStatus = RecordingStatus.model_validate(
                self.worker.call(NativeRequest(
                    operation="recording_initialize",
                    plan=JSON_VALUE.validate_json(plan.model_dump_json()),
                )),
            )
        except (NativeSessionError, ValidationError):
            self.worker.close()
            raise

    def observe(self) -> RecordingStatus:
        """Read only through the owning process."""
        return RecordingStatus.model_validate(
            self.worker.call(NativeRequest(operation="recording_observe")),
        )

    @property
    def uncertain(self) -> bool:
        """Report transport uncertainty separately from ordinary resource closure."""
        return self.worker.uncertain

    def change(self, *, recording: bool) -> RecordingStatus:
        """Confirm native events without replay after an uncertain result."""
        return RecordingStatus.model_validate(self.worker.call(NativeRequest(
            operation="recording_change", recording=recording,
        )))

    def close(self) -> None:
        """Retire this job's worker without terminating Capstone."""
        self.worker.close()

    def save(self, path: str) -> FileArtifact:
        """Save this same native session to a new path after a confirmed stop."""
        return FileArtifact.model_validate(self.worker.call(NativeRequest(
            operation="save_experiment", handle=self.handle, value=path,
        )))


def run_sequence(
    backend: RecordingBackend, plan: RepeatPlan, cancellation: Cancellation,
    *, clock: Callable[[], float] = time.monotonic,
    on_run: Callable[[RunReceipt], None] | None = None,
) -> RepeatOutcome:
    """Run confirmed cycles, always requesting stop if a start attempt was made."""
    initial = backend.observe()
    if initial.recording or not initial.control_enabled:
        msg = "Begin from a stopped experiment with an enabled recording source."
        raise AutomationError(msg)
    receipts: list[RunReceipt] = []
    for ordinal in range(1, plan.repetitions + 1):
        if cancellation.is_set():
            return RepeatOutcome(state="cancelled", runs=receipts)
        state = backend.observe()
        if (
            state.recording
            or not state.control_enabled
            or state.sampling_rate_display != initial.sampling_rate_display
        ):
            msg = "Recording availability or sample-rate display changed between runs."
            raise AutomationError(msg)
        try:
            started = backend.change(recording=True)
            if not started.recording:
                msg = "Start was not confirmed."
                raise AutomationError(msg)
            start_time = clock()
            interrupted = cancellation.wait(plan.duration_seconds)
        finally:
            stopped = backend.change(recording=False)
            if stopped.recording:
                msg = "Stop was not confirmed; inspect Capstone immediately."
                raise AutomationError(msg)
        receipt = RunReceipt(
            ordinal=ordinal, elapsed_seconds=clock() - start_time,
            interrupted=interrupted,
        )
        receipts.append(receipt)
        if on_run is not None:
            on_run(receipt)
        if interrupted:
            return RepeatOutcome(state="cancelled", runs=receipts)
        if ordinal < plan.repetitions and cancellation.wait(plan.pause_seconds):
            return RepeatOutcome(state="cancelled", runs=receipts)
    return RepeatOutcome(state="completed", runs=receipts)


class AcquisitionJob:
    """Mutable cancellation and completion state for one background acquisition."""

    def __init__(self, plan: RepeatPlan, backend: JobRecordingBackend) -> None:
        """Allocate one cancellation signal and one completion future."""
        self.plan: RepeatPlan = plan
        self.backend: JobRecordingBackend = backend
        self.cancel: Event = Event()
        self.result: Future[RepeatOutcome] = Future()
        self.completed_runs: list[RunReceipt] = []
        self.capture: CaptureSession | None = (
            CaptureSession(plan.capture, backend.save)
            if plan.capture is not None else None
        )

    def _after_run(self, receipt: RunReceipt) -> None:
        self.completed_runs.append(receipt)
        if self.capture is not None:
            self.capture.record(receipt.ordinal, interrupted=receipt.interrupted)

    def run(self) -> None:
        """Worker boundary records all failures and preserves their traceback."""
        try:
            try:
                if self.capture is not None:
                    self.capture.begin()
                result = run_sequence(
                    self.backend, self.plan, self.cancel,
                    on_run=self._after_run,
                )
            finally:
                self.backend.close()
        except Exception as error:
            LOGGER.exception("Repeated Capstone acquisition failed")
            details = str(error)
            if error.__context__ is not None:
                details += f"; preceding failure: {error.__context__}"
            if self.backend.uncertain:
                details += "; verify recording stop in Capstone."
            result = RepeatOutcome(
                state="failed", runs=list(self.completed_runs) or None, error=details,
            )
        if self.capture is not None:
            capture = self.capture.result()
            result = result.model_copy(update={"capture": capture})
            if capture.comparison_error is not None:
                result = result.model_copy(update={
                    "state": "failed", "error": capture.comparison_error,
                })
        self.result.set_result(result)


class AcquisitionJobs:
    """Own one active acquisition and bounded completion history."""

    def __init__(self) -> None:
        """Start with no jobs; completed history remains bounded."""
        self.jobs: dict[str, AcquisitionJob] = {}
        self.lock: RLock = RLock()
        self.input_reserved: bool = False

    def require_idle(self) -> None:
        """Prevent other MCP input from racing an active acquisition."""
        with self.lock:
            if self.input_reserved or any(
                not job.result.done() for job in self.jobs.values()
            ):
                msg = "An acquisition or another input is active; no input was queued."
                raise AutomationError(msg)

    @contextmanager
    def interaction(self) -> Generator[None, None, None]:
        """Reserve mutation ownership without holding the registry lock during I/O."""
        with self.lock:
            self.require_idle()
            self.input_reserved = True
        try:
            yield
        finally:
            with self.lock:
                self.input_reserved = False

    def start(self, plan: RepeatPlan) -> JobStatus:
        """Validate the target and readiness before starting the asynchronous worker."""
        if not plan.allow_foreground:
            msg = "Repeated acquisition requires explicit allow_foreground=true."
            raise AutomationError(msg)
        with self.interaction():
            backend = RemoteRecordingBackend(plan)
            state = backend.initial
            if state.recording or not state.control_enabled:
                backend.close()
                msg = "A stopped experiment with connected/configured data is required."
                raise AutomationError(msg)
            identifier = uuid4().hex
            job = AcquisitionJob(plan, backend)
            with self.lock:
                if len(self.jobs) >= MAX_JOB_HISTORY:
                    del self.jobs[next(iter(self.jobs))]
                self.jobs[identifier] = job
            try:
                Thread(target=job.run, daemon=True).start()
            except RuntimeError:
                with self.lock:
                    del self.jobs[identifier]
                backend.close()
                raise
        return self.status(identifier)

    def status(self, identifier: str) -> JobStatus:
        """Return only observed completion; no polling or implicit retry."""
        with self.lock:
            job = self.jobs[identifier]
        result = job.result.result() if job.result.done() else None
        return JobStatus(
            job_id=identifier, state="running" if result is None else result.state,
            result=result,
        )

    def cancel(self, identifier: str) -> JobStatus:
        """Interrupt the timer; the worker then requests a confirmed stop."""
        with self.lock:
            self.jobs[identifier].cancel.set()
        return self.status(identifier)

    def close(self) -> None:
        """Request stop, then bound shutdown even if a native provider is hung."""
        with self.lock:
            jobs = list(self.jobs.values())
            for job in jobs:
                job.cancel.set()
        deadline = time.monotonic() + 5
        for job in jobs:
            try:
                _ = job.result.result(timeout=max(0, deadline - time.monotonic()))
            except FutureTimeout:
                LOGGER.exception("Shutdown could not confirm recording stop")
                job.backend.close()
