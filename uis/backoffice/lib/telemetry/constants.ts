export const TELEMETRY_SOURCE = "web" as const;
export const SCHEMA_VERSION = "1.0";
export const DEFAULT_BATCH_SIZE = 20;
export const DEFAULT_FLUSH_MS = 10_000;
export const MAX_RETRIES = 3;
export const RETRY_BASE_MS = 500;

export const EVENT_SCHEMA_VERSIONS: Record<string, string> = {
  inbound_order_created: "1.0",
  outbound_order_created: "1.0",
  stock_threshold_triggered: "1.0",
  direct_stock_edit_rejected: "1.0",
  kit_cost_variance_detected: "1.0",
  product_created: "1.0",
  outbound_order_rejected: "1.0",
  supplier_rate_edited: "1.0",
  incident_report_analyzed: "1.0",
  login_succeeded: "1.0",
  login_failed: "1.0",
  session_expired: "1.0",
  password_reset_requested: "1.0",
  password_reset_failed: "1.0",
  user_registered: "1.0",
  admin_role_changed: "1.0",
  page_view: "1.0",
  form_abandoned: "1.0",
  api_latency_recorded: "1.0",
  frontend_error_captured: "1.0",
  network_request_failed: "1.0",
  validation_failed: "1.0",
};

export function telemetryEndpoint(): string {
  return (process.env.NEXT_PUBLIC_TELEMETRY_ENDPOINT ?? "").trim();
}
