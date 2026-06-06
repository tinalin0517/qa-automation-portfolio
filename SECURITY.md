# Security Notes for Portfolio Use

This repository is intended for portfolio demonstration only.

## Do not commit

- Real API keys, tokens, cookies, or passwords
- Company internal URLs, AWS hostnames, VPN/SSO details, or database credentials
- Customer data, production logs, Jira IDs, screenshots, or private documents
- `.env`, browser session files, report artifacts, or zipped company source code

## Recommended setup

1. Copy `.env.example` to `.env`.
2. Fill in only local/demo values.
3. Keep `.env` private and verify it is ignored by Git.
4. Use mock log input unless you are testing a private local integration.

All endpoints, service names, logs, and code references in this repository should remain mock/demo data.
