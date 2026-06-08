# Sign in with Apple Setup

Valentina Web supports Apple as an authentication provider. Apple is different
from the other providers in two ways:

- The OAuth client is a **Services ID**, not your app's bundle ID.
- There is **no static client secret**. The server signs a short-lived JWT from
  a downloaded `.p8` private key on every login, so you provide the key material
  (Team ID, Key ID, `.p8` contents) instead of a client secret.

Requires a paid Apple Developer account. All steps are in the
[Apple Developer portal](https://developer.apple.com/account) under
**Certificates, Identifiers & Profiles**.

> **Matching iOS sign-ins:** Apple's user identifier (`sub`) is the same across a
> developer team **only when the apps are grouped**. If you also use Sign in with
> Apple in an iOS app, group the Services ID under that app's primary App ID
> (Step 3) so web logins resolve to the same user as iOS. Otherwise web sign-ins
> create separate accounts. This matters especially for users who chose
> "Hide My Email" — their private relay address is the only thing tying the
> accounts together, and it differs from any other provider's email.

## 1. Enable the App ID as a primary App ID

1. Go to **Identifiers** and select your app's App ID (e.g. `org.example.app`).
2. Under **Capabilities**, enable **Sign in with Apple** and click **Configure**.
3. Choose **Enable as a primary App ID** and save.

## 2. Create a Services ID (the web client ID)

1. In **Identifiers**, click **+** and choose **Services IDs**.
2. Set a description and an identifier (e.g. `org.example.web`). It **must differ
   from the App ID**. This value is `VWEB_OAUTH__APPLE__SERVICES_ID`.
3. Register it, then click into it.

## 3. Configure web authentication

1. With the Services ID open, enable **Sign in with Apple** and click **Configure**.
2. **Primary App ID**: select the App ID from Step 1 (this groups them).
3. **Domains and Subdomains**: your bare domain, e.g. `your-domain.com`
   (no `https://`, no path). Apple does not accept `localhost`.
4. **Return URLs**: the full callback URL.

| Environment | Return URL |
|---|---|
| Development | Not supported — Apple rejects `localhost`; test against a real HTTPS domain. |
| Production | `https://your-domain.com/auth/apple/callback` |

5. Check the domain and return URL boxes, click **Done**, then **Continue** and **Save**.

> No domain-association file is required for login. That file only applies to
> Apple's Private Email Relay, which Valentina Web does not use.

## 4. Create a Sign in with Apple key

1. Go to **Keys** and click **+**.
2. Name the key, enable **Sign in with Apple**, click **Configure**, select the
   primary App ID from Step 1, and save.
3. Click **Continue**, then **Register**.
4. Note the **Key ID** (`VWEB_OAUTH__APPLE__KEY_ID`) and **Download** the
   `AuthKey_XXXXXXXXXX.p8` file. **Apple allows this download only once** — store
   it somewhere safe.

## 5. Find your Team ID

Your 10-character Team ID is on the [Membership](https://developer.apple.com/account)
page (`VWEB_OAUTH__APPLE__TEAM_ID`).

## 6. Set Environment Variables

Add the four values to your `.env.secret` file. The `.p8` contents are multi-line
PEM; store them on one line with the newlines escaped as `\n`:

```bash
VWEB_OAUTH__APPLE__SERVICES_ID=org.example.web
VWEB_OAUTH__APPLE__TEAM_ID=ABCDE12345
VWEB_OAUTH__APPLE__KEY_ID=KEY1234567
VWEB_OAUTH__APPLE__PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIG...\n-----END PRIVATE KEY-----\n"
```

To generate the escaped one-liner from the downloaded key:

```bash
awk 'BEGIN{ORS="\\n"} {print}' AuthKey_KEY1234567.p8
```

Alternatively, you can drop the `-----BEGIN/END PRIVATE KEY-----` lines and store
just the base64 body on a single line (no quotes or escaping needed) — the app
rebuilds the PEM armor before signing:

```bash
VWEB_OAUTH__APPLE__PRIVATE_KEY=MIG...rest-of-the-base64-body-on-one-line...
```

On Railway, you can instead paste the raw multi-line PEM directly into the
variable's value field. All three forms are accepted.

## 7. Required Scopes

The application requests these scopes automatically:

- `openid` — OpenID Connect authentication (and triggers id-token validation)
- `name` — the user's name (returned only on the first authorization)
- `email` — the user's email address (or a private relay address)
