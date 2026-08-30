"""Deterministic research-paper compiler for WikiLLM source Markdown.

Every prose sentence in the output is a verbatim span of the source PDF, and
`paper_digest.grounding` re-checks that after compilation. No generative,
embedding, reranking or vision-language model is loaded or called.
"""

__version__ = "2.3.0"
