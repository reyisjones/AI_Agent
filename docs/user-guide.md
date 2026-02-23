# AI Agent — User Guide

## Overview
The AI Agent is a conversational assistant that can answer questions, look up
information in this knowledge base, fetch data from external APIs, and tell you
the current time in any timezone.

## Getting Started

### Chat endpoint
Send a `POST` request to `/api/v1/chat`:

```json
{
  "session_id": "my-unique-session",
  "message": "What time is it in Tokyo?",
  "user_id": "alice"
}
```

Response:
```json
{
  "session_id": "my-unique-session",
  "response_id": "resp_abc123",
  "reply": "The current time in Tokyo (Asia/Tokyo) is 09:42:15 JST.",
  "tools_called": ["get_time"],
  "input_tokens": 123,
  "output_tokens": 42
}
```

## Available Tools

| Tool | Description |
|------|-------------|
| `get_time` | Returns current date/time for any IANA timezone |
| `http_request` | Fetches data from allowed external APIs |
| `knowledge_search` | Searches this documentation folder |

## Rate Limits
- Tool calls: 30 per minute per server process.
- Request timeouts: 10 seconds per tool call.

## Troubleshooting

### My message was rejected with a 400 error
The content safety layer blocked the message. Review the request for
potentially dangerous patterns (shell commands, SQL injections, etc.).

### The agent isn't calling tools
Make sure you are describing your intent clearly. The agent will call tools
when it determines a tool is needed based on the system policy.

### Redis / Postgres not available
The agent will fall back gracefully:
- Redis unavailable → in-process session storage (lost on restart).
- Postgres unavailable → long-term memory features disabled (no crash).

## Deployment
See the README.md in the repo root for deployment instructions.
