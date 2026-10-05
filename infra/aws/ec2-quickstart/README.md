# EC2 quickstart — NextStep live demo on one instance

Runs the whole stack from `docker-compose.prod.yml` on a single EC2 instance.

```
Internet ──80/443──► EC2 (Ubuntu 24.04, Docker)
                     │
                     ├─ Caddy          HTTPS + Let's Encrypt (only when domain_name is set)
                     └─ nginx          reverse proxy from init_config/nginx/nginx.conf
                        ├─ /          → frontend (Angular, nginx)
├─ /api /hubs /uploads → backend (.NET)
                         │     └─ /api/agents/* proxied to agents (FastAPI)
                         ├─ /auth      → Keycloak
                        └─ PostgreSQL (internal only, never exposed)
```

**What Terraform creates:** 1 EC2 instance (encrypted gp3 root disk, IMDSv2 only),
1 Elastic IP, 1 security group (80/443 in; SSH closed unless you open it),
1 IAM role (SSM Session Manager + read one parameter), and 1 SSM SecureString
parameter holding your `.env`.

## Deploy

1. **Prepare the production `.env`** (git-ignored) in this folder:
   ```bash
   cp ../../../.env.example .env.prod
   ```
   Set strong values for `POSTGRES_PASSWORD` and `KEYCLOAK_ADMIN_PASSWORD`, and at least
   one LLM key (`GROQ_API_KEY` or `GEMINI_API_KEY`). `PUBLIC_URL` and `HTTP_PORT` are set
   automatically on the instance.

2. **Configure:**
   ```bash
   cp terraform.tfvars.example terraform.tfvars   # set repo_url, repo_branch, optional domain
   ```
   The repository must be cloneable over HTTPS without credentials (public repo).

3. **Apply:**
   ```bash
   terraform init
   terraform apply
   ```

4. **With a domain:** create a DNS `A` record for `domain_name` → the `public_ip` output.
   Caddy obtains the certificate as soon as DNS resolves.

5. **Wait ~10–15 minutes** (Docker images are built on first boot), then open `app_url`.
   Follow progress:
   ```bash
   $(terraform output -raw connect_command)
   sudo tail -f /var/log/nextstep-bootstrap.log
   ```

## GitHub Actions variables

The deploy workflow authenticates with OIDC and reads two repository **variables**
(Settings → Secrets and variables → Actions → Variables). No repository *secrets*
are needed: the production `.env` lives in SSM Parameter Store on the instance.

| Variable | Required | Value |
|---|---|---|
| `AWS_EC2_ROLE_ARN` | yes | `terraform output -raw github_actions_role_arn` |
| `AWS_REGION` | no | same region as `aws_region` in `terraform.tfvars`; defaults to `us-east-1` |

`AWS_ROLE_ARN` is accepted as a fallback name. If `github_repo` in
`terraform.tfvars` does not match the repository running the workflow, the trust
policy rejects the token and the AWS credentials step fails with `AccessDenied`.

## Operate

| Task | Command (inside `aws ssm start-session`) |
|---|---|
| Status | `cd /opt/nextstep && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml ps` |
| Logs | `... logs -f backend` |
| Deploy new code | `sudo git pull && sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |
| Load demo data | `cat init_config/postgres/seeds/0*.sql \| sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -v ON_ERROR_STOP=1 -1 -v user_email=you@example.com'` (register and log in once first) |

Changing `.env.prod` and re-running `terraform apply` **replaces the instance**
(the boot script only runs on first boot). The database lives on that instance, so
back it up first (`pg_dump`) if it holds data you need.

**Tear down:** `terraform destroy` (also releases the Elastic IP).

## Limits (by design)

Single instance in one AZ: no automatic failover, and the database is on the same
disk as the app. For production traffic use [`../enterprise-fargate`](../enterprise-fargate/).
Without `domain_name` the app is served over plain HTTP and the Keycloak realm is
switched to `sslRequired=NONE` so login works — use a domain for anything beyond a demo.
