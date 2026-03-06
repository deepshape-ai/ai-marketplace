# Configuration Example

## Configuration File Location

```
~/.usememos/config.json
```

## Configuration Structure

```json
{
  "site_url": "https://your-memos-instance.com",
  "api_token": "your-api-token-here",
  "created_at": "2024-01-15T10:30:00Z"
}
```

## Field Descriptions

### site_url (required)
- Your usememos instance URL
- Must include protocol (https://)
- No trailing slash
- Example: `https://your-memos-instance.com`

### api_token (required)
- Generated from usememos Settings → API Tokens
- Must have read permissions
- Keep this secure and never commit to git

### created_at (auto-generated)
- Timestamp when config was created
- Set automatically by agent

## Getting API Token

1. Navigate to your usememos instance
2. Log in with your account
3. Go to **Settings** → **API Tokens**
4. Click **Create new token**
5. Enter a description (e.g., "Claude Agent Access")
6. Select permissions:
   - **Read memos** (required)
   - Other permissions (optional, not used by this skill)
7. Click **Create**
8. **Copy the token immediately** (shown only once)

## Security Notes

### DO
- Store config in `~/.usememos/config.json`
- Use environment variables for CI/CD
- Restrict file permissions: `chmod 600 ~/.usememos/config.json`
- Rotate tokens periodically

### DON'T
- Commit config file to git
- Share token in chat or email
- Use token with write permissions (read-only is sufficient)
- Store token in plain text in scripts

## Validation

To validate your configuration:

```bash
# Test authentication
curl -H "Authorization: Bearer YOUR_TOKEN" \
  https://your-memos-instance.com/api/v1/users/me
```

Expected response:
```json
{
  "name": "users/1",
  "username": "your-username",
  "email": "your@email.com",
  ...
}
```

If you get 401 Unauthorized, your token is invalid or expired.

## Troubleshooting

### "Config file not found"
Create the config file:
```bash
mkdir -p ~/.usememos
echo '{"site_url":"...", "api_token":"..."}' > ~/.usememos/config.json
chmod 600 ~/.usememos/config.json
```

### "Invalid token"
- Verify token in Settings → API Tokens
- Token may have been revoked
- Generate new token and update config

### "Site unreachable"
- Verify URL format (include https://)
- Check if usememos instance is running
- Test URL in browser

### "Permission denied"
- Token needs read permissions
- Create new token with correct permissions
