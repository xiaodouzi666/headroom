# F6 isolated media toolchain smoke

This is an environment check, not a Headroom demonstration or an F6 handoff.
No final video, live repair, GPU workload or paid model call was generated.

The existing official Playwright Python image was used by its immutable digest:
mcr.microsoft.com/playwright/python@sha256:330d401ae23c905896a0c26c66c36fc971b621519e7b11b435a8328d7bf6e031.
An isolated derived Docker image installed matching playwright 1.64.1 from PyPI,
edge-tts (resolved 7.3.1), and Ubuntu ffmpeg/ffprobe 6.1.1-3ubuntu5. Reuse the
tested image ID sha256:983d2a4e654e9d55ca0f73d7fbf25306fa94d7de34878e741957c4c1d7eac8ff;
the tag is headroom-final48-video-tools:toolchain-smoke. Exact installed Python
versions are in python-packages.txt. Host pyproject.toml, uv.lock and source were
not modified.

A new isolated Chromium 156.0.8078.4 context recorded only inline synthetic HTML.
Both viewport and video size were explicitly set to 1920×1080; browser networking
was disabled. The page says TOOLCHAIN SMOKE and explicitly disclaims a project
demonstration. No user browser, profile, project source, service or credential was
mounted. The tested scripts and raw assets remain under
.cache/final48-video-tools; receipt.json records their sizes and SHA256 hashes.

edge-tts generated the recorded neutral sentence using en-US-AndrewNeural at -5%,
exit 0. Only that sentence was sent to its online speech service. ffmpeg then
burned the generated SRT into the recorded clip and combined it with the MP3.
ffprobe reports one H.264 video stream at 1920×1080 and one AAC audio stream;
the resulting toolchain-smoke.mp4 lasts 6.312 seconds. Browser capture and
composition ran with network none; TTS used the default Docker network.

Initial attempts ran as container uid 0 with all capabilities dropped, which
could not write the host-owned output directory. Those complete failure logs
are preserved. The successful runs used its existing owner uid 1000:gid 1000,
with the same read-only root filesystem, dropped capabilities, no-new-privileges,
ephemeral /tmp, and no GPU. No permissions were broadened.

The official Playwright docs require the separate Python package and matching
image version, and note that recording size must be explicit to avoid the
default downscale:
https://playwright.dev/python/docs/docker
https://playwright.dev/python/docs/videos
The upstream speech package is documented at:
https://github.com/rany2/edge-tts
https://pypi.org/project/edge-tts/

This proves the tested recording/TTS/composition path on azuki at this time.
It does not complete gallery publication, authorize a live s3 run, validate
storyboard numbers, produce the final submission video, or hand work to Opus.
