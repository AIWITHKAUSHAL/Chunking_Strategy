# Experiment Results and Observations

Generated 2026-10-02T14:32:03 in **live** mode.

- Source document: `vector_search_handbook.md` -- 16,037 chars, 2,450 words, 118 sentences, 55 paragraphs, 17 headings
- Embedding model: `gemini-embedding-001`
- Generation model: `gemini-3.5-flash-lite`
- Retrieval depth: top_k = 3
- Configurations: 20 (4 strategies x 5 size/overlap pairs)
- Questions: 5, carrying 14 span-level gold labels

> The document, the embedding model, the generation model, the vector index and the question set are **identical across every row below**. The only independent variable is how the document was cut into chunks.


## Leaderboard

Ranked by mean gold-span coverage, then recall, then precision.

| # | config | span coverage | recall | context precision | chunks |
| --- | --- | --- | --- | --- | --- |
| 1 | semantic_800_0 | 100.0% | 100.0% | 0.0791 | 30 |
| 2 | semantic_800_160 | 100.0% | 100.0% | 0.0729 | 32 |
| 3 | fixed_800_160 | 100.0% | 100.0% | 0.0650 | 25 |
| 4 | semantic_1200_300 | 100.0% | 100.0% | 0.0529 | 24 |
| 5 | recursive_1200_300 | 100.0% | 100.0% | 0.0527 | 19 |
| 6 | fixed_1200_300 | 100.0% | 100.0% | 0.0434 | 18 |
| 7 | recursive_800_0 | 93.3% | 100.0% | 0.0772 | 27 |
| 8 | recursive_800_160 | 93.3% | 100.0% | 0.0748 | 27 |
| 9 | recursive_800_400 | 93.3% | 100.0% | 0.0737 | 31 |
| 10 | semantic_800_400 | 93.3% | 100.0% | 0.0681 | 45 |
| 11 | fixed_800_400 | 93.3% | 100.0% | 0.0598 | 40 |
| 12 | fixed_800_0 | 90.0% | 100.0% | 0.0571 | 21 |
| 13 | fixed_400_40 | 80.0% | 100.0% | 0.1041 | 45 |
| 14 | sentence_1200_300 | 80.0% | 80.0% | 0.1119 | 55 |
| 15 | semantic_400_40 | 73.3% | 100.0% | 0.1115 | 77 |
| 16 | sentence_800_160 | 73.3% | 80.0% | 0.1060 | 56 |
| 17 | sentence_800_0 | 73.3% | 80.0% | 0.1060 | 56 |
| 18 | sentence_800_400 | 73.3% | 80.0% | 0.1060 | 56 |
| 19 | sentence_400_40 | 60.0% | 80.0% | 0.1192 | 76 |
| 20 | recursive_400_40 | 60.0% | 80.0% | 0.0933 | 62 |

## Chunk geometry

