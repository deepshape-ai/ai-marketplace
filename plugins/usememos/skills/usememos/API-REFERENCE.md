# usememos API Reference

## Base URL

```
https://your-memos-instance.com/api/v1
```

For user's instance: `{site_url}/api/v1`

## Authentication

All API requests require Bearer Token authentication.

### Getting API Token

1. Log into usememos web interface
2. Navigate to Settings → API Tokens
3. Create new token with appropriate permissions
4. Copy token (shown only once)

### Using Token

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://memos.example.com/api/v1/memos
```

## Endpoints

### List Memos

**GET /api/v1/memos**

Retrieve memos with filtering, pagination, and sorting.

#### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `pageSize` | integer | 50 | Max results per page (max: 1000) |
| `pageToken` | string | - | Pagination token from previous response |
| `filter` | string | - | CEL expression to filter memos |
| `orderBy` | string | "display_time desc" | Sort order |
| `state` | string | "NORMAL" | "NORMAL" or "ARCHIVED" |
| `showDeleted` | boolean | false | Include deleted memos |

#### Filter Syntax (CEL)

**Common filter patterns:**

```bash
# By tag
filter: "tag == 'API'"
filter: "tag == 'design-patterns' || tag == 'architecture'"

# By visibility
filter: "visibility == 'PUBLIC'"
filter: "visibility == 'PRIVATE'"

# By content (not available via API, must search in response)
# Use keyword search in returned memos

# Combined filters
filter: "tag == 'API' && visibility == 'PUBLIC'"
```

#### Order Options

- `display_time desc` (default) - Most recent first
- `display_time asc` - Oldest first
- `create_time desc` - Creation time, newest first
- `create_time asc` - Creation time, oldest first
- `update_time desc` - Last updated first
- `pinned desc, display_time desc` - Pinned first, then recent

#### Response

```json
{
  "memos": [
    {
      "name": "memos/123",
      "state": "NORMAL",
      "creator": "users/1",
      "createTime": "2024-01-15T10:30:00Z",
      "updateTime": "2024-01-15T10:30:00Z",
      "displayTime": "2024-01-15T10:30:00Z",
      "content": "Memo content here...",
      "visibility": "PUBLIC",
      "tags": ["API", "design-patterns"],
      "pinned": false,
      "attachments": []
    }
  ],
  "nextPageToken": "string"
}
```

#### Example

```bash
# Get recent public memos tagged with "API"
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?filter=tag%3D%3D'API'%20%26%26%20visibility%3D%3D'PUBLIC'&pageSize=20"
```

### Get Memo

**GET /api/v1/memos/{id}**

Retrieve a specific memo by ID.

#### Path Parameters

- `id` (required): Memo ID (e.g., "123" from "memos/123")

#### Response

```json
{
  "name": "memos/123",
  "state": "NORMAL",
  "creator": "users/1",
  "createTime": "2024-01-15T10:30:00Z",
  "updateTime": "2024-01-15T10:30:00Z",
  "displayTime": "2024-01-15T10:30:00Z",
  "content": "Full memo content...",
  "visibility": "PUBLIC",
  "tags": ["API", "design-patterns"],
  "pinned": false,
  "attachments": []
}
```

#### Example

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://your-memos-instance.com/api/v1/memos/123
```

### Get Current User

**GET /api/v1/users/me**

Validate authentication token and get user info.

#### Response

```json
{
  "name": "users/1",
  "id": 1,
  "username": "your-username",
  "email": "your@email.com",
  "nickname": "Your Name",
  "avatarUrl": "...",
  "role": "USER",
  "createTime": "2024-01-01T00:00:00Z",
  "updateTime": "2024-01-01T00:00:00Z"
}
```

#### Example

```bash
curl -H "Authorization: Bearer $TOKEN" \
  https://your-memos-instance.com/api/v1/users/me
```

**Use this to validate token before searching memos.**

## Pagination

### Using Page Tokens

