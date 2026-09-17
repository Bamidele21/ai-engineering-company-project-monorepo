export type UserRole = "admin" | "manager" | "user";

export interface AuthUser {
  id: number;
  email: string;
  is_active: boolean;
  role: UserRole;
  created_at: string;
}

export interface Profile {
  id: number;
  user_id: number;
  name: string;
  phone: string | null;
  address: string | null;
}

export interface UserWithProfile extends AuthUser {
  profile: Profile;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface RegisterPayload {
  email: string;
  password: string;
  name?: string;
  phone?: string;
  address?: string;
}

export interface ProfileUpdatePayload {
  name: string;
  phone: string | null;
  address: string | null;
}

export interface ForgotPasswordPayload {
  email: string;
}

export interface ResetPasswordPayload {
  token: string;
  newPassword: string;
}

export interface ChangePasswordPayload {
  currentPassword: string;
  newPassword: string;
}
