# Bounded charge and retained unknown review

Status: implementation focused tests passed; no actual ledger operation performed.

Future missing-cache responses use Cost usd=null/status=upper_bound plus upper_usd
and verified_tariff_missing_cache_count basis. Runtime requires exact identity,
complete valid usage, strict provider bound and cap compliance; Store receives
billing_status=bounded only after committed settlement. Known charges with cap
violations retain actual but remain billing_status=unresolved.

New calls carry budget_attempt_id. Historical calls are never backfilled.
Historical review retains the original full upper, actual null and old failed
report, with an append-only review row. It only clears the specifically reviewed
closed-run missing-cache halt. Other incidents still block.

Default preparation (read-only, no credentials or provider access):
python -m headroom.billing_review --ledger PATH --store PATH --profile PATH \
  --run-id ID --attempt-id ID > NEW-REVIEW.json

After independently reviewing the entire proposal and its exact SHA256, explicit
execution requires --execute --receipt NEW-REVIEW.json --expected-sha256 SHA \
  --reviewed-by NAME --daily-limit LIMIT

Do not infer approval from this README. The current Nano retention tool has not
been run against the actual ledger by this agent. A repeated/stale/cross-run or
changed-metadata receipt is refused; no actual charge is fabricated or released.
