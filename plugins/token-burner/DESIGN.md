# Token Burner 0.2.0 design notes

## 1. Source of truth

Token Burner never maintains a second token ledger. `GET /api/sessions/{id}/usage` is the accounting authority. The browser stores only the previous sampled total needed to compute a visual delta.

`usage.total` is preferred. If it is unavailable, the fallback is `input + output`; cached/reasoning dimensions are deliberately not added because they are not guaranteed to be disjoint from the primary dimensions.

## 2. State machine

```text
selected Session changes
  -> reset local telemetry impulse / peak
  -> sample authoritative usage + run state

usage total increases
  -> delta / sample time
  -> bounded impulse
  -> exponential decay
  -> logarithmic visual intensity

run active, no fresh usage
  -> optional pilot flame

run terminal / idle
  -> flame decays naturally
```

There is no extra events polling and no artificial activity counter.

## 3. Why polling remains

DSH can inject a Session-scoped `useProjection("tokenUsage")` observable into a UI slot. Current Angelus plugin JS has `window.Angelus.registerPanel/registerCommand/registerSettings`, but it does not yet expose a Session projection subscription seat. Therefore REST refresh is the smallest honest adapter.

The code keeps all sampling inside `poll()` so replacing it with a future observable is local.

## 4. Why the overlay is a compatibility shim

DSH provides a first-class `shell.overlay` slot. Current Angelus has no equivalent frontend bridge slot. Token Burner therefore mounts one fixed root directly under `document.body`.

To preserve lifecycle behavior:

- the root carries `data-angelus-plugin="token-burner"`, which the host unload path removes;
- a `MutationObserver` notices removal and cancels timers;
- the rest of the plugin never reaches into host-owned workbench DOM.

This is intentionally narrower than the 0.1.x implementation.

## 5. Settings ownership

Behavioral knobs are host-owned plugin settings. Position/collapse/size are browser-only presentation state. This follows the Phase-1 frontend boundary that localStorage is not Session or runtime authority.
