# Checkpoint syntax boundary — 2026-10-25

This is a read-only capability review, not a verifier fix, mathematical-equivalence proof, GPU run, or model acceptance result. No production source, test, manifest, or acceptance threshold changed. The current full-regression freeze remains intact.

## Finding

The current context accurately states that candidate source must remain within a reviewed complete normalized program AST, but does not enumerate the checkpoint recognizer's narrow syntax. The implementation can reject legitimate PyTorch API spellings before runtime equivalence is established. Such rejection means **unsupported by this verifier**, not mathematically incorrect.

The recognizer currently requires an unaliased, top-level direct import or fully qualified module import; the reviewed original callable/input expressions as two positional arguments; explicit non-reentrant execution; and at most the optional RNG-preservation argument set to true. Keyword order is immaterial. After normalization, the entire program must still match a reviewed digest. Import aliases, combined imports, extra explicit default keywords, unrelated rewrites, and arbitrary programs are outside this supported subset. Source support alone does not establish input, initialization, precision, update-completeness, cleanup, or numerical equivalence.

## Observed in-memory AST matrix

The review read the existing baseline source, constructed variants only in memory, and invoked the production memory-edit and checkpoint normalizers. It compared the resulting complete AST digest with the reviewed contract. It did not create candidate files, execute the training program, invoke a provider, or launch GPU work. The table gives all 13 observed results; it is a syntax-acceptance check, not a runtime test.

| In-memory variant | Full normalized contract matches | Checkpoint normalization applied |
| --- | --- | --- |
| Original program | Yes | No |
| Direct import, explicit non-reentrant call | Yes | Yes |
| Direct import with explicit RNG preservation | Yes | Yes |
| Fully qualified module call | Yes | Yes |
| Same accepted keywords in reversed order | Yes | Yes |
| Direct function import with alias | No | No |
| Module import with alias | No | No |
| Module obtained through a from-import | No | No |
| Combined from-import including another checkpoint utility | No | No |
| Explicit default debug keyword | No | No |
| Explicit default determinism-check keyword | No | No |
| RNG preservation disabled | No | No |
| Reentrant execution | No | No |

The negative rows have different meanings. Aliases and explicitly supplied default keywords can be legitimate API usage; their absence from normalization is a verifier limitation. Reentrant execution or disabling RNG preservation changes the requested behavior and must not be treated as automatically equivalent. No negative row was converted into a passing proof.

## Official source and interpretation

The [PyTorch 2.5 checkpoint documentation](https://docs.pytorch.org/docs/2.5/checkpoint.html) documents non-reentrant checkpointing and the defaults for the debug and determinism-check parameters. The [PyTorch v2.5.1 implementation](https://github.com/pytorch/pytorch/blob/v2.5.1/torch/utils/checkpoint.py) is the version-pinned primary implementation reference. These sources establish the public API boundary; they do not certify equivalence of an arbitrary edited training program.

The local recognizer rejects explicit default debug and determinism-check arguments because its accepted keyword set is narrower than the official API. This is a concrete syntax limitation rather than evidence that those default arguments alter the training objective. The current capability context's complete-AST warning is therefore accurate but insufficiently specific to distinguish every unsupported spelling.

## Follow-up recommendation

If a subsequent real candidate fails for this boundary, first report the exact unsupported construct and its candidate-local AST location using a generic reason, such as unsupported import binding, unreviewed extra keyword, or normalized program outside the reviewed contract. A concise capability description can disclose permitted import and argument categories without supplying a benchmark-specific repair, source anchor, successful candidate, or resource target.

Any broader alias/default-argument normalization should be an independently reviewed extension with positive and negative binding tests. Do not loosen the current gate simply because an API form is legal. No extra retry or live run is authorized by this report, and no outcome should be predicted before the actual candidate exists.

## Inspected source hashes

| File | SHA-256 |
| --- | --- |
| `headroom/verify/pairing.py` | `0c1418371a14142ff1f8c1ea120cf5f2d62a64fdd5cffa33b19540b336e38ded` |
| `headroom/verify/reference_context.py` | `a76c64fe3f424397429a59f14e24e2f8ec179933a6a2d0fbd2d93323991303ca` |
| `headroom/verify/checkpoint.py` | `29991e96dc706fb176ef4c1a067c3cb9d53d0dac0740d0d3351cbc9ca9e14583` |

Verification scope: 13 pure in-memory AST variants; zero candidate-file writes, zero model calls, and zero GPU runs. Writing this report is the only filesystem mutation from this reporting step. No scenario success code or fixed benchmark source anchor is included for model consumption.
