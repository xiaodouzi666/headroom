# Source-span auditor revision 3

Only the private auditor is revised. The production orchestrator stores candidate_dir before static checks pass. A rejected patch can therefore have candidate bytes without reaching runtime verification. The old auditor treated that directory alone as proof that verification.json was required.

The exemption now requires both a rejected/failed patch and explicit verification_available=false. KEEP, a verification object, positive verification feedback, or patch.status=applied still require the verification artifact even when other fields contradict them. A candidate directory with ambiguous feedback remains fail-closed. Source-span reconstruction, selected KEEP/REVERT chain, financial binding, read-only guard, and final completeness gate are unchanged.

The real v6 s8 fixture has no verify.started event and only a baseline Lab run. Attempts 3 and 4 lack parsed responses and remain unknown. Removing a false missing-verification flag does not make the overall sidecar complete. The old driver, tests, audit report, and historical evidence are retained unchanged.
