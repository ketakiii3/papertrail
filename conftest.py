"""Root pytest config: make the service packages importable from the repo root.

Service code lives in hyphenated folders (`services/claim-extractor/src`) that
Python can't import by path, and inside Docker each one is copied to `/app/src`.
Here each is registered under an importable alias instead, so relative imports
inside the packages keep working:

    claim_extractor, transcript_ingester, contradiction_detector,
    edgar_ingester, surveillance, severity_scorer
"""

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))  # for `shared.*` and `scripts.*`


def _alias(name: str, path: Path) -> None:
    if name in sys.modules:
        return
    spec = importlib.util.spec_from_file_location(
        name, path / "__init__.py", submodule_search_locations=[str(path)]
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)


_alias("claim_extractor", ROOT / "services/claim-extractor/src")
_alias("transcript_ingester", ROOT / "services/transcript-ingester/src")
_alias("contradiction_detector", ROOT / "services/contradiction-detector/src")
_alias("edgar_ingester", ROOT / "services/edgar-ingester/src")
_alias("surveillance", ROOT / "services/surveillance/src")
_alias("severity_scorer", ROOT / "models/severity-scorer")
