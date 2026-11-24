# Retrieval eval: results history

Every round of the retrieval eval, oldest first, so the README can show how the
current setup was reached. Rounds are not directly comparable: the question set
changed between them (noted in each round). Numbers are over all splits (dev + test)
unless stated. R@k = recall@k, P@k = precision@k, MRR = mean reciprocal rank,
ms/q = milliseconds per query on a laptop CPU.

Corpus for every round: 11 markdown documents, 51 sections (one chunk per `##` section).

---

## Round 1: first comparison (47 questions, plain sections)

Snapshot from 2026-11-24, run on uncommitted code at 66e8d3a; the question set has
since changed, so this exact table cannot be re-run.

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | ms/q |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.50 | 0.68 | 0.73 | 0.80 | 0.60 | 0.24 | 0.70 | 0.3 |
| bm25 | 0.57 | 0.67 | 0.75 | 0.80 | 0.66 | 0.24 | 0.73 | 0.0 |
| rrf_keyword (tfidf + bm25) | 0.53 | 0.67 | 0.76 | 0.80 | 0.62 | 0.25 | 0.71 | 0.3 |
| semantic (bge-small-en-v1.5) | 0.66 | 0.79 | 0.90 | 0.95 | 0.77 | 0.29 | 0.84 | 11.1 |
| hybrid_rrf (bm25 + semantic) | 0.63 | 0.75 | 0.84 | 0.90 | 0.74 | 0.28 | 0.82 | 13.3 |
| hybrid_rrf_tfidf | 0.58 | 0.76 | 0.84 | 0.91 | 0.70 | 0.28 | 0.80 | 11.0 |
| hybrid_weighted 0.3 bm25 / 0.7 semantic | 0.66 | 0.81 | 0.88 | 0.94 | 0.79 | 0.29 | 0.86 | 26.6* |
| hybrid_weighted 0.5 | 0.65 | 0.80 | 0.84 | 0.93 | 0.77 | 0.28 | 0.84 | 22.1* |
| hybrid_weighted 0.7 | 0.61 | 0.74 | 0.82 | 0.91 | 0.72 | 0.27 | 0.80 | 21.4* |

\* inflated: the weighted hybrid embedded each query twice. Fixed in round 2.

Recall@4 by question type:

| method | agent-style | distractor | identifier | keyword | multi | paraphrase | vocab mismatch |
|---|---|---|---|---|---|---|---|
| tfidf | 0.69 | 0.92 | 1.00 | 1.00 | 0.75 | 0.62 | **0.00** |
| bm25 | 0.69 | 1.00 | 1.00 | 1.00 | 0.67 | 0.75 | **0.00** |
| semantic | 0.78 | 0.92 | 1.00 | 1.00 | 0.83 | 0.88 | **0.83** |
| hybrid_rrf | 0.78 | 1.00 | 1.00 | 1.00 | 0.75 | 0.88 | 0.42 |
| hybrid_weighted 0.3 | 0.78 | 1.00 | 1.00 | 1.00 | 0.75 | 0.88 | 0.67 |

What it showed:
- Keyword search finds nothing when the worker's words differ from the document's
  (0.00 on vocabulary mismatch); semantic search finds 83% of those.
- Fusing two keyword methods (rrf_keyword) adds almost nothing.
- Hybrid did not beat semantic, but every identifier question already scored 1.00
  for semantic, so the set had no question where keyword search should win.
- No method retrieved the escalation Contacts section for crack questions at any k.

---

## Round 2: identifier questions and contextual chunk headers (53 questions)

Changes: +6 identifier questions (extensions, NCR numbers, measurements, part
counts) written before re-running; p04 relabelled to also accept "Untagged parts";
weighted-hybrid double embedding fixed. Each method run with plain sections and with
each section prefixed by its document title ("contextual headers").

Plain sections:

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | ms/q |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.55 | 0.72 | 0.77 | 0.83 | 0.64 | 0.25 | 0.74 | 0.3 |
| bm25 | 0.62 | 0.70 | 0.78 | 0.83 | 0.70 | 0.25 | 0.76 | 0.0 |
| rrf_keyword | 0.58 | 0.70 | 0.79 | 0.83 | 0.66 | 0.25 | 0.74 | 0.4 |
| semantic | 0.69 | 0.81 | 0.90 | 0.97 | 0.79 | 0.29 | 0.86 | 12.4 |
| hybrid_rrf | 0.67 | 0.77 | 0.87 | 0.92 | 0.77 | 0.28 | 0.84 | 13.4 |
| hybrid_rrf_tfidf | 0.62 | 0.78 | 0.87 | 0.93 | 0.74 | 0.28 | 0.83 | 12.7 |
| hybrid_weighted 0.3 | 0.69 | 0.82 | 0.88 | 0.96 | 0.81 | 0.28 | 0.88 | 11.9 |
| hybrid_weighted 0.5 | 0.68 | 0.81 | 0.87 | 0.95 | 0.79 | 0.28 | 0.86 | 13.7 |
| hybrid_weighted 0.7 | 0.66 | 0.77 | 0.85 | 0.93 | 0.75 | 0.27 | 0.83 | 15.7 |

