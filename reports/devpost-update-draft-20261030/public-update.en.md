Post-submission development update — 30 October 2026

Headroom can now analyze an uploaded PyTorch memory snapshot through the CLI and the authenticated public web interface. This path parses an existing capture and calls Nebius models; it does not execute the uploaded training script or run a new GPU workload. The interface shows reconstructed peak composition, cited allocation stacks, model explanations and any available unverified patch draft. Memory sizes are calculated from the cited stacks, separately from the model's explanation.

Two real CLI cases, s2 and nanoGPT, produced structurally valid diagnoses and retained a needs-human result. A real public nanoGPT upload also produced a valid diagnosis card with four inspectable stack references. Its displayed 17.20 GB is the rounded sum of those cited stacks, not a measured saving or the full activation category. No patch was produced: the uploaded source failed the patch engine's preliminary safety checks before a patch-generation call. A separate public s3 upload received model replies that failed validation; Headroom withheld the diagnosis. A larger s2 upload timed out before analysis. The authenticated-upload window has been extended to 120 seconds in a tested change; a live large-file retest is still pending.

These are functional evidence for snapshot diagnosis, not new hardware repair successes. Manual review found errors in some category summaries and inferred runtime settings, even where the cited-stack numbers were exact. Model explanations and proposed savings therefore remain hypotheses requiring review and hardware verification.

The completed R8 fixed-nine campaign has the following results:

| Measure | R8 result |
|---|---:|
| Memory targets met | 0/9 |
| Raw first-cause category matches | 7/9 |
| Valid diagnoses with a correct first cause | 5/9 |
| Ready, valid diagnoses with a correct first cause | 2/9 |

The denominator stays nine, and our internal fixed-nine memory-target acceptance threshold remains at least 6/9; R8 did not meet it. Raw category matches are not validated accuracy. These diagnosis counts use the saved first-round diagnosis, which may include bounded correction within that round. Unknown scenario truth is not silently converted into a success. Historical runs and failures remain preserved. R9 has not run at the time of this draft and contributes no results here.

The submitted demo video is unchanged.
