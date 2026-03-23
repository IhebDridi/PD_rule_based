# Shared HTML templates

These files are loaded by oTree using paths like `templates/global/YourPage.html` (project root is searched first).

Shared page classes in `pages_classes/` set `template_name` accordingly. **Exception:** `AgentProgramming` has no global template—each app keeps its own (e.g. `AgentProgramming.html`, `ChatGPTPage.html`) under `<app>/templates/<AppName>/`.

You can maintain the same files under `_templates/global/` for reference; the runtime paths used in code point here (`templates/global/`).
