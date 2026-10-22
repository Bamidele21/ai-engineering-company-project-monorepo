"use client";

import { useEffect } from "react";
import { installErrorListeners } from "@/lib/telemetry/error-listeners";
import { installTelemetryLifecycle } from "@/lib/telemetry/telemetry";
import { PageViewTracker } from "./PageViewTracker";

export function TelemetryBootstrap() {
  useEffect(() => {
    const cleanupLifecycle = installTelemetryLifecycle();
    const cleanupErrors = installErrorListeners();

    return () => {
      cleanupLifecycle();
      cleanupErrors();
    };
  }, []);

  return <PageViewTracker />;
}
