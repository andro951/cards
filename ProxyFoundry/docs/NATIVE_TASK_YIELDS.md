# Native renderer task boundaries

The production adapter now yields a browser task after each existing native
stage, using `scheduler.yield()` where available and a zero-delay timer otherwise.
Native calls, order, readiness checks and two drawing passes remain unchanged.
Foreground browser events can run between stages instead of several resolved
promise stages becoming one long task. Internal synchronous calls still run on
the main thread; this does not move CardConjurer into a worker.

## Temporary static-build experiment

Baseline revision: 1d7d389. Seven structural faces use Supernatural artwork.
Each comparison has a cold serial trial and two balanced warm repetitions.
Generated PNG assets are deleted outside measurement between trials, retaining
warm artwork/frame caches. All yielding variants save serially. Metadata,
preparation, iframe bootstrap, plan lookup and result collection are excluded.

| Storage / workload | Serial mean, 7 cards | Stage-yield mean | Mean longest reported task, serial -> stage yield |
| --- | ---: | ---: | ---: |
| Browser, no input probe | 11.674 s | 11.599 s | 588 -> 357 ms |
| Selected folder, no input probe | 19.011 s | 19.543 s | 623 -> 347 ms |
| Browser, keyboard probe | 19.787 s | 18.946 s | 618 -> 385 ms |

This is a responsiveness change, not a proven throughput improvement. Warm
browser timing is similar; filesystem stage yielding was 2.8 percent slower in
this small comparison. Timer gaps still sometimes exceed one second, including
1.39 s in a filesystem yielding trial, and remain a separate investigation.

The keyboard probe sends actual key events during rendering/saving. Command
durations exclude preceding Playwright status probes, so they do not prove
end-to-end input latency. Automation also increases workload; its absolute times
must not be compared with no-input runs. Extra yields inside the drawing pass
showed no clear additional benefit, so only stage boundaries are shipped. The
timer fallback preserves output and has similar warm filesystem time (19.071 s).

All 175 pipeline PNGs match their serial reference across four RGBA channels.
Saved bytes are checked by SHA-256 through the production asset API, and final
outputs survive reload in all three runs. The filesystem run reused the approved
CDP browser and restored its original folder preference without a native picker.

## Broader structural regression

The pinned native renderer was tested on 22 structural faces, twice per variant:
unchanged scheduling, production stage yields and forced timer fallback. All 132
PNGs match exactly, including first use and repeated structural script state.
The test took 342.87 seconds. Render pipeline version is unchanged because output
pixels are unchanged.

Reproduce using `scripts/profile_generation_pipeline.py --fresh-saves --task-yields`
(optionally `--folder` or `--input-latency`) and `tests/test_native_task_yields.py`
with `PF_BROWSER=1` and `PF_LIVE_CC=1`. Both harnesses disable the production yield
in their serial controls, retaining identical drawing calls.
Raw evidence: [pipeline](native-task-yield-profile.json) and
[structural pixels](native-task-yield-pixels.json).