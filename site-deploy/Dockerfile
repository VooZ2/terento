FROM caddy:2.11-alpine@sha256:d8542f48d34a9cf4e4c11a478865229840e87e4c96ea3f439101f31a5d35f75f

# Port 80 is allowed by the container sysctl; file capabilities conflict with cap_drop ALL.
RUN setcap -r /usr/bin/caddy

COPY site-deploy/Caddyfile /etc/caddy/Caddyfile
# The IndexNow key is a server-only read-only mount, never a public image layer.
COPY site/ /srv