| strategy | size | overlap | chunks | mean chars | min-max | stdev | mid-word cuts | broken boundaries | redundancy |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| fixed | 400 | 40 (10.0%) | 45 | 395.2 | 196-400 | 30.0 | 35 | 100.0% | 1.109 |
| fixed | 800 | 160 (20.0%) | 25 | 794.7 | 675-800 | 24.4 | 19 | 100.0% | 1.239 |
| fixed | 1200 | 300 (25.0%) | 18 | 1174.1 | 736-1200 | 106.2 | 12 | 94.4% | 1.318 |
| fixed | 800 | 0 (0.0%) | 21 | 763.4 | 36-800 | 162.6 | 15 | 100.0% | 1.0 |
| fixed | 800 | 400 (50.0%) | 40 | 790.7 | 436-800 | 56.8 | 30 | 100.0% | 1.972 |
| recursive | 400 | 40 (10.0%) | 62 | 258.1 | 21-389 | 131.6 | 0 | 0.0% | 0.998 |
| recursive | 800 | 160 (20.0%) | 27 | 605.1 | 158-797 | 148.1 | 0 | 0.0% | 1.019 |
| recursive | 1200 | 300 (25.0%) | 19 | 937.7 | 599-1157 | 151.4 | 0 | 0.0% | 1.111 |
| recursive | 800 | 0 (0.0%) | 27 | 592.0 | 63-797 | 156.6 | 0 | 0.0% | 0.997 |
| recursive | 800 | 400 (50.0%) | 31 | 625.1 | 381-797 | 116.2 | 0 | 0.0% | 1.208 |
| sentence | 400 | 40 (10.0%) | 76 | 239.1 | 23-398 | 119.7 | 1 | 1.3% | 1.133 |
| sentence | 800 | 160 (20.0%) | 56 | 287.2 | 23-760 | 201.8 | 0 | 0.0% | 1.003 |
| sentence | 1200 | 300 (25.0%) | 55 | 289.6 | 23-820 | 209.0 | 0 | 0.0% | 0.993 |
| sentence | 800 | 0 (0.0%) | 56 | 284.4 | 23-760 | 202.9 | 0 | 0.0% | 0.993 |
| sentence | 800 | 400 (50.0%) | 56 | 291.5 | 23-760 | 204.3 | 0 | 0.0% | 1.018 |
| semantic | 400 | 40 (10.0%) | 77 | 320.8 | 65-399 | 61.7 | 1 | 2.6% | 1.54 |
| semantic | 800 | 160 (20.0%) | 32 | 641.8 | 200-796 | 161.0 | 1 | 6.2% | 1.281 |
| semantic | 1200 | 300 (25.0%) | 24 | 884.1 | 200-1195 | 293.7 | 1 | 4.2% | 1.323 |
| semantic | 800 | 0 (0.0%) | 30 | 532.3 | 36-797 | 231.9 | 0 | 0.0% | 0.996 |
| semantic | 800 | 400 (50.0%) | 45 | 682.8 | 374-796 | 84.0 | 0 | 2.2% | 1.916 |

## Structural metrics (chunking only -- no embedding model involved)

`span integrity` is the share of gold answer spans that survive chunking inside a single chunk. `chunks needed` is how many chunks must be retrieved to cover all of a question's gold spans; anything above top_k=3 cannot be answered completely no matter how good the embedder is.

| config | span integrity | Q1 chunks needed | Q2 chunks needed | Q3 chunks needed | Q4 chunks needed | Q5 chunks needed |
| --- | --- | --- | --- | --- | --- | --- |
| fixed_400_40 | 92.9% | 2 | 3 | 2 | 2 | severed |
| fixed_800_160 | 100.0% | 2 | 2 | 2 | 2 | 2 |
| fixed_1200_300 | 100.0% | 2 | 2 | 1 | 1 | 2 |
| fixed_800_0 | 92.9% | severed | 3 | 2 | 2 | 2 |
| fixed_800_400 | 100.0% | 1 | 3 | 2 | 2 | 3 |
| recursive_400_40 | 100.0% | 1 | 3 | 2 | 2 | 3 |
| recursive_800_160 | 100.0% | 1 | 3 | 1 | 2 | 3 |
| recursive_1200_300 | 100.0% | 1 | 2 | 1 | 2 | 2 |
| recursive_800_0 | 100.0% | 1 | 3 | 1 | 2 | 3 |
| recursive_800_400 | 100.0% | 1 | 3 | 1 | 2 | 3 |
| sentence_400_40 | 100.0% | 1 | 3 | 3 | 2 | 3 |
| sentence_800_160 | 100.0% | 1 | 3 | 2 | 2 | 3 |
| sentence_1200_300 | 100.0% | 1 | 3 | 1 | 2 | 3 |
| sentence_800_0 | 100.0% | 1 | 3 | 2 | 2 | 3 |
| sentence_800_400 | 100.0% | 1 | 3 | 2 | 2 | 3 |
| semantic_400_40 | 100.0% | 2 | 3 | 3 | 2 | 3 |
| semantic_800_160 | 100.0% | 2 | 3 | 2 | 1 | 2 |
| semantic_1200_300 | 100.0% | 1 | 2 | 2 | 1 | 2 |
| semantic_800_0 | 100.0% | 2 | 2 | 2 | 1 | 3 |
| semantic_800_400 | 100.0% | 2 | 2 | 2 | 2 | 3 |

## Retrieval metrics at top_k=3

Embedding model `gemini-embedding-001`, generation model `gemini-3.5-flash-lite`, identical for every row. Only the chunking changes.

