import unittest
from scripts.review_runtime import summarize
class RuntimeReviewTests(unittest.TestCase):
 def data(self,v):return {'runtimes':{'sdxl':{'installed':True,'packages':[{'name':'torch','version':v}]}},'ffmpeg':{}}
 def test_251_flags_both(self):self.assertEqual(len(summarize(self.data('2.5.1+cu121'))['observations']),2)
 def test_26_still_second(self):self.assertEqual(summarize(self.data('2.6.0'))['observations'][0]['code'],'GHSA-63cw-57p8-fm3p')
 def test_291_still_second(self):self.assertEqual(len(summarize(self.data('2.9.1'))['observations']),1)
 def test_210_not_flagged_for_these_only(self):self.assertEqual(summarize(self.data('2.10.0'))['observations'],[])
 def test_unknown_no_safety_claim(self):self.assertEqual(summarize(self.data('custom'))['observations'][0]['code'],'version_unparsed')
 def test_missing_vision_not_inferred_external(self):self.assertFalse(summarize({'runtimes':{'vision':{'installed':False}}})['runtimes']['vision']['installed'])
 def test_gpl_ffmpeg(self):self.assertTrue(summarize({'ffmpeg':{'buildconf':'--enable-gpl'}})['ffmpeg']['gpl_enabled'])
 def test_nonfree(self):self.assertTrue(summarize({'ffmpeg':{'buildconf':'--enable-nonfree'}})['ffmpeg']['nonfree_enabled'])
 def test_names_dedup(self):self.assertEqual(summarize({'runtimes':{'a':{'packages':[{'name':'A_b'}]},'b':{'packages':[{'name':'a-b'}]}}})['unique_names'],1)
 def test_metadata_not_reclassified(self):
  d={'runtimes':{'sdxl':{'packages':[{'name':'easydict','version':'1.13','license_metadata':'LGPL-3.0'}]}}}
  self.assertEqual(summarize(d)['observations'][0]['declared_license'],'LGPL-3.0')
if __name__=='__main__':unittest.main()
