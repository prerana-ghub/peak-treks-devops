# Kubernetes manifests

Files:
- deployment.yml, service.yml, hpa.yml: the PEAK app
- postgres.yml: database with a persistent volume
- db-init-job.yml: creates the tables once

Secrets are created by hand and never committed. Replace every <placeholder>
and keep the Postgres password letters and numbers only:

kubectl create secret generic peak-secrets \
  --from-literal=SECRET_KEY=<64-hex-characters> \
  --from-literal=POSTGRES_PASSWORD=<password> \
  --from-literal=DATABASE_URL=postgresql://peak:<password>@postgres:5432/peak \
  --from-literal=MAIL_USERNAME=<gmail-address> \
  --from-literal=MAIL_PASSWORD=<gmail-app-password> \
  --from-literal=ENQUIRY_INBOX=<inbox-address>

Generate a secret key with:
python3 -c "import secrets; print(secrets.token_hex(32))"