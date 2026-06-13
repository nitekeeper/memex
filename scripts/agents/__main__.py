"""Enable `python -m scripts.agents <cmd> ...`.

scripts/agents was refactored from a single module (scripts/agents.py) into a
package (scripts/agents/__init__.py). A package needs a __main__.py for
`python -m scripts.agents` to dispatch, otherwise it fails with
"No module named scripts.agents.__main__". This restores the CLI parity the
pre-refactor module had and that the sibling CLIs (scripts/roles.py,
scripts/registry.py) provide.
"""

from __future__ import annotations

from scripts.agents import main

if __name__ == "__main__":
    main()
