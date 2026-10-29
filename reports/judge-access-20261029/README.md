# Judging access closeout — 2026-10-29

The owner delegated the judging allocation decision and asked to retain the hourly limit. The deployed application now separates token-backed judging usage from anonymous preset usage. A token proves possession of the credential; it does not establish the visitor's real-world identity.

## Decision and production configuration

- Existing promotional credits only, no recharge. A separate $8.00 gross allowance uses the existing 1.21 tax estimate: $6.61 net total/day and $0.30 net per run. The activation reserve check preserved at least $8 after both allocations.
- This uses the already reviewed local input estimate with margins. It is application admission accounting, not a provider-side hard cap on the eventual bill. Unknown charges or overruns stop further dispatch under the existing policy.
- New dispatch expires at 2026-12-15 20:00 UTC (December 16, 04:00 Beijing). Existing claims can still settle actual costs after expiry.
- The original FINAL48 allocation, its receipt/profile and all historical accounting remain intact. Its $6.43 net / $7.79 gross authorization is unchanged.
- Both routes share one attempt per IP per hour, one active job, at most two waiting/preparing jobs and the 480-second public deadline. The token does not bypass these protections.
- Pages, Verified runs and Results need no token. Preset examples can run anonymously using the original public allocation. Supplying the existing token selects the separate judging allowance; a custom script requires it. Snapshot uploads remain paused.
- Credentials remain private. The token is entered only into page state and is cleared after submission, with no URL or browser-storage persistence.

The launcher is configured with HEADROOM_JUDGE_ALLOCATION_RECEIPT pointing to the private receipt. When explicitly configured, an invalid receipt prevents startup and an unavailable pool rejects token-backed work without falling back. An entirely unconfigured judge allocation preserves the documented legacy behavior.

## Implementation and focused checks

Production source: 612b2bde7f10614fe8219f8fd12a63d3beef00ed.

| Check | Result |
|---|---|
| Independent allocation binding | 38 passed |
| Expanded API, real binding and SDK MockTransport in thread/spawn modes | 13 passed |
| Empty/duplicate/invalid authorization review case | 1 passed |
| Run-form UI | 28 passed |
| TypeScript, Ruff, scoped formatting, production build | Passed |
| Independent source review | No remaining blocker |

These batches overlap earlier checks and are not added into a new full-suite count. See [binding receipt](binding-check.json) and [routing report](../judge-routing-20261029/README.md). Review fixes recheck expiry immediately before dispatch and reject an explicitly empty Authorization header. Source, request, receipt/profile hash, database identity and claims bind each run to its selected allocation.

The publication scan found zero real configured-secret matches in the staged content. Two Gitleaks matches were independently recomputed public source SHA256 strings; narrowly scoped exact path-and-hash allowances were added and Gitleaks then passed. These are hashes, not credentials.

## Deployment and public checks

The [initial immutable deployment receipt](deployment.json) records 1.192 seconds from service stop to recovered origin health. Funnel served the new built Home exactly, with SHA256 bc3fd6ab052b6c7fed72631df146eebe579860bd0746286631f8c65dbd90a03b. Anonymous and valid-token config requests returned 200; invalid and explicitly empty Authorization returned 401. All previous accounting tables were logically unchanged, the existing token and provider credentials were unchanged, and the new judging database had zero attempts, runs and claims.

The [follow-up browser and draft receipt](browser-and-draft.json) closes the deployment receipt's initially pending UI/upload checks. Local Chrome confirmed anonymous example availability, invalid-token rejection, recovery after clearing the dummy token and automatic Reclaim selection for s3. The custom-script token guard was independently reviewed in source; no live submission was clicked. This was not a new model call, GPU job or repair acceptance run. No new Lighthouse score is claimed for this build; the earlier 100 score belongs to the previous readability build.

## Private delivery and remaining submission work

The previously authorized private Devpost attachment was replaced with judge-testing-instructions-20261029-v2.txt, using the same token and recipient group. Save and return to Additional info visibly confirmed that filename under the page's judges/organizers-only notice. The [public review copy](judge-testing-instructions-redacted.txt) contains no credential.

**Devpost is still Draft, 3/5 steps done.** The final video URL is outstanding. The final Terms/Rules checkbox remains unchecked and Submit project was not clicked. Saving an attachment is not final submission. The official judging requirement's unrestricted-access wording has not been reconciled by the organizer with the retained quota; no eligibility assurance is claimed.

The latest fixed-nine campaign remains 1/9 against the unchanged 6/9 requirement; historical failures and the original full-regression receipt remain unaltered. This access change creates no additional repair success.

## Screenshots

- [Saved private v2 attachment and Draft 3/5](devpost-draft-v2-saved.png)
- [Public Run page after clearing the invalid test token](public-run-token-cleared.png)