| config | chunks | recall | span coverage | context precision | time |
| --- | --- | --- | --- | --- | --- |
| fixed_400_40 | 45 | 100.0% | 80.0% | 0.1041 | 17.42s |
| fixed_800_160 | 25 | 100.0% | 100.0% | 0.0650 | 14.17s |
| fixed_1200_300 | 18 | 100.0% | 100.0% | 0.0434 | 10.02s |
| fixed_800_0 | 21 | 100.0% | 90.0% | 0.0571 | 9.83s |
| fixed_800_400 | 40 | 100.0% | 93.3% | 0.0598 | 9.22s |
| recursive_400_40 | 62 | 80.0% | 60.0% | 0.0933 | 10.75s |
| recursive_800_160 | 27 | 100.0% | 93.3% | 0.0748 | 9.39s |
| recursive_1200_300 | 19 | 100.0% | 100.0% | 0.0527 | 8.43s |
| recursive_800_0 | 27 | 100.0% | 93.3% | 0.0772 | 8.15s |
| recursive_800_400 | 31 | 100.0% | 93.3% | 0.0737 | 7.42s |
| sentence_400_40 | 76 | 80.0% | 60.0% | 0.1192 | 9.93s |
| sentence_800_160 | 56 | 80.0% | 73.3% | 0.1060 | 8.91s |
| sentence_1200_300 | 55 | 80.0% | 80.0% | 0.1119 | 6.38s |
| sentence_800_0 | 56 | 80.0% | 73.3% | 0.1060 | 7.93s |
| sentence_800_400 | 56 | 80.0% | 73.3% | 0.1060 | 7.11s |
| semantic_400_40 | 77 | 100.0% | 73.3% | 0.1115 | 14.38s |
| semantic_800_160 | 32 | 100.0% | 100.0% | 0.0729 | 8.66s |
| semantic_1200_300 | 24 | 100.0% | 100.0% | 0.0529 | 8.05s |
| semantic_800_0 | 30 | 100.0% | 100.0% | 0.0791 | 8.11s |
| semantic_800_400 | 45 | 100.0% | 93.3% | 0.0681 | 9.24s |

## Which chunks each strategy retrieved

### Q1. What chunk size and chunk overlap does the handbook recommend for technical manuals, and why is the overlap set that high?

*Designed to probe:* The parameter values and the reason for them sit in neighbouring sentences. A strategy that cuts between them returns the number without the justification.

*Gold spans (2):*

1. `chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters`

2. `a step separated from its precondition retrieves as a confidently wrong answer`

| config | retrieved chunk ids (score) | spans found | precision | hit |
| --- | --- | --- | --- | --- |
| fixed_400_40 | #17(0.835), #18(0.800), #20(0.776) | 2/2 | 0.1446 | yes |
| fixed_800_160 | #10(0.818), #9(0.788), #11(0.750) | 2/2 | 0.0723 | yes |
| fixed_1200_300 | #7(0.834), #6(0.778), #3(0.730) | 2/2 | 0.0482 | yes |
| fixed_800_0 | #8(0.818), #7(0.757), #9(0.726) | 1/2 | 0.0326 | yes |
| fixed_800_400 | #15(0.828), #17(0.824), #16(0.818) | 2/2 | 0.0723 | yes |
| recursive_400_40 | #27(0.848), #26(0.815), #30(0.781) | 2/2 | 0.1897 | yes |
| recursive_800_160 | #10(0.856), #11(0.795), #9(0.738) | 2/2 | 0.0864 | yes |
| recursive_1200_300 | #8(0.836), #9(0.801), #7(0.744) | 2/2 | 0.0633 | yes |
| recursive_800_0 | #10(0.822), #11(0.795), #8(0.746) | 2/2 | 0.0974 | yes |
| recursive_800_400 | #12(0.856), #13(0.795), #14(0.786) | 2/2 | 0.0907 | yes |
| sentence_400_40 | #33(0.852), #31(0.850), #37(0.785) | 2/2 | 0.2590 | yes |
| sentence_800_160 | #22(0.850), #24(0.836), #27(0.785) | 2/2 | 0.2201 | yes |
| sentence_1200_300 | #21(0.850), #23(0.836), #26(0.785) | 2/2 | 0.2201 | yes |
| sentence_800_0 | #22(0.850), #24(0.836), #27(0.785) | 2/2 | 0.2201 | yes |
| sentence_800_400 | #22(0.850), #24(0.836), #27(0.785) | 2/2 | 0.2201 | yes |
| semantic_400_40 | #27(0.856), #28(0.852), #32(0.804) | 2/2 | 0.1587 | yes |
| semantic_800_160 | #14(0.836), #13(0.798), #15(0.794) | 2/2 | 0.0762 | yes |
| semantic_1200_300 | #11(0.804), #12(0.796), #7(0.746) | 2/2 | 0.0663 | yes |
| semantic_800_0 | #13(0.808), #12(0.808), #6(0.766) | 2/2 | 0.1024 | yes |
| semantic_800_400 | #18(0.840), #17(0.808), #20(0.805) | 2/2 | 0.0815 | yes |

