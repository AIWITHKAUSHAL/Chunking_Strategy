# Chunking Strategies Lab

Four chunking strategies, one document, five questions, one frozen embedding model and one
frozen LLM — plus a **live visualizer** that shows retrieval changing in real time as you move
`chunk_size`, `chunk_overlap` and the segmentation rule.

The point of the experiment is a single controlled claim:

> The document, the embedding model (`gemini-embedding-001`), the generation model
> (`gemini-3.5-flash-lite`), the vector index and the question set are **identical** in every
> run. The only independent variable is how the document was cut. Everything that differs in
> the results is therefore caused by chunking alone.

---

## Live demo

```bash
git clone <this-repo> && cd Chunking_Strategies
python -m venv .venv && source .venv/bin/activate
python -m ensurepip --upgrade
python -m pip install -r requirements-dev.txt
python -m pip install -e .

cp .env.example .env            # add your EURI_API_KEY
python -m chunking_lab.cli doctor     # verifies the key, the models and the gold labels
python -m chunking_lab.cli serve      # http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000>, pick strategies, drag the sliders, press **▶ Run live**. The page
streams Server-Sent Events from the backend and paints:

| Panel | What it shows |
| --- | --- |
| **Minimap** | Every chunk as a proportional segment. Green = clean boundary, dark red = the chunk starts mid-word, so a word was severed. |
| **Chunk ribbon** | Each chunk with its offsets, token estimate, separator used, and the **purple region = text repeated from the previous chunk** — `chunk_overlap` made visible. Gold answer spans are highlighted in amber. |
| **Chunk statistics** | Count, mean/min/max size, stdev, mid-word cuts, % broken boundaries, redundancy multiplier, span integrity. |
| **Live event stream** | The raw SSE frames: chunking → embedding → retrieval → generation, per strategy. |
| **Retrieval comparison** | One column per strategy for the selected question: the exact top-k chunks retrieved, their cosine scores, which gold spans each contains, and the LLM's answer from that context. |
| **Scoreboard** | Every metric for every strategy in the current run. |

`docs/chunking_visualizer.html` also runs **without a server**: a snapshot of the last sweep is
baked into the file, so opening it directly still demonstrates the comparison (badge reads
`DEMO · BAKED SNAPSHOT` instead of `LIVE · SSE CONNECTED`).

---

## The four strategies

### 1. Fixed-size (`fixed`)

Walks the character stream and cuts every `chunk_size` characters, stepping forward by
`chunk_size - chunk_overlap`. **Respects nothing** — not sentences, not words, not tables.

```
separators: none — pure character offsets
```

**Advantages** — fastest possible (one pass, no parsing); exactly predictable chunk count, so
index size and embedding cost are known in advance; completely language- and format-agnostic.

**Disadvantages** — severs words, sentences and list items; a fact split across a boundary
becomes unretrievable by *either* half; each chunk embedding mixes the tail of one topic with
the head of the next, blurring the vector.

### 2. Recursive character (`recursive`) — the usual default

Tries an ordered separator ladder and splits on the **coarsest separator that produces pieces
under `chunk_size`**, descending only for pieces that are still too large.

```python
separators = ["\n\n", "\n", ". ", " ", ""]
#              ¶       line  sentence word  character (last resort)
```

**Advantages** — keeps paragraphs and sentences intact whenever the budget allows; still cheap
(no embedding calls at segmentation time); the separator list is tunable per format (Markdown
headings, code blocks, CSV rows).

**Disadvantages** — the size budget still outranks meaning, so a long section is cut at an
arbitrary point; chunk sizes become uneven, complicating cost forecasting; a badly ordered
separator list silently degrades it into character splitting.

### 3. Sentence / paragraph (`sentence`)

Splits into paragraphs first, then packs **whole sentences** until one more would exceed
`chunk_size`. Overlap is applied in whole sentences rather than characters.

```
separators: paragraph (blank line) → sentence (. ! ?, abbreviation-aware)
```

**Advantages** — every chunk is grammatically complete and human-readable, which makes
retrieved context far easier to debug; sentence-level overlap keeps a procedure's precondition
attached to its step; paragraph awareness tracks the author's own topic structure.

**Disadvantages** — depends on reliable sentence detection (abbreviations, lists and headings
break naive splitters); short paragraphs become tiny chunks whose embeddings are weak and
noisy; a single long paragraph covering two subjects still yields one mixed chunk.

### 4. Semantic (`semantic`)

Embeds **every sentence individually**, computes the cosine distance between each adjacent
pair, and places a boundary wherever that distance exceeds a percentile threshold (default:
90th) of all distances in the document. `chunk_size` remains a hard cap.

```
separators: sentence → cosine-distance breakpoint (percentile threshold)
```

**Advantages** — boundaries land where the topic actually shifts, not where a counter runs
out; high internal coherence raises the signal-to-noise ratio of every retrieved chunk; adapts
to documents with no usable heading structure.

**Disadvantages** — one embedding call per sentence, making it by far the most expensive
strategy to ingest; the threshold is corpus-sensitive, so a wrong percentile over- or
under-splits badly; chunk sizes vary wildly, so some chunks blow past the prompt budget.

---

## Parameters

| Parameter | Meaning | Swept values |
| --- | --- | --- |
| `chunk_size` | Maximum characters per chunk. | **400**, **800**, **1200** |
| `chunk_overlap` | Characters (or whole sentences) repeated from the previous chunk. | **40** (10%), **160** (20%), **300** (25%) — plus a second sweep at **0**, **160**, **400** (0%, 20%, 50%) holding size at 800 |
| `separators` | Ordered boundary ladder; only `recursive` takes an explicit list. | `["\n\n", "\n", ". ", " ", ""]` |
| `top_k` | Chunks retrieved per question. | 3 |

That is **4 strategies × 3 size/overlap pairs = 12 configurations**, plus 3 more
overlap-only configurations, all against the same 5 questions.

### How to read `chunk_overlap`

Overlap buys **boundary insurance**: if a fact straddles a cut, the repeated tail gives the
second chunk a complete copy. It is not free — it multiplies the number of embedded characters:

```
redundancy ≈ chunk_size / (chunk_size - chunk_overlap)
   0% overlap → 1.00x      20% → 1.25x      50% → 2.00x
