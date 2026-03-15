---
description: Test the CC-StatusLine script with a sample payload
allowed-tools: Bash
---

Run the CC-StatusLine script with a test payload to verify it renders correctly. Execute this command:

```bash
echo '{"version":"2.1.56","model":{"id":"claude-opus-4-6","display_name":"Opus"},"cwd":"'"$(pwd)"'","cost":{"total_cost_usd":0.42,"total_duration_ms":2712000,"total_api_duration_ms":723000,"total_lines_added":156,"total_lines_removed":23},"context_window":{"used_percentage":17,"context_window_size":200000,"current_usage":{"input_tokens":8500,"output_tokens":1200,"cache_creation_input_tokens":5000,"cache_read_input_tokens":2000}}}' | python3 "${CLAUDE_PLUGIN_ROOT}/scripts/statusline.py"
```

Show the raw output to the user. If it fails, show the error.
