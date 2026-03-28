# Docker Deployment Notes

## Server prerequisites

- Docker Engine with Compose plugin installed
- Repository cloned on the server
- `infra/.env` created from `infra/.env.example`

## Recommended `infra/.env` values for your server

```env
BOT_TOKEN=replace_with_real_bot_token
DATABASE_URL=sqlite+aiosqlite:///app/data/vpn.db
BACKEND_BIND_IP=127.0.0.1
BACKEND_PORT=8000
HYSTERIA_API_URL=http://host.docker.internal:9999
HYSTERIA_API_TOKEN=your_api_secret
HYSTERIA_SERVER_HOST=nikitaluksha.com
HYSTERIA_SERVER_PORT=8443
HYSTERIA_SERVER_SNI=nikitaluksha.com
HYSTERIA_SERVER_INSECURE=0
HYSTERIA_OBFS=
HYSTERIA_OBFS_PASSWORD=
HYSTERIA_REQUEST_TIMEOUT_SECONDS=10
```

## GitHub Actions secrets

- `DEPLOY_HOST`
- `DEPLOY_PORT`
- `DEPLOY_USER`
- `DEPLOY_PATH`
- `DEPLOY_SSH_KEY`