```

Past roughly 30% the index grows faster than recall improves, and near-duplicate chunks start
crowding each other out of the top-k window — you lose the diversity that made retrieval work.

---

## The document and the questions

`data/vector_search_handbook.md` — a ~16,000-character, 2,450-word operations handbook with
17 headings, 55 paragraphs and 118 sentences. It was written **specifically so that chunking
decisions are consequential**: it contains enumerations that span several paragraphs,
procedures whose exception clause sits at the very end of a paragraph, and facts whose
consequences are stated in a different section entirely.

The five questions each carry **span-level gold labels** — verbatim substrings of the document
that a correct answer must be grounded in (14 labels in total). Labelling spans rather than
chunk ids is what makes two chunking strategies comparable at all: a chunk-level label would be
invalidated the moment `chunk_size` changed.

| # | Question | Chunking weakness it probes |
| --- | --- | --- |
| Q1 | Recommended chunk size/overlap for technical manuals, and why so high? | Value and justification sit in neighbouring sentences — tests overlap. |
| Q2 | The three failure modes of hybrid retrieval. | A 3-item enumeration across three long paragraphs — tests whether chunk size can hold a complete list. |
| Q3 | How are tables inside PDFs handled? | A procedure whose exception is the paragraph's last sentence — tests boundary respect. |
| Q4 | Reranking's millisecond budget and the timeout behaviour. | Number in one paragraph, consequence in the next — the cleanest test of `chunk_overlap`. |
| Q5 | Embedding dimensionality and its effect on index memory. | Fact in §4, consequence in §6 — no single chunk holds both, so top-k must span two sections. |

---

## Metrics

**Structural** (chunking only — the embedding model is not involved, so these isolate the
chunking effect completely):

- **`span integrity`** — share of gold spans that survive chunking *intact inside a single
  chunk*. A span severed by a cut is unretrievable **in principle**: no embedding model, no
  reranker and no LLM can recover it.
- **`chunks needed`** — minimum number of chunks required to cover all of a question's gold
  spans. When this exceeds `top_k`, the question cannot be answered completely however good the
  embedder is.
- **`mid-word cuts`**, **`% broken boundaries`**, **`redundancy`** — direct damage counters.

**Retrieval** (at `top_k = 3`):

- **`recall`** — did any retrieved chunk contain a gold span?
- **`span coverage`** — what fraction of the question's gold spans appear anywhere in the
  top-k window? This is the headline number, because it measures *completeness*.
- **`context precision`** — what fraction of the retrieved characters belong to a gold span?
  This is the metric that punishes oversized chunks.

---

## Measured results

Full tables in [`results/OBSERVATIONS.md`](results/OBSERVATIONS.md); raw data in
`results/experiment_results.json`. 20 configurations, `gemini-embedding-001` (3072-dim),
`gemini-3.5-flash-lite`, `top_k = 3`.

### Finding 1 — fixed-size chunking destroys facts outright

`fixed` at 800/0 scores **93% span integrity**: one gold span —
`"chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters"` —
is cut in half and exists in **no chunk at all**. It is unretrievable in principle. No embedding
model, reranker or LLM can recover it. `fixed` at 400/40 severs a different span (Q5's
`"chunk count, not corpus size, drives your memory bill"`).

Every `recursive`, `sentence` and `semantic` configuration keeps **100% span integrity**, because
all three refuse to cut inside a sentence.

### Finding 2 — overlap is non-monotonic, and the peak is measurable

Holding strategy and size fixed (`fixed`, 800) and varying only `chunk_overlap`:

| overlap | span integrity | span coverage | redundancy | chunks |
| --- | --- | --- | --- | --- |
| 0 (0%) | **93%** — a span is severed | 90% | 1.00× | 21 |
| 160 (20%) | 100% | **100%** | 1.24× | 25 |
| 400 (50%) | 100% | **93%** ↓ | 1.97× | 40 |

Overlap at 20% repairs the severed span and lifts coverage to 100%. Pushing to 50% does **not**
help further — coverage *falls back* to 93% while the index nearly doubles. This is duplicate
amplification: near-identical chunks crowd each other inside the `top_k = 3` window, so the
chunk holding the remaining answer gets pushed to rank 4. More overlap is not monotonically
better, and the cost is paid in index size either way.

### Finding 3 — chunk size trades coverage against precision, cleanly

Averaged across all four strategies, on the matched-overlap grid (400/40, 800/160, 1200/300 —
10%, 20% and 25% overlap respectively):

| chunk_size | mean span coverage | mean context precision | mean chunks |
| --- | --- | --- | --- |
| 400 | **68%** | **0.1070** | 65 |
| 800 | 92% | 0.0797 | 35 |
| 1200 | **95%** | **0.0652** | 29 |

Coverage climbs with size and precision falls, monotonically, with the embedding model and LLM
untouched. At 400 characters, `top_k = 3` delivers roughly 1,200 characters of context — not
enough to hold Q2's three-paragraph enumeration — so the answer is partial *even though every
retrieved chunk is correct*. At 1200 characters the answer fits, but two thirds of what the
generator reads is irrelevant.

### Finding 4 — the ranking changes with the metric you choose

- Best coverage: **`semantic_800_0`** — 100% coverage at the highest precision (0.0791) of any
  config that reached 100%, with the lowest redundancy (1.00×).
- Best precision: **`sentence_400_40`** — 0.1192, but only 60% coverage; its chunks average 287
  characters, so three of them are too little evidence.
- `sentence` has the lowest recall of any strategy (**80%**) at every size, and the highest
  precision at every size. It returns little, densely.

Shipping on coverage alone would pick a 1200-character configuration and hand the generator
three times more distractor text; shipping on precision alone would pick 400 and starve it.

---

## Why chunking changes RAG quality even with the embedding model and LLM fixed

Five independent mechanisms, all visible in `results/OBSERVATIONS.md`:

**1. A chunk is the atomic unit of retrieval, so chunking decides what *can* be found.**
Retrieval returns chunks, never characters. If a cut lands between a claim and its
qualification, no chunk contains the complete fact. The best embedding model in the world
cannot retrieve a fact that was destroyed before it was embedded. This is what `span integrity`
measures, and it is the hardest ceiling in the system.

**2. One vector must summarise the whole chunk, so chunk contents decide embedding quality.**
An embedding is a single point representing all of a chunk's text. A chunk holding the tail of
one topic and the head of another lands somewhere between the two in vector space — close to
neither query. This is why fixed-size chunking underperforms at identical size: not because the
chunks are the wrong length, but because their *contents* are incoherent mixtures. Semantic
chunking attacks exactly this term, and it is why the same embedding model yields more useful
similarity scores on semantically coherent chunks.

**3. `top_k` is a budget in *chunks*, so chunk size silently sets how much evidence fits.**
Retrieving 3 chunks of 400 characters gives the LLM 1,200 characters; 3 chunks of 1,200 gives
3,600. For a question whose answer is spread over three paragraphs (Q2), small chunks cannot
fit a complete answer into `top_k=3` *even when every chunk retrieved is correct*. The failure
looks like a generation problem — the model gives a partial answer — but the cause is that
chunking changed how much evidence three slots could hold.

**4. Chunk size trades recall against precision, and the LLM is sensitive to both.**
Larger chunks raise recall (more text per slot, more chance of containing the answer) while
lowering context precision (more irrelevant text diluting the signal the generator conditions
on). Those pull in opposite directions, which is why recall alone is a dangerous ship criterion:
in this project's own evaluation methodology, shipping on a recall improvement alone twice
raised the hallucination rate.

**5. Overlap buys boundary insurance but spends it on redundancy and diversity.**
Overlap repeats the previous chunk's tail, so a straddling fact survives in at least one copy —
Q4 is the clearest case. But at high overlap the same sentence exists in several chunks, all of
which score similarly, and the top-k window fills with near-identical passages. The answer then
sits at rank 4 while ranks 1–3 are three copies of the same paragraph. More overlap is not
monotonically better.

**The practical consequence.** Chunking is not preprocessing you do before the interesting
part — it is the step that determines the ceiling every later component operates under. An
upgrade from a weak embedder to a strong one cannot recover a fact that chunking severed, and a
larger LLM cannot answer completely from context that `top_k` was too small to deliver. That is
why it is worth sweeping — and why the retrieved chunks, not just the final answers, are what
this repository visualizes.

---

## Repository layout

```
data/vector_search_handbook.md     the single source document, every strategy sees this
src/chunking_lab/
  config.py        settings from the environment / .env
  document.py      loading + structural analysis
  strategies.py    the four strategies, all returning annotated Chunk objects with offsets
  euri_client.py   gemini-embedding-001 + gemini-3.5-flash-lite, cached, with offline fallback
  retriever.py     cosine-similarity vector store + the span-level metrics
  questions.py     the 5 questions and their 14 gold spans
  experiment.py    the strategy × size × overlap sweep
  report.py        Markdown rendering of the results
  cli.py           doctor / chunk / ask / compare / experiment / serve
