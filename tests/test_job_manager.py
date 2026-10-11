"""Tests for the background JobManager."""

import time
from unittest.mock import MagicMock, patch
import pytest

from downloader.models import DownloadJob, JobStatus
from downloader.workers.job_manager import JobManager, get_job_manager


def test_get_job_manager_singleton():
    mgr1 = get_job_manager()
    mgr2 = get_job_manager()
    assert mgr1 is mgr2


@pytest.mark.django_db
def test_job_manager_lifecycle():
    mgr = JobManager()
    assert mgr._started is False

    mgr.start()
    assert mgr._started is True
    assert mgr._executor is not None

    mgr.stop()
    assert mgr._started is False


@pytest.mark.django_db
def test_job_manager_submission_and_cancel():
    mgr = JobManager()
    mgr.start()

    job = DownloadJob.objects.create(url="https://example.com/video")
    job_id = str(job.id)

    with patch("downloader.workers.job_manager.JobManager._run_download") as mock_run:
        # Mock a slow running task
        def slow_task(jid, evt):
            while not evt.is_set():
                time.sleep(0.01)

        mock_run.side_effect = slow_task

        submitted = mgr.submit_download(job_id)
        assert submitted is True

        # Check cancellation
        cancelled = mgr.cancel_job(job_id)
        assert cancelled is True

    mgr.stop()
