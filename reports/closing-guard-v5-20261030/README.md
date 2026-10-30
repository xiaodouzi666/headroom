# Closing guard v5 — exact pull-never and single network-none

The historical closing_guarded_v4.py remains byte-for-byte unchanged (SHA256 eb54c81fac699d94f3b48d5f6802404220e41fc7b24a9a0da58a4be4733464cb). Version5 copies it and changes only Docker create/run prefix parsing plus self-probes. The only new permitted option is the separate exact pair `--pull never`; missing/always/missing-mode/uppercase/equals forms remain rejected. This option prevents image pulling and does not enable GPU or networking.

The preexisting network membership check is tightened to require exactly one parsed network option, value none. Duplicate-none, none+host and equals+duplicate forms are rejected. Other GPU/privileged/unknown-host-option rules, protected files/production databases, DNS/INET/INET6 denial and existing AF_UNIX allowance are unchanged. v4's historical results and all test assertions are untouched.

32 isolated parser/audit-function probes passed without launching a process or Docker target. They test create/run, the exact allowed pair, unchanged CPU workload argv, forbidden pull modes, missing values, GPU/device/runtime/unknown flags and host/duplicate networks. After root independently reviewed the frozen diff/probes, the same4 existing CPU Docker tests ran unchanged under v5 and passed (62.671s). See v4-to-v5.diff and isolated-probes.json for the exact frozen source/probes.

## Real CPU Docker verification

All4 existing nodes passed unchanged: hard timeout during serialization, both helper/training launch orders with reference replay, and Python-parent child-source handoff. The tests produced8 actual CPU Lab subruns under image sha256:5703e9edc41be02a69ba7bdf4eb9e5126a5f8915e1dd235ab9fe94b9a412afe5. Every subrun has a captured process PID, verified artifact export and cleanup. Completed training subruns recorded20 updates and the new base-constructor observation; the hard-stop case remained timeout/partial. Existing fixture OOM labels are synthetic CPU classifications, not CUDA or acceptance successes.

The SSH transport closed after durable pytest exit0/JUnit were written. A read-only reconnect confirmed4 passes, no pytest process remained and cleanup receipts were complete; tests were not repeated. See real-cpu.log/xml/exit.json and verification.json for exact image/PID/constructor/cleanup evidence. Parent and spawned selfguard probes both retained DNS/INET, production file/DB and GPU denial while permitting only exact pull-never and a single network-none. No previous guard or historical whole-suite log was changed.
