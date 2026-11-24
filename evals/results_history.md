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
- Semantic search beats keyword search: question by question, BM25 found something
  semantic missed on 2 questions and missed something semantic found on 12. The app
  default switched to semantic search with contextual headers.
- Semantic vs hybrid is not settled: they differ on only 4 to 7 of the 53 questions.

---

## Round 3: the same 53 questions with public documents added (890 chunks)

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

| method | R@1 | R@2 | R@4 | R@8 | MRR | ms/q |
|---|---|---|---|---|---|---|
| tfidf | 0.47 | 0.65 | 0.74 | 0.78 | 0.66 | 0.5 |
| bm25 | 0.61 | 0.67 | 0.71 | 0.79 | 0.74 | 0.5 |
| **semantic** | 0.64 | 0.78 | **0.87** | 0.88 | 0.83 | 11.5 |
| hybrid_rrf | 0.61 | 0.72 | 0.82 | 0.94 | 0.80 | 12.0 |
| hybrid_rrf_tfidf | 0.57 | 0.69 | 0.80 | 0.94 | 0.77 | 13.1 |
| hybrid_weighted 0.3 | 0.68 | 0.77 | 0.83 | 0.94 | **0.85** | 13.0 |
| hybrid_weighted 0.5 | 0.67 | 0.73 | 0.81 | 0.85 | 0.82 | 12.0 |
| hybrid_weighted 0.7 | 0.65 | 0.70 | 0.76 | 0.81 | 0.79 | 12.7 |

How much each method lost when the public documents were added (R@4, and how many of
the 53 questions got worse, stayed the same, or got better):

| method | plant only | plant + public | change | worse / same / better |
|---|---|---|---|---|
| tfidf | 0.77 | 0.74 | -0.03 | 4 / 48 / 1 |
| bm25 | 0.78 | 0.71 | -0.07 | 5 / 48 / 0 |
| semantic | 0.93 | 0.87 | -0.06 | 4 / 49 / 0 |
| hybrid_rrf | 0.88 | 0.82 | -0.06 | 5 / 46 / 2 |
| hybrid_rrf_tfidf | 0.88 | 0.80 | -0.08 | 6 / 46 / 1 |
| hybrid_weighted 0.3 | 0.90 | 0.83 | -0.07 | 5 / 48 / 0 |
| hybrid_weighted 0.5 | 0.88 | 0.81 | -0.08 | 5 / 48 / 0 |
| hybrid_weighted 0.7 | 0.86 | 0.76 | -0.10 | 6 / 47 / 0 |

Plant + public, every method against semantic, question by question (R@4): how many
questions the method did better on, the same, or worse:

| method | better / same / worse than semantic |
|---|---|
| tfidf | 3 / 38 / 12 |
| bm25 | 3 / 36 / 14 |
| hybrid_rrf | 3 / 44 / 6 |
| hybrid_rrf_tfidf | 1 / 46 / 6 |
| hybrid_weighted 0.3 | 2 / 46 / 5 |
| hybrid_weighted 0.5 | 3 / 43 / 7 |
| hybrid_weighted 0.7 | 3 / 40 / 10 |

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
  0.93 -> 0.87 (4 questions worse, none better). About a quarter of the top-4
  slots go to public text for questions the plant's own rule book answers.
- Semantic search is still clearly better than keyword search (0.87 vs 0.71-0.74).
- The hybrids still don't beat semantic at R@4. At R@8 the hybrids recover more
  (0.94 vs 0.88), which is worth checking if k is ever raised.
- Caveat: the labels only name plant sections, so a public chunk that also answers a
  question (OSHA lockout/tagout for the lockout question, say) counts as a miss. The
  eval measures what public text costs, not what it adds: no question yet needs it.

**Decision after round 3:** the public corpus stays as an **eval-only distractor set**.
The agent answers from the plant's rule book only. On plant questions the public text
only cost recall (and no question yet needs it), and FAA aircraft repair and generic
OSHA rules are not the plant's rules. The corpus keeps its value as a test of how
retrieval holds up at ~900 chunks of real regulatory text, and as the ingestion
pipeline (`ingest/`: fetch with checksums, XML/PDF parsing, structure-aware chunking,
data-quality checks). Run it with `python -m evals.retrieval_eval --contextual --corpus all`.

