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

## API Key

Managed in `scripts/extract.py`. Rotate via ChatAnywhere dashboard when expired.

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
