# Nuitka entry for the command line (routemap-cli.exe on Windows; the single
# "routemap" binary on macOS and Linux, which opens the window with no arguments).
import sys

from routemap.cli import main

if __name__ == "__main__":
    sys.exit(main())
