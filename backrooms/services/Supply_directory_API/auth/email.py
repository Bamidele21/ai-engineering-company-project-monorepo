import os

import resend
from dotenv import load_dotenv


load_dotenv()

DEFAULT_RESET_URL = "http://localhost:3000/reset-password"
DEFAULT_FROM_EMAIL = "Nexova <onboarding@resend.dev>"


def build_password_reset_url(token: str) -> str:
	base_url = os.getenv("PASSWORD_RESET_URL", DEFAULT_RESET_URL)
	separator = "&" if "?" in base_url else "?"
	return f"{base_url}{separator}token={token}"


def _render_email(reset_url: str, expires_in_minutes: int) -> tuple[str, str]:
	text = (
		"Hello,\n\n"
		"We received a request to reset your Nexova password.\n"
		f"Open this link to choose a new password (valid for {expires_in_minutes} minutes):\n\n"
		f"{reset_url}\n\n"
		"If you did not request a password reset, you can safely ignore this email.\n"
	)
	html = f"""<!DOCTYPE html>
<html lang="en">
	<head>
		<meta charset="utf-8" />
		<meta name="viewport" content="width=device-width, initial-scale=1" />
		<title>Reset your Nexova password</title>
	</head>
	<body style="margin:0;padding:24px;background-color:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
		<div style="max-width:520px;margin:0 auto;background-color:#ffffff;border-radius:12px;padding:32px;">
			<p style="margin:0 0 8px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:#0f766e;">Nexova</p>
			<h1 style="margin:0 0 16px;font-size:22px;line-height:1.3;">Reset your password</h1>
			<p style="margin:0 0 24px;font-size:15px;line-height:1.6;color:#334155;">
				We received a request to reset your Nexova password. This link is valid for {expires_in_minutes} minutes and can be used once.
			</p>
			<a href="{reset_url}" style="display:inline-block;background-color:#0f766e;color:#ffffff;text-decoration:none;font-size:16px;font-weight:bold;padding:14px 24px;border-radius:8px;">Choose a new password</a>
			<p style="margin:24px 0 8px;font-size:13px;line-height:1.6;color:#64748b;">
				If the button does not work, copy and paste this address into your browser:
			</p>
			<p style="margin:0 0 24px;font-size:13px;line-height:1.6;word-break:break-all;color:#0f766e;">{reset_url}</p>
			<p style="margin:0;font-size:13px;line-height:1.6;color:#64748b;">
				If you did not request a password reset, you can safely ignore this email.
			</p>
		</div>
	</body>
</html>"""
	return html, text


def send_password_reset_email(
	to_email: str, token: str, expires_in_minutes: int
) -> None:
	api_key = os.getenv("RESEND_API_KEY")
	if not api_key:
		raise RuntimeError("RESEND_API_KEY must be configured")

	from_email = os.getenv("RESEND_FROM_EMAIL", DEFAULT_FROM_EMAIL)
	reset_url = build_password_reset_url(token)
	html, text = _render_email(reset_url, expires_in_minutes)

	resend.api_key = api_key
	resend.Emails.send(
		{
			"from": from_email,
			"to": [to_email],
			"subject": "Reset your Nexova password",
			"html": html,
			"text": text,
		}
	)
