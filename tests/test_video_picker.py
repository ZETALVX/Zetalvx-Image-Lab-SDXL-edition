import io,json,shutil,subprocess,tempfile,unittest,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.video_picker import VideoPicker
@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg required')
class PickerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.video=self.root/'source.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc=size=160x96:rate=10:duration=1','-c:v','mpeg4','-y',str(self.video)],check=True,capture_output=True)
        self.picker=VideoPicker(self.root/'cache')
        with self.video.open('rb') as f:self.meta=self.picker.upload(f,'source.mp4','project','owner')
    def tearDown(self):self.tmp.cleanup()
    def test_preview_png_and_immutable_selection(self):
        a=self.picker.preview(self.meta['id'],'owner','timestamp',.4);p,m,i=self.picker.selected(self.meta['id'],'owner',a['id']);b=p.read_bytes();self.assertTrue(b.startswith(b'\x89PNG'));self.assertEqual(i['width'],160)
        self.picker.preview(self.meta['id'],'owner','last',0)
        with self.assertRaises(ValueError):self.picker.selected(self.meta['id'],'owner',a['id'])
    def test_owner_isolation(self):
        with self.assertRaises(ValueError):self.picker.get(self.meta['id'],'other')
    def test_discard(self):
        self.picker.discard(self.meta['id'],'owner');self.assertFalse((self.root/'cache'/self.meta['id']).exists())
    def test_bad_time(self):
        with self.assertRaises(ValueError):self.picker.preview(self.meta['id'],'owner','timestamp','bad')
    def test_no_network_input(self):
        with self.assertRaises(ValueError):self.picker.upload(io.BytesIO(b'http://example.org'),'list.m3u','project','owner')
if __name__=='__main__':unittest.main()
