"""Application bootstrap for RubikPI.

Copyright (C) 2026 Gwilherm Kerherve

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""

from __future__ import annotations

import sys


def main() -> int:
    """Launch RubikPI. Returns the Qt exit code."""
    try:
        from PyQt6.QtWidgets import QApplication
    except ImportError:
        sys.stderr.write(
            "RubikPI requires PyQt6.\n"
            "Install the dependencies with:  pip install -r requirements.txt\n"
        )
        return 1

    from rubikpi import __app_name__
    from rubikpi.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("Gwilherm Kerherve")

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
