# SECURITY.md

Security rules for this project. These apply to every contributor, human or AI.

## Credentials
- Never hardcode API keys, passwords, tokens, or connection strings in source, scripts, or config files.
- Use environment variables (or a proper secrets manager) for all configuration.
- Never commit `.env` or any file containing real credentials — `.env.example` (placeholders only) is the only env file that belongs in version control.
- Prefer platform-native auth (e.g. OAuth, IAM roles, Windows Integrated Auth) over embedded credentials wherever possible.

## Logging
- Never log secrets, passwords, API keys, session tokens, or full connection strings — redact them (e.g. `Password=****`) before logging or printing.
- Never log sensitive personal information (PII) in plaintext application logs.
- When a connection string or credential must be shown for debugging, redact the sensitive portion.

## Data Handling
- Validate and sanitize all external input (user input, API responses, file uploads) at the system boundary.
- Avoid introducing common vulnerability classes: SQL/command injection, XSS, insecure deserialization, path traversal.
- Enforce access control at the data layer, not just the UI — a user should never be able to fetch another user's data by changing an ID.

## Dependencies & Deployment
- Don't add dependencies without checking they're actively maintained and free of known critical CVEs.
- Never push to production without review/approval from a human.
- Never disable security checks (linters, CI security scans, `--no-verify`) to unblock a merge — fix the underlying issue instead.
