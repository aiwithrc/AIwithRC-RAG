# Deploy on a VPS

This puts AIwithRC-RAG on the internet at `https://your-domain` with a free, auto-renewing HTTPS certificate.
About 20 minutes. You need:

- A VPS with **2 GB RAM or more**, 2 vCPUs and 20 GB disk, running Ubuntu 24.04 or Debian 12 (Hetzner CX22,
  DigitalOcean Basic, Lightsail and similar all work). No GPU needed.
- A domain or subdomain you control, e.g. `rag.example.com`.
- An API key for a cloud model (Anthropic, OpenAI or OpenRouter). A VPS this size can't run a local LLM, but
  documents are still embedded **on the server**; only the passages needed for each answer go to the model.

Measured: indexing a 50-page PDF peaks at about 950 MB of memory, so 2 GB leaves room for the OS and Caddy.

## 1. Point the domain at the server

At your DNS provider, add an **A record**: `rag.example.com → <your server's IPv4>` (and an AAAA record if the
server has IPv6). Check it from your computer:

```bash
nslookup rag.example.com
```

## 2. Prepare the server

SSH in as root (or a sudo user) and run:

```bash
apt update && apt -y upgrade
curl -fsSL https://get.docker.com | sh

# Firewall: SSH, HTTP (for the certificate) and HTTPS only.
ufw allow OpenSSH && ufw allow 80/tcp && ufw allow 443/tcp && ufw allow 443/udp && ufw --force enable

# 2 GB of swap: headroom for re-indexing large documents on a 2 GB server.
fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab
```

## 3. Get the code and configure it

```bash
git clone https://github.com/aiwithrc/aiwithrc-rag.git /opt/aiwithrc-rag
cd /opt/aiwithrc-rag
cp .env.example .env
nano .env
```

Set at least these in `.env`:

```bash
APP_SECRET=<paste the output of: python3 -c "import secrets; print(secrets.token_urlsafe(48))">
DOMAIN=rag.example.com
PUBLIC_URL=https://rag.example.com
ALLOW_SIGNUP=false
```

`APP_SECRET` encrypts saved API keys: **set it once and never change it** (changing it makes saved keys unreadable).
`COOKIE_SECURE` is turned on for you by the VPS compose file.

## 4. Start it

```bash
docker compose -f deploy/docker-compose.vps.yml up -d --build
```

The first build takes 5–10 minutes (it bakes the embedding and rerank models into the image). Then open
`https://rag.example.com`. Caddy fetches the certificate on the first request, which can take a few seconds.

**Create your account straight away.** The first account becomes the workspace owner, and sign-up then closes
(unless `ALLOW_SIGNUP=true`). Then:

1. **API keys** → add `https://api.anthropic.com/v1` (or `https://api.openai.com/v1`) with your key.
2. **Knowledge bases** → upload a document, then ask a question in **Chat**.
3. **Settings** → with a cloud model you can raise **Context per answer** to 32,000 tokens for long reports.

To add teammates: set `ALLOW_SIGNUP=true`, restart (step 6), let them sign up, then set it back to `false`.
Or create accounts from the command line:

```bash
docker compose -f deploy/docker-compose.vps.yml exec app python -m app.cli create-user --email them@example.com --name "Their Name"
```

## 5. Check it's healthy

```bash
docker compose -f deploy/docker-compose.vps.yml ps          # both services "running (healthy)"
docker compose -f deploy/docker-compose.vps.yml logs -f app  # Ctrl+C to stop following
docker stats --no-stream                                    # memory use
docker compose -f deploy/docker-compose.vps.yml exec app python -m app.cli check   # index health
```

## 6. Everyday operations

Save typing with an alias:

```bash
echo "alias rag='docker compose -f /opt/aiwithrc-rag/deploy/docker-compose.vps.yml'" >> ~/.bashrc && source ~/.bashrc
```

| Task | Command |
|---|---|
| Restart after editing `.env` | `rag up -d` |
| Upgrade to the latest version | `cd /opt/aiwithrc-rag && git pull && rag up -d --build` (migrations run on start) |
| Reset a forgotten password | `rag exec app python -m app.cli reset-password --email you@example.com` |
| Re-index everything | `rag exec app python -m app.cli reindex` |
| Stop | `rag down` (data is kept in `./data`) |

## 7. Backups

Everything (database, vectors, uploaded files) lives in `/opt/aiwithrc-rag/data`, plus your `.env`.
For a consistent copy, stop the app for a few seconds while archiving:

```bash
cd /opt/aiwithrc-rag
rag stop app && tar czf /root/rag-backup-$(date +%F).tar.gz data .env && rag start app
```

Nightly at 03:00, keeping 14 days:

```bash
crontab -e
# add this line:
0 3 * * * cd /opt/aiwithrc-rag && docker compose -f deploy/docker-compose.vps.yml stop app && tar czf /root/rag-backup-$(date +\%F).tar.gz data .env; docker compose -f deploy/docker-compose.vps.yml start app; find /root -name 'rag-backup-*.tar.gz' -mtime +14 -delete
```

Copy the archives off the server (e.g. `rsync`, or your provider's backup/snapshot feature).
**Restore:** stop the app, replace `data/` and `.env` with the archive's contents, start the app.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Browser shows a certificate error | DNS isn't pointing at the server yet, or ports 80/443 are blocked. `rag logs caddy` shows the reason. |
| "Missing X-Requested-With header" | Something between the browser and the app strips headers; use the Caddyfile as provided. |
| Answers arrive all at once instead of streaming | Another proxy (e.g. Cloudflare with buffering) sits in front; turn off response buffering for this host. |
| Sign-in doesn't stick | `PUBLIC_URL` must be the `https://` address you open, and you must use HTTPS (the cookie is Secure). |
| Upload rejected as too large | Raise `MAX_UPLOAD_MB` in `.env` and `max_size` in `deploy/Caddyfile`, then `rag up -d`. |
| Container restarts under load | Check `docker stats`; add swap (step 2) or move to a 4 GB server. |
