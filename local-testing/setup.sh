#!/usr/bin/env bash
# Generates the secrets/certs local-testing/ needs (gitignored — regenerate
# per machine, never commit). Idempotent: skips anything that already
# exists. Run once before `docker compose -f compose.yml -f
# local-testing/docker-compose.proxy.yml up -d`.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

gen_secret() {
	local file="$1"
	[ -f "$file" ] && return
	python3 -c "import secrets; print(secrets.token_urlsafe(48))" > "$file"
}

echo "== Authelia secrets =="
gen_secret authelia/.jwt_secret
gen_secret authelia/.session_secret
gen_secret authelia/.storage_encryption_key
gen_secret authelia/.oidc_hmac_secret

if [ ! -f authelia/oidc_issuer_private_key.pem ]; then
	openssl genrsa -out authelia/oidc_issuer_private_key.pem 4096
fi

if [ ! -f authelia/.admin_password_plaintext ]; then
	python3 -c "import secrets; print(secrets.token_urlsafe(16))" > authelia/.admin_password_plaintext
fi
if [ ! -f authelia/.admin_password_hash ]; then
	docker run --rm authelia/authelia:latest authelia crypto hash generate bcrypt \
		--password "$(cat authelia/.admin_password_plaintext)" \
		| grep -oE '\$2b\$.*' > authelia/.admin_password_hash
fi

if [ ! -f authelia/.oidc_client_secret_plaintext ]; then
	python3 -c "import secrets; print(secrets.token_urlsafe(32))" > authelia/.oidc_client_secret_plaintext
fi
if [ ! -f authelia/.oidc_client_secret_hash ]; then
	docker run --rm authelia/authelia:latest authelia crypto hash generate pbkdf2 \
		--password "$(cat authelia/.oidc_client_secret_plaintext)" \
		| grep -oE '\$pbkdf2.*' > authelia/.oidc_client_secret_hash
fi

# users_database.yml and configuration.yml's client_secret digest are
# checked in with the placeholder values this script produces the first
# time it runs — if you regenerate the admin password or client secret
# hash above, paste the new digest into both files yourself.
echo "Authelia admin login: username 'admin', password: $(cat authelia/.admin_password_plaintext)"
echo "QEComp OIDC_CLIENT_SECRET env var value: $(cat authelia/.oidc_client_secret_plaintext)"

echo "== TLS cert for *.vex.localhost (Traefik's default) =="
mkdir -p traefik/certs
if [ ! -f traefik/certs/vex.localhost.crt ]; then
	cat > traefik/certs/san.cnf <<-'EOF'
	[req]
	distinguished_name = req_distinguished_name
	x509_extensions = v3_req
	prompt = no
	[req_distinguished_name]
	CN = vex.localhost
	[v3_req]
	keyUsage = keyEncipherment, digitalSignature
	extendedKeyUsage = serverAuth
	subjectAltName = @alt_names
	[alt_names]
	DNS.1 = vex.localhost
	DNS.2 = *.vex.localhost
	EOF
	openssl req -x509 -nodes -newkey rsa:2048 \
		-keyout traefik/certs/vex.localhost.key \
		-out traefik/certs/vex.localhost.crt \
		-days 825 -config traefik/certs/san.cnf
fi

echo
echo "Done. Backend processes that call out to https://authelia.vex.localhost"
echo "(OIDC discovery/token exchange) need to trust traefik/certs/vex.localhost.crt"
echo "— e.g. append it to your venv's certifi bundle:"
echo '  python3 -c "import certifi; print(certifi.where())"'
