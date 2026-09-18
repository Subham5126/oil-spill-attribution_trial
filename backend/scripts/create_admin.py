"""Bootstrap CLI — create the initial OILTRACE TECH_ADMIN account.

Delegates to backend.auth.create_admin.
"""

from __future__ import annotations

from backend.auth.create_admin import main

if __name__ == "__main__":
    main()
