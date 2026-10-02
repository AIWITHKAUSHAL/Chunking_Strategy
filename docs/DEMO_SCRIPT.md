# Demo & Video Walkthrough

A running order for demonstrating the lab, mapped to the panels of
`docs/chunking_visualizer.html`. Everything below is something the page shows live — no slides
required.

## Setup (before recording)

```bash
source .venv/bin/activate
python -m chunking_lab.cli doctor      # should print: mode live, 3072 dimensions, gold labels OK
python -m chunking_lab.cli serve       # http://127.0.0.1:8000
```

Embeddings are cached on disk, so a second run of the same configuration is instant — warm the
cache once before recording and the demo never stalls on the network.

---

## 1. The setup — what is being held constant (≈1 min)

Point at the header badges: `LIVE · SSE CONNECTED`, `embedding: gemini-embedding-001`,
`llm: gemini-3.5-flash-lite`. Then the document bar: 16,037 chars, 2,450 words, 118 sentences,
55 paragraphs.

> "One document. One embedding model. One LLM. One index. One question set. The only thing I am
> going to change is where the cuts go."

## 2. Fixed-size — watch it break words (≈2 min)

Deselect everything except **Fixed**, preset **800 / 160**, press **▶ Run live**.

- The **minimap** fills in — most segments are dark red, meaning the chunk starts mid-word.
- **Chunk statistics**: ~19 mid-word cuts, **100% broken boundaries**, redundancy 1.24×.
- Scroll the **chunk ribbon** to chunk #1. It opens with `ty percent of indexed volume` — the
  word "sixty" was cut in half. The purple underlined region is the 160 characters repeated
  from chunk #0; that is `chunk_overlap` made visible.

> "Nothing here knows what a word is. It counted to 800 and cut."

Explain the parameters while this is on screen: `chunk_size` = window width,
`chunk_overlap` = how much of the previous window is repeated, `separators` = none.

## 3. Recursive — the same size, better cuts (≈2 min)

Add **Recursive**, run again.

- Minimap turns green: **0 mid-word cuts, 0% broken boundaries**, redundancy 1.02×.
- Ribbon chunks show `sep '\n\n'` — the separator each chunk was actually split on.
- Point out the separator ladder on the reference card:
  `["\n\n", "\n", ". ", " ", ""]` — paragraph, line, sentence, word, character.

> "Same 800-character budget. It just tries paragraph breaks first and only falls back to
> finer separators when a piece is still too big."

## 4. Sentence and Semantic (≈2 min)

Add both and run. In the ribbon:

- **Sentence** chunks carry a `sentence_count` and never cross a paragraph; many are far under
  budget, which is why the chunk count roughly doubles.
- **Semantic** chunks carry `boundary_reason` — `topic_shift` when the cosine distance between
  adjacent sentences spiked, `size_cap` when the hard limit hit first — plus the distance `d=`
  that triggered it.

> "Semantic chunking is the only one that pays for an embedding call per sentence at ingest
> time. That is the cost; coherent boundaries are what you buy."

## 5. The payoff — same question, different chunks (≈4 min)

Scroll to **Stage 2**. Walk Q1 first, then Q2 and Q4.

**Q1 — the overlap question.** The gold spans are listed in amber. Compare columns:
fixed-size retrieves a chunk that *starts mid-sentence*, so the recommendation's first half is
missing and the badge says `needs 2 chunks`; recursive retrieves one chunk tagged `★ 2 gold` and
`needs 1 chunk`.

**Q2 — the completeness question.** Three failure modes spread across three paragraphs. Switch
the preset between **400 / 40** and **1200 / 300** and re-run: at 400 the answer needs more
chunks than `top_k=3` can hold, so the LLM answers partially *even though every chunk retrieved
is correct*.

**Q4 — the overlap-insurance question.** Switch between **800 / 0** and **800 / 400**. At zero
overlap the millisecond budget and the timeout behaviour fall on opposite sides of a cut.

> "Same embedder, same LLM, same prompt. The only difference is which chunks retrieval could
> hand over."

## 6. The scoreboard and the trade-off (≈2 min)

Scroll to **Metrics across this run** and read the two columns that move in opposite directions:

- **span coverage** rises with chunk size — more text per `top_k` slot.
- **ctx precision** falls with chunk size — more irrelevant text diluting the signal.

> "This is why recall alone is a dangerous thing to ship on. Bigger chunks make recall look
> better while giving the generator more to be distracted by."

## 7. Close (≈1 min)

Five mechanisms, in one sentence each:

1. A chunk is the unit of retrieval — a severed fact is unretrievable in principle.
2. One vector summarises the whole chunk — incoherent chunks embed to a useless midpoint.
3. `top_k` is a budget in chunks — chunk size silently decides how much evidence fits.
4. Size trades recall against precision — and the LLM is sensitive to both.
5. Overlap buys boundary insurance and spends it on redundancy and lost diversity.

> "Chunking isn't preprocessing before the interesting part. It sets the ceiling everything
> downstream operates under."

---

## Fallback if the network is down

The page works without the server: open `docs/chunking_visualizer.html` directly. The badge
reads `DEMO · BAKED SNAPSHOT` and the full sweep replays from the snapshot baked into the file.
Chunk-ribbon text is bundled for the 800 / 160 configurations only; everything else needs the
server.