With contextual headers (document title in front of every section):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | ms/q |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.53 | 0.70 | 0.77 | 0.83 | 0.62 | 0.25 | 0.72 | 0.3 |
| bm25 | 0.62 | 0.69 | 0.78 | 0.83 | 0.70 | 0.25 | 0.76 | 0.0 |
| rrf_keyword | 0.56 | 0.69 | 0.79 | 0.83 | 0.64 | 0.25 | 0.73 | 0.4 |
| **semantic** | 0.69 | 0.80 | **0.93** | 0.97 | 0.83 | 0.30 | **0.89** | 12.1 |
| hybrid_rrf | 0.67 | 0.76 | 0.88 | 0.92 | 0.77 | 0.28 | 0.85 | 11.0 |
| hybrid_rrf_tfidf | 0.61 | 0.78 | 0.88 | 0.93 | 0.72 | 0.28 | 0.82 | 11.2 |
| hybrid_weighted 0.3 | 0.70 | 0.82 | 0.90 | 0.97 | 0.83 | 0.29 | 0.89 | 10.7 |
| hybrid_weighted 0.5 | 0.70 | 0.78 | 0.88 | 0.96 | 0.83 | 0.28 | 0.88 | 11.1 |
| hybrid_weighted 0.7 | 0.64 | 0.73 | 0.86 | 0.91 | 0.74 | 0.27 | 0.81 | 11.1 |

Smallest k at which every relevant section is found, per defect type (agent-style
questions, contextual headers):

| defect | tfidf | bm25 | semantic | hybrid_rrf |
|---|---|---|---|---|
| crack | never (k <= 8) | never | never | never |
| dimensional deviation | 8 | 8 | **4** | 4 |
| surface scratch | 4 | 4 | 4 | 2 |
| no defect | 4 | 4 | **2** | 2 |

### Why k = 4

Recall for semantic search with contextual headers as k grows:

| k | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| recall | 0.69 | 0.80 | **0.93** | 0.97 |

Going from 4 to 8 passages adds 0.04 recall but doubles the text the 3B model must
read (longer prompt, slower, more distraction). With semantic search every defect
type except crack is fully covered by k = 4. The agent passes the top 4 sections
(`TOP_K = 4` in app/agent.py). Not yet checked: whether the model's *answers* are
better with 4 passages than 8; that is an agent-eval question.

What it showed:
- Keyword search does help on exact numbers, a little: BM25 got all 6 new
  identifier questions, semantic missed one ("Is a 0.5 mm gap ok?").
- Contextual headers help semantic search (R@4 0.90 -> 0.93) and do nothing for
  keyword search.
- The crack -> Contacts gap remains: a section listing names and extensions never
  matches "who do I call about a crack?".

---

## Round 3: how sure are we? (same 53 questions, contextual headers)

95% bootstrap intervals (2,000 resamples of the questions, seed 0):

| method | R@4 [95% CI] | MRR [95% CI] |
|---|---|---|
| tfidf | 0.77 [0.66, 0.87] | 0.72 [0.62, 0.82] |
| bm25 | 0.78 [0.67, 0.88] | 0.76 [0.66, 0.86] |
| rrf_keyword | 0.79 [0.68, 0.89] | 0.73 [0.63, 0.83] |
| **semantic** | **0.93 [0.86, 0.98]** | **0.89 [0.82, 0.95]** |
| hybrid_rrf | 0.88 [0.80, 0.95] | 0.85 [0.76, 0.92] |
| hybrid_rrf_tfidf | 0.88 [0.80, 0.95] | 0.82 [0.73, 0.90] |
| hybrid_weighted 0.3 | 0.90 [0.83, 0.96] | 0.89 [0.82, 0.95] |
| hybrid_weighted 0.5 | 0.88 [0.81, 0.95] | 0.88 [0.80, 0.95] |
| hybrid_weighted 0.7 | 0.86 [0.77, 0.94] | 0.81 [0.72, 0.90] |

