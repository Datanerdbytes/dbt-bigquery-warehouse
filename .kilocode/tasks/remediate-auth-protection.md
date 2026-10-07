# Task: Implement Rate Limiting and Brute-Force Protection on Auth Endpoints

## Target Files
- `my-dash-app/auth.py`

## Issue Description
Public-facing authentication routes (such as `/login`, `/signup`, `/auth/callback`, and `/auth/session`) currently lack rate limiting and explicit account enumeration protection. This exposes the application to credential stuffing, password spraying, and automated user-probing attacks.

## Remediation Requirements
1. **Pre-Implementation Audit**: Review the authentication setup to determine if `flask-login` or another framework is managing sessions, and check how the Flask server instance is exposed within the Dash application shell.
2. **Rate Limiting Integration**: Add robust rate limiting (e.g., using `flask-limiter` tied to a memory backend or client IP addresses) to all exposed authentication and session verification routes.
3. **Account Enumeration Protection**: Ensure all login, password-reset, or registration routes return generic error messages (e.g., *"Invalid email or password"*) regardless of whether the email address actually exists in the database.
4. **Testing Verification**: Generate matching `pytest` unit tests that simulate successive rapid requests to confirm that a `429 Too Many Requests` status code is triggered correctly, and verify that the authentication failure responses match the required generic patterns.