### Q2. What are the three failure modes of hybrid retrieval described in the handbook?

*Designed to probe:* A three-item enumeration spanning three long paragraphs. Small chunks cannot hold all three, so the answer's completeness depends directly on chunk size.

*Gold spans (3):*

1. `The first failure mode is score-scale mismatch`

2. `The second failure mode is vocabulary collapse on short chunks`

3. `The third failure mode is duplicate amplification`

| config | retrieved chunk ids (score) | spans found | precision | hit |
| --- | --- | --- | --- | --- |
| fixed_400_40 | #32(0.755), #34(0.729), #35(0.725) | 2/3 | 0.0928 | yes |
| fixed_800_160 | #19(0.767), #18(0.752), #20(0.715) | 3/3 | 0.0656 | yes |
| fixed_1200_300 | #13(0.765), #14(0.731), #12(0.684) | 3/3 | 0.0437 | yes |
| fixed_800_0 | #14(0.720), #16(0.715), #15(0.709) | 3/3 | 0.0657 | yes |
| fixed_800_400 | #29(0.777), #31(0.726), #28(0.720) | 2/3 | 0.0397 | yes |
| recursive_400_40 | #45(0.779), #52(0.747), #44(0.735) | 0/3 | 0.0000 | **no** |
| recursive_800_160 | #18(0.725), #21(0.706), #19(0.705) | 2/3 | 0.0614 | yes |
| recursive_1200_300 | #14(0.737), #15(0.723), #16(0.702) | 3/3 | 0.0505 | yes |
| recursive_800_0 | #18(0.725), #21(0.706), #19(0.705) | 2/3 | 0.0614 | yes |
| recursive_800_400 | #23(0.766), #22(0.725), #25(0.706) | 2/3 | 0.0505 | yes |
| sentence_400_40 | #55(0.901), #56(0.768), #63(0.747) | 0/3 | 0.0000 | **no** |
| sentence_800_160 | #42(0.901), #43(0.768), #47(0.747) | 0/3 | 0.0000 | **no** |
| sentence_1200_300 | #41(0.901), #42(0.768), #46(0.747) | 0/3 | 0.0000 | **no** |
| sentence_800_0 | #42(0.901), #43(0.768), #47(0.747) | 0/3 | 0.0000 | **no** |
| sentence_800_400 | #42(0.901), #43(0.768), #47(0.747) | 0/3 | 0.0000 | **no** |
| semantic_400_40 | #56(0.781), #55(0.753), #58(0.732) | 2/3 | 0.1044 | yes |
| semantic_800_160 | #24(0.740), #25(0.709), #26(0.705) | 3/3 | 0.0729 | yes |
| semantic_1200_300 | #20(0.765), #19(0.740), #21(0.699) | 3/3 | 0.0466 | yes |
| semantic_800_0 | #23(0.771), #24(0.727), #26(0.691) | 3/3 | 0.0742 | yes |
| semantic_800_400 | #34(0.771), #35(0.741), #33(0.736) | 3/3 | 0.0709 | yes |

### Q3. How does the ingestion pipeline handle tables found inside PDF files?

*Designed to probe:* A multi-step procedure with its exception at the very end of the paragraph. A mid-paragraph cut drops the exception silently.

*Gold spans (3):*

