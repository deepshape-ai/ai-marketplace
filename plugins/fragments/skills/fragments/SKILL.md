---
name: fragments
description: >
  Fragmented work logging and idea capture powered by Memos.
  Two modes: (1) memo — capture ideas, notes, code snippets on demand
  with semantic search; (2) daily-log — structured daily work journal
  in .plan format (* done, + todo, - note, ? question).
  Passive trigger: after agent completes a task, prompt user to record
  daily log. Active trigger: user says "memo", "note", "capture",
  "daily log", "fragments", "记录", "笔记", "日志", "想法".
---

# Fragments

## Version Check

1. Read `VERSION` file in this skill directory → SKILL_VERSION.
2. Read `~/.config/fragments.json` (Windows: `%USERPROFILE%\.config\fragments.json`).
3. Route:
   - File missing → first install. Detect current platform, read the matching setup guide:
     - Claude Code → `references/setup-claude-code.md`
     - OpenCode → `references/setup-opencode.md`
   - `version` < SKILL_VERSION → update needed. Read the setup guide's **Update** section.
   - `version` == SKILL_VERSION → verify platform MCP and hooks are configured.
     If incomplete → read the matching setup guide.
   - All good → proceed to normal usage.

## Modes

### memo — Capture Ideas

Create, search, and manage memos via MCP tools (auto-discovered).
Write operations require user confirmation before calling.

Detailed workflow, content routing, and attachment handling:
→ `references/memo-capture.md`

### daily-log — Daily Work Journal

One structured log per user per day. Content follows `.plan` format
enforced by the Memos server.

Format rules, diff-merge logic, and hook trigger workflow:
→ `references/daily-log.md`

### search — Semantic Search

Server-side full-text retrieval via MCP, optional client-side
TF-IDF + LSA rerank for semantic/fuzzy queries.

Pipeline details and tuning parameters:
→ `references/search-strategy.md`

## Retrieval Strategy

Data volume can be large. Always prefer targeted retrieval over bulk listing.

### Memos

1. **Search first**: `memos_search_memos(query=...)` — use when the user has
   any intent, keyword, or topic. Returns bounded results.
2. **Get by ID**: `memos_get_memo(name=...)` — use when you already know the
   memo name. Expand full content only for shortlisted results.
3. **List as fallback**: `memos_list_memos(page_size=10)` — use only for
   explicit "show recent" requests. Always set a small `page_size`.
4. **Client-side rerank**: pipe search results through `scripts/fragments_search.py`
   for semantic ranking when server-side results need refinement.

### Daily Logs

1. **Get by date**: `memos_get_daily_log(date=YYYY-MM-DD)` — single log lookup.
   Pass `creator="users/{id}"` to view another user's log (PROTECTED visibility).
2. **List with date range**: `memos_list_daily_logs(start_date, end_date, page_size=10)`
   — use only for explicit "show this week/month" requests. Always bound the range.

### Tags

- `memos_list_tags` — lightweight, use to discover available tags for filtering.

No read operations require user confirmation.

## Write Safety

All MCP write operations (create, update, delete, save) require
explicit user confirmation before calling. Read operations need
no confirmation. Never echo PAT tokens to the conversation.

## Hook Workflow (Passive Trigger)

When triggered by agent task completion:

1. Assess whether this session performed meaningful work. Skip if trivial.
2. Call `memos_get_daily_log` for today's date.
3. Format new entries in `.plan` style.
4. Diff against existing content. Skip if no new information.
5. Long-form content → suggest creating a memo first, reference in daily log.
6. Show user the full merged log (existing + new). Wait for confirmation.
7. Call `memos_save_daily_log` with complete content (full replacement).
