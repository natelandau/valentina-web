# Google OAuth Setup

Valentina Web supports Google as an authentication provider. To configure it:

## 1. Create a Google Cloud Project

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Click the project dropdown in the top navigation bar
3. Click **New Project**, give it a name (e.g., "Valentina Web"), and click **Create**
4. Make sure the new project is selected in the project dropdown

## 2. Configure the OAuth Consent Screen

Before creating credentials, you must configure the consent screen that users see when logging in:

1. Navigate to **APIs & Services** > [**OAuth consent screen**](https://console.cloud.google.com/apis/credentials/consent)
2. Select **External** as the user type (allows any Google account to log in) and click **Create**
3. Fill in the required fields on the **App information** page:
   - **App name**: Your application name (e.g., "Valentina Web")
   - **User support email**: Select your email address
   - **Developer contact information**: Enter your email address
4. Click **Save and Continue**
5. On the **Scopes** page, click **Add or Remove Scopes** and add:
   - `openid`
   - `.../auth/userinfo.email`
   - `.../auth/userinfo.profile`
6. Click **Update**, then **Save and Continue**
7. On the **Test users** page, click **Add Users** and add the Google email addresses of anyone who needs to log in during testing. While the app is in "Testing" publishing status, only these users can authenticate.
8. Click **Save and Continue**, then **Back to Dashboard**

> **Note:** The app starts in "Testing" mode, which limits login to the test users you added. To allow any Google account to log in, click **Publish App** on the consent screen dashboard. For internal/small-team use, you can stay in testing mode and just add your team as test users.

## 3. Create OAuth Client Credentials

1. Navigate to **APIs & Services** > [**Credentials**](https://console.cloud.google.com/apis/credentials)
2. Click **Create Credentials** > **OAuth client ID**
3. Select **Web application** as the application type
4. Give it a name (e.g., "Valentina Web Client")
5. Under **Authorized redirect URIs**, click **Add URI** and enter your callback URL:

| Environment | Authorized redirect URI |
|---|---|
| Development | `http://127.0.0.1:8089/auth/google/callback` |
| Production | `https://your-domain.com/auth/google/callback` |

6. Click **Create**

## 4. Get Credentials

After creating the client, a dialog displays your credentials:

- **Client ID** — Copy for `VWEB_OAUTH__GOOGLE__CLIENT_ID`
- **Client Secret** — Copy for `VWEB_OAUTH__GOOGLE__CLIENT_SECRET`

You can also find these later on the [Credentials](https://console.cloud.google.com/apis/credentials) page by clicking on your OAuth client name.

## 5. Set Environment Variables

Add the credentials to your `.env.secret` file:

```bash
VWEB_OAUTH__GOOGLE__CLIENT_ID=your-client-id
VWEB_OAUTH__GOOGLE__CLIENT_SECRET=your-client-secret
```

## 6. Required Scopes

The application requests the following Google OAuth scopes (configured automatically):

- `openid` — OpenID Connect authentication
- `email` — Access the user's email address
- `profile` — Access the user's name, profile picture, and locale