Paired comparison on R@4, every method against semantic on the same questions:

| method | difference [95% CI] | wins / ties / losses | verdict |
|---|---|---|---|
| tfidf | -0.16 [-0.27, -0.06] | 2 / 39 / 12 | worse |
| bm25 | -0.15 [-0.25, -0.05] | 2 / 39 / 12 | worse |
| rrf_keyword | -0.14 [-0.25, -0.04] | 2 / 40 / 11 | worse |
| hybrid_rrf | -0.05 [-0.13, +0.03] | 2 / 46 / 5 | can't tell apart |
| hybrid_rrf_tfidf | -0.05 [-0.13, +0.03] | 2 / 46 / 5 | can't tell apart |
| hybrid_weighted 0.3 | -0.03 [-0.08, +0.01] | 1 / 49 / 3 | can't tell apart |
| hybrid_weighted 0.5 | -0.05 [-0.12, +0.02] | 1 / 47 / 5 | can't tell apart |
| hybrid_weighted 0.7 | -0.07 [-0.15, +0.01] | 1 / 46 / 6 | can't tell apart |

Conclusions so far:
- **Settled:** semantic search beats keyword search. App default switched to
  semantic search with contextual headers.
- **Not settled:** semantic vs hybrid; they differ on only 4 to 7 of 53 questions.
  Next round runs the same 53 questions against a much bigger corpus: the plant's
  rule book plus public OSHA and FAA documents as realistic distractors.

---

## Round 4: the same 53 questions with public documents added (890 chunks)

New corpus, built by `ingest/` from public-domain US government documents and added
next to the plant's 51 sections:

| source | chunks | median words | notes |
|---|---|---|---|
| OSHA 29 CFR 1910 Subpart O (machinery and machine guarding) | 196 | 219 | eCFR XML |
| OSHA 29 CFR 1910 Subpart I (personal protective equipment) | 169 | 222 | eCFR XML, incl. appendices |
| OSHA 29 CFR 1910.147 (lockout/tagout) | 22 | 236 | eCFR XML |
| FAA AC 43.13-1B, chapters 4-7 (metal repair, NDI, corrosion, hardware) | 452 | 157 | 240-page PDF |

Data quality: 8 heading-only chunks and 5 number-only tables dropped, 13 table-like
chunks kept and listed in corpus/quality_report.json, no chunk over the embedding
model's ~380-word limit, every chunk carries a citation. All 53 label phrases still
match exactly one chunk in the bigger corpus.

All methods with contextual headers, all 53 questions:

| method | R@1 | R@2 | R@4 | R@8 | MRR | R@4 [95% CI] | ms/q |
|---|---|---|---|---|---|---|---|
| tfidf | 0.47 | 0.65 | 0.74 | 0.78 | 0.66 | 0.74 [0.63, 0.84] | 0.5 |
| bm25 | 0.61 | 0.67 | 0.71 | 0.79 | 0.74 | 0.71 [0.60, 0.82] | 0.5 |
| rrf_keyword | 0.54 | 0.68 | 0.72 | 0.79 | 0.70 | 0.72 [0.60, 0.83] | 1.1 |
| **semantic** | 0.64 | 0.78 | **0.87** | 0.88 | 0.83 | 0.87 [0.79, 0.94] | 11.5 |
| hybrid_rrf | 0.61 | 0.72 | 0.82 | 0.94 | 0.80 | 0.82 [0.73, 0.91] | 12.0 |
| hybrid_rrf_tfidf | 0.57 | 0.69 | 0.80 | 0.94 | 0.77 | 0.80 [0.69, 0.89] | 13.1 |
| hybrid_weighted 0.3 | 0.68 | 0.77 | 0.83 | 0.94 | **0.85** | 0.83 [0.74, 0.92] | 13.0 |
| hybrid_weighted 0.5 | 0.67 | 0.73 | 0.81 | 0.85 | 0.82 | 0.81 [0.70, 0.90] | 12.0 |
| hybrid_weighted 0.7 | 0.65 | 0.70 | 0.76 | 0.81 | 0.79 | 0.76 [0.65, 0.86] | 12.7 |

How much each method lost when the public documents were added (paired, same
questions, R@4):