---

## Intermediate count: 200 questions (superseded by round 4)

147 new questions were added, written section by section to cover all 51 plant sections
and the same 7 question types, before any eval was run on them. Total: 200 questions
(keyword 33, paraphrase 38, vocabulary mismatch 31, identifier 28, multi-section 26,
distractor 23, agent-style 21), 140 dev / 60 test. Every label still matches exactly one
section, with and without the public corpus. New metric: **MAP@4** (mean average
precision over the top 4), which, unlike MRR, rewards finding *every* relevant section
near the top, not just the first. All runs with contextual headers.

Plant rule book only (51 chunks):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | MAP@4 | ms/q |
|---|---|---|---|---|---|---|---|---|---|
| tfidf | 0.53 | 0.68 | 0.76 | 0.84 | 0.62 | 0.23 | 0.72 | 0.66 | 0.3 |
| bm25 | 0.61 | 0.69 | 0.77 | 0.84 | 0.70 | 0.24 | 0.76 | 0.70 | 0.0 |
| semantic | 0.66 | 0.79 | **0.89** | 0.94 | 0.77 | **0.28** | 0.85 | 0.79 | 12.4 |
| hybrid_rrf | 0.62 | 0.77 | 0.87 | 0.94 | 0.71 | 0.27 | 0.81 | 0.75 | 11.6 |
| hybrid_rrf_tfidf | 0.59 | 0.76 | 0.87 | 0.94 | 0.69 | 0.27 | 0.80 | 0.74 | 13.3 |
| **hybrid_weighted 0.3** | **0.69** | **0.82** | **0.89** | **0.95** | **0.80** | **0.28** | **0.87** | **0.81** | 11.9 |
| hybrid_weighted 0.5 | 0.66 | 0.80 | 0.88 | 0.95 | 0.77 | 0.27 | 0.84 | 0.79 | 11.9 |
| hybrid_weighted 0.7 | 0.63 | 0.74 | 0.86 | 0.92 | 0.72 | 0.26 | 0.81 | 0.75 | 11.5 |

Plant + public OSHA/FAA corpus (890 chunks):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | MAP@4 | ms/q |
|---|---|---|---|---|---|---|---|---|---|
| tfidf | 0.43 | 0.58 | 0.69 | 0.74 | 0.52 | 0.21 | 0.62 | 0.56 | 0.4 |
| bm25 | 0.54 | 0.63 | 0.71 | 0.76 | 0.62 | 0.22 | 0.69 | 0.63 | 0.4 |
| semantic | 0.62 | 0.75 | 0.83 | 0.88 | 0.71 | 0.26 | 0.80 | 0.73 | 11.7 |
| hybrid_rrf | 0.58 | 0.72 | 0.82 | 0.90 | 0.67 | 0.25 | 0.77 | 0.71 | 12.2 |
| hybrid_rrf_tfidf | 0.54 | 0.68 | 0.81 | 0.90 | 0.63 | 0.25 | 0.74 | 0.68 | 13.1 |
| **hybrid_weighted 0.3** | **0.65** | **0.76** | **0.85** | **0.92** | **0.75** | **0.26** | **0.82** | **0.76** | 12.6 |
| hybrid_weighted 0.5 | 0.61 | 0.72 | 0.79 | 0.87 | 0.71 | 0.24 | 0.77 | 0.72 | 13.2 |
| hybrid_weighted 0.7 | 0.59 | 0.69 | 0.75 | 0.80 | 0.69 | 0.23 | 0.74 | 0.68 | 12.3 |

Question by question against semantic (R@4): how many of the 200 questions each method
did better on / the same / worse:

| method | plant only | plant + public |
|---|---|---|
| tfidf | 12 / 146 / 42 | 15 / 139 / 46 |
| bm25 | 14 / 144 / 42 | 16 / 138 / 46 |
| hybrid_rrf | 12 / 171 / 17 | 16 / 166 / 18 |
| hybrid_rrf_tfidf | 12 / 173 / 15 | 13 / 169 / 18 |
| hybrid_weighted 0.3 | 8 / 186 / 6 | 15 / 174 / 11 |
| hybrid_weighted 0.5 | 13 / 171 / 16 | 18 / 156 / 26 |
| hybrid_weighted 0.7 | 13 / 166 / 21 | 16 / 149 / 35 |

