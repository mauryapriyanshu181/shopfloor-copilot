# ShopFloor Copilot

A worker on the factory floor sends a photo of a part and a question.

The service does four things. It looks at the photo. It reads the ID stamped on the
part. It finds the plant rules that apply. Then it answers, showing which rules it used
and every step it took.

It never scraps or escalates a part by itself. It writes down a proposal, and a
supervisor signs it.

Everything runs locally on open-source tools. No cloud AI services.

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

If Ollama is not running, the service still works. It falls back to a fixed set of
steps and a fill-in-the-blanks answer. It notes in the response that it did this.

If tesseract is missing, the text reading returns an error instead of crashing.

## Trying it

Piping any response through `scripts/show.py` prints it as readable text instead of raw
JSON. It works for `/inspect` and for `/bandit`.

Send a photo and a question:

```bash
curl -s -X POST http://localhost:8000/inspect \
  -F "query=Is this part within tolerance?" \
  -F "image=@samples/part_crack.png" | python scripts/show.py
```

Ask a question with no photo:

```bash
curl -s -X POST http://localhost:8000/inspect \
  -F "query=Who do I escalate a crack to?" | python -m json.tool
```

Rate an answer. Use the `transaction_id` from the response above. 1 means helpful,
0 means not helpful:

```bash
curl -s -X POST http://localhost:8000/feedback \
  -H 'Content-Type: application/json' \
  -d '{"transaction_id":"PASTE_ID_HERE","score":1}' | python -m json.tool
```

Look up a past answer:

```bash
curl -s http://localhost:8000/transactions/PASTE_ID_HERE | python -m json.tool
```

See what the learning loop currently knows:

```bash
curl -s http://localhost:8000/bandit | python -m json.tool
```

## What comes back

A call to `/inspect` returns the answer plus everything needed to check it later:

| Field | What it is |
|---|---|
| `answer` | what the worker reads |
| `defect_category` | crack, surface_scratch, dimensional_deviation, or no_defect |
| `defect_detail` | the measurement that led to that call |
| `ocr` | the text read off the part, and the work order ID pulled out of it |
| `decision_trace` | every step taken, in order, with the reason for each |
| `config` | which model, how many rule paragraphs were used, why that number, and any step that had to fall back |
| `proposed_action` | set when a human needs to sign off |
| `latency_s` | how long the whole call took |
| `transaction_id` | the ID used for rating and for looking it up again |

## How each part works

**Looking at the photo** (`app/vision.py`). First I separate the part from the
background. Then I look for straight lines on it.

A line darker than the part is a crack. A line brighter than the part is a scratch. If
the width-to-height ratio is outside 1.60 give or take 0.08, the size is wrong.

The ID is stamped near the top of the part. I skip that strip before looking for lines.
Otherwise the letters get read as cracks.

The checks run worst first. So a part that is cracked and also the wrong size is
reported as a crack.

**Reading the stamp** (`app/ocr.py`). The ID sits in the top strip of the part, so I cut
that strip out first and hand tesseract only that. Reading one clean line works far
better than reading a whole photo that is mostly blank part face.

Then enlarge it, convert to black and white, run tesseract, and pull out anything shaped
like `WO-1042`. The pattern allows a stray character or two, because the reader
sometimes slips an extra digit in.

**Finding the right rules** (`app/rag.py`). The four documents in `knowledge/` are
split into 14 paragraphs, one per heading.

For a question, I throw away the common words like "the" and "is". Rare words count for
more. Then I score every paragraph on how many of the important words it shares with the
question. The top few go to the model.

Because this is a search, someone can edit a rule and it takes effect right away.

**Deciding what to do** (`app/agent.py`). The model gets the question and the rules. It
then picks one action at a time. The choices are: look at the photo, search the rules,
check the work order, escalate, or answer.

The menu it is shown shrinks as it goes. Once a tool has been run, it is taken off the
list, so the model cannot ask for it again. This matters: a small model will keep
reaching for the same tool however firmly you tell it not to, and each wasted ask costs
a full round trip. If it names a tool that is no longer on the list anyway, that turn
goes to the next useful step instead. Escalate and answer are never removed, so it can
always finish.

It gets 4 turns at most. Every turn is recorded, with what it picked and why, including
any turn that had to be redirected.

**Keeping it safe** (`app/store.py`). Every call is added to `data/audit_log.jsonl`,
which is only ever appended to. Escalations come back marked
`PENDING_HUMAN_APPROVAL` with `executed: false`. There is no code anywhere that can set
that to true.

**Not running too long.** The 15 second limit covers the whole request, not each model
call. Every call only gets the time that is left. Once under 2 seconds remain, the
service stops calling the model and finishes with the fixed steps. It writes the reason
into the response.

