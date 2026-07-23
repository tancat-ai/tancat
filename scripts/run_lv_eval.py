"""Run eval resolver against LV Insurance mock site with live scraping."""

import http.server
import os
import socketserver
import subprocess
import sys
import threading
import time

PORT = 8780


# Start server in background thread
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


httpd = socketserver.TCPServer(("", PORT), Handler)
t = threading.Thread(target=httpd.serve_forever, daemon=True)
t.start()
time.sleep(0.5)
print(f"Server: http://localhost:{PORT}")

# Set env for the eval
env = os.environ.copy()
env["PYTHONPATH"] = os.getcwd()

# Step 1: Scrape the mock site
print("\n--- Scraping mock site ---")
result = subprocess.run(
    [sys.executable, "scripts/eval/eval_resolver.py", "--mode", "live"],
    env=env,
    capture_output=True,
    text=True,
    timeout=120,
    cwd=os.getcwd(),
)
print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
if result.stderr:
    print("STDERR:", result.stderr[-300:])

# Step 2: Run with RAG off
print("\n--- RAG OFF ---")
env2 = env.copy()
if "RAG_ENABLED" in env2:
    del env2["RAG_ENABLED"]
result2 = subprocess.run(
    [sys.executable, "scripts/eval/eval_resolver.py", "--mode", "static"],
    env=env2,
    capture_output=True,
    text=True,
    timeout=120,
    cwd=os.getcwd(),
)
# Extract just the summary lines
for line in result2.stdout.split("\n"):
    if any(k in line for k in ["accuracy", "lv_insurance", "RAG:"]):
        print(line.strip())

# Step 3: Run with RAG on
print("\n--- RAG ON ---")
env3 = env.copy()
env3["RAG_ENABLED"] = "1"
result3 = subprocess.run(
    [sys.executable, "scripts/eval/eval_resolver.py", "--mode", "static"],
    env=env3,
    capture_output=True,
    text=True,
    timeout=120,
    cwd=os.getcwd(),
)
for line in result3.stdout.split("\n"):
    if any(k in line for k in ["accuracy", "lv_insurance", "RAG:"]):
        print(line.strip())

httpd.shutdown()
print("\nDone")