```bash
# First page
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?pageSize=50"

# Response contains nextPageToken
{
  "memos": [...],
  "nextPageToken": "abc123token"
}

# Next page
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?pageSize=50&pageToken=abc123token"
```

### Pagination Strategy

1. Start with `pageSize=50` (default)
2. If `nextPageToken` present and need more results, fetch next page
3. Stop when:
   - User's intent satisfied
   - No more results (`nextPageToken` absent)
   - Reached reasonable limit (e.g., 200 memos)

## Error Responses

### Standard Error Format

```json
{
  "code": 3,
  "message": "Invalid argument",
  "details": []
}
```

### Common HTTP Status Codes

| Status | Meaning | Action |
|--------|---------|--------|
| 200 | Success | Process response |
| 400 | Bad Request | Check query syntax |
| 401 | Unauthorized | Token invalid/expired |
| 403 | Forbidden | Token lacks permissions |
| 404 | Not Found | Invalid URL or resource ID |
| 429 | Too Many Requests | Rate limited - wait and retry |
| 500 | Internal Error | Instance issue - check status |

### Rate Limiting

- No official documentation on limits
- Implement exponential backoff on 429 errors
- Reasonable usage: < 100 requests/minute

## Data Types

### Memo Object

```json
{
  "name": "memos/123",           // Resource name (format: "memos/{id}")
  "state": "NORMAL",             // "NORMAL" or "ARCHIVED"
  "creator": "users/1",          // Creator resource name
  "createTime": "2024-01-15T10:30:00Z",
  "updateTime": "2024-01-15T10:30:00Z",
  "displayTime": "2024-01-15T10:30:00Z",
  "content": "Memo text...",      // Full content
  "visibility": "PUBLIC",        // "PUBLIC", "PRIVATE", or "PROTECTED"
  "tags": ["tag1", "tag2"],      // Array of tags
  "pinned": false,               // Whether memo is pinned
  "attachments": [               // Array of attachments
    {
      "name": "attachments/456",
      "createTime": "...",
      "filename": "image.png",
      "externalLink": "...",
      "type": "IMAGE"
    }
  ]
}
```

### Visibility Values

- `PUBLIC`: Visible to all users (including anonymous)
- `PRIVATE`: Only visible to creator
- `PROTECTED`: Visible to authenticated users

### State Values

- `NORMAL`: Active memo
- `ARCHIVED`: Archived memo (use `state=ARCHIVED` to list)

## Best Practices

### 1. Validate Token First

Always call `GET /api/v1/users/me` before searching to ensure token is valid.

### 2. Use Filters Effectively

```bash
# Good: Specific filter
filter: "tag == 'API' && visibility == 'PUBLIC'"

# Avoid: Too broad (fetches all memos)
# Then filter in code
```

### 3. Handle Pagination

Don't assume all results fit in one response. Use `nextPageToken` for completeness.

### 4. Respect Rate Limits

Implement exponential backoff:
- 1st retry: wait 1s
- 2nd retry: wait 2s
- 3rd retry: wait 4s
- Then fail gracefully

### 5. Error Messages

When errors occur, provide actionable guidance:
- "Your API token is invalid. Please check Settings → API Tokens"
- "Rate limit reached. Waiting 2 seconds before retry..."

## Examples

### Search by Tag

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?filter=tag%3D%3D'API'&pageSize=20"
```

### Search Multiple Tags

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?filter=tag%3D%3D'API'%20%7C%7C%20tag%3D%3D'design'&pageSize=20"
```

### Get Pinned Memos

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?orderBy=pinned%20desc%2C%20display_time%20desc&pageSize=50"
```

### Get Private Memos

```bash
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?filter=visibility%3D%3D'PRIVATE'&pageSize=50"
```

### Get Recent Memos (Last 30 days)

Note: API doesn't support date filtering directly. Filter in code after fetching:

```bash
# Fetch recent memos
curl -H "Authorization: Bearer $TOKEN" \
  "https://your-memos-instance.com/api/v1/memos?orderBy=display_time%20desc&pageSize=100"

# Then filter by createTime in your code (last 30 days)
```
