
## No-Regression Baseline

Five documents were run through `fit_split.py` to establish a concrete baseline. Results are recorded below. "Strictly better" is defined as a set of criteria the new tool must satisfy on every input tested here.

## fit_split.py Behavior

fit_split.py performs a **single heading-level split and stops** — no recursion, no code block handling. Root documents are consistently within target. Subdocuments are not checked or further split.

## Test Results

### prompt-caching.md (~28,255 tokens input)

| Output | Tokens | Status |
|---|---|---|
| root | 1,288 | ✅ |
| introduction.md | 1,760 | ✅ |
| pricing.md | 565 | ✅ |
| automatic-caching.md | 2,445 | ✅ |
| explicit-cache-breakpoints.md | 1,462 | ✅ |
| caching-strategies-and-considerations.md | 3,351 | ⚠️ over target |
| 1-hour-cache-duration.md | 735 | ✅ |
| **prompt-caching-examples.md** | **14,343** | 🚨 critical failure |
| faq.md | 3,069 | ⚠️ over target |

`prompt-caching-examples.md` is almost certainly a large block of code examples — exactly the failure mode that inline language preference is designed to prevent. This is the primary prototype corpus for language detection.

---

### extended-thinking.md (~35,399 tokens input)

| Output | Tokens | Status |
|---|---|---|
| root | 2,649 | ✅ |
| **how-to-use-extended-thinking.md** | **9,578** | 🚨 critical failure |
| **extended-thinking-with-tool-use.md** | **8,315** | 🚨 critical failure |
| **extended-thinking-with-prompt-caching.md** | **13,174** | 🚨 critical failure |
| max-tokens-and-context-window-size.md | 722 | ✅ |
| differences-in-thinking-across-model-versions.md | 822 | ✅ |
| best-practices-and-considerations.md | 838 | ✅ |

Three subdocs are massively over target — pure recursion failure. These likely contain significant code block content as well.

---

### openrouter/prompt-caching.md (~3,935 tokens input)

| Output | Tokens | Status |
|---|---|---|
| root | 1,669 | ✅ |
| anthropic-claude.md | 1,350 | ✅ |
| google-gemini.md | 1,033 | ✅ |

Clean output. All subdocs within target. Good regression check.

---

### tool-use/overview.md (~2,137 tokens input)

fit_split.py split this document into 4 sections despite the input being under 3k tokens. **This is incorrect behavior** — a document already within the target should not be split at all. The new tool must leave it alone.

---

### adaptive-thinking.md (~8,579 tokens input)

| Output | Tokens | Status |
|---|---|---|
| root | 1,962 | ✅ |
| how-to-use-adaptive-thinking.md | 1,624 | ✅ |
| adaptive-thinking-with-the-effort-parameter.md | 1,462 | ✅ |
| streaming-with-adaptive-thinking.md | 1,733 | ✅ |
| working-with-thinking-blocks.md | 2,070 | ✅ |

Clean output. All subdocs within target. Good regression check.

---

## Failure Modes Identified

**1. No recursion.** fit_split.py performs a single heading-level pass and stops. Six subdocs across two documents exceed 3k tokens; four exceed 8k.

**2. Code block blindness.** `prompt-caching-examples.md` at 14,343 tokens is almost certainly dominated by code blocks. Recursion alone won't fix this — it requires code-block-level splitting with language identification.

**3. Splits documents already within target.** `tool-use/overview.md` at 2,137 tokens was split unnecessarily. No document under the target should be touched.

## "Strictly Better" Criteria

The new tool must satisfy all of the following on every test document above:

1. **No splits on sub-target documents.** Any input document already within the token target (≤3k) must be left entirely unchanged. (`tool-use/overview.md` is the test case.)
2. **No output document exceeds 5k tokens.** Hard ceiling, no exceptions.
3. **No output document exceeds 3k tokens** unless the ceiling exemption applies (further splitting would lose more than it gains, e.g. breaking a code block mid-statement).
4. **Root documents remain within target** for all 5 test inputs — fit_split.py already achieves this; the new tool must too.
5. **`prompt-caching-examples.md` is split into multiple subdocs** with language-identified names (e.g. `python-01.md`, `typescript-01.md`), all under 3k tokens.

## Sentence Splitting Tests

The stdlib regex `(?<=[.!?])\s+(?=[A-Z])` is used as a last-resort fallback. It has a known limitation: false splits on abbreviations followed by uppercase words. Tests to include:

- **Common case:** "The quick brown fox. He jumped over the lazy dog." → splits correctly at sentence boundary
- **False positive — title abbreviation:** "U.S. He went home." → incorrectly splits after 'S.'
- **False positive — figure reference:** "See Fig. 1 The results show..." → incorrectly splits after 'Fig'
- **False positive — honorific:** "Dr. Smith said the procedure went well." → incorrectly splits after 'Dr'

These confirm the known behavior is present and unchanged — the limitation is acceptable for a last resort, but must not regress silently.
