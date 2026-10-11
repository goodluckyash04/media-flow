"""
Lightweight background job manager for the media downloader.

Design
------
- Uses Python's threading.ThreadPoolExecutor with a configurable max-workers.
- Each submitted job gets a Future stored in a dict keyed by job UUID.
- A cancel_events dict holds a threading.Event per active job; services
  check this event via a cancel_check() callback to stop cleanly.
- Job metadata (status, progress, errors) is persisted to SQLite by the
  individual service functions – not by this module.
- On startup, any jobs in RUNNING state are reset to QUEUED (stale recovery).

Limitations
-----------
- This is a single-process, single-machine scheduler.
- State is not shared across processes (e.g., manage.py shell + runserver).
- If the Django process is killed during a download, the job will be
  reset to QUEUED on the next start rather than resuming mid-download.
- Pause/resume is not supported because yt-dlp and FFmpeg do not expose
  a reliable cross-platform suspend mechanism.
- Maximum concurrency is read from AppSettings at startup; changes
  require an application restart.
- This manager is designed for a single user on a local machine.
  It is NOT a production task queue.
"""

import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_INSTANCE: Optional["JobManager"] = None
_INSTANCE_LOCK = threading.Lock()


def get_job_manager() -> "JobManager":
    """Return the global singleton JobManager, creating it if necessary."""
    global _INSTANCE
    if _INSTANCE is None:
        with _INSTANCE_LOCK:
            if _INSTANCE is None:
                _INSTANCE = JobManager()
    return _INSTANCE


class JobManager:
    """
    Thread-safe background job scheduler.

    All public methods are safe to call from any thread (including Django
    request handlers).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._futures: Dict[str, Future] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._executor: Optional[ThreadPoolExecutor] = None
        self._started = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self):
        """Initialise the executor and recover stale jobs."""
        if self._started:
            return

        from django.conf import settings

        try:
            from downloader.models import AppSettings
            max_workers = AppSettings.get().max_concurrent_jobs
        except Exception:
            max_workers = getattr(settings, "MAX_CONCURRENT_JOBS", 3)

        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="job-worker",
        )
        self._started = True
        logger.info("JobManager started with max_workers=%d", max_workers)

        # Recover stale jobs from a previous crash
        self._recover_stale_jobs()

    def stop(self):
        """Shutdown the executor gracefully."""
        if self._executor:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._started = False
            logger.info("JobManager stopped")

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def submit_download(self, job_id: str) -> bool:
        """
        Submit a DownloadJob or Playlist job to the executor.
        Returns True if accepted, False if already queued/running.
        """
        return self._submit(job_id, self._run_download)

    def submit_conversion(self, job_id: str) -> bool:
        """
        Submit a ConversionJob to the executor.
        Returns True if accepted, False if already active.
        """
        return self._submit(job_id, self._run_conversion)

    def cancel_job(self, job_id: str) -> bool:
        """
        Request cancellation of a running or queued job.
        Returns True if the cancel signal was sent.
        """
        with self._lock:
            event = self._cancel_events.get(job_id)
            if event:
                event.set()
                logger.info("Cancel requested for job %s", job_id)
                return True

            # Not running – mark directly in DB
            future = self._futures.get(job_id)
            if future and not future.done():
                future.cancel()

        # Mark as cancelled in DB if it never started
        self._mark_cancelled_in_db(job_id)
        return False

    def is_active(self, job_id: str) -> bool:
        """Return True if the job is currently queued or executing."""
        with self._lock:
            f = self._futures.get(job_id)
            return f is not None and not f.done()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _submit(self, job_id: str, fn: Callable) -> bool:
        if not self._started or self._executor is None:
            logger.warning("JobManager not started, cannot submit job %s", job_id)
            return False

        with self._lock:
            if job_id in self._futures and not self._futures[job_id].done():
                logger.warning("Job %s is already active", job_id)
                return False

            cancel_event = threading.Event()
            self._cancel_events[job_id] = cancel_event
            future = self._executor.submit(fn, job_id, cancel_event)
            self._futures[job_id] = future
            future.add_done_callback(lambda f: self._cleanup(job_id, f))

        logger.info("Submitted job %s", job_id)
        return True

    def _cleanup(self, job_id: str, future: Future):
        with self._lock:
            self._futures.pop(job_id, None)
            self._cancel_events.pop(job_id, None)
        if future.exception():
            logger.error(
                "Job %s raised an unhandled exception: %s",
                job_id,
                future.exception(),
            )

    def _run_download(self, job_id: str, cancel_event: threading.Event):
        """Worker entry point for download jobs."""
        from downloader.models import DownloadJob, JobType

        try:
            job = DownloadJob.objects.get(pk=job_id)
        except DownloadJob.DoesNotExist:
            logger.error("DownloadJob %s missing from DB", job_id)
            return

        cancel_check = cancel_event.is_set

        if job.job_type == JobType.PLAYLIST:
            from downloader.services.download_service import run_playlist_job
            run_playlist_job(job_id, cancel_check)
        else:
            from downloader.services.download_service import run_download_job
            run_download_job(job_id, cancel_check)

    def _run_conversion(self, job_id: str, cancel_event: threading.Event):
        """Worker entry point for conversion jobs."""
        from downloader.services.conversion_service import run_conversion_job

        run_conversion_job(job_id, cancel_event.is_set)

    def _recover_stale_jobs(self):
        """
        Reset RUNNING jobs to QUEUED on startup.
        These were interrupted by a previous crash or restart.
        """
        try:
            from downloader.models import ConversionJob, DownloadJob, JobStatus

            stale_downloads = DownloadJob.objects.filter(status=JobStatus.RUNNING)
            count = stale_downloads.update(
                status=JobStatus.QUEUED,
                stage="Recovered (interrupted by restart)",
                progress_pct=0.0,
            )
            if count:
                logger.warning("Recovered %d stale download job(s)", count)

            stale_conversions = ConversionJob.objects.filter(status=JobStatus.RUNNING)
            count = stale_conversions.update(
                status=JobStatus.QUEUED,
                stage="Recovered (interrupted by restart)",
                progress_pct=0.0,
            )
            if count:
                logger.warning("Recovered %d stale conversion job(s)", count)

        except Exception as exc:
            # Tables may not exist yet (pre-migration)
            logger.debug("Stale job recovery skipped: %s", exc)

    def _mark_cancelled_in_db(self, job_id: str):
        from django.utils import timezone

        from downloader.models import ConversionJob, DownloadJob, JobStatus

        updated = DownloadJob.objects.filter(
            pk=job_id, status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
        ).update(status=JobStatus.CANCELLED, completed_at=timezone.now(), stage="Cancelled")

        if not updated:
            ConversionJob.objects.filter(
                pk=job_id, status__in=[JobStatus.QUEUED, JobStatus.RUNNING]
            ).update(status=JobStatus.CANCELLED, completed_at=timezone.now(), stage="Cancelled")
