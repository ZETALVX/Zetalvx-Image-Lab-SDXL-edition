import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

class WindowsBootstrap50(unittest.TestCase):
    def test_checksum_sidecar_is_read_as_text_file(self):
        s=(ROOT/'scripts/bootstrap.ps1').read_text(encoding='utf-8')
        self.assertIn("$ChecksumFile = Join-Path $Tmp ($Name+'.sha256')",s)
        self.assertIn("Invoke-WebRequest -UseBasicParsing -Uri ($Url+'.sha256') -OutFile $ChecksumFile",s)
        self.assertIn('Get-Content -LiteralPath $ChecksumFile -Raw -Encoding ASCII',s)

    def test_no_iwr_content_trim_on_checksum_response(self):
        s=(ROOT/'scripts/bootstrap.ps1').read_text(encoding='utf-8')
        self.assertNotIn("(Invoke-WebRequest -UseBasicParsing -Uri ($Url+'.sha256')).Content",s)
        self.assertIn("$UvExpected = ($Checksum.Trim() -split '\\s+')[0].ToLowerInvariant()",s)

if __name__=='__main__': unittest.main()
