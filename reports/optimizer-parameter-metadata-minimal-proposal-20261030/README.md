# Minimal parameter metadata proposal — not implemented

Wait for actual R17 output. If a genuinely needed AdamW-in-backward premise is the parameter dtype/device/layout, the smallest addition is a fresh bounded aggregate of already-known weak parameter identities, sampled at base-constructor return, step-pre and successful-step-post. Full shapes and optimizer-state relationships are unnecessary for that first increment and remain unknown.

The concrete source anchors, proposed raw/model fields and negative tests are in proposal.json. The minimum touches a small new Lab helper, three existing hook boundaries and the optimizer summary adapter. Optional failures cannot alter existing parameter/update/loss capture or the target's native error/return. No production or test file was changed.

Only exact cached native Tensor/Parameter metadata and exact built-in optimizer containers are eligible. No item, tensor conversion, copy, synchronization, storage walk, pointer, state_dict or arbitrary object traversal is used. New identities are forbidden; only the existing weak registry is read. Dtype/device/layout do not authenticate the optimizer implementation or establish no-alias, unscaled-gradient, absent-clipping, reference-family or mathematical equivalence.

The three temporal boundaries remain distinct. Constructor metadata does not prove subclass completion or a successful update. Pre-step does not reveal moments lazily created inside the call. An exception/OOM has no successful-post observation. This minimum reads no state tensors at all, so no stage can declare their absence, dtype, shape or initialization. Constructor-only OOM must remain one constructor observation and zero pre/post updates.

There is still one shared 64 KiB optional raw envelope with existing group options, and the optimizer model summary remains 3072 bytes. Legacy facts win. If the new component cannot fit, it is unavailable/omitted and remains unknown; no old facts are deleted and no cap is increased.

Using the real R16 summary byte sizes, a **synthetic** uniform-FP32/CUDA/strided/leaf aggregate would add about 286–288 bytes plus its field name:

| Existing selected summary | Existing bytes | Example combined bytes |
| --- | ---: | ---: |
| s2 | 2591 | 2910 |
| s5 | 2506 | 2824 |
| s7 | 2588 | 2906 |
| s8 | 2572 | 2889 |

These are serialization estimates only. No parameter dtype/device/layout was observed or inferred from those old captures. Mixed or changed metadata may exceed this compact example and must remain partial/unknown.

The necessary tests include forbidden-operation canaries, custom tensors and dispatch, sparse/meta/unknown device, weak-ID reuse/GC, failed pre-without-post, last post before StepLimitReached, dtype/layout/numel changes, exact shared raw/context limits, old-capture compatibility and source/run/round mismatch. No tensor execution, GPU work, provider call or source/test change was performed to prepare this report.
