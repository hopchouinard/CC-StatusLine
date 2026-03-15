# CC-StatusLine Plugin — Packaging Spec

**Project directory:** `~/Developer/CC-StatusLine`
**Goal:** Package the existing `statusline.py` as an installable Claude Code plugin (`.plugin` file)

---

## Plugin Directory Structure

Create the following structure alongside the existing project files:

```
CC-StatusLine/
├── .claude-plugin/
│   └── plugin.json
├── scripts/
│   └── statusline.py          ← copy of existing statusline.py
├── settings.json               ← statusLine config using plugin path
├── commands/
│   └── statusline-test.md      ← test command
├── README.md                   ← already exists, update if needed
└── cc-statusline.plugin        ← final packaged output
```

---

## plugin.json

```json
{
  "name": "cc-statusline",
  "version": "1.0.0",
  "description": "4-line ANSI dashboard statusline for Claude Code showing environment, context window, session cost, and git status",
  "author": {
    "name": "Patrick Chouinard"
  },
  "license": "MIT",
  "keywords": ["statusline", "dashboard", "status", "context", "git"]
}
```

---

## settings.json

Plugin-level `settings.json` at the plugin root. This registers the statusline automatically when the plugin is installed.

```json
{
  "statusLine": {
    "type": "command",
    "command": "python3 ${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py",
    "padding": 2
  }
}
```

**Key:** Use `${CLAUDE_PLUGIN_ROOT}` so the path resolves correctly regardless of where the plugin is cached after installation.

---

## commands/statusline-test.md

A slash command to test the statusline with a sample payload without restarting Claude Code.

```markdown
---
description: Test the CC-StatusLine script with a sample payload
allowed-tools: Bash
---

Run the CC-StatusLine script with a test payload to verify it renders correctly. Execute:

bash -c 'echo '"'"'{"version":"2.1.56","model":{"id":"claude-opus-4-6","display_name":"Opus"},"cwd":"'$(pwd)'","cost":{"total_cost_usd":0.42,"total_duration_ms":2712000,"total_api_duration_ms":723000,"total_lines_added":156,"total_lines_removed":23},"context_window":{"used_percentage":17,"context_window_size":200000,"current_usage":{"input_tokens":8500,"output_tokens":1200,"cache_creation_input_tokens":5000,"cache_read_input_tokens":2000}}}'"'"' | python3 ${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py'

Show the raw output to the user. If it fails, show the error.
```

---

## scripts/statusline.py

Copy the existing `statusline.py` from the project root into `scripts/statusline.py`. No modifications needed — the script reads from stdin and writes to stdout, so it's already path-independent.

---

## Packaging

After creating all files, package the plugin:

```bash
cd ~/Developer/CC-StatusLine && zip -r /tmp/cc-statusline.plugin \
  .claude-plugin/ \
  scripts/statusline.py \
  settings.json \
  commands/ \
  README.md \
  -x "*.DS_Store"
```

The final `cc-statusline.plugin` file should be copied back to the project root.

---

## Validation

Before packaging, run:

```bash
claude plugin validate ~/Developer/CC-StatusLine/.claude-plugin/plugin.json
```

Fix any errors or warnings before proceeding to the zip step.

---

## README.md Updates

If the existing README doesn't already cover plugin installation, add a section:

```markdown
## Plugin Installation

Install the `.plugin` file in Claude Code:

\`\`\`bash
claude plugin install cc-statusline.plugin
\`\`\`

The statusline activates automatically. Restart Claude Code to see it.

### Test

Use the included slash command to verify rendering:

\`\`\`
/cc-statusline:statusline-test
\`\`\`
```
