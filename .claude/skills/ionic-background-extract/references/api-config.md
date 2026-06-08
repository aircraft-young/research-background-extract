# API Configuration

## Endpoint

- **Provider**: ChatAnywhere
- **Base URL**: `https://api.chatanywhere.tech`
- **Endpoint**: `/v1/chat/completions`
- **Model**: `deepseek-v4-pro`

## Request Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| temperature | 0.3 | Low temperature for deterministic extraction |
| max_tokens | 8192 | Large enough for full JSON output with provenance |
| timeout | 180s | Long timeout for large prompts (introduction can be 10k+ chars) |
| system message | "You are a JSON-only extraction assistant..." | Prevents reasoning preamble in output |

## Configuration

All API parameters are configured via environment variables with sensible defaults:

| Variable | Default | Notes |
|----------|---------|-------|
| `CHATANYWHERE_API_KEY` | *(built-in)* | Rotate via ChatAnywhere dashboard |
| `EXTRACT_BASE_URL` | `https://api.chatanywhere.tech` | Override for custom endpoints |
| `EXTRACT_MODEL_NAME` | `deepseek-v4-pro` | Override for different models |
| `EXTRACT_API_TIMEOUT` | `180` | Seconds |
| `EXTRACT_API_MAX_TOKENS` | `8192` | Max response tokens |
| `EXTRACT_API_TEMPERATURE` | `0.3` | Deterministic extraction |

## Rate Limits

- Batch processing adds 1s delay between papers to avoid rate limiting
- Default batch behavior skips papers with existing `research_background.json`

## Troubleshooting

### Connection reset / timeout
The API may be slow with large prompts. The script uses a 180s timeout.
If it still fails, try processing papers individually.

### Model returns non-JSON
The system message instructs JSON-only output. If the model still returns
explanatory text, check if the model version changed. Try adding
`response_format: {"type": "json_object"}` if the API supports it.

### Truncated output
If the JSON is cut off mid-response, increase max_tokens beyond 8192.
Large papers with extensive introductions may need more tokens.
