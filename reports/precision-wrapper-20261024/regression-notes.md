# Intermediate regression observations

An initial focused run passed 91 tests and failed two existing loss-capture tests:
`test_adamw_override_is_counted_after_real_update` and
`test_global_hook_covers_distinct_optimizer_classes`. A capture-wide
TorchFunctionMode caused Tensor.backward to redispatch through the installed
wrapper and append each scalar twice. Gradients were executed once.

The correction limits the observation mode to root forwards and deduplicates
only an in-flight invocation on the same Tensor identity using thread-local
integer IDs and try/finally cleanup. New regression cases check that forward-external
backward/optimizer dispatch has no added mode, sequential backward calls are
retained, forward-internal backward is captured once, and actual gradients match.
The subsequent focused run passed 95 tests in 2.35 seconds; see root-focused.log.
This does not replace the later whole-suite and hardware validation.
