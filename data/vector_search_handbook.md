# The Vector Search Operations Handbook

## 1. Purpose and Scope

This handbook documents how the Atlas Retrieval Platform ingests, indexes, and serves
unstructured text for production retrieval-augmented generation workloads. It is written for
platform engineers who operate the service and for application teams who build on top of it.
Every number quoted here is a measured production value from the Frankfurt and Oregon regions
over the twelve months ending in March, not a vendor datasheet figure.

The platform serves three classes of corpus. Technical manuals are long, deeply nested, and
full of tables; they account for roughly sixty percent of indexed volume. Customer support
transcripts are short, conversational, and noisy. Regulatory filings sit in between: long, but
written in dense legal prose with very few headings. Each class behaves differently under the
same chunking configuration, which is why Section 3 gives per-class recommendations rather than
a single global default.

Readers looking for the API contract should consult the service reference instead. This document
covers operational behaviour: what the pipeline does to a document, what knobs exist, what breaks
in production, and how to tell which failure you are looking at.

## 2. The Ingestion Pipeline

Ingestion runs as a five-stage pipeline. A document enters as bytes and leaves as a set of
embedded, metadata-tagged chunks committed to the index. The stages are extraction,
normalisation, segmentation, embedding, and commit. Each stage is independently retryable and
writes a checkpoint, so a failure in embedding does not force a re-extraction of a
four-hundred-page manual.

Extraction converts source bytes into plain text plus a structural outline. For HTML and
Markdown this is cheap and lossless. For PDF it is neither. The extractor runs a layout analysis
pass that classifies every text block on the page as body text, heading, caption, footnote, or
table cell. Blocks classified as table cells are routed away from the normal text path.

Tables inside PDFs receive special handling because naive extraction interleaves column values
into unreadable word salad. The extractor reconstructs each table into a row-major Markdown
table, then wraps it in an HTML comment carrying the table's caption and the page number it came
from. Crucially, the reconstructed table is then treated as a single atomic unit for the rest of
the pipeline: segmentation is forbidden from splitting inside it, even when doing so would
produce a chunk that exceeds the configured maximum size. An oversized table chunk is accepted
and flagged with the `oversize_atomic` tag rather than being cut in half, because half a table
is worse than a large one. Tables wider than forty columns are the single exception; those are
split by column group and each fragment repeats the header row.

Normalisation collapses runs of whitespace, repairs hyphenated line breaks introduced by
two-column PDF layouts, strips repeated page headers and footers detected by frequency analysis,
and converts smart quotes to ASCII. Normalisation deliberately does not lowercase, stem, or strip
punctuation; the embedding model is case- and punctuation-sensitive and performs measurably worse
on pre-mangled input.

Segmentation is the stage this handbook's companion experiments study in detail. It takes
normalised text plus the structural outline and emits chunks. Four segmentation strategies are
supported and are described in Section 3.

Embedding sends each chunk to the embedding service in batches of ninety-six. Commit writes
vectors and metadata into the index transactionally per document, so a partially embedded
document is never queryable.

## 3. Segmentation Strategies and Their Parameters

### 3.1 Fixed-size segmentation

Fixed-size segmentation walks the character stream and cuts every `chunk_size` characters,
stepping forward by `chunk_size` minus `chunk_overlap`. It respects nothing: not sentences, not
words, not headings. Its only virtues are speed and perfectly predictable chunk counts, which
makes it the right choice for cost modelling and for load tests where you need an exact vector
count. It is almost never the right choice for quality.

### 3.2 Recursive character segmentation

Recursive character segmentation is the platform default. It takes an ordered list of separators
and tries each in turn: paragraph breaks first, then single newlines, then sentence-ending
punctuation, then spaces, then raw characters as a last resort. The configured separator list is
`["\n\n", "\n", ". ", " ", ""]`. The splitter recurses: it splits on the coarsest separator that
produces pieces under `chunk_size`, and only descends to a finer separator for pieces that are
still too large. The effect is that natural boundaries are preserved wherever possible and
violated only where unavoidable.

### 3.3 Sentence and paragraph segmentation

Sentence and paragraph segmentation first splits the document into paragraphs, then packs whole
sentences into chunks until adding one more sentence would exceed `chunk_size`. Overlap is
expressed in sentences rather than characters: an overlap of two means the last two sentences of
chunk N are repeated as the first two sentences of chunk N plus one. Every chunk is therefore a
grammatically complete unit, which makes retrieved context far more readable for both humans
debugging the system and for the generation model.

