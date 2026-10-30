# Final submission requirements review — 2026-10-30

Read-only review at 03:41 UTC / 11:41 Beijing; source HEAD 3425964fe183886b984739bbece5c5570a902e5b. No browser/form edits, deployment, model calls, GPU runs or credentials were used. This is not a Submitted receipt or a review of the final local video.

## Decision

Recorded evidence supports the required Nebius/NVIDIA integration, public source, license, setup and feedback. Latest fixed-nine **1/9** misses the internal **6/9** goal, but the latter is not a published competition threshold. It must remain accurately disclosed; it does not by itself prohibit entry. The concrete remaining items are the public YouTube URL/form submission and a newly discovered judging-period expiry mismatch. The user has authorized submission first and remaining fixes afterward; no new approval or repair campaign is proposed here.

## Official requirements and scoring

The [overview](https://nebiusglobalaihackathon.devpost.com/) requires a working demo, public source with a visible open-source license and setup instructions, track, technology explanation, feedback and a public YouTube demonstration of at most three minutes. Existing projects must explain substantial event-period changes. The video must show real functionality and tool use. The [rules](https://nebiusglobalaihackathon.devpost.com/rules) recommend below three minutes; a Public video shorter than three minutes satisfies both formulations. English or English translations and rights to third-party materials are required.

Rules require actual Token Factory inference or Nebius AI Cloud compute and an NVIDIA open-source model. Serverless deployment is optional. Tavily is optional for general eligibility; its bonus requires a functional runtime API call. Stage one checks viability, track fit and technology use. Four equally weighted criteria assess implementation, design, impact and originality; highest scores determine potential winners. No published CUDA-repair percentage or fixed-nine minimum was found.

## New dates and organizer clarification

Current [rules §1](https://nebiusglobalaihackathon.devpost.com/rules) and [dates](https://nebiusglobalaihackathon.devpost.com/details/dates) both specify:

- Submission: October 30, 2026, 10:00 PDT = **October 31, 01:00 Beijing**.
- Judging: December 9, 09:00 PST through December 23, 12:00 PST = **December 10, 01:00 through December 24, 04:00 Beijing**.
- Winner announcement: January 25, 2027, 12:00 PST.

Testing access must last through judging. The [access discussion](https://nebiusglobalaihackathon.devpost.com/forum_topics/45534-clarifying-free-judging-access-for-apps-with-metered-apis) now has three comments. Its newest reply is by **Janet Fang, marked Manager**, about two hours before this review. She accepts separate judge access with enough reserved capacity for a full judging pass, actual Nebius/NVIDIA runtime calls and reasonable abuse protection; no fixed minimum count is supplied. Her reply still names December 15, while both updated schedule pages say December 23. Use the later official end for access planning.

Finite sponsored capacity is therefore no longer an unanswered categorical issue. This reply does not certify this implementation's actual capacity, permit blocking legitimate use or establish automatic disqualification.

## Project evidence and concrete gaps

| Item | Finding |
| --- | --- |
| Public source/license | GitHub currently reports xiaodouzi666/headroom as Public and Apache-2.0; root LICENSE contains Apache 2.0. README has setup/run instructions and links the disabled runtime-profile example. |
| Models/platform | README and FEEDBACK identify Ultra nvidia/Nemotron-3-Ultra-550b-a55b, Super nvidia/nemotron-3-super-120b-a12b and Nano nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B through Token Factory. Historical live evidence supports real inference; this review made none. |
| Working demonstration | reports/final48h-live-demo-20261029/receipt.json records completed/target_met, 20 baseline and candidate updates and 20 identical compared losses. Its separate demo explicitly preserves the fixed-nine score 1/9. |
| Tavily/feedback | FEEDBACK covers the used technologies. reports/research-component-20261024T022414Z.json records four actual research calls; FEEDBACK separates component, model-directed and missing scenario-specific evidence. Do not claim every request calls Tavily. |
| Current access | Deployment receipt records public anonymous/token 200, invalid token 401, anonymous one/IP/hour, token no hourly quota and snapshot disabled. Token possession authorizes access; it does not prove a person's identity. Queue/resource/time/spend guards remain. |
| Video | README:8 and DEVPOST:50 still have {{VIDEO_URL}}; SUBMISSION_FIELDS:17 has {{PUBLIC_YOUTUBE_URL}}. A local file is not the required Public YouTube link. Root owns final review/upload/playback/form completion. |
| Formal entry | Inspected documents record Draft 3/5, not Submitted. Root must retain the actual final confirmation; this report does not re-request the user's authorization. |
| Updated end date | **Gap:** headroom/acceptance/judge_binding.py:44 fixes expiry at 2026-12-15T20:00:00Z; _active strictly checks it. The activation receipt matches. This is eight days short. Add an auditable compatible extension to **2026-12-23T20:00:00Z**, preserving history, money and credentials; do not simply rewrite the private receipt. |

## Statement safeguards

- Latest fixed-nine 1/9 and historical union 5/9 are different measures. The separate successful public demo does not change either campaign score.
- Historical s1/s4 compare the first **five** reference losses against candidates completing 20 updates. Do not claim every repair has 20 paired losses or identical complete optimizer/parameter state.
- Two snapshot checks returned no usable diagnosis; upload is paused. Watch triggering and clean CLI/GPU/model execution are not successful repairs.
- SUBMISSION_FIELDS:40 is stale about no organizer confirmation. Update it to the Manager's conditional reply. Final-summary's older access sections are explicitly superseded; do not reuse their old limits. Its remaining local-video-edit item is stale once the supplied final file passes review.
- README's headline should not be narrated as a guaranteed repair for every OOM; Results/Limitations disclose the actual scope.
- Resources city-award wording differs from rules/overview. Keep the user's truthful no-IRL declaration.

## Completion actions

Root can complete the authorized video/form submission without a new internal success threshold. Replace the video placeholders, verify public playback and links, finish required declarations and retain Submitted confirmation. In parallel, correct the access expiry and testing instructions to the updated end, without new paid testing, expanded money or altered credentials. Do not describe the date fix as already deployed until its own receipt exists.

## Artifact hashes

Inspected remote source SHA-256:

- README.md: ac89c4028b17164fac61859fa3ac0fb1f5fb21bee7f151d0a15d18bebf2aee19
- docs/SUBMISSION_FIELDS.md: 82a2c1b3eb9925220d698896699341b41c2ee8a5c14c86fa430ebc41129d643f
- docs/DEVPOST.md: 710083745755be503b3ecd73a30bf6de2816cf2de86df9f51507f2dc7023d730
- docs/FEEDBACK.md: 28f3c9e2bb702d6a1aced02ae5bcd8e077964759f0b88f83593183001acfa891
- reports/final-summary.md: 9088775ea01ea94e42fe83873fd3cab0221b65a5b610615820d434ec04362209
- LICENSE: c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4
- live-demo receipt: eefa0a07cf5b820360e41b9dd351d27d008e5b7fc7d6075751e344caa6b3750c
- research component: ef4fe97cf35e1453b4945c2d8920877c6ecb50f738adb37ec23fb8defd7c3716
- security deployment: 3cf9f3ebf75994bbfa73e053ac9d05224a03ac2a70f46c15c76d51f6004bb825
- credit activation: 7b9c7436f646fcf79e01f89cb0a710d829ac056b4f3dd0cb57f5320616ab37dd

No account balance, private receipt contents, keys or testing credentials are reproduced.
