# Auth Service - Environment Configuration

## Kubernetes (Production/Dev)

OAuth credentials are managed via **AWS Systems Manager Parameter Store** and automatically injected using **External Secrets Operator**.

### SSM Parameters

```
/sesacthon/dev/api/auth/google-client-id
/sesacthon/dev/api/auth/google-client-secret
/sesacthon/dev/api/auth/kakao-client-id
/sesacthon/dev/api/auth/naver-client-id
/sesacthon/dev/api/auth/naver-client-secret
```

### ExternalSecret Configuration

See: `workloads/secrets/auth-external-secret.yaml`

The ExternalSecret automatically creates a Kubernetes Secret `auth-secret` in the `auth` namespace with all OAuth credentials.

## Local Development (Docker Compose)

For local development, create `.env.local` from the template:

```bash
cd domains/auth
cp env.local.sample .env.local
```

Then edit `.env.local` and add your **personal OAuth credentials** (NOT production keys):

1. **Google OAuth**: https://console.cloud.google.com/apis/credentials
2. **Kakao OAuth**: https://developers.kakao.com/console/app
3. **Naver OAuth**: https://developers.naver.com/apps

⚠️ **IMPORTANT**: Never commit `.env.local` with real credentials to git!

## Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `AUTH_GOOGLE_CLIENT_ID` | Google OAuth Client ID | `123-abc.apps.googleusercontent.com` |
| `AUTH_GOOGLE_CLIENT_SECRET` | Google OAuth Client Secret | `GOCSPX-xxx` |
| `AUTH_KAKAO_CLIENT_ID` | Kakao REST API Key | `abc123...` |
| `AUTH_NAVER_CLIENT_ID` | Naver Client ID | `K84iKp...` |
| `AUTH_NAVER_CLIENT_SECRET` | Naver Client Secret | `mpILlX...` |

## How It Works

### Kubernetes
```
AWS SSM → External Secrets Operator → Kubernetes Secret → Pod Environment Variables
```

### Local Development
```
.env.local (ignored by git) → Docker Compose → Container Environment Variables
```

