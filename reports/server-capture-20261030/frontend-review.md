# Stored server capture frontend — 2026-10-30

The default Snapshot panel now lists server-held captures from the backend allowlist and starts a new Nebius analysis by opaque ID. The browser sends only `{example_id}` plus the judge token in the Authorization header; it does not download or reupload the capture. File upload remains a secondary option for users with their own captures.

The selected capture must be available. Server analysis always requires a judge token, including when the legacy anonymous-upload prop is false. List errors and unavailable examples do not trigger a POST. A submitted task clears any previous displayed job, then uses the existing owner-bound polling/result path. The token is cleared after completion or failure of submission. A stored capture is not displayed as a new GPU measurement or a successful hardware repair.

GET /api/snapshot-examples returns `{examples:[{id,label,description,snapshot_bytes,available,reason}]}`. POST /api/snapshots/from-example accepts only `{example_id}` and returns the existing queued SnapshotJob shape. The backend contract was confirmed with its owner before implementation. The result card uses “Saved snapshot” language for both stored and externally supplied captures.

Final focused UI suite: 35 passed. TypeScript build and scoped git diff check passed. Full logs and source hashes are in frontend-verification.json. The first typecheck reported an unused `init` argument in one newly added test; removing that unused declaration resolved TS6133 without changing product behavior. All verification was offline: zero provider calls and zero GPU jobs. No build deployment, browser flow, live model diagnosis or hardware repair is established by these receipts.
