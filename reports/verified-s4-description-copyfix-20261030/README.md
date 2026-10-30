# Historical s4 description correction — prepared only

The downloadable curated report and gallery description still call this historical run the latest evaluation. The prepared change says “The recorded evaluation removed…” and leaves the remainder unchanged.

The three before copies are under before/; the complete current-catalog candidate is under candidate/. copyfix-plan.json records expected before/after hashes and the fixed apply order. description-only.patch contains the three-file repository patch. The original raw run report is untouched and retains SHA 9b97be85d4e8116cda811b2b0e3b3587509d06f52db7700be92fe16fbf443cd6.

The candidate catalog and all downloadable fingerprints passed the existing load_verified validator (six cards). This is a wording correction: peaks, losses, compared scalar count, selected round, source provenance and all other report/index fields remain unchanged.

The running service uses this repository’s public-evidence directly through verified_routes.py; runs/public-api/submissions is the separate evaluations-only mirror and has no Verified catalog. Do not create or copy Verified files there.

Do not apply until root confirms R18 terminal and source freeze released. Check the plan SHA and every current before fingerprint. Quiesce the public service for the multi-file replacement so requests cannot observe mismatched old-index/new-asset fingerprints. Atomically replace report assets first and the index last, validate with load_verified, verify the raw report hash, then let root restart the service separately. If any step fails, restore touched files from the preserved before copies before restarting.

No production/public file, service, model or GPU workload was changed by preparing this report.
