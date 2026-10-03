# PyInstaller entry point: the same main() as the "routemap" console script.
import sys

from routemap.cli import main

if __name__ == "__main__":
    sys.exit(main())