app/server.py      FastAPI + Server-Sent Events backend for the live visualizer
docs/chunking_visualizer.html   the live visualizer (single file, works with or without a server)
scripts/build_snapshot.py       bakes results into the visualizer for serverless viewing
results/           experiment_results.json + OBSERVATIONS.md (generated)
tests/             51 tests covering strategy invariants, metrics and the API
```

## Commands

```bash
python -m chunking_lab.cli doctor                         # config, key and gold-label check
python -m chunking_lab.cli chunk --strategy fixed --chunk-size 400 --chunk-overlap 40
python -m chunking_lab.cli compare --chunk-size 800 --chunk-overlap 160
python -m chunking_lab.cli ask "how are PDF tables handled?" --strategy semantic
python -m chunking_lab.cli experiment --verbose            # the 12-configuration sweep
python -m chunking_lab.cli experiment --grid overlap       # the overlap-only sweep
python -m chunking_lab.cli serve                           # live visualizer
python scripts/build_snapshot.py --run                     # sweep + bake into the HTML
```

## Quality

```bash
ruff check src app tests scripts    # lint (E, W, F, I, D, UP, B, SIM, C4, RET, PTH, ARG, N)
ruff format src app tests scripts   # format
pytest -q                           # 51 tests
```

Docstrings are enforced by ruff's pydocstyle rules (`D`, Google convention) on every module,
class, method and function.

## Models

Both models are reached through the Euron gateway with the OpenAI-compatible client:

```python
client = OpenAI(api_key=os.environ["EURI_API_KEY"], base_url="https://api.euron.one/api/v1/euri")
client.embeddings.create(model="gemini-embedding-001", input=[...])  # 3072-dim vectors
client.chat.completions.create(model="gemini-3.5-flash-lite", messages=[...])
```

Every embedding is cached on disk by `sha256(model + text)`, so repeated sweeps are nearly free
— most chunks are byte-identical between configurations. Without `EURI_API_KEY` the lab falls
back to a deterministic hashed bag-of-words embedder: all code paths, experiments and the
visualizer still run, but retrieval rankings are lexical rather than semantic. The mode is
reported by `doctor`, printed in every report, and shown in the visualizer's header badge.
