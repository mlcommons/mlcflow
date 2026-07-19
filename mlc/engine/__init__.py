"""MLC script execution engine.

Migrated from ``mlperf-automations/automation/script/`` into mlcflow as part of
the Option B architecture migration. The engine (``ScriptAutomation`` and its
helpers) is now a first-class package inside mlcflow and is imported directly
instead of being dynamically loaded from a git clone.
"""

import sys as _sys

# Backward-compatibility shim.
#
# Before the migration, the engine was loaded dynamically with the
# ``automation/`` directory prepended to ``sys.path``. That made ``utils``
# (i.e. ``automation/utils.py``) importable as a top-level module, and ~190
# script ``customize.py`` files rely on ``from utils import is_true`` (and
# ``from utils import *``). The migration contract is that existing scripts run
# unmodified (redesign proposal §06), so we re-expose the engine's utils module
# under the top-level name ``utils``. This also shadows any unrelated
# third-party ``utils`` package that might be installed in the environment.
from mlc.engine import utils as _engine_utils
_sys.modules["utils"] = _engine_utils

from mlc.engine.module import ScriptAutomation

__all__ = ["ScriptAutomation"]