## The learning loop

Every question needs some number of rule paragraphs. Too few and the answer misses
something. Too many and it gets slow. The right number is not the same for every defect,
so instead of picking one myself I let the service work it out.

- **The situation:** which defect was found, or that no photo was sent.
- **The choice:** use 2, 4, or 8 paragraphs.
- **The score:** `rating x 10 - seconds taken`. Helpful is worth 10 points, each second
  costs 1.

It keeps a separate record for each defect. Each of the three settings gets tried once
first. After that it uses the best scoring one 80% of the time. The other 20% it tries a
different one anyway, in case the early results were just luck.

Run it against a running service:

```bash
python scripts/bandit_demo.py 32
```

A full run of 32 rounds against `qwen2.5:3b` on an M1 MacBook Air, starting from an
empty scoreboard. Nothing below is trimmed:

```
 1  crack                  k=8 explore_cold_start latency= 8.96s score=1 reward=  1.040
 2  surface_scratch        k=2 explore_cold_start latency=16.27s score=1 reward= -6.274
 3  dimensional_deviation  k=2 explore_cold_start latency=12.67s score=0 reward=-12.667
 4  crack                  k=4 explore_cold_start latency=12.41s score=0 reward=-12.407
 5  surface_scratch        k=4 explore_cold_start latency=12.08s score=1 reward= -2.080
 6  dimensional_deviation  k=4 explore_cold_start latency=18.61s score=1 reward= -8.612
 7  crack                  k=2 explore_cold_start latency=10.93s score=0 reward=-10.929
 8  surface_scratch        k=8 explore_cold_start latency=11.56s score=1 reward= -1.558
 9  dimensional_deviation  k=8 explore_cold_start latency=10.66s score=1 reward= -0.664
10  crack                  k=8 exploit            latency=12.97s score=1 reward= -2.974
11  surface_scratch        k=8 exploit            latency=10.62s score=1 reward= -0.618
12  dimensional_deviation  k=8 exploit            latency= 9.20s score=1 reward=  0.803
13  crack                  k=8 exploit            latency=11.77s score=1 reward= -1.773
14  surface_scratch        k=8 exploit            latency=11.02s score=1 reward= -1.023
15  dimensional_deviation  k=8 exploit            latency=10.21s score=1 reward= -0.205
16  crack                  k=8 exploit            latency=10.95s score=1 reward= -0.951
17  surface_scratch        k=8 exploit            latency=11.43s score=1 reward= -1.433
18  dimensional_deviation  k=8 exploit            latency=10.73s score=1 reward= -0.727
19  crack                  k=8 exploit            latency=11.83s score=1 reward= -1.829
20  surface_scratch        k=8 exploit            latency=14.72s score=1 reward= -4.724
21  dimensional_deviation  k=4 explore            latency=24.00s score=1 reward=-14.003
22  crack                  k=8 explore            latency=11.94s score=1 reward= -1.940
23  surface_scratch        k=8 exploit            latency=12.07s score=1 reward= -2.067
24  dimensional_deviation  k=8 exploit            latency=12.87s score=1 reward= -2.874
25  crack                  k=2 explore            latency=12.23s score=0 reward=-12.230
26  surface_scratch        k=8 explore            latency=12.06s score=1 reward= -2.057
27  dimensional_deviation  k=8 exploit            latency=12.89s score=1 reward= -2.894
28  crack                  k=8 exploit            latency=12.33s score=1 reward= -2.331
29  surface_scratch        k=8 exploit            latency=12.25s score=1 reward= -2.246
30  dimensional_deviation  k=2 explore            latency=17.17s score=0 reward=-17.166
31  crack                  k=8 exploit            latency=13.00s score=1 reward= -3.002
32  surface_scratch        k=8 exploit            latency=12.40s score=1 reward= -2.405

final bandit table:
  crack                  {'2': n=2 mean=-11.58, '4': n=1 mean=-12.41, '8': n=8 mean= -1.72}  -> best k=8
  dimensional_deviation  {'2': n=2 mean=-14.92, '4': n=2 mean=-11.31, '8': n=6 mean= -1.09}  -> best k=8
  surface_scratch        {'2': n=1 mean= -6.27, '4': n=1 mean= -2.08, '8': n=9 mean= -2.01}  -> too close to call
```

Rounds 1 to 9 are the cold start: each setting gets tried once for each defect. From
round 10 the service starts using what it has learned, and the word in the third column
changes from `explore_cold_start` to `exploit`. The occasional `explore` after that is
the 20% that keeps checking the other settings.

