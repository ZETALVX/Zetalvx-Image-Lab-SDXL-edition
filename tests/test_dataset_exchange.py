import io,json,stat,tempfile,unittest,zipfile,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from core.dataset_exchange import *

def png():
    out=io.BytesIO();Image.new('RGB',(20,12),'navy').save(out,'PNG');return out.getvalue()
class DatasetTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):self.tmp.cleanup()
    def test_trigger_all_positions(self):
        for c in ['itapigna, a man','a man, itapigna','a photo of itapigna outdoors']:
            self.assertEqual(len(trigger_spans(c,'itapigna')),1)
            for p in ['prefix','suffix','context']:self.assertEqual(apply_trigger(c,'itapigna',p),c)
    def test_trigger_insertion(self):
        self.assertEqual(apply_trigger('a man','itapigna','prefix'),'itapigna, a man')
        self.assertEqual(apply_trigger('a man','itapigna','suffix'),'a man, itapigna')
        self.assertEqual(apply_trigger('a man','itapigna','context'),'a man')
    def test_not_substring(self):self.assertFalse(trigger_spans('notitapigna itapignas','itapigna'))
    def test_case_sensitive(self):self.assertFalse(trigger_spans('ItaPigna','itapigna'))
    def test_regex_literal(self):self.assertEqual(len(trigger_spans('(id)+ in city','(id)+')),1)
    def test_checks(self):
        r=caption_report({'trigger':'idword','items':[{'id':'a','caption':''},{'id':'b','caption':'idword outdoors idword'},{'id':'c','caption':'a person'}]})
        self.assertEqual((r['empty'],r['missing'],r['repeated']),(1,2,1));self.assertEqual(r['token_count'],'not_computed')
    def test_word_length_warning(self):
        r=caption_report({'items':[{'id':'a','caption':'word '*65}]});self.assertIn('check_token_length',r['items'][0]['warnings'])
    def test_exact_export_import(self):
        d=create_dataset(self.root,'My set','itapigna','context');caption='A photo of itapigna in town.\n  Fine texture.'
        append_image(self.root,d,png(),'Original.PNG',caption);atomic_json(self.root/d['id']/'dataset.json',d)
        out=self.root/'out.zip';export_zip(self.root,d['id'],out)
        with zipfile.ZipFile(out) as z:
            self.assertEqual(z.read('images/00001.txt').decode(),caption)
            self.assertNotIn(str(self.root),z.read('dataset.json').decode())
        new=import_zip(self.root,out);self.assertNotEqual(d['id'],new['id']);self.assertEqual(new['items'][0]['caption'],caption)
        self.assertEqual(Path(new['items'][0]['file']).read_bytes(),png())
    def test_duplicate_image(self):
        d=create_dataset(self.root,'dup');self.assertTrue(append_image(self.root,d,png(),'a.png'));self.assertIsNone(append_image(self.root,d,png(),'b.png'))
    def test_invalid_image(self):
        with self.assertRaises(DatasetError):check_image(b'not an image')
    def bad_zip(self,entries):
        out=io.BytesIO()
        with zipfile.ZipFile(out,'w') as z:
            for n,c in entries:z.writestr(n,c)
        out.seek(0);return out
    def test_zip_traversal(self):
        with self.assertRaises(DatasetError):import_zip(self.root,self.bad_zip([('../a.png',png())]))
    def test_zip_absolute(self):
        with self.assertRaises(DatasetError):import_zip(self.root,self.bad_zip([('/a.png',png())]))
    def test_zip_symlink(self):
        zi=zipfile.ZipInfo('link.png');zi.external_attr=(stat.S_IFLNK|0o777)<<16
        with self.assertRaises(DatasetError):import_zip(self.root,self.bad_zip([(zi,b'../target')]))
    def test_zip_duplicate_stem(self):
        with self.assertRaises(DatasetError):import_zip(self.root,self.bad_zip([('a.png',png()),('a.jpg',png())]))
        self.assertFalse(list(self.root.glob('*/dataset.json')))
    def test_utf8_captions(self):
        d=import_zip(self.root,self.bad_zip([('a.png',png()),('a.txt','写真, idword, العربية'.encode())]))
        self.assertEqual(d['items'][0]['caption'],'写真, idword, العربية')
    def test_missing_caption_allowed(self):
        d=import_zip(self.root,self.bad_zip([('a.png',png())]));self.assertEqual(caption_report(d)['empty'],1)
    def test_unsafe_export(self):
        d=create_dataset(self.root,'escape');d['items']=[{'file':str(self.root/'outside.png')}];atomic_json(self.root/d['id']/'dataset.json',d);(self.root/'outside.png').write_bytes(png())
        with self.assertRaises(DatasetError):export_zip(self.root,d['id'],self.root/'bad.zip')
    def test_no_position_forced_by_import(self):
        for pos,cap in [('prefix','idword at front'),('suffix','word at end idword'),('context','a person idword walking')]:
            d=create_dataset(self.root,pos,'idword',pos);append_image(self.root,d,png(),'a.png',cap);atomic_json(self.root/d['id']/'dataset.json',d);out=self.root/'out.zip';export_zip(self.root,d['id'],out);nd=import_zip(self.root,out);self.assertEqual(nd['items'][0]['caption'],cap)
if __name__=='__main__':unittest.main()
