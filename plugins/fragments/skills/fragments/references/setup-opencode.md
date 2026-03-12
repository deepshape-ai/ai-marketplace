# Setup — OpenCode

## Language

Communicate with the user in their current conversation language.
Each step requires user confirmation before proceeding.
Sensitive values (PAT token) are written to local config only, never echoed.

## First Install

### Step 1: Verify Memos Service

Check reachability of the Memos server.

- Read `~/.config/fragments.json` for an existing `site_url`, or ask the user.
- Test connectivity: use Bash to run `curl -sf <site_url>/api/v1/status` (macOS/Linux)
  or `Invoke-WebRequest -Uri <site_url>/api/v1/status` (Windows PowerShell).
- If unreachable, ask user to verify the URL and that the Memos server is running.

### Step 2: Configure PAT Token

Ask the user for their Memos Personal Access Token (format: `memos_pat_*`).

Write `~/.config/fragments.json`:

```json
{
  "version": "<SKILL_VERSION>",
  "pat_token": "<user_provided_token>",
  "site_url": "<confirmed_url>",
  "mcp_url": "<confirmed_url>/mcp"
}
```

Paths:
- macOS / Linux: `~/.config/fragments.json`
- Windows: `%USERPROFILE%\.config\fragments.json`

Ensure the `.config` directory exists before writing.

### Step 3: Configure MCP

Read `assets/opencode/mcp.json` in this skill directory.
Substitute `{{MCP_URL}}` and `{{PAT_TOKEN}}`.

Merge the resulting config into the user's OpenCode config.
OpenCode MCP config lives in one of:
- Project: `opencode.json` → `mcp` key
- Global: `~/.config/opencode/opencode.json` → `mcp` key

Prefer project-level config. Add a `memos` entry under `mcp` with `type: "remote"`.

### Step 4: Install Plugin

Read `assets/opencode/plugin.ts` in this skill directory.

Copy it to the OpenCode plugins directory:
- Project: `.opencode/plugins/fragments-hook.ts`
- Or global: `~/.config/opencode/plugins/fragments-hook.ts`

Prefer project-level. Create the directory if absent.

### Step 5: Verify

Call `memos_list_tags` via MCP. Confirm success.

### Step 6: Confirm Version

Set `version` in `fragments.json` to SKILL_VERSION.

## Update

### Step 1: Re-read Asset Templates

Read `assets/opencode/mcp.json` and `assets/opencode/plugin.ts`.

### Step 2: Merge Config

- Update MCP entry in OpenCode config.
- Overwrite `fragments-hook.ts` with new version.
- Preserve `pat_token`, `site_url`, `mcp_url` in `fragments.json`.

### Step 3: Update Version

Set `version` in `fragments.json` to SKILL_VERSION.

### Step 4: Verify

Call `memos_list_tags`. Confirm success.

## Platform Paths

| Item | macOS / Linux | Windows |
|------|--------------|---------|
| Config | `~/.config/fragments.json` | `%USERPROFILE%\.config\fragments.json` |
| OpenCode config | `~/.config/opencode/opencode.json` | `%USERPROFILE%\.config\opencode\opencode.json` |
| OpenCode plugins | `.opencode/plugins/` or `~/.config/opencode/plugins/` | Same relative paths |
| Python | `python3` / `pip3` | `py` / `pip` |
