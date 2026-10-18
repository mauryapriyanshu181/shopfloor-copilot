# Section G — Decision Rationale

## 1. Why vector RAG (vs. a vectorless/long-context read) fits this SOP corpus — and what would change your answer if the plant's SOP set were fixed at 20 pages instead of continuously growing.

There are only four short documents here. I could send all of them with every question,
and then nothing could ever be missed. I chose to search them instead, because a plant's
rule book keeps growing. With search, someone edits a rule and it takes effect straight
away. Each answer can also name the document it came from, which the SOP requires for
record keeping.

If the rule book really were fixed at 20 pages, I would drop the search and just send
everything. Searching adds one way to fail: it can look in the wrong place. That
happened to me while building this. My search matches exact words. The document said
"Cracked parts" and the question said "crack". The two never matched, so the scrap rule
never showed up for cracked parts. I fixed it by changing the wording of my own
document. You cannot do that with a customer's real documents. So before using this in a
plant, I would switch to a search that matches meaning instead of exact words.

## 2. Why an agent loop (vs. a fixed pipeline) is justified for the tool-selection step here — and name the one part of this system you would NOT make agentic, and why.

The questions are not all the same. Sometimes there is a photo. Sometimes only text.
Sometimes just a work order number. A fixed set of steps would run the image checks even
when someone only asks "who do I call about a crack?", which wastes time. It would also
skip the ERP check when the answer depends on whether the job is on hold. So I let the
model pick the next step each time, and I write down every choice it makes.

The one thing I do not let it pick is the verdict: rework, scrap, or escalate. That
stays a simple lookup in Rules R1 to R4. The same part should always get the same
verdict. And when a quality auditor asks why, "Rule R1 says scrap" is an answer you can
defend. "The model decided" is not.

## 3. Why you chose classical CV, a pretrained model, or both for the defect classifier — and what would push you to fine-tune a custom model instead.

I used basic image processing, not a trained model. The four types can be told apart by
shape alone. A crack is a dark line. A scratch is a bright line. A wrong size is a box
with the wrong width-to-height ratio. There is also no labelled data to train on, and a
ready-made detector has only seen everyday objects, never a machining crack.

The main reason was that the simple version explains itself. It reports "4 dark lines,
peak contrast 84". An inspector can hold the part up and check that. A score of 0.95
tells them nothing.

Real photos would change my mind. Once pictures come from a phone, with changing light
and angles, fixed rules stop working. Once we had about 500 labelled photos per type
from that cell's own camera, training a small model would be the cheaper path. Not
before that.

## 4. If this pilot needed to scale from one plant to ten, which cost-optimization lever — prompt/response caching, model tiering, batching, a smaller fine-tuned model, or quantization — would you apply first, and why that one before the others.

Caching, first. The same questions come up again and again: the same parts, the same few
questions each shift, the same rule book for weeks. Saving answers and reusing them
removes a large share of the model calls. It is little work, and it carries no risk to
accuracy, because a saved answer was already correct.

Next I would send the easy questions to a smaller model, and keep the bigger model for
the hard ones.

A smaller trained model and quantization come last. Both change how the model behaves,
so the plant would have to re-check the whole system against its quality process. That
costs more than the computing time it saves.

I would not use batching at all. Batching helps when many requests can wait together.
Here it is one worker standing at a machine, waiting. It would add delay they feel, to
gain speed nobody needs.

## 5. Name one governance risk specific to a shop floor (not a generic AI risk) that this design does not yet fully address, and how you'd close it in a real engagement.

The ratings come from a supervisor who is under pressure to keep the line running. So
the system learns what gets people back to work, not what is correct.

Here is how that goes wrong in this build. A short answer that leaves out the escalation
contact gets the worker moving faster, so it is more likely to be marked helpful. But
that is exactly the setting that weakens the crack path, where the escalation contact
only appears when more of the rule book is pulled in. Over a few thousand uses, the
system could slowly shift towards escalating less often. No accuracy check would catch
it, because the ratings themselves are the problem.

The harm is limited today. Ratings only change how much of the rule book is pulled in.
They never change the verdict.

To close it properly I would do three things. Stop learning on the serious types, so a
crack always pulls in the full rule book. Attach a badge ID to every rating, so one
shift approving everything shows up instead of being averaged away. And once a week,
compare what the system said with what the ERP recorded later: a rework ticket, a scrap
note, a customer return. Then it is judged on what actually happened, rather than on who
was in a hurry.

---

## From Section E — Action space: pick ONE axis to optimize, either which OCR engine to use or the RAG top-K, and justify why you chose that axis over the others.

I chose how many rule paragraphs to pull in, and not which text reader to use.

The main reason is that the text reader makes no real difference here. There is one line
of printed text, on a flat surface, in even light. Both readers get `WO-1042` right every
time. If both choices give the same answer, there is nothing to learn. The score would
only reflect which one happened to run faster, and the system would be tuning something
that never affects the worker.

The number of paragraphs has a real trade-off in both directions. Too few and the answer
is missing something the worker needs. Too many and the answer gets slower. There is no
single right number, and it is not even the same for every defect, which the demo shows:
a crack needs 8 paragraphs to reach the escalation contact, while a scratch is answered
correctly with 2. That is exactly the kind of choice worth learning from real use rather
than guessing at.

Two smaller reasons. The paragraph count affects every question, including ones with no
photo at all, so evidence builds up faster. And the second reader, EasyOCR, brings in
about 2GB of extra downloads, which works against a service that is meant to be easy to
set up and run locally.

It is also worth being clear about when I would choose the other way. My sample photos
are clean and generated by a script. On a real floor, with oily parts, bad angles and
poor light, which text reader you use would matter a great deal, and a wrong work order
number is a serious problem because it files the result against the wrong job. If this
moved to real photographs, the text reader would become the better thing to tune, and
the paragraph count would be better set once by hand.
