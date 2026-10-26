# Repair applicability records

The opt-in `headroom scope` commands answer a narrow question: **has this exact
repair and workload context been observed to satisfy its checks?** They inspect
saved artifacts without executing the workload or calling a model. A different
input, source tree, precision, device, environment, or policy is a new context.

This is an engineering addition, not a claim of world-first research. See
[the prior-art review](../reports/development-20261027/prior-art.md).
It leaves the original repair acceptance and six-of-nine gates unchanged.

## Build and query

Create a JSON selection file. Paths are relative to the explicitly selected,
trusted archive root; a selection names a recorded round, not a success label.

```json
{
  "selections": [
    {
      "job": "runs/evaluation/live/20261025T121115251021Z-2fe7da84/jobs/b6091354c73d43f88a10e50f01e4d5b2",
      "round": 2
    }
  ]
}
```

From the repository directory on azuki:

```sh
headroom scope build selections.json --evidence-root . --output scope.json
```

The new file contains all observations, including failures, their artifact
hashes, their provenance, and the exact `context` for each observation.
Copy an observation's `context` object to `query.json` to check that point:

```sh
headroom scope check scope.json query.json --evidence-root .
```

Build refuses to overwrite an existing file. Check reopens and verifies the
archive and implementation before consulting any stored verdict. Build returns
0 when the record was created, including records with unknown or failed points;
this is not an acceptance result. Check returns 0 only for `tested_pass`, and
78 for all other states.

| State | Meaning |
|---|---|
| `tested_pass` | Every included observation at this exact context satisfies the stricter empirical checks. |
| `tested_fail` | At least one included observation at this context records a concrete failure. |
| `unknown` | No exact point matches, or required observations are unavailable/unsupported. |
| `invalid_evidence` | The supplied record or underlying artifact identities are inconsistent or changed. |

A failure at the same context overrides a success; an incomplete observation
prevents unanimous success. Adding irrelevant fields or altering their types
does not create a match. Two successful endpoints never establish that the
points between them work. The command explains differing fields, without
silently changing the query or dropping failures.

## What is bound

- Baseline and candidate source trees, patch bytes, and exact patch application.
- Original/effective arguments and requested target, steps, time limit, device, and policy.
- Input and initialized-parameter fingerprints and observed update structure.
- GPU model/capacity, runtime image, Python, PyTorch, CUDA/cuDNN, seed, allocator,
  and determinism settings.
- Observed numerical precision, pairing, losses, peak allocations, and the
  original comparison checks.

Independent source and Lab files are re-read. Paths embedded in archived JSON
do not grant access outside the selected root. Missing observations are not
silently filled from configuration. Unsupported source transformations return
unknown even when an old scalar-only comparison passed.

## Present scope and limitations

Version 1 supports the existing reviewed standalone s1/s3/s4 source contracts,
and requires a completed original baseline. Generic repositories, unsupported
transforms and OOM/transformed-reference cases remain unknown. It does not
automatically discover or execute a new boundary point, and cannot guarantee a
future run will succeed.

These are empirical records from a trusted local archive. Hashes detect
changes; they are not a signature, proof of authenticity, or formal proof of
all-input equivalence. The runtime observers assume a cooperative program.
Scalar loss comparison does not prove identical final optimizer state.
Finite observations do not justify interpolation, a confidence interval, or
a continuous safe operating range. Host load can confound timing.

The caller selects the observations. The tool preserves the complete selected
set and detects a record inconsistent with that set; it cannot discover
omitted experiments elsewhere or prevent someone from constructing a different
archive and record. Keep the selection index alongside the experiment protocol.

Historical live runs and new human controls keep their separate provenance.
Reinspecting either adds no automated repair success. Replay remains removed;
this is a command-line evidence lookup, not a frontend replay feature.


The environment key binds the fields listed above, not a complete machine image.
Host driver version, GPU clocks, dynamic free memory and background load are not
independently bound by v1. Queries are caller-supplied context objects, not an
automatic capture of a new machine. A match describes prior observations under
the recorded fields; it never authorizes or predicts a future execution.