All 35 requests in this run reached a real conclusion, either an answer or a proposed
escalation. None ran out of steps, and no tool was called twice.

## Two settle on 8, one is a genuine tie

Here are the ratings behind that table, and what each run was missing:

```
  crack                  k=2 [0,0]   k=4 [0]     k=8 [1,1,1,1,1,1,1,1]
                         k=2 and k=4 both missing escalation.md

  dimensional_deviation  k=2 [0,0]   k=4 [1,1]   k=8 [1,1,1,1,1,1]
                         k=2 missing tolerances.md, k=4 had everything

  surface_scratch        k=2 [1]     k=4 [1]     k=8 [1,1,1,1,1,1,1,1,1]
                         every setting had what it needed
```

**A crack only works at 8.** It needs the escalation contact, and that paragraph does
not appear until 8 are pulled in. Two and four were marked unhelpful every time. This
one is settled by the rating alone, and the gap says so: -1.72 against -11.58 is almost
the full 10 points the rating is worth.

**A wrong size works at 4 or 8.** Two paragraphs misses the tolerance table and was
marked unhelpful both times, so the rating rules it out. Four and eight both had what
they needed, so the rating cannot separate those two - the clock does, and 8 was
quicker.

**A scratch works at any setting.** Every rating is helpful, so the ratings cancel out
and only speed is left. The best two finish within 0.07 of each other, which is noise,
so the service reports it as too close to call rather than naming a winner.

So the two halves of the score do different jobs in different rows. For a crack the
rating does all the work. For a scratch there is nothing to decide. For a wrong size
both matter: the rating knocks out the smallest setting, then the clock picks between
the two that are left.

## More context can be faster

The speed part sounds backwards until you look at how long each one took:

```
  defect                 k    runs   avg secs   steps
  dimensional_deviation  2       2       14.9       4
  dimensional_deviation  4       3       19.8       4
  dimensional_deviation  8       6       11.1       3
  surface_scratch        2       1       16.3       4
  surface_scratch        8       9       12.0       3
```

A step costs about 4 seconds, and the time a request takes is roughly steps times 4.
The size of the prompt barely matters. With 8 paragraphs the model had enough to finish
in three steps instead of four, so the biggest setting was also the quickest.

So the number of paragraphs affects the time only through how many steps the model
needs. Worth knowing before tuning anything against a clock.

## A note on the scoring

The score is `rating x 10 - seconds taken`. A helpful answer is always worth 10 more
than an unhelpful one, so the ranking is sound.

The risk is that the seconds swamp the rating. A call here takes 9 to 24 seconds and
varies between runs for reasons that have nothing to do with the answer. If one setting
is more than 10 seconds slower than another, it loses even when it is the only one
giving the right answer. That is not a hypothetical: an earlier version of the agent
wasted a step re-running a tool it had already run, which pushed some calls past 30
seconds, and the wrong-but-fast setting won on wrong sizes. Cutting that wasted step
brought every call under about 15 seconds and the right settings won comfortably.

I left the formula as the brief sets it. In a real project I would measure the time
against a target, say 15 seconds, instead of using raw seconds, so the time part stays
on a similar scale to the rating. And since the time goes on steps rather than
paragraphs, cutting a step saves more than cutting the context.

The ratings in the demo are not from a real supervisor. They come from a scoring rule
inside `scripts/bandit_demo.py`. It marks an answer helpful only if the paragraphs
pulled in cover every document needed to act on that defect.

## Tests

```bash
pytest tests/ -q
```

20 tests. They cover the four defect types, the stamp reading, the search, the learning
loop, the shrinking tool menu, and the three endpoints. The tests point the model at a dead port, so they run
without Ollama. They take about 15 seconds, nearly all of which is scikit-learn
loading - the tests themselves are quick.

## What I kept simple on purpose

The brief allows 4 to 5 hours, so these are deliberate:

- **Word matching for the search, not a meaning-based model.** 14 paragraphs across
  four documents does not need a 200MB download. The cost is that "crack" and "Cracked"
  do not match each other. DECISIONS.md covers this.
- **Basic image processing, not a trained detector.** The four types can be told apart by
  shape alone. There is no labelled data to train on. And this version reports a
  measurement an inspector can check against the part.
- **The sample photos come from a script,** so the results are the same on any machine.
  The detector is tuned to those photos: a part at brightness 180 on a background at 30.
  A photo from a phone would need the numbers set again.
- **One model, not two.** A second model is listed as a bonus. The fill-in-the-blanks
  answer already works as the backup when the model is slow or missing.
- **Past answers are kept in memory.** Restarting the service clears them. The audit file
  on disk is not affected.

## Why I built it this way

See [DECISIONS.md](DECISIONS.md).
