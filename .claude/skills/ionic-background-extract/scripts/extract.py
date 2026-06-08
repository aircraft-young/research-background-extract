#!/usr/bin/env python3
"""
Ionic liquid paper research background extractor.
离子液体论文研究背景提取器

Parses article.json from paper directories, builds prompts from a template,
calls the ChatAnywhere LLM API, and saves structured JSON with provenance tracing.

Usage:
    python3 scripts/extract.py --paper <paper-dir>     # single paper
    python3 scripts/extract.py --batch                  # all papers
    python3 scripts/extract.py --batch --no-skip        # force re-extract all
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Optional, Tuple

import requests

# ── Resolve paths relative to the script or project root ──────────────

SCRIPT_DIR = Path(__file__).resolve().parent          # .../scripts/
SKILL_DIR = SCRIPT_DIR.parent                        # .../ionic-background-extract/
PROJECT_ROOT = SKILL_DIR.parent.parent.parent        # .../ionic-background-extract/ → .claude/skills/ → .claude/ → project/

PROMPT_TEMPLATE_PATH = PROJECT_ROOT / "p01_research_background.txt"
DEFAULT_PAPERS_DIR = PROJECT_ROOT / "15篇离子液体论文"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "research_backgrounds"

# ── API configuration ─────────────────────────────────────────────────

API_KEY = os.environ.get(
    "CHATANYWHERE_API_KEY",
    "sk-ur78CDqIf2MxGNuDBrHkhFD7eue9of8uND32UmJ0x4NA2CPl",
)
ENDPOINT = "/v1/chat/completions"
MODEL_NAME = os.environ.get("EXTRACT_MODEL_NAME", "deepseek-v4-pro")
BASE_URL = os.environ.get("EXTRACT_BASE_URL", "https://api.chatanywhere.tech")

API_TIMEOUT = int(os.environ.get("EXTRACT_API_TIMEOUT", "180"))
API_MAX_TOKENS = int(os.environ.get("EXTRACT_API_MAX_TOKENS", "8192"))
API_TEMPERATURE = float(os.environ.get("EXTRACT_API_TEMPERATURE", "0.3"))

SYSTEM_PROMPT = (
    "You are a JSON-only extraction assistant. "
    "Output ONLY valid JSON, no explanation, no markdown fences, no reasoning."
)

# ── Helpers ───────────────────────────────────────────────────────────


def log(msg: str, *, level: str = "info") -> None:
    """Print a timestamped log line to stderr."""
    prefix = {"info": "•", "warn": "⚠", "error": "✗"}.get(level, "•")
    print(f"  {prefix} {msg}", file=sys.stderr)


def get_paragraph_text(para: Dict) -> str:
    """Safely extract paragraph text: handles string, list-of-str, and list-of-dict."""
    p = para.get("paragraph", "")
    if isinstance(p, str):
        return p
    if isinstance(p, list):
        parts = []
        for item in p:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(item.get("text", item.get("paragraph", str(item))))
        return " ".join(parts)
    return str(p)


# ── Field extractors ──────────────────────────────────────────────────


def extract_title(paper: Dict) -> str:
    """Extract title from paper JSON."""
    if paper.get("title"):
        return paper["title"]

    paragraphs = paper.get("paragraphs", [])
    if paragraphs:
        text = get_paragraph_text(paragraphs[0])
        # Strip trailing author/affiliation markers
        text = re.sub(r"\s*\*.*$", "", text)
        return text.strip()
    return ""


def extract_abstract(paper: Dict) -> str:
    """Extract abstract from abstracts field or ABSTRACT paragraphs."""
    abstracts = paper.get("abstracts")
    if abstracts:
        if isinstance(abstracts, list):
            return " ".join(a.get("text", "") for a in abstracts)
        return str(abstracts)

    paragraphs = paper.get("paragraphs", [])
    parts = []
    for para in paragraphs:
        head = para.get("head", "").upper()
        text = get_paragraph_text(para).strip()
        if "ABSTRACT" in head or (not head and text.upper().startswith("ABSTRACT")):
            if text:
                parts.append(text)
    return " ".join(parts)


def extract_keywords(paper: Dict) -> str:
    """Extract keywords from keywords field or KEYWORDS paragraph."""
    kw = paper.get("keywords")
    if kw:
        if isinstance(kw, list):
            items = []
            for k in kw:
                if isinstance(k, dict):
                    items.append(k.get("text", k.get("keyword", str(k))))
                else:
                    items.append(str(k))
            return ", ".join(items)
        return str(kw)

    for para in paper.get("paragraphs", []):
        if "KEYWORD" in para.get("head", "").upper():
            text = get_paragraph_text(para).strip()
            if text:
                return text
    return ""


def extract_section(paper: Dict, section_names: Tuple[str, ...],
                    stop_names: Tuple[str, ...]) -> str:
    """Generic section extractor. Collects paragraphs after a section title
    until a stop section is encountered. Title detection checks both the
    head field and the paragraph text content."""
    paragraphs = paper.get("paragraphs", [])
    parts = []
    inside = False

    # Pre-compute upper-case variants to avoid repeated .upper() in the loop
    stop_upper = tuple(s.upper() for s in stop_names)

    for para in paragraphs:
        head = para.get("head", "").upper()
        text = get_paragraph_text(para).strip()
        content_upper = text.upper()

        # Detect section title: head contains section name AND text is short,
        # OR paragraph text content matches section name exactly (for empty-head cases)
        head_match = any(s in head for s in section_names) and len(text) < 50
        content_match = any(s == content_upper for s in section_names) and len(text) < 30
        is_title = head_match or content_match

        if is_title:
            inside = True
            continue

        if inside:
            # Stop at next major section
            if any(s in head for s in stop_names):
                break
            if any(content_upper.startswith(s) for s in stop_upper):
                break
            if text:
                parts.append(text)

    return "\n\n".join(parts)


def extract_introduction(paper: Dict) -> str:
    """Extract introduction paragraphs."""
    return extract_section(
        paper,
        section_names=("INTRODUCTION",),
        stop_names=(
            "EXPERIMENTAL", "METHODS", "RESULTS", "DISCUSSION",
            "CONCLUSION", "CONCLUSIONS", "MATERIALS",
            "ACKNOWLEDGMENT", "REFERENCES",
        ),
    )


def extract_conclusion(paper: Dict) -> str:
    """Extract conclusion paragraphs."""
    return extract_section(
        paper,
        section_names=("CONCLUSION", "CONCLUSIONS"),
        stop_names=(
            "ACKNOWLEDGMENT", "ACKNOWLEDGEMENTS", "REFERENCES",
            "SUPPORTING INFORMATION", "ASSOCIATED CONTENT",
            "AUTHOR INFORMATION", "■", "EXPERIMENTAL",
        ),
    )


# ── Paper parsing ─────────────────────────────────────────────────────


def parse_paper_json(paper_dir: str) -> Dict[str, str]:
    """Parse article.json from a paper directory. Returns {title, abstract, keywords, introduction, conclusion}."""
    article_path = os.path.join(paper_dir, "article.json")
    if not os.path.exists(article_path):
        raise FileNotFoundError(f"article.json not found: {article_path}")

    with open(article_path, encoding="utf-8") as f:
        paper = json.load(f)

    return {
        "title": extract_title(paper),
        "abstract": extract_abstract(paper),
        "keywords": extract_keywords(paper),
        "introduction": extract_introduction(paper),
        "conclusion": extract_conclusion(paper),
    }


# ── LLM API ───────────────────────────────────────────────────────────


# ── Prompt template cache ─────────────────────────────────────────────

_prompt_template_cache: Optional[str] = None


def load_prompt_template() -> str:
    """Load the prompt template file (cached after first read)."""
    global _prompt_template_cache
    if _prompt_template_cache is not None:
        return _prompt_template_cache
    path = str(PROMPT_TEMPLATE_PATH)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Prompt template not found: {path}")
    with open(path, encoding="utf-8") as f:
        _prompt_template_cache = f.read()
    return _prompt_template_cache


def build_prompt(paper_info: Dict[str, str]) -> str:
    """Fill the prompt template with paper data (single-pass substitution)."""
    template = load_prompt_template()
    replacements = {f"{{{k}}}": paper_info.get(k, "") or "" for k in
                    ("title", "abstract", "keywords", "introduction", "conclusion")}
    return re.sub(
        r"\{title\}|\{abstract\}|\{keywords\}|\{introduction\}|\{conclusion\}",
        lambda m: replacements[m.group()],
        template,
    )


def call_llm_api(prompt: str, *, max_retries: int = 2) -> Optional[str]:
    """Call the LLM API with retry logic. Returns response text or None."""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": API_MAX_TOKENS,
        "temperature": API_TEMPERATURE,
    }
    url = f"{BASE_URL}{ENDPOINT}"

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, data=json.dumps(data),
                                timeout=API_TIMEOUT)
            resp.raise_for_status()
            body = resp.json()

            if body.get("choices"):
                content = body["choices"][0]["message"]["content"]
                return content

            log(f"No 'choices' in API response: {json.dumps(body, indent=2, ensure_ascii=False)}",
                level="error")
            return None

        except requests.exceptions.Timeout:
            log(f"Request timed out (attempt {attempt}/{max_retries})", level="warn")
            if attempt == max_retries:
                return None
            time.sleep(5)

        except requests.exceptions.RequestException as e:
            log(f"API request failed: {e}", level="error")
            if hasattr(e, "response") and e.response is not None:
                try:
                    detail = e.response.json()
                    log(f"Error detail: {json.dumps(detail, indent=2, ensure_ascii=False)}",
                        level="error")
                except json.JSONDecodeError:
                    log(f"HTTP {e.response.status_code}", level="error")
            return None

    return None


def _extract_first_json(text: str) -> Optional[str]:
    """Extract the first balanced JSON object from text using brace counting."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_llm_response(raw: str) -> Optional[Dict]:
    """Parse the LLM response as JSON, with fallback extraction."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Fallback: find first balanced JSON object
    json_str = _extract_first_json(raw)
    if json_str:
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    log(f"Failed to parse JSON from response (first 300 chars): {raw[:300]}", level="error")
    return None


def extract_research_background(paper_info: Dict[str, str]) -> Optional[Dict]:
    """Run the full extraction pipeline: build prompt → call API → parse JSON."""
    if not paper_info.get("title") or not paper_info.get("introduction"):
        log("Missing required fields (title or introduction)", level="warn")
        return None

    prompt = build_prompt(paper_info)
    raw = call_llm_api(prompt)

    if raw is None:
        return None

    return parse_llm_response(raw)


# ── Paper processors ──────────────────────────────────────────────────


def process_single_paper(paper_dir: str, output_dir: Optional[str] = None) -> bool:
    """Extract background from one paper directory. Returns True on success."""
    paper_name = os.path.basename(paper_dir)
    print(f"\n{'─' * 56}")
    print(f"Paper: {paper_name}")
    print(f"{'─' * 56}")

    try:
        paper_info = parse_paper_json(paper_dir)
        print(f"  Title        : {paper_info['title'][:70]}…")
        print(f"  Abstract     : {len(paper_info['abstract']):,} chars")
        print(f"  Keywords     : {paper_info['keywords'][:60]}")
        print(f"  Introduction : {len(paper_info['introduction']):,} chars")
        print(f"  Conclusion   : {len(paper_info['conclusion']):,} chars")

        print("  Calling API …", end=" ", flush=True)
        result = extract_research_background(paper_info)

        if result is None:
            print("FAILED")
            return False

        print("OK")

        out_dir = output_dir or str(DEFAULT_OUTPUT_DIR)
        os.makedirs(out_dir, exist_ok=True)
        out_path = os.path.join(out_dir, f"{paper_name}_research_background.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        items = result.get("items", [])
        n_items = len(items)
        for idx, item in enumerate(items, 1):
            preview = item.get("text", "")[:100]
            mode = item.get("extraction_mode", "?")
            tag = f"[{idx}/{n_items}]" if n_items > 1 else ""
            print(f"  Item {tag} ({mode}): {preview}…")
        print(f"  Saved → {out_path}")
        return True

    except Exception as e:
        log(str(e), level="error")
        return False


def process_batch(papers_dir: str, output_dir: Optional[str] = None,
                  skip_existing: bool = True) -> Dict[str, bool]:
    """Batch-process all papers in a directory. Returns {paper_dir: success}."""
    out_dir = output_dir or str(DEFAULT_OUTPUT_DIR)
    print(f"\n{'═' * 56}")
    print(f"Batch: {papers_dir}")
    print(f"Output: {out_dir}")
    print(f"{'═' * 56}")

    if not os.path.isdir(papers_dir):
        log(f"Directory not found: {papers_dir}", level="error")
        return {}

    paper_dirs = sorted(
        d.path for d in os.scandir(papers_dir)
        if d.is_dir() and os.path.exists(os.path.join(d.path, "article.json"))
    )

    print(f"Found {len(paper_dirs)} paper(s)\n")

    if not paper_dirs:
        return {}

    os.makedirs(out_dir, exist_ok=True)

    results: Dict[str, bool] = {}
    for i, paper_dir in enumerate(paper_dirs, 1):
        label = os.path.basename(paper_dir)
        out_path = os.path.join(out_dir, f"{label}_research_background.json")

        if skip_existing and os.path.exists(out_path):
            print(f"[{i:>2}/{len(paper_dirs)}] {label[:40]} … SKIP (exists)")
            results[paper_dir] = True
            continue

        print(f"[{i:>2}/{len(paper_dirs)}] ", end="")
        results[paper_dir] = process_single_paper(paper_dir, output_dir=out_dir)

        if i < len(paper_dirs):
            time.sleep(1)  # rate-limit friendly

    ok = sum(results.values())
    print(f"\n{'─' * 56}")
    print(f"Summary: {ok}/{len(results)} succeeded")
    if ok != len(results):
        print(f"  Failed: {[os.path.basename(d) for d, s in results.items() if not s]}")
    print(f"{'─' * 56}\n")
    return results


# ── CLI ────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Extract research background from ionic liquid papers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/extract.py --paper 15篇离子液体论文/4609501675dfcf877ab8433851a0f998
  python3 scripts/extract.py --batch
  python3 scripts/extract.py --batch --no-skip
  python3 scripts/extract.py --batch --output research_backgrounds
        """,
    )
    parser.add_argument("--paper", "-p", help="Single paper directory path")
    parser.add_argument("--batch", "-b", action="store_true", help="Batch mode")
    parser.add_argument("--dir", "-d", help="Papers root directory (batch mode)")
    parser.add_argument("--no-skip", action="store_true", help="Re-extract even if result exists")
    parser.add_argument("--output", "-o", help="Output directory (default: research_backgrounds/)")
    args = parser.parse_args()

    if args.paper:
        ok = process_single_paper(args.paper, args.output)
        sys.exit(0 if ok else 1)

    if args.batch:
        papers_dir = args.dir or str(DEFAULT_PAPERS_DIR)
        results = process_batch(papers_dir, output_dir=args.output, skip_existing=not args.no_skip)
        all_ok = all(results.values()) if results else False
        sys.exit(0 if all_ok else 1)

    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()