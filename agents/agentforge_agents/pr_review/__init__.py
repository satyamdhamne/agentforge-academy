from ..core import AgentSpec
from .agent import PRReviewInput, run
from .blueprint import BLUEPRINT
from .mock import RESPONDERS

EXAMPLE_DIFF = """diff --git a/app/users.py b/app/users.py
index 3b18e51..a9c2f1d 100644
--- a/app/users.py
+++ b/app/users.py
@@ -1,6 +1,14 @@
 import sqlite3
+import requests
+
+API_KEY = "sk-live-4f9a8b7c6d5e4f3a2b1c0d9e"

 def get_user(conn, user_id):
-    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
+    row = conn.execute(f"SELECT * FROM users WHERE id = {user_id}").fetchone()
+    print("fetched", row)
+    return row
+
+def sync(user):
+    # TODO: add retries
+    return requests.post("https://crm.example.com/sync", json=user, verify=False)
"""

SPEC = AgentSpec(
    slug="github-pr-review-agent",
    name="GitHub PR Review Agent",
    input_model=PRReviewInput,
    run=run,
    mock_responders=RESPONDERS,
    examples=[{"title": "Add CRM sync", "description": "Syncs users to the CRM.", "diff": EXAMPLE_DIFF}],
    blueprint=BLUEPRINT,
    package=__name__,
)
