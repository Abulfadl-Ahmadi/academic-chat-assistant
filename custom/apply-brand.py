#!/usr/bin/env python3
"""Apply G-CAT branding to the upstream Open WebUI env.py at image build time.

Run inside the derived image build. Idempotent: re-running is a no-op.

We patch env.py instead of shipping our own copy so that upstream updates to
every other line keep flowing in. Only the branding lines are touched.
"""

import re
import sys
from pathlib import Path

ENV_PY = Path("/app/backend/open_webui/env.py")
BRAND = "G-CAT"

# Upstream defines:
#     WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')
#     if WEBUI_NAME != 'Open WebUI':
#         WEBUI_NAME += ' (Open WebUI)'
# The suffix branch forces "(Open WebUI)" onto any custom name, which defeats
# branding, so both the default and the suffix branch are replaced.
OLD_BLOCK = (
    "WEBUI_NAME = os.getenv('WEBUI_NAME', 'Open WebUI')\n"
    "if WEBUI_NAME != 'Open WebUI':\n"
    "    WEBUI_NAME += ' (Open WebUI)'\n"
)
NEW_BLOCK = f"WEBUI_NAME = os.getenv('WEBUI_NAME', '{BRAND}')\n"


def main() -> int:
    if not ENV_PY.is_file():
        print(f"ERROR: {ENV_PY} not found in image", file=sys.stderr)
        return 1

    src = ENV_PY.read_text()

    if NEW_BLOCK in src:
        print("brand_webui.py: already applied, nothing to do")
        return 0

    if OLD_BLOCK not in src:
        # Upstream changed this block. Fail loudly rather than silently
        # leaving the site unbranded after an image rebuild.
        print(
            "ERROR: could not find the expected WEBUI_NAME block in env.py.\n"
            "Upstream Open WebUI likely changed this code. Review\n"
            "custom/apply-brand.py and update it to match.",
            file=sys.stderr,
        )
        return 1

    ENV_PY.write_text(src.replace(OLD_BLOCK, NEW_BLOCK, 1))

    # Sanity check: the module must still import-parse.
    compile(ENV_PY.read_text(), str(ENV_PY), "exec")
    print(f"brand_webui.py: WEBUI_NAME default set to {BRAND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
