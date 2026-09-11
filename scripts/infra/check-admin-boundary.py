#!/usr/bin/env python3
"""Check the public admin gate without granting deployment CI admin access."""
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TEAM = 'polished-pond-5159.cloudflareaccess.com'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def valid_access(status, location):
    u = urllib.parse.urlsplit(location)
    return (status == 302 and u.scheme == 'https' and u.netloc == TEAM
            and u.path == '/cdn-cgi/access/login/api.terento.app')

def verify_response(path, status, headers, body, required):
    if valid_access(status, headers.get('Location', '')):
        return
    if required:
        raise AssertionError('Expected configured Cloudflare Access boundary')
    if path == '/admin/login':
        assert status == 200 and b'<title>Admin sign in \xc2\xb7 Terento</title>' in body
    else:
        assert status == 303 and headers.get('Location') == '/admin/login'
        assert "script-src 'none'" in headers.get('Content-Security-Policy', '')

if __name__ == '__main__':
    required = os.environ.get('TERENTO_ADMIN_ACCESS_REQUIRED', 'false') == 'true'
    opener = urllib.request.build_opener(NoRedirect)
    for path in ('/admin/login', '/admin/campaign-links'):
        for attempt in range(3):
            try:
                response = opener.open(urllib.request.Request('https://api.terento.app' + path, headers={'User-Agent': 'Terento-Deployment-Check/1.0'}), timeout=10)
            except urllib.error.HTTPError as e:
                response = e
            except (TimeoutError, urllib.error.URLError):
                if attempt == 2:
                    raise
                time.sleep(2 * (attempt + 1))
                continue
            if response.code not in (408, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524, 525, 526) or attempt == 2:
                break
            response.close()
            time.sleep(2 * (attempt + 1))
        with response:
            verify_response(path, response.code, response.headers, response.read(2*1024*1024), required)
    print('Public admin boundary PASS (Access required=%s)' % required)
