# Parameter update policy — read-only audit

The existing registered-parameter-count gate does not detect freezing or removing optimizer parameters. Real R14 s7 retained **1,075,970,304** registered elements on both sides, while measured optimizer/trainable catalog and every logical update narrowed from **34 parameters / 1,075,970,304 elements** to **2 parameters / 2,097,408 elements**. The loss gate already rejected the candidate (max delta 3.3520333766937256); this is no claim of a passed repair.

Current source-bound optimizer observations can supply an explicit coverage-change finding. Group observations by actual logical backward update and compare unions of unique parameters, so a valid AdamWInBackward implementation with 34 native children is not rejected merely for having more optimizer objects/calls. Do not compare p00001 tokens across processes. Flags are first observations, and parameters absent from an optimizer are not automatically proven frozen. Zero-step OOM construction metadata does not prove full baseline update coverage.

Suggested next step after R15 is a separately reviewed semantic-policy observation and planner feedback for known reductions under strict no-model-change policy. Keep incomplete coverage unknown and preserve every existing numerical/reference/input gate. Stable exact set matching would need new parameter-name identity capture; current aggregates are a necessary diagnostic, not a complete semantic proof.

No source, tests, policy, required checks, historical results or live R15 files were changed. No model/GPU/test execution occurred. Paths, immutable hashes, exact captured fields and bounded recommendations are in audit.json.
