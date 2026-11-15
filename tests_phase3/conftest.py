from __future__ import annotations
import importlib.util
from pathlib import Path

# phase 3 tests reuse the phase 2 test setup (temp data folder, small fake database);
# everything is re-exported so both test folders can also run together
_spec = importlib.util.spec_from_file_location(
    'phase2_test_setup', Path(__file__).resolve().parents[1] / 'tests_phase2' / 'conftest.py')
_setup = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_setup)
globals().update({k: v for k, v in vars(_setup).items() if not k.startswith('__')})