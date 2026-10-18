export type SupplierCountry = "Spain" | "USA";
export type SupplierStatus = "active" | "suspended";
export type SupplierCategory =
  | "job_boards"
  | "ats_software"
  | "assessment_tools"
  | "training_platforms"
  | "payroll_and_hr_software"
  | "video_interview"
  | "background_check"
  | "office_and_facilities"
  | "it_and_software_licenses";

export type SupplierRecord = {
  id: number;
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: number;
  currency: "EUR" | "USD";
  updated_at: string;
  status: SupplierStatus;
  contract_renewal_date: string | null;
  contact_email: string | null;
  notes: string | null;
};

export type SupplierCreatePayload = {
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: number;
  currency: "EUR" | "USD";
  status: SupplierStatus;
  contract_renewal_date?: string;
  contact_email?: string;
  notes?: string;
};

export const SUPPLIERS_API_URL =
  process.env.NEXT_PUBLIC_SUPPLIERS_API_URL ?? "http://localhost:8000";

export const CATEGORY_OPTIONS: Array<{ value: SupplierCategory; label: string }> = [
  { value: "job_boards", label: "Job boards" },
  { value: "ats_software", label: "ATS software" },
  { value: "assessment_tools", label: "Assessment tools" },
  { value: "training_platforms", label: "Training platforms" },
  {
    value: "payroll_and_hr_software",
    label: "Payroll and HR software",
  },
  { value: "video_interview", label: "Video interview" },
  { value: "background_check", label: "Background check" },
  { value: "office_and_facilities", label: "Office and facilities" },
  {
    value: "it_and_software_licenses",
    label: "IT and software licenses",
  },
];

export type NewSupplierForm = {
  name: string;
  country: SupplierCountry;
  categories: SupplierCategory[];
  monthly_rate: string;
  status: SupplierStatus;
  contract_renewal_date: string;
  contact_email: string;
  notes: string;
};

export const INITIAL_FORM: NewSupplierForm = {
  name: "",
  country: "Spain",
  categories: [],
  monthly_rate: "",
  status: "active",
  contract_renewal_date: "",
  contact_email: "",
  notes: "",
};

export function isRenewalWithin60Days(value: string | null): boolean {
  if (!value) {
    return false;
  }

  const renewal = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(renewal.getTime())) {
    return false;
  }

  const now = new Date();
  const today = new Date(
    Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate())
  );
  const diffDays = Math.ceil(
    (renewal.getTime() - today.getTime()) / (1000 * 60 * 60 * 24)
  );

  return diffDays >= 0 && diffDays <= 60;
}
