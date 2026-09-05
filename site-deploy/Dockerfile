FROM caddy:2.10-alpine@sha256:4c6e91c6ed0e2fa03efd5b44747b625fec79bc9cd06ac5235a779726618e530d

# Port 80 is allowed by the container sysctl; file capabilities conflict with cap_drop ALL.
RUN setcap -r /usr/bin/caddy

COPY site-deploy/Caddyfile /etc/caddy/Caddyfile
COPY site/ /srv