Adding the public corpus (R@4, plant only -> plant + public):

| method | plant only | plant + public | change | worse / same / better |
|---|---|---|---|---|
| tfidf | 0.76 | 0.69 | -0.07 | 19 / 178 / 3 |
| bm25 | 0.77 | 0.71 | -0.07 | 17 / 182 / 1 |
| semantic | 0.89 | 0.83 | -0.06 | 15 / 185 / 0 |
| hybrid_rrf | 0.87 | 0.82 | -0.04 | 16 / 178 / 6 |
| hybrid_weighted 0.3 | 0.89 | 0.85 | -0.05 | 13 / 186 / 1 |
| hybrid_weighted 0.7 | 0.86 | 0.75 | -0.11 | 25 / 175 / 0 |

Share of top-4 slots taken by public text: tfidf 32%, bm25 30%, semantic 31%,
hybrid_rrf 27%, hybrid_weighted 0.3 26%.

Recall@4 by question type, plant only:

| method | agent-style | distractor | identifier | keyword | multi | paraphrase | vocab mismatch |
|---|---|---|---|---|---|---|---|
| tfidf | 0.63 | 0.98 | 1.00 | 1.00 | 0.67 | 0.75 | 0.31 |
| bm25 | 0.61 | 1.00 | 1.00 | 1.00 | 0.65 | 0.79 | 0.35 |
| semantic | 0.77 | 0.91 | 0.91 | 1.00 | **0.81** | **0.93** | 0.81 |
| hybrid_rrf | 0.77 | 0.98 | 1.00 | 1.00 | 0.71 | 0.89 | 0.69 |
| hybrid_weighted 0.3 | **0.79** | 0.98 | 0.93 | 1.00 | 0.77 | 0.92 | **0.82** |

The original 53 questions against the 147 new ones (plant only, R@4 / MRR / MAP@4):

| method | original 53 | new 147 |
|---|---|---|
| bm25 | 0.78 / 0.76 / 0.71 | 0.77 / 0.76 / 0.70 |
| semantic | 0.93 / 0.89 / 0.82 | 0.87 / 0.83 / 0.78 |
| hybrid_weighted 0.3 | 0.90 / 0.89 / 0.83 | 0.89 / 0.86 / 0.80 |

Recall of semantic search as k grows (plant only): k=1 0.66, k=2 0.79, k=4 0.89,
k=8 0.94. Smallest k that finds every relevant section, semantic: no defect 2, surface
scratch 4, dimensional deviation 4, crack never within 8.

What it showed:
- **Semantic and hybrid search both clearly beat keyword search** (R@4 0.89 vs 0.77 on
  the plant rule book; semantic is better than BM25 on 42 questions, worse on 14).
- **The weighted hybrid (0.3 BM25 / 0.7 semantic) caught up with semantic.** On the
  plant rule book they tie on R@4 (0.89) and the hybrid is slightly ahead on MRR and
  MAP@4, but they differ on only 14 of 200 questions (8 hybrid wins, 6 semantic wins).
  With the public distractors the hybrid holds up better: R@4 0.85 vs 0.83, and it
  loses fewer top-4 slots to public text (26% vs 31%).
- **The first 53 questions flattered semantic search a little**: 0.93 on them, 0.87 on
  the new 147. The weighted hybrid scored about the same on both (0.90 / 0.89), so it
  is the more consistent of the two.
- **MAP@4 shows where ranking is weakest:** questions that need two sections. Multi-section
  questions are semantic search's most common miss (10 of the 32 questions it does not fully answer).
- **k = 4 still holds**: going to 8 adds 0.05 recall for twice the text.
- The crack -> Contacts gap is still there: no method finds every relevant section for
  crack questions within 8.
- The test split is harder than dev for every method (semantic 0.83 vs 0.91); nothing
  was tuned on dev except the choice of method, so this is the questions, not overfitting.
- Not changed yet: the app still uses semantic search. Switching to the weighted hybrid
  is a judgement call on a small margin.

---