### 3.4 Semantic segmentation

Semantic segmentation embeds every sentence individually, computes the cosine distance between
each adjacent pair, and places a chunk boundary wherever that distance exceeds a percentile
threshold of all distances in the document. The default threshold is the ninety-fifth percentile.
Boundaries therefore land where the topic actually shifts rather than where a character counter
happens to run out. The cost is an extra embedding call per sentence at ingestion time, which
roughly triples ingestion spend for a given corpus; the benefit is chunks whose internal
coherence is high, which raises the signal-to-noise ratio of every chunk the retriever returns.

### 3.5 Recommended chunk sizes and overlaps

The following defaults were chosen by sweeping sizes from two hundred to two thousand characters
against a hand-labelled question set for each corpus class.

Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one
hundred and sixty characters, which is twenty percent. The overlap is set this high specifically
because procedures in manuals routinely run across a paragraph boundary, and a step separated
from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest
overlap at which the labelled procedure questions stopped losing their preconditions.

Support transcripts use a chunk size of four hundred characters with an overlap of forty
characters, which is ten percent. Transcripts are already short and self-contained per turn;
larger chunks simply mix several unrelated customer issues into one vector and blur it.

Regulatory filings use a chunk size of one thousand two hundred characters with an overlap of
three hundred characters, which is twenty-five percent. Legal prose carries definitions and
qualifications at long range, and the high overlap is the cheapest available insurance against
severing a clause from the definition it depends on.

Overlap above thirty percent is not recommended for any corpus. Beyond that point the index
grows faster than recall improves, and near-duplicate chunks begin crowding each other out of
the top-k window, which costs you the diversity that made retrieval work in the first place.

## 4. The Embedding Layer

The platform embeds with `gemini-embedding-001`, served through the Euron gateway using an
OpenAI-compatible client. The model emits vectors of three thousand and seventy-two dimensions.
Vectors are L2-normalised at write time, which lets the index use a dot product as its similarity
function and skip a per-query normalisation.

Embedding calls are batched at ninety-six inputs per request and retried with exponential backoff
on 429 and 5xx responses, with a jittered base delay of eight hundred milliseconds and a cap of
five attempts. Every embedding is cached on content hash, so re-indexing a document whose text
has not changed costs nothing. In practice the cache absorbs about seventy percent of
re-ingestion traffic after a configuration change, because most chunking configuration changes
leave the majority of chunks byte-identical.

The generation model is `gemini-3.5-flash-lite`, selected over larger alternatives because the
quality difference on grounded extraction prompts was within noise while the cost difference was
not. Temperature is fixed at 0.2 for answer generation and 0.0 for any structured output.

## 5. Query-Time Behaviour and Latency Budget

A query is processed in four phases: embed the query, search the vector index, rerank the
candidates, and generate the answer. The platform commits to a 900 millisecond p95 for everything
up to and including rerank, excluding generation, which is streamed and therefore measured
separately.

That budget is allocated as follows. Query embedding is allotted 120 milliseconds. Vector search
over the HNSW index is allotted 180 milliseconds at `ef_search` equal to one hundred and
twenty-eight. Reranking is allotted 450 milliseconds and is the single largest line item.
Metadata filtering and response assembly take the remaining 150 milliseconds.

If reranking exceeds its 450 millisecond allocation the request does not fail. The reranker runs
behind a hard deadline, and on timeout the platform falls back to returning the raw vector-search
ordering, sets the `rerank_degraded` flag on the response, and increments a counter that pages
the on-call engineer once the five-minute rate crosses two percent of traffic. Answer quality
under degradation is noticeably worse on multi-hop questions and almost unchanged on single-fact
lookups, which is the expected shape: reranking mostly buys you precision in the middle of the
candidate list.

Retrieval returns the top five chunks by default. Applications may request up to twenty, but the
generation prompt template truncates context at eight thousand characters, so requesting twenty
large chunks silently discards the tail of the list.

## 6. Index Sizing and Memory Footprint

Index memory is dominated by the vectors themselves. At three thousand and seventy-two dimensions
in float32, a single vector occupies twelve thousand two hundred and eighty-eight bytes, or
roughly twelve kilobytes. The HNSW graph adds approximately fifteen percent on top of that for
its edge lists at the default connectivity of thirty-two.

