# Report-script publication formatting

Seven report scripts were formatted and lint-cleaned without re-execution. Their
original already-executed bytes were saved first under the private cache paths in
publication-formatting.json. Five originals also have exact adjacent
.py.executed.txt copies. Two test-script originals contain deliberate synthetic
secret-like markers and are held privately for root scanning before public copy.

The current .py hashes describe the publication formatting conversion. Existing
report receipts keep their original hashes and paths. The new crosswalk maps each
original hash to preserved executed bytes; the old paths now contain the formatted
publication copies and are not claimed to retain those original hashes.
All13 pre-existing result/receipt JSON files under the owned report directories
were checked byte-for-byte unchanged. No output JSON,fixture,raw run,production
source,model/GPU call or budget was changed,and no commit was made.

Changes are safe import/UTC/regex-alias cleanup,dict.items/static startswith/empty
tuple equivalents,and formatting. S102 is justified only at the two fixed local
AST-execution statements used by the offline draft tests; no global lint/security
rule was disabled. Ruff check and format check pass for all seven scripts. Python
parse/compile passes without running them or replacing their recorded results.
