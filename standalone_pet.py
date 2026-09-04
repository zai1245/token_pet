import sys
# Automatically enable standalone mode
if "--standalone" not in sys.argv:
    sys.argv.append("--standalone")

from emojinoko_monitor import _start_app

if __name__ == "__main__":
    _start_app()
