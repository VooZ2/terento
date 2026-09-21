#!/bin/sh
set -eu

repo_root=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)

if ! command -v docker >/dev/null 2>&1; then
  echo "SKIP: IndexNow Docker/Caddy runtime test is CI-ready but Docker is unavailable locally."
  exit 0
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "FAIL: Docker is available but curl is required for the localhost HTTP checks." >&2
  exit 1
fi

temporary=$(mktemp -d)
image="terento-site-indexnow-runtime-$$"
container="terento-site-indexnow-runtime-$$"
missing_container="${container}-missing"
test_key=$(python3 -c 'import secrets; print(secrets.token_hex(16), end="")')
key_file="$temporary/indexnow-key.txt"

cleanup() {
  docker rm -f "$container" "$missing_container" >/dev/null 2>&1 || true
  docker image rm "$image" >/dev/null 2>&1 || true
  rm -rf -- "$temporary"
}
trap cleanup EXIT INT TERM

printf '%s' "$test_key" > "$key_file"
chmod 0444 "$key_file"

docker build --pull=false --file "$repo_root/site-deploy/Dockerfile" --tag "$image" "$repo_root" >/dev/null
docker run --rm --entrypoint caddy "$image" validate \
  --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null

docker run --detach --name "$container" --read-only --cap-drop=ALL \
  --security-opt no-new-privileges:true --user 10001:10001 \
  --sysctl net.ipv4.ip_unprivileged_port_start=0 \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --tmpfs /data:rw,nosuid,uid=10001,gid=10001,size=32m \
  --tmpfs /config:rw,nosuid,uid=10001,gid=10001,size=16m \
  --publish 127.0.0.1::80 \
  --mount "type=bind,src=$key_file,dst=/srv/$test_key.txt,readonly" \
  "$image" >/dev/null

port=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  port=$(docker port "$container" 80/tcp 2>/dev/null | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | head -n 1 || true)
  if [ -n "$port" ] && curl --silent --show-error --output /dev/null "http://127.0.0.1:$port/"; then
    break
  fi
  sleep 1
done
[ -n "$port" ] || { echo "FAIL: runtime container did not become reachable." >&2; exit 1; }

http_status() {
  curl --silent --show-error --output "$2" --write-out '%{http_code}' "$1"
}

home_body="$temporary/home.html"
sitemap_body="$temporary/sitemap.xml"
key_body="$temporary/key-response.txt"
bad_body="$temporary/bad-response.html"
[ "$(http_status "http://127.0.0.1:$port/" "$home_body")" = 200 ]
[ "$(http_status "http://127.0.0.1:$port/sitemap.xml" "$sitemap_body")" = 200 ]
grep -q '<urlset' "$sitemap_body"
[ "$(http_status "http://127.0.0.1:$port/$test_key.txt" "$key_body")" = 200 ]
cmp -s "$key_file" "$key_body"

bad_key=$(python3 -c 'import sys; key=sys.argv[1]; print(key[:-1] + ("0" if key[-1] != "0" else "1"), end="")' "$test_key")
[ "$(http_status "http://127.0.0.1:$port/$bad_key.txt" "$bad_body")" = 404 ]
! grep -Fq "$test_key" "$bad_body"
[ "$(http_status "http://127.0.0.1:$port/not-a-key.txt" "$bad_body")" = 404 ]
! grep -Fq "$test_key" "$bad_body"

docker run --detach --name "$missing_container" --read-only --cap-drop=ALL \
  --security-opt no-new-privileges:true --user 10001:10001 \
  --sysctl net.ipv4.ip_unprivileged_port_start=0 \
  --tmpfs /tmp:rw,noexec,nosuid,size=32m \
  --tmpfs /data:rw,nosuid,uid=10001,gid=10001,size=32m \
  --tmpfs /config:rw,nosuid,uid=10001,gid=10001,size=16m \
  --publish 127.0.0.1::80 \
  "$image" >/dev/null
missing_port=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  missing_port=$(docker port "$missing_container" 80/tcp 2>/dev/null | sed -n 's/.*:\([0-9][0-9]*\)$/\1/p' | head -n 1 || true)
  if [ -n "$missing_port" ] && curl --silent --show-error --output /dev/null "http://127.0.0.1:$missing_port/"; then
    break
  fi
  sleep 1
done
[ -n "$missing_port" ] || { echo "FAIL: runtime container without the key mount did not become reachable." >&2; exit 1; }
[ "$(http_status "http://127.0.0.1:$missing_port/" "$home_body")" = 200 ]
[ "$(http_status "http://127.0.0.1:$missing_port/$test_key.txt" "$bad_body")" = 404 ]
! grep -Fq "$test_key" "$bad_body"

echo "IndexNow Docker/Caddy runtime checks passed with an isolated synthetic key and localhost-only containers."
