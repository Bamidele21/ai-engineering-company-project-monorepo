import { shouldEmitThrottled } from "./catalog";
import { pagePath } from "./sanitize";
import { getSessionId } from "./session";
import { track } from "./telemetry";

export function trackValidationFailure(
  context: string,
  field: string,
  reason: string,
  pathname: string
): void {
  const key = `validation:${getSessionId()}:${context}:${reason}`;
  if (!shouldEmitThrottled(key, 60_000)) {
    return;
  }

  track("validation_failed", {
    source: "client",
    context,
    field,
    reason,
    page_path: pagePath(pathname),
  });
}
