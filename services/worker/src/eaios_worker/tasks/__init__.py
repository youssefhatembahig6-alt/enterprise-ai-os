"""Task modules, imported here so registration does not depend on autodiscovery.

`celery_app.autodiscover_tasks(["eaios_worker.tasks"])` looks for a module named
`eaios_worker.tasks.tasks`, which does not exist — so it found nothing, and the
retention entry in `beat_schedule` named a task the worker had never registered.
The configuration looked correct from every angle except the one that mattered:
`celery_app.tasks` was empty, and beat would have dispatched a name nothing
answered to. Importing here makes registration a consequence of the package being
loaded rather than of a naming convention holding.

`tests/integration/test_retention.py::test_the_scheduled_task_name_is_actually_registered`
checks this in a fresh interpreter, because within one test session an earlier
import hides the failure.
"""

from __future__ import annotations

from . import retention

__all__ = ["retention"]
