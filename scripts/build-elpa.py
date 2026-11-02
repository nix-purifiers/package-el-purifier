# SPDX-License-Identifier: MIT
"""Publish the native single-file package beside the documentation."""
from pathlib import Path
import sys
import shutil
source = Path(__file__).resolve().parents[1] / 'lisp/package-el-purifier.el'
output = Path(sys.argv[1]) / 'elpa'
output.mkdir(parents=True, exist_ok=True)
shutil.copyfile(source, output/'package-el-purifier-0.1.0.el')
(output/'archive-contents').write_text('(1 (package-el-purifier . [(0 1 0) ((emacs (29 1))) "Nix-resolved package.el dependencies" single]))\n')