| method | plant only | plant + public | change [95% CI] | worse / same / better |
|---|---|---|---|---|
| tfidf | 0.77 | 0.74 | -0.03 [-0.08, +0.03] | 4 / 48 / 1 |
| bm25 | 0.78 | 0.71 | -0.07 [-0.13, -0.02] | 5 / 48 / 0 |
| rrf_keyword | 0.79 | 0.72 | -0.07 [-0.13, -0.02] | 5 / 48 / 0 |
| semantic | 0.93 | 0.87 | -0.06 [-0.12, -0.01] | 4 / 49 / 0 |
| hybrid_rrf | 0.88 | 0.82 | -0.06 [-0.14, +0.03] | 5 / 46 / 2 |
| hybrid_rrf_tfidf | 0.88 | 0.80 | -0.08 [-0.16, -0.02] | 6 / 46 / 1 |
| hybrid_weighted 0.3 | 0.90 | 0.83 | -0.07 [-0.13, -0.02] | 5 / 48 / 0 |
| hybrid_weighted 0.5 | 0.88 | 0.81 | -0.08 [-0.15, -0.02] | 5 / 48 / 0 |
| hybrid_weighted 0.7 | 0.86 | 0.76 | -0.10 [-0.19, -0.04] | 6 / 47 / 0 |

Plant + public, every method against semantic (R@4):

| method | difference [95% CI] | wins / ties / losses | verdict |
|---|---|---|---|
| tfidf | -0.13 [-0.25, -0.02] | 3 / 38 / 12 | worse |
| bm25 | -0.16 [-0.28, -0.04] | 3 / 36 / 14 | worse |
| rrf_keyword | -0.15 [-0.27, -0.04] | 3 / 37 / 13 | worse |
| hybrid_rrf | -0.05 [-0.14, +0.04] | 3 / 44 / 6 | can't tell apart |
| hybrid_rrf_tfidf | -0.08 [-0.15, -0.01] | 1 / 46 / 6 | worse |
| hybrid_weighted 0.3 | -0.04 [-0.11, +0.04] | 2 / 46 / 5 | can't tell apart |
| hybrid_weighted 0.5 | -0.07 [-0.17, +0.04] | 3 / 43 / 7 | can't tell apart |
| hybrid_weighted 0.7 | -0.11 [-0.23, +0.00] | 3 / 40 / 10 | can't tell apart |

Share of the top-4 slots taken by public chunks (every question here is answered by
the plant's rule book): tfidf 29%, bm25 28%, semantic 28%, hybrid_rrf 25%,
hybrid_weighted 0.3 22%.

Recall@4 by question type, plant + public:

| method | agent-style | distractor | identifier | keyword | multi | paraphrase | vocab mismatch |
|---|---|---|---|---|---|---|---|
| tfidf | 0.69 | 0.92 | 1.00 | 1.00 | 0.58 | 0.62 | 0.00 |
| bm25 | 0.64 | 0.92 | 1.00 | 1.00 | 0.58 | 0.50 | 0.00 |
| semantic | 0.78 | 0.92 | 0.88 | 1.00 | 0.83 | 0.81 | 0.83 |
| hybrid_rrf | 0.86 | 0.92 | 0.92 | 1.00 | 0.75 | 0.88 | 0.25 |
| hybrid_weighted 0.3 | 0.78 | 0.92 | 0.92 | 1.00 | 0.75 | 0.88 | 0.42 |

Questions semantic search lost from its top 4 (public chunks pushed the plant
section out): p07 flash trimming (OSHA press rules), v06 "lubricant mix" (OSHA press
rules, FAA welding), i03 "ext 4155" (OSHA respirator rules), m04 oversized parts
(OSHA forging, FAA hardware).

What it showed:
- Every method gets worse when realistic distractors are added: semantic R@4 drops
  0.93 -> 0.87, a drop the confidence interval confirms. About a quarter of the top-4
  slots go to public text for questions the plant's own rule book answers.
- Semantic search is still clearly better than keyword search (0.87 vs 0.71-0.74).
- Semantic vs hybrid is still not settled at R@4. At R@8 the hybrids recover more
  (0.94 vs 0.88), which is worth checking if k is ever raised.
- Caveat: the labels only name plant sections, so a public chunk that also answers a
  question (OSHA lockout/tagout for the lockout question, say) counts as a miss. The
  eval measures what public text costs, not what it adds: no question yet needs it.

**Decision after round 4:** the public corpus stays as an **eval-only distractor set**.
The agent answers from the plant's rule book only. On plant questions the public text
only cost recall (and no question yet needs it), and FAA aircraft repair and generic
OSHA rules are not the plant's rules. The corpus keeps its value as a test of how
retrieval holds up at ~900 chunks of real regulatory text, and as the ingestion
pipeline (`ingest/`: fetch with checksums, XML/PDF parsing, structure-aware chunking,
data-quality checks). Run it with `python -m evals.retrieval_eval --contextual --corpus all`.
