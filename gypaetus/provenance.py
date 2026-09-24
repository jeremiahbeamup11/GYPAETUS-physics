"""Record runtime and source identities alongside numerical outputs."""

import hashlib
from importlib.metadata import version
from pathlib import Path
import platform


def provenance():
    return {
        "python": platform.python_version(),
        "dependencies": {name: version(name) for name in ("numpy", "scipy", "pandas", "matplotlib")},
        "source_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in sorted(Path(__file__).parent.glob("*.py"))},
    }

