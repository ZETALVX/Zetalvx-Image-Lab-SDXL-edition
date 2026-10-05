"""Execute the delivered error boundary with request/exception test doubles.
These are NOT HTTP/parser tests. The real HTTP suite is separately gated.
"""
import ast,contextlib,io,unittest,uuid
from functools import wraps
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]
class BadRequest(Exception):code=400
class ClientDisconnected(BadRequest):pass
class RequestEntityTooLarge(Exception):code=413
class UnsupportedMediaType(Exception):code=415
class IdentityBoundary111(unittest.TestCase):
 def setUp(self):
  node=next(x for x in ast.parse((ROOT/'app.py').read_text()).body if isinstance(x,ast.FunctionDef) and x.name=='_identity_upload_boundary')
  self.ctx=dict(wraps=wraps,uuid=uuid,BadRequest=BadRequest,ClientDisconnected=ClientDisconnected,RequestEntityTooLarge=RequestEntityTooLarge,UnsupportedMediaType=UnsupportedMediaType,jsonify=lambda **k:k)
  exec(compile(ast.Module(body=[node],type_ignores=[]),'identity-boundary','exec'),self.ctx)
  self.called=0
  def api_identity_create():self.called+=1;return {'ok':True},202
  self.wrapped=self.ctx['_identity_upload_boundary'](api_identity_create)
 def request(self,**kw):
  values=dict(mimetype='multipart/form-data',mimetype_params={'boundary':'b'},form={'project_id':'test'},files={'references':'test-double'},endpoint='api_identity_create',content_length=100)
  values.update(kw);self.ctx['request']=SimpleNamespace(**values)
 def test_valid_calls_existing_route_once(self):
  self.request();self.assertEqual(self.wrapped()[1],202);self.assertEqual(self.called,1);self.assertEqual(self.wrapped.__name__,'api_identity_create')
 def test_wrong_media_type_stops_before_route(self):
  self.request(mimetype='application/json');r,status=self.wrapped();self.assertEqual(status,415);self.assertFalse(r['queued']);self.assertEqual(self.called,0)
 def test_missing_boundary_is_structured_400(self):
  self.request(mimetype_params={});r,status=self.wrapped();self.assertEqual(status,400);self.assertEqual(r['code'],'identity_upload_invalid')
 def test_empty_multipart_stops_before_queue(self):
  self.request(form={},files={});r,status=self.wrapped();self.assertEqual(status,400);self.assertEqual(self.called,0)
 def test_parser_failures_are_classified_without_leaking_detail(self):
  for err,code,status in [(ClientDisconnected,'identity_upload_incomplete',400),(BadRequest,'identity_upload_invalid',400),(RequestEntityTooLarge,'identity_upload_too_large',413)]:
   with self.subTest(code=code):
    class Request:
     mimetype='multipart/form-data';mimetype_params={'boundary':'b'};endpoint='api_identity_create';content_length=100
     @property
     def form(self):raise err('private prompt must not be logged')
    self.ctx['request']=Request();out=io.StringIO()
    with contextlib.redirect_stdout(out):r,s=self.wrapped()
    self.assertEqual(s,status);self.assertEqual(r['code'],code);self.assertFalse(r['queued']);self.assertNotIn('private prompt',out.getvalue());self.assertNotIn('private prompt',str(r));self.assertEqual(len(r['diagnostic_id']),12)
