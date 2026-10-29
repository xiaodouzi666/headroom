# Prepared update of the verified-run gallery

This update is prepared in an isolated worktree based on source revision 2969195. It has not been deployed.

The gallery remains four successful repairs and two unresolved workloads. The latest successful s4 run is now e8213706570e478f9845e49e24c2b54b from the October 29 fixed-nine evaluation. Its recorded peak reduction is 89.76936730433156231833859823%; numerical comparison covers five loss scalars against an offloaded reference, while the candidate completed 20 optimizer updates.

The latest successful s3 run is d9926ee7bb624e7fb22540bbc4c92cdc, an independent browser demonstration. The card labels this origin explicitly. Its 73.37869416876643934398385962% reduction and 20 identical recorded loss samples do not change any fixed-nine evaluation score or historical campaign result.

The s8, s2, s1, and nanoGPT cards remain byte-for-byte identical as JSON objects. The current selection description calls the failures preserved examples; it does not claim they are newer than the independent Watch demonstration. The s2 card remains the historical tolerance-based fp32 repair; neither failed precision-tier run is presented as a successful trade-off. No new measurement or scoring was performed.

## Evidence and compatibility

Each new card passed the existing recorded-run inspection and exact initial-diagnosis binding checks. The s3 diagnosis has eight bound stacks; s4 has four. Existing parameter counts, measured losses, selected patches, and sources are retained. Neither new run recorded Tavily sources, so the cards say so.

The original catalog is preserved byte-for-byte at public-evidence/verified-runs-history-v1.json; all original assets remain in place. Only the current six cards are listed by /api/verified. The download handler can read that one fixed historical catalog to preserve previously published URLs. It never searches arbitrary historical runs or loose files. Historical downloads retain the same schema, path, and SHA checks; altered files fail closed.

Selection and source hashes are recorded in [preparation.json](preparation.json). The existing publisher now accepts the two already-reviewed report formats and the explicit public API Store, retaining its old default behavior. After applying this commit to the source checkout with its existing raw records, the reproducibility check is:

    PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/publish_verified.py --selection reports/verified-refresh-20261029/selection.json --check

The preparation keeps current and old data separate. Deployment should install new assets and the fixed historical catalog before switching the current catalog, and restart only the read-only public service after the route change is installed. Live and snapshot submissions remain disabled. No replay animation is introduced.
