import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).with_name("offline_tests.py")), run_name="guard_only")
from headroom.cli import main

sys.argv = ["headroom", "eval", "--plan-only", "--search-mode", "bounded_pareto"]
main()
