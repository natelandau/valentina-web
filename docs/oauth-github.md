# GitHub OAuth Setup

Valentina Web supports GitHub as an authentication provider. To configure it:

## 1. Create a GitHub OAuth App

1. Go to [GitHub Developer Settings](https://github.com/settings/developers)
2. Click **OAuth Apps** > **New OAuth App**
3. Fill in the application details:
   - **Application name**: Your app name (e.g., "Valentina Web")
   - **Homepage URL**: Your application URL (e.g., `http://127.0.0.1:8089`)
   - **Authorization callback URL**: See the table below

## 2. Configure Callback URL

| Environment | Authorization callback URL |
|---|---|
| Development | `http://127.0.0.1:8089/auth/github/callback` |
| Production | `https://your-domain.com/auth/github/callback` |

## 3. Get Credentials

After creating the app:

- **Client ID** — Displayed on the app page. Copy for `VWEB_OAUTH__GITHUB__CLIENT_ID`
- **Client Secret** — Click **Generate a new client secret**. Copy the value for `VWEB_OAUTH__GITHUB__CLIENT_SECRET`

> **Note:** The client secret is only shown once. Save it immediately.

## 4. Set Environment Variables

Add the credentials to your `.env.secret` file:

```bash
VWEB_OAUTH__GITHUB__CLIENT_ID=your-client-id
VWEB_OAUTH__GITHUB__CLIENT_SECRET=your-client-secret
```

## 5. Required Scopes

The application requests the following GitHub OAuth scopes (configured automatically):

- `read:user` — Access the user's GitHub profile (username, avatar, profile URL)
- `user:email` — Access the user's email address
