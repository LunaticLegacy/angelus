# MNavRAG: Explicit Hierarchical Navigation over Editable Markdown Knowledge Bases for Retrieval-Augmented Generation

> **Status:** Pre-experiment arXiv draft. Performance claims, dataset sizes,
> and statistical conclusions are intentionally omitted until experiments run.
>
> **Authors:** [Author name(s) withheld for anonymous drafting]

## Abstract

Retrieval-augmented generation (RAG) usually retrieves chunks from a flat
index. That abstraction is effective for large, mostly static corpora, but it
does not expose the navigational structure of editable knowledge bases such as
repositories, technical runbooks, and hierarchically maintained Markdown
documentation. We introduce **MNavRAG**, a retrieval framework in which an LLM
resolves a request by navigating explicit Markdown index pages and leaf
documents. At each step, the model issues a structured navigation action,
receives a bounded document view, and records an auditable route. A versioned
route cache maps normalized query intents to validated leaf paths; cache
entries are accepted only when every path component and document revision still
exists. This separates a cache hit from a model's unsupported claim that a
route is known.

MNavRAG is designed for knowledge bases that are frequently edited by humans
or agents. It combines hierarchy-aware route planning, cache validation,
budget-aware document reads, and evidence-grounded answer generation. We
propose an evaluation spanning single-document, multi-hop, and post-update
retrieval tasks, comparing MNavRAG with flat sparse/dense/hybrid RAG,
unconstrained file-browsing agents, and long-context prompting. Primary
measures are answer correctness, evidence recall, route validity, input-token
cost, tool calls, latency, and update robustness. The central hypothesis is
that explicit navigational structure can reduce retrieval cost and improve
traceability without sacrificing answer quality on editable, structured
corpora.

## 1. Introduction

LLMs need access to information beyond parametric knowledge. Two common
approaches are to provide a large context window or retrieve a smaller evidence
set. Long-context models can be capable but costly; RAG can reduce cost through
selective access. Most RAG systems, however, return a flat ranked list of
chunks.

Practical knowledge bases are often hierarchical. Software repositories,
internal handbooks, scientific project notes, and operations manuals use root
indexes, domain indexes, and leaf documents. This structure is useful to people
and agents, but flat RAG commonly discards it or treats it only as metadata.

We ask: **can an LLM use explicit, editable document hierarchy as a first-class
retrieval policy?** The method must not merely ask a model to remember a route.
It must expose navigation actions, verify cached routes against the active
corpus revision, and retain an audit trail of the index and evidence documents
that were read.

This paper does not claim Markdown itself as a new storage format. Its proposed
contribution is enforceable hierarchical navigation under a retrieval budget.

## 2. Problem Formulation

Let a knowledge base be a rooted tree \(G=(V,E,r)\). Each node is a versioned
Markdown document. Internal nodes are **index pages** containing child links;
leaves contain evidence. For query \(q\), an LLM selects actions from:

\[
\mathcal{A}=\{\texttt{lookup},\ \texttt{read\_index},\ \texttt{read\_leaf},\ \texttt{answer}\}.
\]

`lookup` returns a cached route only if every path component resolves and its
stored revisions remain valid. `read_index` and `read_leaf` return bounded
views. The final output contains answer \(a\), evidence set \(S\), and route
\(\pi\). We optimize:

\[
\max_{\pi,S,a} Q(a)+\lambda E(S)-\alpha C(\pi,S),
\]

where \(Q\) is answer quality, \(E\) is evidence support, and \(C\) combines
input tokens, reads, latency, and cache misses. A correct answer with an
invalid route is not a successful retrieval outcome.

## 3. MNavRAG

### 3.1 Hierarchical Markdown contract

Every directory contains an `INDEX.md`. Each entry includes a stable ID,
display name, child path, short description, and optional tags. Leaf documents
include a stable document ID, revision hash, and source references. The indexer
validates links; dangling links cannot become cache destinations.

### 3.2 Structured navigation actions

The method replaces retrieval-by-unrestricted-shell with typed actions:

```json
{"action":"lookup", "intent":"vanilla character profile"}
{"action":"read_index", "path":"nekopara/INDEX.md"}
{"action":"read_leaf", "path":"nekopara/vanilla.md", "sections":["basic_profile", "relationships"]}
```

The executor checks path scope, document type, revision, and token budget. It
emits an immutable trace with action, path, bytes/tokens returned, cache state,
and timestamp. The model may choose actions but cannot fabricate a cache hit in
the recorded trace.

### 3.3 Versioned route cache

The cache maps normalized intent to route, revision hashes, last validation,
and usage statistics:

\[
K:\text{intent}\mapsto(\pi,h,t,c).
\]

On a hit, the executor validates every link and hash. On an invalidated entry,
the agent starts at the root or an allowed ancestor and may write a new entry
only after reading evidence. This is fundamentally different from a prose table
in which a model merely announces “HIT.”

### 3.4 Context budgeting and faithful answers

MNavRAG concerns *which* evidence to retrieve. Context engineering controls
*how* selected evidence and conversation history fit into a model request.
Compaction thresholds, section limits, and tool-output truncation are controlled
variables rather than the primary retrieval contribution. Answers must cite
document IDs and sections returned by `read_leaf`; unsupported citations are
rejected or marked as insufficient evidence.

## 4. Research Questions

1. Does explicit hierarchy reduce input tokens, document reads, or latency
   while preserving answer correctness against flat RAG and file browsing?
2. Does validated route caching improve repeated-query performance without
   increasing stale-evidence errors after edits?
3. Does hierarchy improve evidence recall on multi-hop questions?
4. Can route validity and provenance expose retrieval failures hidden by
   answer-only evaluation?