## Round 4: 300 questions (final)

The 200-question count above was taken on the way. Round 4 adds 100 more questions in
the same type proportions, for 300 in total (keyword 48, paraphrase 56, vocabulary
mismatch 48, identifier 40, multi-section 40, distractor 35, agent-style 33; 210 dev /
90 test), with extra coverage for the least-covered sections. Unlike the 147 before
them, these 100 were written *after* the intermediate count's results were known. The
type proportions were kept the same to avoid aiming at known weak spots, and the 100 are
reported separately below so their effect can be seen. All labels still match exactly
one section on both corpora. Contextual headers on.

Plant rule book only (51 chunks):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | MAP@4 |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.53 | 0.67 | 0.78 | 0.84 | 0.63 | 0.24 | 0.73 | 0.66 |
| bm25 | 0.59 | 0.67 | 0.78 | 0.85 | 0.69 | 0.24 | 0.75 | 0.69 |
| semantic | 0.65 | 0.79 | 0.87 | 0.94 | 0.77 | 0.27 | 0.84 | 0.78 |
| hybrid_rrf | 0.63 | 0.78 | 0.87 | 0.94 | 0.73 | 0.27 | 0.82 | 0.76 |
| hybrid_rrf_tfidf | 0.61 | 0.77 | 0.87 | 0.94 | 0.71 | 0.27 | 0.81 | 0.75 |
| **hybrid_weighted 0.3** | **0.68** | **0.81** | **0.89** | **0.95** | **0.79** | **0.28** | **0.86** | **0.80** |
| hybrid_weighted 0.5 | 0.66 | 0.78 | 0.88 | 0.95 | 0.77 | 0.27 | 0.84 | 0.78 |
| hybrid_weighted 0.7 | 0.63 | 0.74 | 0.86 | 0.93 | 0.73 | 0.27 | 0.81 | 0.75 |

Plant + public OSHA/FAA corpus (890 chunks):

| method | R@1 | R@2 | R@4 | R@8 | P@1 | P@4 | MRR | MAP@4 |
|---|---|---|---|---|---|---|---|---|
| tfidf | 0.43 | 0.58 | 0.71 | 0.76 | 0.53 | 0.22 | 0.63 | 0.57 |
| bm25 | 0.54 | 0.63 | 0.70 | 0.76 | 0.64 | 0.22 | 0.70 | 0.64 |
| semantic | 0.61 | 0.74 | 0.82 | 0.88 | 0.71 | 0.25 | 0.79 | 0.72 |
| hybrid_rrf | 0.59 | 0.72 | 0.82 | 0.90 | 0.69 | 0.26 | 0.78 | 0.72 |
| hybrid_rrf_tfidf | 0.57 | 0.69 | 0.81 | 0.90 | 0.67 | 0.25 | 0.76 | 0.70 |
| **hybrid_weighted 0.3** | **0.64** | **0.75** | **0.85** | **0.91** | **0.75** | **0.26** | **0.82** | **0.76** |
| hybrid_weighted 0.5 | 0.61 | 0.72 | 0.80 | 0.87 | 0.72 | 0.25 | 0.78 | 0.72 |
| hybrid_weighted 0.7 | 0.59 | 0.69 | 0.76 | 0.81 | 0.70 | 0.24 | 0.75 | 0.69 |

Question by question against semantic (R@4), better / same / worse out of 300:

| method | plant only | plant + public |
|---|---|---|
| tfidf | 21 / 225 / 54 | 26 / 212 / 62 |
| bm25 | 22 / 223 / 55 | 26 / 209 / 65 |
| hybrid_rrf | 20 / 260 / 20 | 25 / 253 / 22 |
| hybrid_rrf_tfidf | 20 / 262 / 18 | 22 / 255 / 23 |
| hybrid_weighted 0.3 | 14 / 279 / 7 | 25 / 262 / 13 |
| hybrid_weighted 0.5 | 22 / 259 / 19 | 28 / 240 / 32 |
| hybrid_weighted 0.7 | 22 / 253 / 25 | 27 / 229 / 44 |

Weighted 0.3 against semantic on ranking (plant only), better / same / worse: MRR
34 / 251 / 15, MAP@4 44 / 232 / 24.

