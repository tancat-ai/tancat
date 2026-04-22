import os

src_dir = os.path.join(os.path.dirname(__file__), "..", "src")
files = []
for f in sorted(os.listdir(src_dir)):
    if f.endswith(".py") and f != "__init__.py":
        path = os.path.join(src_dir, f)
        lines = sum(1 for _ in open(path, encoding="utf-8", errors="replace"))
        files.append((f, lines))

files.sort(key=lambda x: -x[1])
for f, lines in files:
    print(f"{f}: {lines} lines")
