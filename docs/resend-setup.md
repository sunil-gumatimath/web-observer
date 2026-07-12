# Resend email setup

Web Observer sends alert emails through the **notification worker** using the official Resend SDK.

## Configure (root `.env`)

```env
RESEND_API_KEY=re_your_real_key_here
EMAIL_FROM=onboarding@resend.dev
```

- **Testing:** use `onboarding@resend.dev` as `from` (Resend allows this without a custom domain).
- **Production:** verify your domain in Resend, then set e.g. `EMAIL_FROM=alerts@yourdomain.com`.

Never commit real keys. `.env` is gitignored.

## Test send

```powershell
cd backend
.\.venv\Scripts\python scripts\send_test_email.py --to you@example.com
```

## How product emails work

1. A change is detected → outbox row created  
2. Dramatiq `notifications` worker calls `app.services.email.send_email`  
3. Resend delivers to the workspace’s **email** notification channel  

Add an alert email in the UI: **Settings → Alert channels**.

## Security

If a key was pasted into chat or a ticket, **rotate it** in the Resend dashboard and update `.env`.
