# Snapshot retry allocation proposal (not activated)

The original F3b parent and four children remain byte-for-byte unchanged. The original receipt, profile and shared ledger also remain unchanged. A new reviewed revision creates a new parent in the existing feature_parents table with a unique F3b-retry:<revision>:<slot> scope, and a child in the existing feature_children table. It does not create another budget database or increase any cap.

The existing BEGIN IMMEDIATE registry transaction serializes admission. DemoAllocation already rejects any non-settled feature_children, so the new claim blocks a competing demo before its ledger run opens. The retry path also checks f2_demo_runs before registration, covering the reverse demo-claim/open window. Other original feature paths already check feature_children.

Preparation pins the original settled child/parent, receipt/profile identity, content-identical snapshot intent, reviewed code hashes and the current pool logical state. Claiming requires the exact reviewed proposal SHA and rechecks it within the registry transaction. Duplicate revision+slot and run IDs fail closed.

The new child's total ledger ceiling is min(original shared-pool approved total, current shared-pool charged + remaining F3b cap). Remaining F3b cap is the original <=$1 less conservative charges of original F3b children and every registered F3b retry. This ceiling may never exceed the original pool total. Run allowance retains the original pinned snapshot intent, hence also <= the original F3b_snapshot task cap and <=$0.30.

Before open_run and reserve, recheck receipt/profile/ledger identity, code and input hashes, registration, original/history integrity, other active claims and unresolved charges. At mark_dispatched repeat these checks while permitting only that run's one exact undispatched reserved attempt; all other unresolved/active work remains blocked. Unknown actual costs stay unknown; only existing reviewed conservative settlement can resolve a charge. Failed or unverified cleanup blocks the retry and the shared original demo/feature paths.

Live is not authorized by this file or its hash. The parent agent must review code, offline fixtures, the actual proposal and available gift/reserve state before it claims or dispatches. No actual claim is created by preparing this document.
