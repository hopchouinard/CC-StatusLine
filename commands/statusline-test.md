---
description: Test the CC-StatusLine script with a sample payload
allowed-tools: Bash
---

Run the CC-StatusLine script with the test payload to verify it renders correctly. Detect the platform and run the appropriate command:

On macOS/Linux:

```bash
cat "${CLAUDE_PLUGIN_ROOT}/test-payload.json" | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py"
```

On Windows:

```bash
type "${CLAUDE_PLUGIN_ROOT}\test-payload.json" | python "${CLAUDE_PLUGIN_ROOT}\scripts\statusline.py"
```

Show the raw output to the user. If it fails, show the error.
