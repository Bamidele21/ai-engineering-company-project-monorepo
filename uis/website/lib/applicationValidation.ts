export type FormValues = {
  fullName: string;
  email: string;
  phone: string;
  country: string;
  experience: string;
  sector: string;
  english: string;
  availability: string;
  linkedin: string;
  comments: string;
  policy: boolean;
};

export type FormErrors = Partial<Record<keyof FormValues, string>>;

export const INITIAL_VALUES: FormValues = {
  fullName: "",
  email: "",
  phone: "",
  country: "",
  experience: "",
  sector: "",
  english: "",
  availability: "",
  linkedin: "",
  comments: "",
  policy: false,
};

export const COMMENTS_LIMIT = 500;

export function validateField(name: keyof FormValues, values: FormValues): string {
  const fullName = values.fullName.trim();
  const email = values.email.trim();
  const phone = values.phone.trim();
  const linkedin = values.linkedin.trim();
  const experience = Number(values.experience);
  const remaining = COMMENTS_LIMIT - values.comments.length;

  if (name === "fullName") {
    if (!/^\S+\s+\S+/.test(fullName)) {
      return "Name must contain at least first and last name";
    }
  }

  if (name === "email") {
    if (!/^\S+@\S+\.\S+$/.test(email)) {
      return "Enter a valid email (example: name@company.com)";
    }
  }

  if (name === "phone") {
    if (!/^\+\d{1,3}\s?\d{3,}$/.test(phone)) {
      return "Phone must include country code (example: +34 612 345 678)";
    }
  }

  if (name === "country") {
    if (!values.country) {
      return "Select your country of residence";
    }
  }

  if (name === "experience") {
    if (Number.isNaN(experience) || experience < 0 || experience > 50) {
      return "Years of experience must be between 0 and 50";
    }
  }

  if (name === "sector") {
    if (!values.sector) {
      return "Select your sector of interest";
    }
  }

  if (name === "english") {
    if (!values.english) {
      return "Indicate your English level";
    }
  }

  if (name === "availability") {
    if (!values.availability) {
      return "Select your availability";
    }
  }

  if (name === "linkedin") {
    if (linkedin && !/^https?:\/\//.test(linkedin)) {
      return "If you include LinkedIn, it must be a valid URL";
    }
  }

  if (name === "comments") {
    if (values.comments.length > COMMENTS_LIMIT) {
      return `Comments cannot exceed ${COMMENTS_LIMIT} characters (${remaining} remaining)`;
    }
  }

  if (name === "policy") {
    if (!values.policy) {
      return "You must accept the data processing policy to continue";
    }
  }

  return "";
}

export function validateAll(values: FormValues): FormErrors {
  const nextErrors: FormErrors = {};

  (Object.keys(values) as (keyof FormValues)[]).forEach((key) => {
    const message = validateField(key, values);
    if (message) {
      nextErrors[key] = message;
    }
  });

  return nextErrors;
}
