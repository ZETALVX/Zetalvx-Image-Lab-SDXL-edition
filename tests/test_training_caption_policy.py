import ast, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from core.training_captions import training_caption, clip_training_caption, job_policy, SAVED_TEXT, LEGACY

class CaptionPolicyTests(unittest.TestCase):
    def test_saved_prefix(self):self.assertEqual(training_caption({'caption':'tag, a person'},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),'tag, a person')
    def test_saved_suffix(self):self.assertEqual(training_caption({'caption':'a person, tag'},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),'a person, tag')
    def test_saved_context(self):self.assertEqual(training_caption({'caption':'photo of tag in a garden'},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),'photo of tag in a garden')
    def test_whitespace_unicode_preserved(self):
        text='  photo\nè, 文 tag  ';self.assertEqual(training_caption({'caption':text},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),text)
    def test_missing_trigger_not_invented(self):self.assertEqual(training_caption({'caption':'person'},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),'person')
    def test_empty_not_replaced(self):self.assertEqual(training_caption({'caption':''},{'trigger':'tag','common_caption':'other'},{'caption_policy':SAVED_TEXT}),'')
    def test_duplicate_not_silently_deleted(self):self.assertEqual(training_caption({'caption':'tag and tag'},{'trigger':'tag'},{'caption_policy':SAVED_TEXT}),'tag and tag')
    def test_no_policy_is_legacy(self):self.assertEqual(job_policy({}),LEGACY)
    def test_legacy_suffix_moves(self):self.assertEqual(training_caption({'caption':'a person, tag'},{'trigger':'tag'}),'tag, a person')
    def test_legacy_fallback(self):self.assertEqual(training_caption({'caption':''},{'trigger':'tag','common_caption':'a person'}),'tag, a person')
    def test_invalid_policy_rejected(self):self.assertRaises(ValueError,job_policy,{'caption_policy':'foo'})
    def test_worker_all_calls_receive_job(self):
        source=Path(__file__).resolve().parents[1]/'services/training_worker.py';tree=ast.parse(source.read_text());calls=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='training_caption'];self.assertGreaterEqual(len(calls),1);self.assertTrue(all(len(x.args)==3 for x in calls))

    def test_clip_fit_preserves_selected_trigger_position_and_saved_text(self):
        class Tok:
            model_max_length=12
            def __call__(self,text,truncation=False,add_special_tokens=True):
                class R: pass
                r=R();r.input_ids=([0]+str(text).replace(',', ' ').split()+[1]) if add_special_tokens else str(text).split();return r
        tok=Tok();long='one two three four five six seven eight nine ten eleven twelve tag'
        saved=training_caption({'caption':long},{'trigger':'tag','trigger_position':'suffix'},{'caption_policy':SAVED_TEXT})
        eff=clip_training_caption(saved,{'trigger':'tag','trigger_position':'suffix'},tok)
        self.assertEqual(saved,long);self.assertTrue(eff.endswith('tag'));self.assertLessEqual(len(tok(eff).input_ids),12)
        pref=clip_training_caption('tag, one two three four five six seven eight nine ten eleven twelve',{'trigger':'tag','trigger_position':'prefix'},tok)
        self.assertTrue(pref.startswith('tag'));self.assertLessEqual(len(tok(pref).input_ids),12)
        ctx=clip_training_caption('one two three four five tag six seven eight nine ten eleven twelve',{'trigger':'tag','trigger_position':'context'},tok)
        self.assertIn('tag',ctx);self.assertLessEqual(len(tok(ctx).input_ids),12)

    def test_create_and_continue_preserve_policy(self):
        from core import training_manager as t
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            with patch.multiple(t,ROOT=root,DATASETS=root/'datasets',JOBS=root/'jobs',RECIPES=root/'recipes',CACHE=root/'cache',LOGS=root/'logs',LORA_ROOT=root/'loras',FULL_ROOT=root/'full',EXPORTS=root/'exports'),patch.object(t,'worker_call',return_value={'ok':True}):
                d=t.create_dataset('test','tag');d['items']=[{'id':'i','caption':'a person, tag','file':'not_loaded'}];t._write(t.DATASETS/d['id']/'dataset.json',d);base=root/'base.safetensors';base.write_bytes(b'test')
                j=t.create_job({'dataset_id':d['id'],'base_model':str(base)},submit=False);jpath=t.JOBS/j['id']/'job.json';self.assertEqual(t._read(jpath)['caption_policy'],SAVED_TEXT)
                cp=root/'step_000100';cp.mkdir();n=t.continue_job(j['id'],10,str(cp));self.assertEqual(t._read(t.JOBS/n['id']/'job.json')['caption_policy'],SAVED_TEXT)
                old=t._read(jpath);old.pop('caption_policy');t._write(jpath,old);n=t.continue_job(j['id'],10,str(cp));self.assertEqual(t._read(t.JOBS/n['id']/'job.json')['caption_policy'],LEGACY)
                with patch.object(t,'worker_call',return_value={'ok':True}) as call:t.resume_job(j['id'],str(cp));self.assertEqual(job_policy(call.call_args.args[1]['job']),LEGACY)

if __name__=='__main__':unittest.main()