1. `reconstructs each table into a row-major Markdown table`

2. `segmentation is forbidden from splitting inside it`

3. `Tables wider than forty columns are the single exception`

| config | retrieved chunk ids (score) | spans found | precision | hit |
| --- | --- | --- | --- | --- |
| fixed_400_40 | #5(0.795), #6(0.747), #3(0.706) | 2/3 | 0.0877 | yes |
| fixed_800_160 | #3(0.799), #2(0.774), #4(0.696) | 3/3 | 0.0672 | yes |
| fixed_1200_300 | #2(0.783), #1(0.744), #3(0.708) | 3/3 | 0.0449 | yes |
| fixed_800_0 | #2(0.770), #3(0.724), #1(0.675) | 3/3 | 0.0672 | yes |
| fixed_800_400 | #5(0.795), #4(0.770), #3(0.740) | 3/3 | 0.0672 | yes |
| recursive_400_40 | #8(0.794), #7(0.778), #6(0.716) | 1/3 | 0.0488 | yes |
| recursive_800_160 | #2(0.779), #3(0.773), #1(0.715) | 3/3 | 0.0696 | yes |
| recursive_1200_300 | #2(0.778), #1(0.750), #3(0.646) | 3/3 | 0.0579 | yes |
| recursive_800_0 | #2(0.782), #3(0.773), #1(0.715) | 3/3 | 0.0705 | yes |
| recursive_800_400 | #3(0.782), #4(0.773), #1(0.715) | 3/3 | 0.0705 | yes |
| sentence_400_40 | #10(0.791), #9(0.778), #8(0.716) | 1/3 | 0.0531 | yes |
| sentence_800_160 | #8(0.784), #7(0.778), #6(0.716) | 2/3 | 0.0732 | yes |
| sentence_1200_300 | #8(0.778), #7(0.778), #6(0.716) | 3/3 | 0.1027 | yes |
| sentence_800_0 | #8(0.784), #7(0.778), #6(0.716) | 2/3 | 0.0732 | yes |
| sentence_800_400 | #8(0.784), #7(0.778), #6(0.716) | 2/3 | 0.0732 | yes |
| semantic_400_40 | #8(0.811), #9(0.791), #6(0.719) | 1/3 | 0.0604 | yes |
| semantic_800_160 | #4(0.784), #3(0.762), #5(0.709) | 3/3 | 0.0737 | yes |
| semantic_1200_300 | #3(0.785), #4(0.723), #2(0.721) | 3/3 | 0.0501 | yes |
| semantic_800_0 | #3(0.813), #4(0.709), #2(0.696) | 3/3 | 0.0688 | yes |
| semantic_800_400 | #5(0.813), #4(0.762), #3(0.722) | 2/3 | 0.0471 | yes |

### Q4. How many milliseconds are budgeted for reranking, and what does the platform do when that budget is exceeded?

*Designed to probe:* The allocation is stated in one paragraph and the timeout behaviour in the next. This is the clearest test of whether chunk_overlap is doing its job.

*Gold spans (3):*

1. `Reranking is allotted 450 milliseconds`

2. `falls back to returning the raw vector-search ordering`

3. `rerank_degraded`

