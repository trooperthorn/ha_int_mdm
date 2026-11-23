"""Filter a /api/states dump on stdin to one tablet's entities.

Usage: curl .../api/states | python states.py <entity id fragment>
"""

import json
import sys

needle = sys.argv[1]
for state in json.load(sys.stdin):
    if needle in state["entity_id"]:
        print(
            state["entity_id"].split("_", 6)[-1], "=", state["state"], state["last_updated"][11:19]
        )
