# Submission requirements and remaining access gap — 2026-10-29

This supplements FINAL_48H without editing its frozen text. Official sources were checked today.

- Submission closes on October 30 at 10:00 PDT, or October 31 at 01:00 Beijing time. Judging ends on December 15 at 12:00 PST, or December 16 at 04:00 Beijing time. Keep the intended review service available through that endpoint. [Official dates](https://nebiusglobalaihackathon.devpost.com/details/dates).
- The track is Coding and Agentic Engineering Track. A public open-source repository, English submission materials, a working demo/test-build URL, and tool feedback in the submission form are required. The video must be public on YouTube and shorter than three minutes; the planned 170-second edit fits. [Official rules, section 4](https://nebiusglobalaihackathon.devpost.com/rules).
- Testing requires free access for organizers and judges through the end of judging. Private access credentials must be supplied in testing instructions. The current one-run-per-IP-per-hour restriction and finite demo scope do not establish that the entire judging-period requirement is met. Read-only historical evidence does not, by itself, prove full test access. [Official Testing provision](https://nebiusglobalaihackathon.devpost.com/rules).
- The current public configuration has preset runs and judge scripts enabled, snapshot uploads disabled. GPU and budget readiness were available, with no running/preparing/queued work, when checked this turn. The UI separately handles loading, queue, GPU and budget readiness.
- The sole approved allocation remains $6.43 net. The plan's $0.30 limit is per run; its earlier implementation as a cumulative demo cap was corrected and deployed at ed73197. The last deployment receipt records $4.362263328 remaining in the original shared pool, with all historical charges preserved and no new allocation or provider request. See [the correction](final48h-demo-budget-correction-20261029/README.md). This fixes runtime admission; it does not establish a separate judging-period allowance or an unrestricted-access agreement.
- Update after browser access was restored: the actual Devpost entry is still DRAFT / 3 of 5 steps. Its project story, links, tags and technical feedback have been saved; the final video remains absent. Additional info is labelled for judges and organizers except noted fields; there is no dedicated Testing instructions field, so the private attachment is the available handoff location. Frank explicitly approved delivery; the existing judge token and instructions were uploaded there and the saved filename was verified. The public Home thumbnail/gallery image is also saved. A fresh provider balance observation passed the $8 reserve check; the separate Builder gift was then redeemed without card payment or new spending authorization. Details stay private. See [draft evidence](devpost-draft-20261029/README.md).
- The README now uses reclaim mode for the s3 example because that workload already completes. This is a documentation correction. The actual F5 command used fix-oom, returned needs_human, and remains unchanged; it is not rescored or rerun.

The remaining concrete decisions are: establish the funded judge-access period within the user's no-recharge limit, and obtain the final public video and Submitted receipt. No fabricated success or unlimited-access claim is substituted for them.

## Judge-access proposal, not deployed

The official wording does not expressly grant an exception for per-hour quotas
or a depleted allowance. We cannot confirm compliance from the present settings,
and this observation is not a disqualification decision. Private credentials
are expressly supported by the rules; the approved private attachment has now
provided the existing app credential.

A public [discussion about metered-API judging access](https://nebiusglobalaihackathon.devpost.com/forum_topics/45534-clarifying-free-judging-access-for-apps-with-metered-apis) was read on October 29. Its question asks about separate judge access and reserved capacity; the two visible comments are other participants asking similar questions. No organizer response was visible, so that thread is not approval of a quota or minimum capacity. This was read-only research; no message was posted.

The smallest proposed change is to retain anonymous visitor limits, but route
an authenticated judge through a separate allowance and rate policy. This would
keep sandbox isolation, source restrictions, cost accounting and safe queue /
cleanup controls. The existing token currently permits script entry only; it
does not exempt a judge from the public IP or spending limits.

Before implementing that change, Frank must choose the judging-period gift-only
allowance and service commitment. An additional gift is not an increased
spending authorization. Any retained limits should be described accurately; if
their acceptability needs clarification, Frank can choose to ask the organizers.
No such communication, permission expansion or allocation was performed here.

Current credential delivery, public screenshot delivery and the personal
eligibility fields need no repeat approval. Moderate learning has been saved and the IRL city left blank after Frank
confirmed no attendance. Remaining form input is the final Public video URL,
and final Rules/Terms acceptance and submission once the entry is ready.
