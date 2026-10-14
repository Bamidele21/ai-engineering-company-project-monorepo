"use client";

import { useCallback, useState } from "react";

interface AuthSubmitOptions {
  action: () => Promise<void>;
  fallback: string;
  // When true, never surface the thrown error's message (used by flows that
  // must not reveal whether an account exists).
  useFallbackOnly?: boolean;
  // Optional synchronous validation; a returned string blocks submission.
  validate?: () => string | null;
}

export function useAuthSubmit() {
  const [formError, setFormError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  const run = useCallback(
    async ({
      action,
      fallback,
      useFallbackOnly = false,
      validate,
    }: AuthSubmitOptions): Promise<boolean> => {
      setFormError("");

      if (validate) {
        const validationMessage = validate();
        if (validationMessage) {
          setFormError(validationMessage);
          return false;
        }
      }

      setIsSubmitting(true);

      try {
        await action();
        return true;
      } catch (error) {
        setFormError(
          useFallbackOnly || !(error instanceof Error) ? fallback : error.message
        );
        return false;
      } finally {
        setIsSubmitting(false);
      }
    },
    []
  );

  return { formError, setFormError, isSubmitting, run };
}
