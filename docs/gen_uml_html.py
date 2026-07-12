import re, pathlib

doc = pathlib.Path("docs/architecture-uml.md").read_text(encoding="utf-8")
blocks = re.findall(r"```mermaid\n(.*?)```", doc, re.S)

html = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Web Observer — UML</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 0; background: #0d1117; color: #e6edf3; }
  header { padding: 16px 24px; border-bottom: 1px solid #30363d; }
  h1 { margin: 0; font-size: 20px; }
  main { display: grid; gap: 24px; padding: 24px; }
  .card { border: 1px solid #30363d; border-radius: 8px; padding: 16px; background: #161b22; }
  .card h2 { margin-top: 0; font-size: 16px; color: #58a6ff; }
  .mermaid { overflow: auto; }
</style>
</head>
<body>
<header><h1>Web Observer — Architecture UML</h1></header>
<main>
"""

titles = [
    "1. Component / Deployment Diagram",
    "2. Backend Module Structure (Package Diagram)",
    "3. Data Model (Class Diagram / ERD)",
    "4. Sequence — Scheduled Live Check",
    "5. Sequence — Manual / API-Triggered Run",
    "6. Pipeline Decision Flow (Activity Diagram)",
]
for title, b in zip(titles, blocks):
    html += f'<section class="card"><h2>{title}</h2><div class="mermaid">{b}</div></section>\n'

html += """</main>
<script> mermaid.initialize({ startOnLoad: true, theme: "dark" }); </script>
</body>
</html>"""

out = pathlib.Path("docs/architecture-uml.html")
out.write_text(html, encoding="utf-8")
print("wrote", out, "with", len(blocks), "diagrams")
