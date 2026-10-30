# Native optimizer tensor metadata — optional feasibility only

No production code, prompt, capture or budget was changed. No optimizer/tensor
workload, GPU operation, provider call or browser research was performed. Wait
for the actual R16 findings before deciding whether this addition is necessary.

The current Torch sources and R15 captures report2.5.1+cu124. Native Optimizer
creates an initially empty defaultdict state. AdamW _init_group skips parameters
without gradients and lazily allocates step/exp_avg/exp_avg_sq inside the native
step. Pre-hooks run before that call; post-hooks run only after it returns.
TensorBase sizes/numel/itemsize/dtype/device getters read TensorImpl metadata.
This supports a narrow exact-native CPU/CUDA strided-tensor observer; it is not
permission to inspect arbitrary custom objects or infer historical values.

## Minimum observation

Read only already-known weak Parameter IDs. For exact supported native tensors,
record bounded concrete shape,dtype,device,layout,numel and logical bytes. Inspect
only fixed native state keys:exp_avg,exp_avg_sq,max_exp_avg_sq,momentum_buffer,step.
Use fixed-key dict.get with a sentinel:state[p] would create missing defaultdict
entries and must not be used. Unknown keys/objects remain unsupported without
names,repr or values copied. No item/cpu/numpy/value conversion,sync,storage walk,
state_dict or optimizer mutation is needed. Logical bytes are not allocator bytes
or a proof of independent storage; signature sharing is not tensor identity.

## Timepoints and unknowns

Constructor-return metadata describes that instant,not completion of a custom
subclass. Initial absent moments stay absent; they are not zero-filled moments or
future memory. First step-pre cannot see state created inside that step. A native
successful post-hook can inspect its actual new metadata before the host's step
limit raises. If the native step fails,there is no successful post observation;
state changed during that failed call is unknown. No Tensor step counter value is
read. Actual update counts and numerical/workload gates keep their existing rules.
Old R15 captures cannot be backfilled:these new fields remain not_captured.

## Bounds and capacity

Deduplicate shape/dtype/device signatures and exact parameter-ID sets; reference
those sets from stage/state-profile records. Only identical observed sets may be
reused. A mixed/partial/lazy state requires separate bounded buckets; exceeding
any shared record/member/byte limit marks only this optional metadata incomplete.
The raw allowance must remain one shared64KiB envelope with current group options,
and the model-visible optimizer summary must remain3072B. Preserve old facts on
overflow; do not make raw-only facts appear model-visible.

The real s2 catalog has204 entries in three numel bins; s8 has8 entries in five
numel bins. Neither has captured shape/dtype/state metadata. Their legacy summaries
are1898/1878B,leaving1174/1194B. The following examples are **synthetic flat-FP32
serialization models**,not new observations or inferred defaults:

| Size example | s2 | s8 |
|---|---:|---:|
| Combined optional raw,profiled |8217B|3969B|
| Context with dummy options plus dtype/device/layout |2830B|2806B|
| Context plus moment relations |3270B|3238B|
| Context including complete example shape profiles |3826B|4066B|

Raw capture looks feasible for these small-profile examples. The dtype-only
summary fits. Full state relations or exact shape lists exceed3KiB in this example;
there is no basis to promise full delivery without further bounded serialization
work. Actual distinct shapes/devices/state changes may require more buckets.
If R16 only needs parameter dtype,prefer that minimal increment. If a genuinely
needed state question persists,first demonstrate a representation that fits all
current caps; do not enlarge the code or prompt pre-emptively. Metadata cannot
establish unscaled gradients,numerical equivalence or other genuine prerequisites.

See proposal.json for the exact minimum contract,capacity-estimates.json for
explicit synthetic assumptions,and source-evidence.json for immutable source and
R15 capture references. Nothing here declares a new scenario success.
