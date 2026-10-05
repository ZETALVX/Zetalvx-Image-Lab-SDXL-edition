"""Real CPU FFmpeg tests using a generated, tiny local fixture."""
import shutil, subprocess, tempfile, unittest
from pathlib import Path
from PIL import Image
from core.frame_extract import extract_frame,timestamp_seconds

class TimestampTests(unittest.TestCase):
    def test_hms(self):self.assertEqual(timestamp_seconds('01:02:03.5'),3723.5)
    def test_seconds(self):self.assertEqual(timestamp_seconds('1.25'),1.25)
    def test_bad_values(self):
        for value in ['-1','NaN','inf','1:80','notime']:
            with self.subTest(value=value),self.assertRaises(ValueError):timestamp_seconds(value)

@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'),'FFmpeg/ffprobe not installed')
class FrameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        for i,col in enumerate(['red','green','blue','white']):Image.new('RGB',(32,32),col).save(cls.root/f'{i}.png')
        cls.clip=cls.root/'test.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-framerate','2','-i',str(cls.root/'%d.png'),'-c:v','libx264','-pix_fmt','yuv420p',str(cls.clip)],check=True,capture_output=True)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def pixels(self,mode,ts=0):
        out=self.root/f'{mode}.png';info=extract_frame(self.clip,out,mode,ts)
        return Image.open(out).convert('RGB').getpixel((10,10)),info
    def test_first(self):rgb,_=self.pixels('first');self.assertGreater(rgb[0],200);self.assertLess(rgb[2],20)
    def test_last_is_actual_final_white_frame(self):
        rgb,info=self.pixels('last');self.assertTrue(all(x>230 for x in rgb));self.assertTrue(info['last_frame_exact'])
    def test_chosen_time(self):rgb,_=self.pixels('timestamp',1.0);self.assertGreater(rgb[2],200);self.assertLess(rgb[0],20)
    def test_past_end(self):
        with self.assertRaises(ValueError):self.pixels('timestamp',20)

if __name__=='__main__':unittest.main(verbosity=2)
