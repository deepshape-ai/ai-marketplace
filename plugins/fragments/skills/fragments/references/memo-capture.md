# Memo Capture

## Trigger

User explicitly requests to record a note, idea, or memo.
Keywords: "memo", "note", "capture", "jot down", "记录", "笔记", "想法".

## Workflow

1. Parse user input into memo content (markdown supported).
2. Auto-extract tags from content (pattern: `#TagName`).
3. Determine visibility:
   - Default: PRIVATE
   - User can override to PROTECTED or PUBLIC.
4. Show user a preview of the memo content. Get confirmation.
5. Call `memos_create_memo(content=..., visibility=...)`.
6. Return the memo name (`memos/{uid}`) for reference.

## Content Routing (Daily Log Integration)

When memo capture is invoked during a daily-log flow:

1. Create the memo first via `memos_create_memo`.
2. Receive `memos/{uid}` from the response.
3. Append a reference line to the daily log:
   `* <one-line summary>, see memos/{uid}`

This keeps daily logs concise while preserving detailed context in memos.

## Attachments

MCP does not support file upload (protocol limitation).

When the user wants to attach images or files:

1. Create the text memo via MCP first. Note the returned `memos/{uid}`.
2. Provide the Memos web UI URL: `{site_url}/m/{uid}`
   (read `site_url` from `~/.config/fragments.json`).
3. Instruct the user to open that URL in a browser and upload
   attachments there using the Memos web interface.

## Dedup Before Create

Before creating a new memo, run a quick search to avoid duplicates:

1. Call `memos_search_memos(query=<key_phrases_from_content>)`.
2. If a highly similar memo exists, show it to the user and ask:
   - Update the existing memo?
   - Create a new one anyway?
3. If no match, proceed with creation.
