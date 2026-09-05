#!/usr/bin/env python3
"""Check the public admin gate without granting deployment CI admin access."""
import os
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
        try:
            response = opener.open(urllib.request.Request('https://api.terento.app' + path, headers={'User-Agent': 'Terento-Deployment-Check/1.0'}), timeout=10)
        except urllib.error.HTTPError as e:
            response = e
        with response:
            verify_response(path, response.code, response.headers, response.read(2*1024*1024), required)
    print('Public admin boundary PASS (Access required=%s)' % required)
