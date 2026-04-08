# Discord OAuth Setup

Valentina Web uses Discord as one of its authentication providers. To configure it:

## 1. Create a Discord Application

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Click **New Application** and give it a name
3. Navigate to **OAuth2** in the left sidebar

## 2. Configure OAuth2

Under **OAuth2 > General**:

- **Client ID** — Copy this value for `VWEB_OAUTH__DISCORD__CLIENT_ID`
- **Client Secret** — Click **Reset Secret**, then copy the value for `VWEB_OAUTH__DISCORD__CLIENT_SECRET`

Under **OAuth2 > Redirects**, add your callback URL:

| Environment | Redirect URL |
|---|---|
| Development | `http://127.0.0.1:8089/auth/discord/callback` |
| Production | `https://your-domain.com/auth/discord/callback` |

## 3. Set Environment Variables

Add the credentials to your `.env.secret` file:

```bash
VWEB_OAUTH__DISCORD__CLIENT_ID=your-client-id
VWEB_OAUTH__DISCORD__CLIENT_SECRET=your-client-secret
```

You also need to set `VWEB_API__SERVER_ADMIN_USER_ID` to the API user ID of the server administrator. This user is used as the `requesting_user_id` when creating new accounts during OAuth registration.

## 4. Required Scopes

The application requests the following Discord OAuth scopes (configured automatically):

- `identify` — Access the user's Discord ID, username, avatar, and discriminator
- `email` — Access the user's email address

No bot permissions or guild access are required.
