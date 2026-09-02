# Control Plane UI v0.2 — design notes

## Information hierarchy

```text
Workspace
  └─ Run
      ├─ Timeline      when / what / how long
      ├─ Transcript    what the Agents said
      ├─ Agents        topology / assignment
      ├─ Plan          intended work
      └─ Statistics    longitudinal runtime/provider telemetry
```

The command composer is a control interface for the Run, not the product's
primary information hierarchy.

## Timeline model

```text
TIME       coordinator                researcher                osint
           TOOL | MODEL | INPUT       TOOL | MODEL | INPUT      TOOL | MODEL | INPUT
18:11      ....   ████   ◆
18:12      ██     ████                ....   █████
18:13                                    ██   █████              ███
```

The renderer consumes spans rather than presenting every lifecycle event as a
separate row.  Raw lifecycle records remain available from the block overlay.

## Overlay interaction

The detail overlay is spatially anchored to the selected block.  It starts at
the source block's bounding rectangle, animates to a readable fixed panel, and
animates back when closed.  No global backdrop and no `backdrop-filter` are
used; the timeline remains visually present behind the layer.

## Statistics semantics

`JITTER` means **call-to-call throughput variation**, not inter-token jitter.
It is the coefficient of variation of per-call decode TPS in the selected
window.

`1d` means local calendar day (00:00 → now), while `24h` is a rolling window.

Longer ranges use coarser time buckets so the number of SVG points stays
bounded and the browser does not render minute-level data for seven days.
