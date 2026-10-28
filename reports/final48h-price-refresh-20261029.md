# Token Factory price refresh — 2026-10-29

Read-only check of the official pricing page in the signed-in physical Chrome browser, plus independent official-document review. No model invocation, payment, new profile or allocation was made.

Prices below are USD per one million tokens, excluding applicable taxes. The page labels these billing rows eu-north1; that label is not evidence of the actual processing location or current API availability.

| Billing product | Input | Output | Cached input | Ordinary rates valid from | Cached rate valid from |
|---|---:|---:|---:|---|---|
| Nemotron-3-Ultra-550B-a55B | 1.00 | 3.00 | 0.12 | 2026-06-01 | 2026-10-20 |
| Nvidia-Nemotron-3-Super-120B-A12B | 0.30 | 0.90 | 0.06 | 2026-03-01 | 2026-10-20 |
| Nvidia-Nemotron-3-Nano-30B-A3B | 0.06 | 0.24 | 0.012 | 2026-01-01 | 2026-10-20 |

Source: [official account pricing page](https://tokenfactory.nebius.com/organization/prices). The [public Nemotron model page](https://nebius.com/services/token-factory/models/nvidia-nemotron-models-inference) independently lists the same ordinary input/output rates.

The Ultra/Super ordinary rates match those used by the current [F1 preview](final48-f1-preparation-20261029/cost-preview-final.json). Its 1.4487068 USD net estimate therefore needs no change solely from these ordinary rates. It is not an actual charge or guaranteed total. Admission must not assume a cache hit; settlement needs the provider's actual usage fields. [Official cache billing explanation](https://docs.tokenfactory.nebius.com/cached-tokens).

## Identity and processing-region boundaries

Official cookbooks name Ultra as nvidia/Nemotron-3-Ultra-550b-a55b and Super as nvidia/nemotron-3-super-120b-a12b. The Nano cookbook uses a different case spelling from the project's saved real API identity; retain the validated runtime identity unless the actual provider catalog proves a change.

- [Ultra cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-ultra-550b-a55b.md)
- [Super cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-super-120B.md)
- [Nano cookbook](https://github.com/nebius/token-factory-cookbook/blob/main/models/nemotron/nemotron3-nano-30b.md)

The [current public-serverless documentation](https://docs.tokenfactory.nebius.com/public-serverless) describes public endpoints as Global and does not guarantee a fixed processing region. Cookbook examples using us-central1 do not establish a permanent regional restriction. No working base URL or model ID was changed by this review. This price check does not replace model availability/capability validation at activation.

The three existing runtime profiles were also checked read-only: all nine rates match the table, and all retain the verified Nano ID nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B. No historical profile needs a price or ID edit solely from this refresh. The future approved receipt should bind the selected profile and this fresh evidence.