The practical consequence is that chunk count, not corpus size, drives your memory bill. Halving
`chunk_size` roughly doubles chunk count and therefore roughly doubles index memory for exactly
the same source text. A one-million-chunk index needs about fourteen gigabytes of resident
memory before replication. This is the main reason the platform refuses to accept a chunk size
below two hundred characters without an explicit override: the memory cost grows without bound
while retrieval quality plateaus and then declines.

Scalar quantisation to int8 is available and cuts vector memory by a factor of four at a measured
recall@5 cost of about one and a half percent. It is enabled by default for corpora above five
million chunks and disabled below that, where the memory saving does not justify the recall
penalty.

## 7. Troubleshooting Guide

### 7.1 The three failure modes of hybrid retrieval

Hybrid retrieval blends dense vector scores with sparse BM25 scores using reciprocal rank fusion.
It fails in exactly three ways in production, and distinguishing them is the first diagnostic
step whenever hybrid search underperforms pure dense search.

The first failure mode is score-scale mismatch. Dense cosine scores occupy a narrow band, often
0.6 to 0.9 for plausible candidates, while BM25 scores are unbounded and corpus-dependent. If
fusion is implemented by weighted sum of raw scores rather than by rank, a single document with
an extreme BM25 score dominates the fused ranking and the dense signal is effectively discarded.
The symptom is hybrid results that look like pure keyword results.

The second failure mode is vocabulary collapse on short chunks. BM25 needs enough tokens per
document to estimate term saturation sensibly. Below roughly thirty tokens per chunk, inverse
document frequency starts rewarding rare-but-irrelevant tokens, and the sparse arm begins
surfacing chunks that share an unusual word with the query and nothing else. The symptom is
irrelevant chunks that contain exactly one striking word from the query.

The third failure mode is duplicate amplification. When overlap is high, the same sentence exists
in several chunks. Both retrieval arms rank all copies highly, fusion rewards the agreement, and
the top-k window fills with near-identical text. The symptom is a top-five list in which three or
four entries are variations of the same passage, and the user's question is answerable only from
material that got pushed to rank six.

### 7.2 Diagnosing poor retrieval generally

When retrieval quality is poor, check in this order. First confirm the chunk actually containing
the answer exists and is embedded, by searching the index for an exact substring of it; an answer
that was never indexed cannot be retrieved, and roughly a third of reported retrieval bugs are
ingestion bugs. Second, embed the question and the known-good chunk and compute their cosine
similarity directly; if it is below 0.5 the problem is a vocabulary mismatch between how users
ask and how the document is written, and the fix is query rewriting, not chunking. Third, check
whether the known-good chunk is being retrieved but ranked outside top-k, which is a reranking
problem. Only after all three come back clean should you change the chunking configuration.

### 7.3 Common operational errors

A sudden jump in chunk count after a deploy almost always means the separator list was
misconfigured and the recursive splitter fell through to character-level splitting. Compare the
chunk-count-per-document histogram against the previous deploy before investigating anything
else.

Queries that return nothing at all, rather than returning bad results, point at the metadata
filter rather than the vector search. The filter is applied pre-search, so an over-restrictive
filter on tenant or document date produces an empty candidate set that looks identical to an
embedding failure in the logs.

## 8. Evaluation Methodology

Every configuration change is evaluated against a frozen question set of two hundred and forty
labelled questions, forty per corpus class per difficulty tier. Each question carries the
identifier of the source span that answers it, not merely the chunk, so the label survives a
change in chunking configuration. This is the single most important property of the evaluation
harness: labelling at the span level rather than the chunk level is what makes two chunking
strategies comparable at all.

Three metrics are tracked. Recall at five measures whether the labelled span appears inside any
of the top five retrieved chunks. Context precision measures what fraction of the retrieved
characters belong to the labelled span, and it is the metric that punishes oversized chunks.
Answer faithfulness is judged by a model-graded rubric against the labelled span and catches the
case where retrieval looked fine but the generator hallucinated anyway.

A configuration ships only if recall at five does not regress and context precision improves, or
if recall improves by more than two points while precision regresses by less than one. Shipping
on a recall improvement alone has twice produced a measurable rise in hallucination rate, because
longer chunks raise recall while diluting the signal the generator actually conditions on.
