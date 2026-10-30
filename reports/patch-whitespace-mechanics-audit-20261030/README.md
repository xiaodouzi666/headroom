# Patch source whitespace and embedded literal audit

No mechanical whitespace stripping or schema-shape conflict was found. The live source-span codec keeps every supplied source string unchanged, uses original simultaneous line coordinates, and verifies actual candidate bytes. Its Pydantic classes do not use the unrelated Nonempty whitespace-stripping alias.

Actual saved R17 Super call 4 has identical system and native JSON Schema. The existing repair request already contains candidate-only SyntaxError line/column/excerpts and the previous proposal. The prompts explicitly require retained quotes and separate original IDs from candidate coordinates; no instruction to remove outer/literal quotes exists.

Ten bounded offline static tests passed in 1.18s, using real Git application only on synthetic temporary source. The concrete counterexample is valid JSON carrying a new_lines string like parser.add_argument(--window, ..., help=Window size): Pydantic and normalization preserve that malformed Python exactly, and the unchanged source-syntax gate rejects it. Single or double Python literal quotes survive transport and application.

The smallest general follow-up is one explicit JSON-transport versus Python-literal quoting example, plus bounded feedback mapping a candidate SyntaxError to the previous edit original source span/hash and nearby original text. Candidate error excerpts already exist, so another generic request to preserve quotes alone duplicates current guidance. No host auto-repair, source changes, extra calls, different limits, GPU execution, or acceptance changes were made by this audit.
