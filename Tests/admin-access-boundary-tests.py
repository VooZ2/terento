import importlib.util
from pathlib import Path
import unittest
spec=importlib.util.spec_from_file_location('boundary',Path(__file__).resolve().parents[1]/'scripts/infra/check-admin-boundary.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Boundary(unittest.TestCase):
 def test_exact_access_redirect(self):
  m.verify_response('/admin/login',302,{'Location':'https://'+m.TEAM+'/cdn-cgi/access/login/api.terento.app?redirect_url=x'},b'',True)
 def test_reject_untrusted_redirects(self):
  for u in ['http://'+m.TEAM+'/cdn-cgi/access/login/api.terento.app','https://'+m.TEAM+'.evil.test/cdn-cgi/access/login/api.terento.app','https://'+m.TEAM+'/other','/admin/login']:
   with self.assertRaises(AssertionError):m.verify_response('/admin/login',302,{'Location':u},b'',True)
 def test_enforced_mode_rejects_unprotected_login(self):
  with self.assertRaises(AssertionError):m.verify_response('/admin/login',200,{},b'<title>Admin sign in \xc2\xb7 Terento</title>',True)
 def test_transition_mode_preserves_app_gate(self):
  m.verify_response('/admin/campaign-links',303,{'Location':'/admin/login','Content-Security-Policy':"script-src 'none'"},b'',False)
  with self.assertRaises(AssertionError):m.verify_response('/admin/campaign-links',200,{},b'',False)
if __name__=='__main__':unittest.main()
