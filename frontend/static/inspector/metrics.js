/**
 * Metrics panel — run statistics.
 */

import { $ } from "../utils.js";
import { formatDuration, formatSeconds } from "../utils.js";

export function update(data) {
  if (!data) return;

  const cells = $("metrics").querySelectorAll("b");
  cells[0].textContent = data.rounds ?? "—";
  cells[1].textContent = data.usage?.total ?? data.total ?? "—";
  if (data.duration_ms) cells[2].textContent = formatSeconds(data.duration_ms);

  $("header-tokens").textContent = data.usage?.total ?? data.total ?? "—";
  if (data.duration_ms)
    $("header-duration").textContent = formatDuration(data.duration_ms);
}
