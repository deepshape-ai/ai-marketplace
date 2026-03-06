# Semantic Retrieval Strategy

This document describes how to search large memo collections with strong relevance and controlled token usage.

## Retrieval Pipeline

### Stage A: Candidate Collection (server side)

Fetch a bounded candidate pool:
```bash
python scripts/usememos_cli.py memo search "intent" --page-size 20 --max-pages 2
```

Controls:
- `--page-size`: candidates per API page
- `--max-pages`: upper bound on pages fetched

This prevents unbounded context growth while preserving enough recall for ranking.

### Stage B: Semantic Ranking (client side)

`memo search` ranks candidates using:
1. TF-IDF vectors from full memo text (`content + tags + snippet`),
2. LSA latent space via SVD,
3. cosine similarity between query and memo vectors,
4. fused relevance score with lexical and token-coverage signals.

This supports intent-level matching without requiring exact phrase overlap.

### Stage C: Readable Output

Each result includes:
- `title`
- `excerpt`
- `relevance` breakdown (`semantic`, `lexical`, `coverage`, final `score`)

This format is designed for direct LLM use, not just raw API transfer.

## Tuning Guidelines

### High Precision (strict)

```bash
python scripts/usememos_cli.py memo search "intent" --min-score 0.25 --top-k 5
```

Use when false positives are expensive.

### High Recall (broad)

```bash
python scripts/usememos_cli.py memo search "intent" --max-pages 4 --min-score 0.10 --top-k 10
```

Use when you must avoid missing potentially relevant memos.

### Ambiguous Queries

If `results` is empty, the command returns `suggestions` from observed tags.
Recommended next step:
1. refine intent with one suggested tag,
2. rerun search,
3. only then increase `max-pages`.

## Token Discipline

1. Start with `memo search` or `memo list --compact`.
2. Expand to full content only for shortlisted IDs.
3. Avoid bulk `memo get` unless explicitly requested.

Example:
```bash
python scripts/usememos_cli.py memo search "runtime profiling in c++" --top-k 3
python scripts/usememos_cli.py memo get <top_result_id>
```

## Validation Checklist

- Query retrieves semantically related memo even with paraphrased wording.
- No hardcoded synonym dictionary is required.
- Result payload is human/LLM readable without additional post-processing.
- Candidate limits (`page-size`, `max-pages`) keep response size predictable.
