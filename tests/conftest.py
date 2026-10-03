import os
import sys

# Headless Qt for the GUI tests. Not on Windows: there the offscreen platform has
# no font database (text silently fails to render), while the native platform
# works on a CI runner with no window shown.
if sys.platform != "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
