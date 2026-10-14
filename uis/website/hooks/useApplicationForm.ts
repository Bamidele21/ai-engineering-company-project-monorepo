"use client";

import { useCallback, useMemo, useState } from "react";
import {
  COMMENTS_LIMIT,
  type FormErrors,
  type FormValues,
  INITIAL_VALUES,
  validateAll,
  validateField,
} from "../lib/applicationValidation";

export function useApplicationForm() {
  const [values, setValues] = useState<FormValues>(INITIAL_VALUES);
  const [errors, setErrors] = useState<FormErrors>({});

  const commentsRemaining = useMemo(
    () => COMMENTS_LIMIT - values.comments.length,
    [values.comments]
  );

  const setFieldValue = useCallback((name: keyof FormValues, value: string | boolean) => {
    setValues((current) => ({
      ...current,
      [name]: value,
    }));
  }, []);

  const validateAndSetField = useCallback((name: keyof FormValues, nextValues: FormValues) => {
    setErrors((current) => ({
      ...current,
      [name]: validateField(name, nextValues),
    }));
  }, []);

  const setFieldAndValidate = useCallback(
    (name: keyof FormValues, value: string | boolean) => {
      const nextValues = { ...values, [name]: value };
      setValues(nextValues);
      validateAndSetField(name, nextValues);
    },
    [validateAndSetField, values]
  );

  const handleBlur = useCallback(
    (name: keyof FormValues) => {
      validateAndSetField(name, values);
    },
    [validateAndSetField, values]
  );

  const validate = useCallback(() => {
    const nextErrors = validateAll(values);
    setErrors(nextErrors);
    return nextErrors;
  }, [values]);

  const reset = useCallback(() => {
    setValues(INITIAL_VALUES);
    setErrors({});
  }, []);

  return {
    values,
    errors,
    commentsRemaining,
    setFieldValue,
    setFieldAndValidate,
    handleBlur,
    validate,
    reset,
  };
}