| config | retrieved chunk ids (score) | spans found | precision | hit |
| --- | --- | --- | --- | --- |
| fixed_400_40 | #26(0.848), #25(0.805), #27(0.753) | 3/3 | 0.0893 | yes |
| fixed_800_160 | #14(0.837), #15(0.794), #13(0.697) | 3/3 | 0.0447 | yes |
| fixed_1200_300 | #10(0.811), #11(0.725), #9(0.715) | 3/3 | 0.0298 | yes |
| fixed_800_0 | #11(0.807), #12(0.794), #10(0.659) | 3/3 | 0.0447 | yes |
| fixed_800_400 | #23(0.821), #22(0.807), #24(0.794) | 3/3 | 0.0447 | yes |
| recursive_400_40 | #38(0.810), #37(0.802), #36(0.759) | 3/3 | 0.1041 | yes |
| recursive_800_160 | #15(0.802), #14(0.801), #16(0.686) | 3/3 | 0.0560 | yes |
| recursive_1200_300 | #12(0.801), #11(0.737), #13(0.701) | 3/3 | 0.0356 | yes |
| recursive_800_0 | #15(0.802), #14(0.801), #16(0.686) | 3/3 | 0.0560 | yes |
| recursive_800_400 | #19(0.802), #18(0.801), #17(0.711) | 3/3 | 0.0563 | yes |
| sentence_400_40 | #46(0.817), #45(0.805), #44(0.759) | 3/3 | 0.1056 | yes |
| sentence_800_160 | #34(0.805), #35(0.802), #33(0.759) | 3/3 | 0.0866 | yes |
| sentence_1200_300 | #33(0.805), #34(0.802), #32(0.759) | 3/3 | 0.0866 | yes |
| sentence_800_0 | #34(0.805), #35(0.802), #33(0.759) | 3/3 | 0.0866 | yes |
| sentence_800_400 | #34(0.805), #35(0.802), #33(0.759) | 3/3 | 0.0866 | yes |
| semantic_400_40 | #43(0.826), #46(0.817), #44(0.805) | 3/3 | 0.1159 | yes |
| semantic_800_160 | #20(0.846), #19(0.826), #21(0.793) | 3/3 | 0.0636 | yes |
| semantic_1200_300 | #16(0.830), #15(0.826), #17(0.719) | 3/3 | 0.0424 | yes |
| semantic_800_0 | #19(0.848), #17(0.793), #20(0.731) | 3/3 | 0.0680 | yes |
| semantic_800_400 | #27(0.848), #26(0.815), #28(0.802) | 3/3 | 0.0510 | yes |

### Q5. What embedding dimensionality does the platform use, and how does that dimension affect the index memory footprint?

*Designed to probe:* The dimension is in section 4 and its memory consequence is in section 6. No single chunk can contain both, so the top-k list must span two sections.

*Gold spans (3):*

1. `vectors of three thousand and seventy-two dimensions`

2. `a single vector occupies twelve thousand two hundred and eighty-eight bytes`

3. `chunk count, not corpus size, drives your memory bill`

| config | retrieved chunk ids (score) | spans found | precision | hit |
| --- | --- | --- | --- | --- |
| fixed_400_40 | #21(0.784), #22(0.763), #29(0.759) | 2/3 | 0.1061 | yes |
| fixed_800_160 | #12(0.798), #16(0.781), #17(0.746) | 3/3 | 0.0753 | yes |
| fixed_1200_300 | #8(0.768), #11(0.764), #12(0.741) | 3/3 | 0.0502 | yes |
| fixed_800_0 | #13(0.819), #9(0.758), #12(0.729) | 3/3 | 0.0752 | yes |
| fixed_800_400 | #26(0.819), #19(0.792), #25(0.769) | 3/3 | 0.0752 | yes |
| recursive_400_40 | #41(0.806), #32(0.794), #40(0.792) | 2/3 | 0.1240 | yes |
| recursive_800_160 | #12(0.794), #16(0.793), #17(0.770) | 3/3 | 0.1006 | yes |
| recursive_1200_300 | #13(0.806), #10(0.776), #12(0.734) | 3/3 | 0.0565 | yes |
| recursive_800_0 | #12(0.794), #16(0.793), #17(0.770) | 3/3 | 0.1006 | yes |
| recursive_800_400 | #15(0.794), #20(0.793), #21(0.770) | 3/3 | 0.1006 | yes |
| sentence_400_40 | #39(0.777), #50(0.772), #49(0.768) | 2/3 | 0.1784 | yes |
| sentence_800_160 | #29(0.777), #38(0.772), #39(0.770) | 3/3 | 0.1503 | yes |
| sentence_1200_300 | #28(0.777), #37(0.772), #38(0.770) | 3/3 | 0.1503 | yes |
| sentence_800_0 | #29(0.777), #38(0.772), #39(0.770) | 3/3 | 0.1503 | yes |
| sentence_800_400 | #29(0.777), #38(0.772), #39(0.770) | 3/3 | 0.1503 | yes |
| semantic_400_40 | #49(0.806), #48(0.800), #35(0.797) | 2/3 | 0.1179 | yes |
| semantic_800_160 | #16(0.805), #22(0.782), #23(0.775) | 3/3 | 0.0781 | yes |
| semantic_1200_300 | #13(0.796), #17(0.777), #18(0.775) | 3/3 | 0.0592 | yes |
| semantic_800_0 | #15(0.802), #21(0.782), #20(0.775) | 3/3 | 0.0819 | yes |
| semantic_800_400 | #30(0.815), #22(0.802), #21(0.796) | 3/3 | 0.0898 | yes |

