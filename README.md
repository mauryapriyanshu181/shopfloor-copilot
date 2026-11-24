# ShopFloor Copilot

A worker on the factory floor sends a photo of a part and a question.

A small agent looks at the photo, reads the work order stamped on the part, checks the
work order in the ERP, and searches the plant's rule book. Then it answers, naming the
rule documents it used, or proposes an escalation for a supervisor to sign. It never
scraps or escalates anything by itself.

Everything runs locally on open-source tools: a 3B model through Ollama, OpenCV,
Tesseract, and a small embedding model. No cloud AI services.

The interesting part is the **retrieval evaluation**: four rounds of experiments that
took search from keyword matching to semantic and hybrid search, with a stress test
against ~840 chunks of real OSHA and FAA documents and a final recount on 300 questions.
See [Retrieval evaluation](#retrieval-evaluation) and its
[key takeaways](#key-takeaways).

## What changed on 2026-11-24

- **Simpler agent.** The agent is now a plain loop over three tools. Everything that
  was not needed to answer a question was removed. Rule search uses a fixed top 4
  sections, a number chosen from the retrieval eval.
- **Bigger rule book.** 7 new plant documents, taking it from 4 documents (14 sections)
  to 11 documents (51 sections), written to overlap on purpose ("crack" appears in the
  moulding guide, "scratch" in material handling) so search has to rank, not just match.
- **Retrieval evaluation.** 300 labelled questions; TF-IDF, BM25, semantic search and
  two hybrid methods; recall, precision, MRR and MAP at several k.
- **Hybrid search with contextual headers** is now the default (0.3 × BM25 + 0.7 ×
  semantic), replacing word matching (TF-IDF). It came out best on 300 questions.
- **Ingestion pipeline for real documents.** OSHA regulations (eCFR XML) and an FAA
  advisory circular (PDF) are downloaded, parsed, chunked and quality-checked into 839
  chunks, used to stress-test retrieval.

## Setup

Install the two outside tools:

```bash
brew install tesseract ollama
```

Start the model server and download the model (leave the first one running):

```bash
ollama serve
```

```bash
ollama pull qwen2.5:3b
```

Set up Python:

```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
```

Make the sample part photos:

```bash
python scripts/gen_samples.py
```

Run it:

```bash
uvicorn app.main:app --reload
```

The first start downloads the embedding model `BAAI/bge-small-en-v1.5` (about 130 MB)
from Hugging Face and caches it. Section embeddings are cached in `data/`.

If Ollama is not running, the service says the model is unavailable and lists the
closest rule sections instead of making up an answer. If Tesseract is missing, reading
the stamp returns an error instead of crashing.

## Trying it

Piping a response through `scripts/show.py` prints it as readable text.

Send a photo and a question:

```bash
curl -s -X POST http://localhost:8000/inspect -F "query=Can I ship this?" -F "image=@samples/part_crack.png" | python scripts/show.py
```

Ask a question with no photo:

```bash
curl -s -X POST http://localhost:8000/inspect -F "query=Who do I escalate a crack to?" | python scripts/show.py
```

Look up a past answer (use the `transaction_id` from a response):

```bash
curl -s http://localhost:8000/transactions/PASTE_ID_HERE | python -m json.tool
```

## What comes back

| Field | What it is |
|---|---|
| `answer` | what the worker reads |
| `escalation` | set when the agent proposes one: who to, why, `PENDING_HUMAN_APPROVAL`, `executed: false` |
| `facts` | the defect found in the photo (with the measurement behind it), the work order read off the part, the ERP record |
| `sources` | the rule sections that were retrieved |
| `steps` | every step the agent took, in order, with its reason and any error |
| `config` | model, search method, contextual headers on or off, top k |
| `llm_calls` | one entry per model call, with its latency |
| `latency_s` | how long the whole call took |
| `transaction_id` | the ID for looking it up again |

## How it works

**The agent** (`app/agent.py`). Each turn the model sees the question, what it has
found so far, and the tools it can still use. It replies with one JSON object:

| Tool | What it does |
|---|---|
| `inspect_photo` | finds the defect in the photo and reads the work order stamped on the part |
| `search_rules(query)` | hybrid search (meaning + keywords) over the rule book, top 4 sections |
| `lookup_work_order(id)` | the work order's status in the ERP (mocked) |
| `answer(text)` | final reply, naming the documents each rule came from |
| `escalate(reason)` | proposes a hand-over to the shift supervisor; nothing is actioned |

Each tool runs at most once, and the photo tool is not offered when no photo was sent:
a small model will otherwise keep asking for the same thing. A reply that is not valid
JSON, or names a tool that is not on offer, is recorded and the loop moves on. At most
5 steps.

**The photo** (`app/vision.py`). The part is separated from the background, then
searched for straight lines. A line darker than the part is a crack, a brighter one is a
scratch. A width-to-height ratio outside 1.60 ± 0.08 is a dimensional deviation. The
stamped ID strip is skipped so its letters are not read as cracks.

**The stamp** (`app/ocr.py`). The top strip of the part is cut out, enlarged, turned
black and white and read by Tesseract. Anything shaped like `WO-1042` is pulled out,
allowing for a stray character.

**The rules** (`app/rag.py`, `app/retrievers.py`). The 11 documents in `knowledge/` are
split into 51 sections, one per `##` heading. Each section gets its document's title in
front ("contextual headers"). A question is scored against every section two ways: by
meaning (cosine similarity of `bge-small-en-v1.5` embeddings) and by keywords (BM25).
Both scores are scaled to 0–1 and blended 70% meaning / 30% keywords, and the 4 best
sections go to the model. TF-IDF, plain semantic search and RRF fusion are also
implemented, for the eval.

**Keeping it safe** (`app/store.py`). Every call is appended to `data/audit_log.jsonl`.
Escalations come back `PENDING_HUMAN_APPROVAL` with `executed: false`; no code can set
it to true.

## Retrieval evaluation

Search decides what the model gets to read, so it is evaluated on its own, before the
model is involved.

**The question set** (`evals/retrieval_cases.jsonl`). 300 questions, each labelled with
the rule sections a correct search must return, covering all 51 plant sections. Rounds
1 to 3 used the first 47 to 53 of them; round 4 uses all 300. Seven types, so that each
search method has questions it should win and questions it should lose:

| type | count | example |
|---|---|---|
| keyword | 48 | "How often are calipers calibrated?" |
| paraphrase | 56 | "Somebody dropped the micrometer, can I keep using it?" |
| vocabulary mismatch | 48 | "Is the lubricant mix strong enough?" (the doc says *coolant concentration*) |
| identifier | 40 | "Who is on ext 4170?", "What does NCR-2026-0042 refer to?" |
| multi-section | 40 | "I found a crack, what do I do and who do I call?" |
| distractor | 35 | "There's a crack on the injection cover" (moulded cover, not the CNC rule) |
| agent-style | 33 | "Can I rework this?" + the defect the photo check found |

Labels are short phrases copied from the documents, not section IDs, so they survive a
change of chunking. Before every run the eval checks that each phrase matches exactly
one section; a phrase that matches none or several stops the run. A labelling mistake
cannot quietly skew the numbers. 90 of the 300 questions (30%) are a held-out test split.

**The metrics** (`evals/retrieval_metrics.py`).

- **Recall@k**: of the sections the question needs, the share found in the top k.
  The headline metric, at k = 4, because the agent passes exactly 4 sections to the
  model.
- **Precision@k**: of the k sections returned, the share that are relevant. Capped by
  how many relevant sections exist: with one relevant section, precision@4 can be at
  most 0.25, so low precision at larger k is expected.
- **MRR** (mean reciprocal rank): 1 / the rank of the first relevant section, averaged.
  How high the right section lands.
- **MAP@4** (mean average precision over the top 4): the precision at each rank where a
  relevant section appears, averaged over the relevant sections. Unlike MRR it rewards
  finding *every* relevant section near the top, not just the first, so it matters for
  questions that need two sections. With one relevant section it equals MRR.

**The methods** (`app/retrievers.py`):

| method | how it ranks |
|---|---|
| `tfidf` | word overlap, rare words weighted up |
| `bm25` | word overlap with term-frequency saturation and length normalisation (written from the formula, tested against hand-computed values) |
| `semantic` | cosine similarity of `bge-small-en-v1.5` embeddings |
| `hybrid_rrf` | Reciprocal Rank Fusion of BM25 and semantic: `sum of 1 / (60 + rank)` |
| `hybrid_weighted a` | `a × BM25 + (1 − a) × semantic`, scores min-max normalised, a = 0.3 / 0.5 / 0.7 |

Run it:

```bash
python -m evals.retrieval_eval --contextual
```

`--corpus all` adds the public OSHA/FAA corpus, `--failures semantic` lists the
questions a method misses, and each run is saved to `evals/results/`.

The full tables for every round are in
[evals/results_history.md](evals/results_history.md). The main ones are below.

### Round 1: keyword vs semantic vs hybrid

47 questions, plain sections. Recall (R@k), precision (P@k) and MRR over all questions:

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | ms/query |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.50 | 0.68 | 0.73 | 0.80 | 0.60 | 0.24 | 0.70 | 0.3 |
| bm25 | 0.57 | 0.67 | 0.75 | 0.80 | 0.66 | 0.24 | 0.73 | 0.0 |
| **semantic** | **0.66** | 0.79 | **0.90** | **0.95** | 0.77 | **0.29** | 0.84 | 11.1 |
| hybrid_rrf | 0.63 | 0.75 | 0.84 | 0.90 | 0.74 | 0.28 | 0.82 | 13.3 |
| hybrid_rrf_tfidf | 0.58 | 0.76 | 0.84 | 0.91 | 0.70 | 0.28 | 0.80 | 11.0 |
| hybrid_weighted 0.3 | 0.66 | **0.81** | 0.88 | 0.94 | **0.79** | **0.29** | **0.86** | 26.6* |
| hybrid_weighted 0.5 | 0.65 | 0.80 | 0.84 | 0.93 | 0.77 | 0.28 | 0.84 | 22.1* |
| hybrid_weighted 0.7 | 0.61 | 0.74 | 0.82 | 0.91 | 0.72 | 0.27 | 0.80 | 21.4* |

\* inflated by a bug that embedded each query twice, fixed in round 2.

Recall@4 by question type:

| method | agent-style | distractor | identifier | keyword | multi | paraphrase | vocab mismatch |
|---|---|---|---|---|---|---|---|
| tfidf | 0.69 | 0.92 | 1.00 | 1.00 | 0.75 | 0.62 | **0.00** |
| bm25 | 0.69 | 1.00 | 1.00 | 1.00 | 0.67 | 0.75 | **0.00** |
| semantic | 0.78 | 0.92 | 1.00 | 1.00 | 0.83 | 0.88 | **0.83** |
| hybrid_rrf | 0.78 | 1.00 | 1.00 | 1.00 | 0.75 | 0.88 | 0.42 |
| hybrid_weighted 0.3 | 0.78 | 1.00 | 1.00 | 1.00 | 0.75 | 0.88 | 0.67 |

Conclusions:
- **Keyword search finds nothing when the worker's words differ from the document's**
  (0.00 on vocabulary mismatch). Semantic search finds 83% of those.
- Hybrid did not beat semantic, but the set had no question where keyword search should
  win: semantic already scored 1.00 on every identifier question.
- No method found the escalation contacts for crack questions at any k.

### Round 2: identifier questions, contextual headers, and why k = 4

6 more identifier questions (extensions, NCR numbers, measurements, part counts) were
written before re-running, to give keyword search a fair chance. Each method was run
with plain sections and with **contextual headers**: the document's title put in front
of every section, so "## Contacts" becomes "# Escalation Contacts and Rules / ## Contacts".

Recall@4 and MRR on 53 questions:

| method | plain | contextual headers |
|---|---|---|
| tfidf | 0.77 / 0.74 | 0.77 / 0.72 |
| bm25 | 0.78 / 0.76 | 0.78 / 0.76 |
| **semantic** | 0.90 / 0.86 | **0.93 / 0.89** |
| hybrid_rrf | 0.87 / 0.84 | 0.88 / 0.85 |
| hybrid_weighted 0.3 | 0.88 / 0.88 | 0.90 / 0.89 |

**Why the agent uses k = 4.** Recall of semantic search with contextual headers as k grows:

| k | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| recall | 0.69 | 0.80 | **0.93** | 0.97 |

Going from 4 to 8 sections adds 0.04 recall but doubles what the 3B model has to read.
With semantic search every defect type except crack is fully covered at k = 4:

| defect | smallest k that finds every relevant section (semantic) |
|---|---|
| no defect | 2 |
| surface scratch | 4 |
| dimensional deviation | 4 |
| crack | never within 8 (the escalation contacts are not found) |

Conclusions:
- Keyword search does help on exact numbers, a little: BM25 got all 6 new identifier
  questions, semantic missed one ("Is a 0.5 mm gap ok?").
- Contextual headers help semantic search (0.90 → 0.93) and do nothing for keyword search.
- **k = 4** is where the recall curve flattens. Not yet checked: whether the model's
  *answers* are better with 4 sections than with 8.
- **Semantic search beats keyword search**: question by question, BM25 found something
  semantic missed on 2 questions, and missed something semantic found on 12. The app's
  default became semantic search with contextual headers.
- **Semantic vs hybrid is not settled.** They differ on only 4 to 7 of the 53
  questions, too few to call a winner.

### Round 3: real documents as distractors

A real rule book is not 51 tidy sections. To test how retrieval holds up, ~840 chunks of
public-domain US government documents were added next to the plant's sections:

| source | chunks |
|---|---|
| OSHA 29 CFR 1910 Subpart O (machinery and machine guarding) | 196 |
| OSHA 29 CFR 1910 Subpart I (personal protective equipment) | 169 |
| OSHA 29 CFR 1910.147 (lockout/tagout) | 22 |
| FAA AC 43.13-1B, chapters 4–7 (metal repair, inspection, corrosion, hardware) | 452 |

Same 53 questions (all answered by the plant's rule book), Recall@4:

| method | plant only | plant + public | change |
|---|---|---|---|
| tfidf | 0.77 | 0.74 | −0.03 |
| bm25 | 0.78 | 0.71 | −0.07 |
| **semantic** | 0.93 | **0.87** | −0.06 |
| hybrid_rrf | 0.88 | 0.82 | −0.06 |
| hybrid_weighted 0.3 | 0.90 | 0.83 | −0.07 |

Conclusions:
- **Every method gets worse with realistic distractors.** About a quarter of the top-4
  slots (22–29%) go to OSHA or FAA text for questions the plant's own rules answer:
  "Who answers ext 4155?" now pulls in OSHA respirator rules.
- **Semantic is still clearly ahead of keyword search** (0.87 vs 0.71–0.74), and the
  hybrids still don't beat it at k = 4. At k = 8 the hybrids recover more (0.94 vs 0.88).
- **Decision: the public corpus is an eval-only distractor set.** The agent answers from
  the plant's rule book only. The public text only cost recall on plant questions, and
  FAA aircraft repair and generic OSHA rules are not the plant's rules.
- Caveat: labels only name plant sections, so a public chunk that also answers a
  question (OSHA lockout/tagout for the lockout question) counts as a miss.

### Round 4: 300 questions, every number recounted

247 questions were added in two batches, written section by section to cover every
plant section and all seven types: 147 before any eval was run on them, then 100 more
in the same proportions after an intermediate count at 200. Everything was then counted
once more on all 300, with MAP@4 added. All runs use contextual headers.

Plant rule book only (51 sections):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | MAP@4 |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.53 | 0.67 | 0.78 | 0.84 | 0.63 | 0.24 | 0.73 | 0.66 |
| bm25 | 0.59 | 0.67 | 0.78 | 0.85 | 0.69 | 0.24 | 0.75 | 0.69 |
| semantic | 0.65 | 0.79 | 0.87 | 0.94 | 0.77 | 0.27 | 0.84 | 0.78 |
| hybrid_rrf | 0.63 | 0.78 | 0.87 | 0.94 | 0.73 | 0.27 | 0.82 | 0.76 |
| **hybrid_weighted 0.3** | **0.68** | **0.81** | **0.89** | **0.95** | **0.79** | **0.28** | **0.86** | **0.80** |
| hybrid_weighted 0.5 | 0.66 | 0.78 | 0.88 | 0.95 | 0.77 | 0.27 | 0.84 | 0.78 |
| hybrid_weighted 0.7 | 0.63 | 0.74 | 0.86 | 0.93 | 0.73 | 0.27 | 0.81 | 0.75 |

Plant rule book plus the ~840 public OSHA/FAA chunks:

| method | R@4 | MRR | MAP@4 | top-4 slots taken by public text |
|---|---|---|---|---|
| tfidf | 0.71 | 0.63 | 0.57 | 32% |
| bm25 | 0.70 | 0.70 | 0.64 | 31% |
| semantic | 0.82 | 0.79 | 0.72 | 30% |
| hybrid_rrf | 0.82 | 0.78 | 0.72 | 27% |
| **hybrid_weighted 0.3** | **0.85** | **0.82** | **0.76** | **26%** |

Question by question against semantic search (Recall@4): on how many of the 300
questions each method did better / the same / worse:

| method | plant only | plant + public |
|---|---|---|
| tfidf | 21 / 225 / 54 | 26 / 212 / 62 |
| bm25 | 22 / 223 / 55 | 26 / 209 / 65 |
| hybrid_rrf | 20 / 260 / 20 | 25 / 253 / 22 |
| hybrid_weighted 0.3 | 14 / 279 / 7 | 25 / 262 / 13 |

By batch of questions (plant only, R@4 / MRR / MAP@4):

| questions | bm25 | semantic | hybrid_weighted 0.3 |
|---|---|---|---|
| first 53 (rounds 1–3) | 0.78 / 0.76 / 0.71 | **0.93** / 0.89 / 0.82 | 0.90 / 0.89 / **0.83** |
| next 147 | 0.77 / 0.76 / 0.70 | 0.87 / 0.83 / 0.78 | **0.89 / 0.86 / 0.80** |
| last 100 | 0.79 / 0.74 / 0.67 | 0.84 / 0.84 / 0.76 | **0.88 / 0.86 / 0.79** |
| test split (90) | 0.78 / 0.71 / 0.67 | 0.86 / 0.82 / 0.77 | 0.87 / 0.82 / 0.77 |

Conclusions:
- **The weighted hybrid (0.3 BM25 / 0.7 semantic) is ahead of semantic search on every
  headline metric**: recall@4 0.89 vs 0.87, MRR 0.86 vs 0.84, MAP@4 0.80 vs 0.78 on the
  plant rule book, and 0.85 vs 0.82 with the public distractors. Question by question it
  is better on 14 and worse on 7 (plant), and better on 25, worse on 13 (with
  distractors). It also ranks better more often than worse: MRR on 34 questions vs 15,
  MAP@4 on 44 vs 24.
- **It is the most consistent**: 0.88 to 0.90 on every batch, while semantic search
  drifts from 0.93 on the first 53 to 0.84 on the last 100. On the test split they tie.
- **Caveat**: the last 100 questions were written after the intermediate count, and
  they show the widest gap. On the first 200 alone the two tie on recall@4 and the
  hybrid is still ahead on MRR, MAP@4 and with distractors, so the conclusion does not
  rest on them.
- **How the two are combined matters.** RRF fusion is no better than semantic alone,
  and a heavy keyword share (0.7) is the worst hybrid. A light keyword share (0.3) is
  what helps: it rescues exact codes and numbers without dragging down paraphrases.
- **Keyword search alone stays well behind** (0.78).
- **k = 4 still holds**: recall for the hybrid is 0.68 / 0.81 / 0.89 / 0.95 at
  k = 1 / 2 / 4 / 8.
- **Decision: the app now uses the weighted hybrid** (0.3 × BM25 + 0.7 × semantic,
  contextual headers, top 4).

### Where it stands

| | |
|---|---|
| **Settled** | Search is hybrid: 0.3 × BM25 + 0.7 × semantic with contextual headers, top 4. Best on 300 questions, on the plant's rule book and with 840 chunks of distractors. Keyword-only search is clearly worse. |
| **Open** | Whether the model answers better with 4 sections or 8 (an agent-eval question). |
| **Known gap** | "Who do I call about a crack?" never retrieves the Contacts section: it lists names and extensions and never mentions cracks. No search method fixes it; next experiment: LLM-written context for each chunk (Anthropic-style contextual retrieval). |

### Key takeaways

1. **Meaning beats keywords for how workers actually talk.** Keyword search scored 0.00
   on questions phrased differently from the documents; semantic search found 83% of
   them. That was the single biggest gain: +0.09 to +0.15 recall@4 over keyword search.
2. **Small eval sets mislead.** On 53 questions semantic search looked best (0.93) and
   hybrid search looked pointless. At 300 questions semantic search fell to 0.87 and a
   lightly weighted hybrid came out ahead. Close calls need more questions before a
   decision.
3. **How you combine methods matters more than whether you do.** RRF never beat
   semantic search, and a keyword-heavy blend was the worst hybrid. A 30% keyword share
   was the one that helped.
4. **Cheap context helps.** Putting each document's title in front of its sections
   raised semantic recall@4 from 0.90 to 0.93, at no cost when answering.
5. **Test with realistic noise, not just a clean corpus.** Adding ~840 chunks of real
   regulations cost the main methods 4 to 8 points of recall@4 and took about a quarter of
   the top slots. It also settled that the public documents stay out of the agent.
6. **Labels are infrastructure.** Labels written as phrases and checked on every run
   let the corpus grow from 51 to 890 chunks and the question set from 47 to 300 without
   a single silent labelling error.
7. **Some failures are in the content, not the search.** The crack → contacts miss
   survives every method; it has to be fixed in what gets indexed, not by switching
   search methods.
8. **Pick k from the recall curve.** Recall flattens after 4 sections; going to 8 adds
   about 6 points for twice the text the model has to read.

## Ingesting the public documents

`ingest/` turns the public documents into the distractor corpus:

```bash
python -m ingest.fetch
```

```bash
python -m ingest.build
```

- **fetch** downloads the sources in `corpus/sources.json` (~22 MB, mostly the FAA PDF)
  into `corpus/raw/` (not committed) and records each file's size, SHA-256 and date in
  `corpus/manifest.json`. Unchanged files are skipped on re-runs.
- **parse** reads the eCFR XML into one block per numbered paragraph with its exact
  citation, e.g. `29 CFR 1910.147 (c)(4)`, and tables as rows. From the FAA PDF it removes
  running headers and footers, rejoins words broken across lines, finds the numbered
  paragraphs (`4-58.`), including headings that wrap onto a second line or have no
  closing period, skips `[RESERVED]` ranges, and fixes letter-spaced text.
- **build** packs consecutive blocks of the same paragraph into chunks of up to ~250
  words, splitting long ones at sentence ends or table rows. It drops heading-only
  fragments and number-only tables, lists table-like chunks, and **stops** if any chunk
  is over the embedding model's limit or has no citation. Output: `corpus/chunks.jsonl`
  and `corpus/quality_report.json`.

Result: 839 chunks, 283 FAA numbered paragraphs found (2 gaps in the numbering, both
real), 8 heading-only fragments and 5 number tables dropped, 13 table-like chunks kept.

## Tests

```bash
pytest tests/ -q
```

41 tests, about 7 seconds, no Ollama needed (agent tests script the model's replies):

- the four defect types and the stamp reading
- the agent loop: tool flow, each tool once, the photo tool hidden without a photo,
  invalid replies, the step limit, model unavailable, escalations never executed
- the API
- BM25 against hand-computed values, RRF and weighted fusion, the metrics (MAP@4
  included), and that every label matches exactly one section
- ingestion: designator paths, XML parsing, header/footer removal, de-hyphenation,
  heading detection, chunk packing and the quality checks

## Known limits

- **The sample photos come from a script.** The detector is tuned to them; a phone photo
  would need the thresholds set again.
- **The question set was written by the same author as the plant documents**, which
  makes it easier than real questions would be. Most added questions were written
  before any run on them; the last 100 came after an intermediate count and are
  reported separately, and a test split is held out. Round 4 showed the first 53
  questions flattered semantic search. Questions from real workers would make the eval
  stronger still.
- **The agent itself is not evaluated yet.** Retrieval is; whether the model escalates
  every crack is the next eval to build.
- **There is no guardrail on the model's decisions.** The plan is to measure how often
  the model escalates a crack first, and add a rule only if the numbers show it is needed.

## Why I built it this way

See [DECISIONS.md](DECISIONS.md). It was written before the changes of 2026-11-24; the
parts on word-matching search and on tuning the number of rule sections from ratings
are out of date. The evaluation above supersedes them.
