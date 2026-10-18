# Measured design decisions and remaining costs

- Replaced global busy rejection and whole-job draining with scoped ownership,
  resumable preparation/import/runtime/GitHub/archive/order/backup export jobs,
  owned progress and cancellation, and foreground request/job priority.
- Individual deck generation uses one ready notification; its low-level render
  toast is suppressed. Completion during editing retains a persistent notice.
- Serial render → save remains the production choice. Fresh-write overlap and
  additional native renderers did not demonstrate a throughput benefit on this
  machine. Exact PNG/persistence checks accompany those decisions.
- The runtime bundle retains mixed-build validation and no-store fetching.
  Local transfer measured below 0.1 seconds, insufficient evidence for adding
  another cache layer. Public network behavior can differ.
- Complete deck snapshots on progress and initial large-grid mounting remain
  measurable costs. Stable DOM and small previews reduce input loss and image
  bytes without claiming they eliminate these costs or native canvas pauses.