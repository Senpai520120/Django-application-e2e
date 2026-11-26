"""Import shim used only by mutation testing (see pyproject, [tool.mutmut]).

The tests import ``upload_groups`` the way Airflow does, from its dags folder.
mutmut names the mutants of airflow/dags/upload_groups.py after its path,
``airflow.dags.upload_groups``, and only switches a mutant on inside a module of
that name. This shim makes ``import upload_groups`` return that very module, so
the tests exercise the mutants and monkeypatching still hits the real module.
"""

import importlib
import sys

sys.modules[__name__] = importlib.import_module("airflow.dags.upload_groups")
