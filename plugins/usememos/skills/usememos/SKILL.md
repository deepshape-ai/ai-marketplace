---
name: usememos
description: Access a user's Memos instance to retrieve historical notes, search memos semantically, and perform guarded create/update operations. Use when the user mentions "memo", "usememos", "notes", "recall", "search my notes", "remember", "my memos", or needs to access their Memos instance.
---

# usememos

Access a user's Memos instance through `scripts/usememos_cli.py` with:
- robust read APIs,
- semantic retrieval for long memo lists,
- guarded write operations (`create`/`update`) restricted to the token owner.

## Prerequisites

**Required dependencies:**
- Python 3.8+
- `numpy` - Required for semantic search (TF-IDF + LSA ranking)

**Verify dependencies:**
```bash
python -c "import numpy; print('numpy version:', numpy.__version__)"
```

If numpy is missing:
```bash
pip install numpy
```

## Configuration

**Required environment variables:**

| Variable | Description | Example |
|----------|-------------|----------|
| `USEMEMOS_API_TOKEN` | API token from your Memos instance | `eyJhbGc...` (JWT) or `pat_xxx` (PAT) |
| `USEMEMOS_SITE_URL` | Your Memos instance URL | `https://memos.example.com` |

**Optional:**
- `USEMEMOS_CONFIG_FILE` - Custom config file path (default: `~/.usememos/config.json`)

**Configuration methods:**

Method 1 - Environment variables (recommended):
```bash
export USEMEMOS_API_TOKEN="your-api-token"
export USEMEMOS_SITE_URL="https://your-memos-instance.com"
```

Method 2 - Config file (`~/.usememos/config.json`):
```json
{
  "api_token": "your-api-token",
  "site_url": "https://your-memos-instance.com"
}
```

## Setup Validation

**Copy this checklist and track your progress:**

```
Setup Progress:
- [ ] Step 1: Verify dependencies (check numpy)
- [ ] Step 2: Configure credentials (env vars or config file)
- [ ] Step 3: Test connectivity (run auth check)
- [ ] Step 4: Verify instance access (run instance profile)
```

**Step 1: Verify dependencies**
```bash
python -c "import numpy; print('numpy OK')"
```

**Step 2: Configure credentials**

Check if credentials are configured:
```bash
# Check environment variables
echo "API_TOKEN set: ${USEMEMOS_API_TOKEN:+YES}"
echo "SITE_URL set: ${USEMEMOS_SITE_URL:+YES}"

# Or check config file
cat ~/.usememos/config.json 2>/dev/null || echo "Config file not found"
```

If missing, guide the user:
> I don't see your Memos credentials configured. You need to set either:
> 1. Environment variables: `USEMEMOS_API_TOKEN` and `USEMEMOS_SITE_URL`
> 2. Or create a config file at `~/.usememos/config.json`
>
> Where to find these values:
> - **API Token**: In your Memos instance, go to Settings → API Keys (or Settings → Account → Access Tokens)
> - **Site URL**: The URL where your Memos instance is hosted (e.g., `https://memos.yourdomain.com`)
>
> Would you like me to help you set up the configuration?

**Step 3: Test connectivity**
```bash
python scripts/usememos_cli.py auth me
```

Expected output:
```json
{
  "user": {
    "name": "users/your-username",
    ...
  }
}
```

**Step 4: Verify instance access**
```bash
python scripts/usememos_cli.py instance profile
```

If any step fails, check:
- API token is valid and not expired
- Site URL is correct (include `https://`)
- Network can reach the Memos instance

## Core Workflows

### 1) Read Memos and Related Data

```bash
python scripts/usememos_cli.py memo list --page-size 20 --order-by "pinned desc, display_time desc"
python scripts/usememos_cli.py memo get memos/<memo_id>
python scripts/usememos_cli.py memo attachments memos/<memo_id>
python scripts/usememos_cli.py memo comments memos/<memo_id>
python scripts/usememos_cli.py memo relations memos/<memo_id>
python scripts/usememos_cli.py memo reactions memos/<memo_id>
```

### 2) Semantic Search

```bash
python scripts/usememos_cli.py memo search "intent in natural language" \
  --page-size 20 \
  --max-pages 2 \
  --top-k 8 \
  --min-score 0.15
```

Output is intentionally readable for LLM consumption:
- `title` and `excerpt` for each hit,
- `relevance` scores (`semantic`, `lexical`, `coverage`, final `score`),
- `suggestions` when no strong match is found.

### 3) Guarded Write Operations

Supported writes:
- `memo create`
- `memo update`

All writes require:
- explicit human approval text: `--user-consent`
- target-bound confirmation:
- `--confirm-text` exact value

Agent behavior requirement:
1. Before running `create` or `update`, the agent must send a human-readable change proposal.
2. The agent must ask for explicit user approval in text.
3. Only after an affirmative reply may the agent execute the write command.

```bash
# Create
python scripts/usememos_cli.py memo create \
  --content "Release note ..." \
  --user-consent "User approved creating this memo after reviewing the proposal." \
  --visibility PRIVATE \
  --confirm-text 'CREATE:memo'

# Update
python scripts/usememos_cli.py memo update memos/<memo_id> \
  --content "Updated content" \
  --user-consent "User approved this exact update after diff review." \
  --confirm-text 'UPDATE:memos/<memo_id>'
```

Write safety enforcement:
- `update` verifies memo ownership (`creator == current token user`).
- Cross-user writes are rejected.

`--confirm-text` purpose:
- Binds the command to a specific action target.
  Example: `'UPDATE:memos/<memo_id>'` prevents accidental updates to a different memo ID.

## Script Usage Reference

### Command Groups

- `auth`: `me`
- `memo`: `list|get|search|create|update|attachments|comments|relations|reactions`
- `user`: `list|get|stats|setting|settings|notifications|webhooks`
- `activity`: `list|get`
- `attachment`: `list|get`
- `shortcut`: `list|get`
- `identity-provider`: `list|get`
- `instance`: `profile`

### Resource ID Input

The CLI accepts either raw IDs or resource names:
- `K95L...` and `memos/K95L...` are both valid for memo operations.
- Same normalization applies to `users/...`, `attachments/...`, etc.

### Error Contract (LLM-Friendly)

Errors are JSON objects:
```json
{
  "ok": false,
  "error": {
    "type": "validation_error",
    "message": "...",
    "details": {"...": "..."},
    "hint": "..."
  }
}
```

## Search Method Notes

Semantic ranking is implemented as:
- TF-IDF vectorization,
- LSA (SVD-based latent semantic space),
- cosine similarity scoring,
- score fusion with lexical and coverage signals.

No predefined synonym dictionary is used.

For full retrieval strategy and scaling guidance, see `SEARCH-STRATEGY.md`.