## Generated answers for Q1

*What chunk size and chunk overlap does the handbook recommend for technical manuals, and why is the overlap set that high?*

Same question, same generation model, same prompt template. The only difference is which chunks retrieval supplied.

**`fixed_400_40`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and separating a step from its precondition results in a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`fixed_800_160`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters, which is twenty percent. The overlap is set this high specifically because procedures in manuals routinely run across a paragraph boundary, and a step separated from its precondition retrieves as a confidently wrong answer.

**`fixed_1200_300`**

> The handbook recommends a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent) for technical manuals. 

The overlap is set this high because procedures in manuals routinely run across a paragraph boundary, and a step separated from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`fixed_800_0`**

> For technical manuals, the handbook recommends a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters, which is twenty percent. The overlap is set this high because procedures in manuals routinely run across a paragraph boundary, and a step separated from its precondition retrieves as a confidently wrong answer.

**`fixed_800_400`**

> For technical manuals, the recommended chunk size is eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across a paragraph boundary, and a step separated from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`recursive_400_40`**

> Based on the provided context, technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and separating a step from its precondition results in a confidently wrong answer.

**`recursive_800_160`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and separating a step from its precondition results in a retrieved answer that is confidently wrong. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`recursive_1200_300`**

> For technical manuals, the recommended chunk size is eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely cross paragraph boundaries, and separating a step from its precondition leads to a confidently wrong answer. Twenty percent was the smallest overlap that prevented labelled procedure questions from losing their preconditions.

**`recursive_800_0`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions, preventing a step separated from its precondition from retrieving a confidently wrong answer.

**`recursive_800_400`**

> For technical manuals, the recommended chunk size is eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and a step separated from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`sentence_400_40`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and a step separated from its precondition retrieves as a confidently wrong answer.

**`sentence_800_160`**

> For technical manuals, a chunk size of eight hundred characters with an overlap of one hundred and sixty characters (twenty percent) is recommended. The overlap is set this high because procedures routinely run across paragraph boundaries, and separating a step from its precondition results in a confidently wrong answer. Twenty percent was the smallest overlap that prevented labelled procedure questions from losing their preconditions.

**`sentence_1200_300`**

> For technical manuals, a chunk size of eight hundred characters is recommended with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries. A step separated from its precondition can result in a confidently wrong answer. Twenty percent was determined to be the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`sentence_800_0`**

> Based on the provided context, technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures routinely run across paragraph boundaries, and a step separated from its precondition results in a confidently wrong answer. Twenty percent was the smallest overlap where labelled procedure questions stopped losing their preconditions.

**`sentence_800_400`**

> For technical manuals, a chunk size of eight hundred characters is recommended, with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures routinely run across paragraph boundaries, and a step separated from its precondition results in a confidently wrong answer. Twenty percent was the smallest overlap where labelled procedure questions stopped losing their preconditions.

**`semantic_400_40`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). The overlap is set this high specifically because procedures in manuals routinely run across a paragraph boundary, and a step separated from its precondition retrieves as a confidently wrong answer.

**`semantic_800_160`**

> For technical manuals, the handbook recommends a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and a step separated from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`semantic_1200_300`**

> For technical manuals, the recommended chunk size is eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and separating a step from its precondition results in a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

**`semantic_800_0`**

> Technical manuals use a chunk size of eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and a step separated from its precondition retrieves as a confidently wrong answer.

**`semantic_800_400`**

> For technical manuals, the recommended chunk size is eight hundred characters with a chunk overlap of one hundred and sixty characters (twenty percent). 

The overlap is set this high because procedures in manuals routinely run across paragraph boundaries, and a step separated from its precondition retrieves as a confidently wrong answer. Twenty percent was the smallest overlap at which labelled procedure questions stopped losing their preconditions.

