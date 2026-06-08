---
name: ionic-background-extract
description: |
  Extract research problem background from ionic liquid (离子液体) academic papers.
  Parses article.json from 15篇离子液体论文/, builds prompts from p01_research_background.txt,
  calls the LLM API via ChatAnywhere, and saves structured JSON with provenance tracing.

  Use when user asks to: extract research background from ionic liquid papers,
  batch-extract backgrounds from the 15 papers folder, "提取离子液体论文背景",
  "抽取论文研究背景", "批量提取背景", or any request involving academic background
  extraction from the ionic liquid paper collection.

  Supports single-paper and batch processing. Output saved as research_background.json.
---

# Ionic Liquid Paper Research Background Extractor

Extract the research-problem background from ionic liquid papers in `15篇离子液体论文/`,
returning structured JSON with provenance tracing.

## Workflow

### 1. Determine processing mode

Ask the user whether to process a single paper or batch. If not specified, default to
single-paper mode using the first paper in `15篇离子液体论文/`.

### 2. Run the extraction script

The script handles data parsing, prompt building, API calling, and result saving.

**Single paper:**

```bash
python3 scripts/extract.py --paper "<path-to-paper-dir>"
```

**Batch (all 15 papers):**

```bash
python3 scripts/extract.py --batch
```

**Batch (force re-extract all papers, skipping none):**

```bash
python3 scripts/extract.py --batch --no-skip
```

### 3. Present results

After extraction succeeds, read the generated `research_background.json` and present
the key findings to the user:

- Paper title
- Extracted background text (the core finding)
- Extraction mode (extracted vs summarized)
- Source section and sentence
- Brief 4-step method summary

### 4. Handle errors

- **Network timeout**: Retry once with a longer timeout (the script uses 180s by default)
- **JSON parse failure**: Show the raw response prefix so the user can diagnose
- **Missing article.json**: Report which paper directory is missing data
- **Empty introduction/conclusion**: Warn the user but continue with available fields

## Script details

The `scripts/extract.py` script:

1. Parses `article.json` — extracts title, abstract, keywords, introduction, conclusion
   from the PDF-parsed JSON structure (handles both string and list paragraph formats)
2. Loads the prompt template from `p01_research_background.txt`
3. Calls the ChatAnywhere API (deepseek-v4-pro, temperature=0.3, max_tokens=8192)
4. Validates and saves the JSON response to `research_backgrounds/{paper}_research_background.json`

For API configuration details, see `references/api-config.md`.

## Output

Results are saved to `research_backgrounds/{paper_dir_name}_research_background.json` by default.
Override with `--output <dir>`.

### Output format

The output JSON contains:

- `knowledge_object`: identifier for the extracted knowledge unit
- `method_feedback`: 4-step extraction trace (identify → locate → decide → finalize),
  each with action, finding, feedback, and provenance
- `items`: 1-3 background items (allows multiple when the paper has distinct background aspects),
  each with text, extraction_mode, and provenance
