"""Execute every notebook cell in a clean kernel belonging to this interpreter."""

import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import json

import nbformat
from nbclient import NotebookClient


def main():
    root = Path(__file__).resolve().parents[1]
    path = root / "notebooks" / "design_gate.ipynb"
    notebook = nbformat.read(path, as_version=4)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    os.environ.setdefault("MPLCONFIGDIR", str(root / ".mplconfig"))
    with TemporaryDirectory(prefix="gypaetus-kernel-") as directory:
        kernel = Path(directory) / "kernels" / "gypaetus-fresh"
        kernel.mkdir(parents=True)
        (kernel / "kernel.json").write_text(json.dumps({
            "argv": [sys.executable, "-m", "ipykernel_launcher", "-f", "{connection_file}"],
            "display_name": "GYPAETUS fresh interpreter", "language": "python"}))
        old = os.environ.get("JUPYTER_PATH")
        os.environ["JUPYTER_PATH"] = directory + (os.pathsep + old if old else "")
        try:
            NotebookClient(notebook, timeout=600, kernel_name="gypaetus-fresh",
                           resources={"metadata": {"path": str(root)}}, allow_errors=False).execute()
        finally:
            if old is None:
                os.environ.pop("JUPYTER_PATH", None)
            else:
                os.environ["JUPYTER_PATH"] = old
    nbformat.write(notebook, path)
    print(f"Executed all cells successfully: {path}")


if __name__ == "__main__":
    main()