5. Are findings stable across models, domains, corpus sizes, and budgets?

## 5. Proposed Contributions

The paper will claim the following only after validation:

1. A formal model of editable hierarchical Markdown retrieval with explicit
   route validity.
2. A machine-enforced, versioned route cache with validated hits, misses, and
   stale-entry invalidation.
3. A benchmark protocol for single-hop, multi-hop, and post-update tasks in
   structured document trees.
4. Trace-based evaluation of answer quality, evidence, route correctness, and
   cost.
5. An open-source reference implementation, data manifests, and traces where
   licenses permit release.

## 6. Experimental Design

### 6.1 Corpora and tasks

Use at least three public, license-compatible corpus types: open-source
software documentation, versioned technical manuals, and a public
multi-document QA corpus converted into a documented tree. The current
anime-character tree is a qualitative demo only: it is too small and its facts
are insufficiently verified for central evaluation.

For each corpus, annotate query, answer, evidence leaves, and permitted route.
Test five settings: single-hop retrieval, hierarchy disambiguation, multi-hop
retrieval, post-update retrieval after move/delete/supersede edits, and negative
retrieval requiring justified abstention.

### 6.2 Baselines

| System | Purpose |
|---|---|
| Long-context prompting | Direct corpus context or an equal-budget slice |
| BM25 RAG | Sparse flat retrieval |
| Dense RAG | Embedding-based flat retrieval |
| Hybrid RAG + reranker | Strong flat-RAG baseline |
| Unconstrained browsing Agent | Separates hierarchy policy from generic tool access |
| MNavRAG without cache | Isolates hierarchy-aware navigation |
| MNavRAG without revision checks | Measures stale-cache harm |
| Full MNavRAG | Proposed method |

All systems receive identical document text, backbone-model family, generation
budget, and published prompts. Use multiple seeds where supported.

### 6.3 Metrics and ablations

| Category | Metrics |
|---|---|
| Answer | exact match, F1, task score, human correctness sample |
| Retrieval | evidence Recall@k / Precision@k, route validity |
| Faithfulness | citation precision, unsupported-claim rate |
| Cost | input/output tokens, reads, tool calls, latency |
| Cache | hit, validated-hit, stale-hit, invalidation recovery rates |
| Robustness | post-update accuracy and abstention accuracy |

Run ablations removing root summaries, cache lookup, revision checks, or typed
actions; force exhaustive traversal; vary leaf budgets and context-compaction
thresholds; and compare multiple model families.

## 7. Expected Findings and Falsifiability

MNavRAG should help when hierarchy is meaningful, queries repeat or cluster,
and documents change often enough that stale routes matter. It may lose to
hybrid RAG for shallow homogeneous corpora, and to long-context prompting when
all relevant material fits cheaply in context.

The method should be considered unsuccessful if it cannot match flat hybrid RAG
on answer/evidence quality while materially improving cost, route auditability,
or update robustness. This criterion is stated before experiments to prevent
post-hoc reinterpretation.

## 8. Related Work

RAG and long-context prompting have documented quality-cost trade-offs.
Hierarchical knowledge and chunking have also been studied. MNavRAG differs by
treating human-maintained index pages as executable navigation objects,
requiring every route decision to be traceable, and validating cache entries at
execution time. Repository-level code graphs provide a related precedent for
structure-aware context selection, but MNavRAG targets any versioned Markdown
knowledge tree rather than source code alone.

## 9. Limitations and Responsible Use

- Directory hierarchy can encode maintainer bias or omit important cross-links.
- Extra planning actions may be wasteful for simple one-shot factual queries.
- Route-cache keys can leak query intent and require access control.
- Provenance and licensing must be preserved; LLM-generated documentation is
  not ground truth without verification.
- Evaluation must separate fluent answers from evidence-supported answers.

## 10. Reproducibility Checklist

- [ ] Release corpus manifests, document revisions, and licenses.
- [ ] Release query/evidence annotations and data-split scripts.
- [ ] Release action, cache, and trace schemas plus prompts and configuration.
- [ ] Record model/provider/version, decoding parameters, seeds, and budgets.
- [ ] Release exact baseline implementations and dependency lockfiles.
- [ ] Pre-register primary metrics and report failures and cost outliers.

## References

Saad-Falcon, J., Khattab, O., Potts, C., & Zaharia, M. (2024). *ARES: An
Automated Evaluation Framework for Retrieval-Augmented Generation Systems*.
NAACL 2024.

Li, Z., Li, C., Zhang, M., Mei, Q., & Bendersky, M. (2024). *Retrieval
Augmented Generation or Long-Context LLMs? A Comprehensive Study and Hybrid
Approach*. arXiv:2407.16833.

Qi, Z., Xu, R., Guo, Z., Wang, C., Zhang, H., & Xu, W. (2024). *Long²RAG:
Evaluating Long-Context & Long-Form Retrieval-Augmented Generation with Key
Point Recall*. arXiv:2410.23000.

Ouyang, S., et al. (2024). *RepoGraph: Enhancing AI Software Engineering with
Repository-level Code Graph*. arXiv:2410.14684.

Rau, D., et al. (2024). *BERGEN: A Benchmarking Library for
Retrieval-Augmented Generation*. Findings of EMNLP 2024.

Zou, J., et al. (2026). *RAG over Tables: Hierarchical Memory Index,
Multi-Stage Retrieval, and Benchmarking*. Findings of ACL 2026.

Lu, W., Chen, K., Shen, Z., Qiao, R., & Sun, X. (2026). *HiChunk: Evaluating
and Enhancing Retrieval Augmented Generation with Hierarchical Chunking*. ACL
2026.