By batch of questions (plant only, R@4 / MRR / MAP@4):

| questions | bm25 | semantic | hybrid_rrf | hybrid_weighted 0.3 |
|---|---|---|---|---|
| first 53 (rounds 1-3) | 0.78 / 0.76 / 0.71 | **0.93** / 0.89 / 0.82 | 0.88 / 0.85 / 0.79 | 0.90 / 0.89 / **0.83** |
| 147 of the intermediate count | 0.77 / 0.76 / 0.70 | 0.87 / 0.83 / 0.78 | 0.86 / 0.80 / 0.74 | **0.89 / 0.86 / 0.80** |
| last 100 | 0.79 / 0.74 / 0.67 | 0.84 / 0.84 / 0.76 | 0.87 / 0.84 / 0.78 | **0.88 / 0.86 / 0.79** |
| dev (210) | 0.78 / 0.77 / 0.70 | 0.88 / 0.86 / 0.78 | 0.87 / 0.84 / 0.77 | **0.90 / 0.88 / 0.82** |
| test (90) | 0.78 / 0.71 / 0.67 | 0.86 / 0.82 / 0.77 | 0.87 / 0.78 / 0.74 | 0.87 / 0.82 / 0.77 |

Adding the public corpus (R@4): tfidf 0.78 -> 0.71, bm25 0.78 -> 0.70, semantic
0.87 -> 0.82 (22 questions worse, none better), hybrid_rrf 0.87 -> 0.82,
hybrid_weighted 0.3 0.89 -> 0.85 (18 worse, 3 better). Share of top-4 slots taken by
public text: tfidf 32%, bm25 31%, semantic 30%, hybrid_rrf 27%, hybrid_weighted 0.3 26%.

Recall@4 by question type, plant only:

| method | agent-style | distractor | identifier | keyword | multi | paraphrase | vocab mismatch |
|---|---|---|---|---|---|---|---|
| tfidf | 0.69 | 0.96 | 1.00 | 1.00 | 0.70 | 0.79 | 0.33 |
| bm25 | 0.63 | 0.97 | 1.00 | 1.00 | 0.69 | 0.82 | 0.36 |
| semantic | 0.76 | 0.87 | 0.91 | 0.97 | 0.79 | **0.93** | 0.82 |
| hybrid_rrf | 0.78 | 0.94 | 1.00 | 1.00 | 0.76 | 0.88 | 0.71 |
| hybrid_weighted 0.3 | 0.78 | 0.94 | 0.95 | 0.98 | **0.80** | 0.90 | **0.83** |

Recall as k grows (plant only): semantic 0.65 / 0.79 / 0.87 / 0.94, weighted 0.3
0.68 / 0.81 / 0.89 / 0.95 at k = 1 / 2 / 4 / 8.

What it showed:
- **The weighted hybrid (0.3 BM25 / 0.7 semantic) is now ahead of semantic search on
  every headline metric**: R@4 0.89 vs 0.87, MRR 0.86 vs 0.84, MAP@4 0.80 vs 0.78 on the
  plant rule book, and 0.85 vs 0.82 with the public distractors. Question by question
  it is better on 14 and worse on 7 (plant), better on 25 and worse on 13 (with
  distractors), and it ranks better more often than worse (MRR 34 vs 15, MAP@4 44 vs 24).
- **It is the most consistent**: 0.88 to 0.90 on every batch of questions, while
  semantic search drifts from 0.93 on the first 53 to 0.84 on the last 100. On the test
  split the two tie.
- **Caveat on the last 100**: they were written after the intermediate count, and they
  are where the gap is widest (0.88 vs 0.84). On the first 200 alone the two tie on R@4 and the hybrid is
  ahead on MRR, MAP@4 and with distractors, so the conclusion does not rest on them.
- Keyword search stays well behind (0.78), and fusing with RRF is no better than
  semantic alone; the weighted mix with a small keyword share (0.3) is what helps.
- k = 4 still reasonable: 4 -> 8 adds 0.06 to 0.07 recall for twice the text.

**Decision after round 4:** the app's search switched from semantic to the weighted
hybrid (0.3 x BM25 + 0.7 x semantic, contextual headers, top 4).
