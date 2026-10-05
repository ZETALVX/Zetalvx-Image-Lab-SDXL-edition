"""Planner unit tests: no models, downloads, Flask, GPU or installed user data."""
from pathlib import Path
import sys, unittest, copy, json, ast, types
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.image_test_plan import plan_image_test, range_values, MAX_SEED

class PlanTests(unittest.TestCase):
    def setUp(self):self.params={'cfg':7,'steps':30,'seed':42,'strength':.35,'batch':8}
    def plan(self, ranges, task='generate', **extra):
        return plan_image_test(self.params,{'mode':'custom','ranges':ranges,**extra},task)
    def test_six_distinct_combinations(self):
        p=self.plan({'cfg':{'min':5,'max':9,'count':3},'steps':{'min':20,'max':40,'count':2}})
        self.assertEqual(p['count'],6);self.assertEqual(p['axes']['cfg'],[5,7,9]);self.assertEqual(p['variants'][-1]['steps'],40)
    def test_batch_is_not_multiplied(self):self.assertEqual(self.plan({'cfg':{'min':5,'max':9,'count':3}})['count'],3)
    def test_unchanged_default(self):self.assertEqual(self.plan({'cfg':{'min':5,'max':9,'count':3}})['axes']['steps'],[30])
    def test_twelve_edit_variations(self):self.assertEqual(self.plan({'cfg':{'min':5,'max':9,'count':3},'steps':{'min':20,'max':40,'count':2},'strength':{'min':.2,'max':.5,'count':2}},'edit')['count'],12)
    def test_denoise_rejected_in_text_generation(self):
        with self.assertRaisesRegex(ValueError,'not available'):self.plan({'strength':{'min':.2,'max':.5,'count':2}})
    def test_seed_range_multiplies(self):
        p=self.plan({'cfg':{'min':5,'max':9,'count':3},'seed':{'min':1,'max':3,'count':3}})
        self.assertEqual(p['count'],9);self.assertEqual([v['seed'] for v in p['variants'][:3]],[1,2,3])
    def test_fixed_seed(self):self.assertEqual({v['seed'] for v in self.plan({'cfg':{'min':5,'max':9,'count':3}})['variants']},{42})
    def test_increment_seed(self):self.assertEqual([v['seed'] for v in self.plan({'cfg':{'min':5,'max':9,'count':3}},vary_seed=True)['variants']],[42,43,44])
    def test_increment_wraps(self):
        self.params['seed']=MAX_SEED
        self.assertEqual([v['seed'] for v in self.plan({'cfg':{'min':5,'max':9,'count':3}},vary_seed=True)['variants']],[MAX_SEED,0,1])
    def test_seed_range_and_vary_rejected(self):
        with self.assertRaises(ValueError):self.plan({'seed':{'min':1,'max':3,'count':3}},vary_seed=True)
    def test_random_preview_freezes_seed(self):
        self.params['seed']=-1;sweep={'cfg_values':[6,7,8]}
        a=plan_image_test(self.params,sweep,'generate',random_seed=lambda:123)
        b=plan_image_test({**self.params,'seed':a['base_seed']},sweep,'generate',random_seed=lambda:999)
        self.assertEqual(a,b)
    def test_random_increment_preview_stable(self):
        self.params['seed']=-1;sweep={'cfg_values':[6,7,8],'vary_seed':True}
        a=plan_image_test(self.params,sweep,'generate',random_seed=lambda:100)
        b=plan_image_test({**self.params,'seed':a['base_seed']},sweep,'generate')
        self.assertEqual(a,b)
    def test_inputs_not_mutated(self):
        sweep={'mode':'custom','ranges':{'cfg':{'min':5,'max':9,'count':3}}};before=copy.deepcopy((self.params,sweep))
        plan_image_test(self.params,sweep,'generate');self.assertEqual((self.params,sweep),before)
    def test_single_value_uses_minimum(self):self.assertEqual(range_values('cfg',{'min':5,'max':9,'count':1}),[5])
    def test_integer_interpolation(self):self.assertEqual(range_values('steps',{'min':20,'max':25,'count':3}),[20,23,25])
    def test_float_endpoints(self):self.assertEqual(range_values('strength',{'min':.1,'max':.3,'count':3}),[.1,.2,.3])
    def test_reversed_range(self):
        with self.assertRaises(ValueError):range_values('cfg',{'min':9,'max':5,'count':3})
    def test_duplicate_integers_rejected(self):
        with self.assertRaises(ValueError):range_values('steps',{'min':20,'max':21,'count':3})
    def test_tiny_float_duplicates_rejected(self):
        with self.assertRaises(ValueError):range_values('cfg',{'min':5,'max':5.00000001,'count':3})
    def test_unbounded_count_rejected(self):
        with self.assertRaises(ValueError):range_values('cfg',{'min':1,'max':20,'count':1000000})
    def test_fractional_count_rejected(self):
        with self.assertRaises(ValueError):range_values('cfg',{'min':5,'max':9,'count':2.5})
    def test_unknown_axis_rejected(self):
        with self.assertRaises(ValueError):self.plan({'arbitrary':{'min':0,'max':1,'count':2}})
    def test_no_custom_axes_rejected(self):
        with self.assertRaises(ValueError):self.plan({})
    def test_nan_infinity_rejected(self):
        for v in (float('nan'),float('inf'),'-Infinity','NaN'):
            with self.subTest(v=v),self.assertRaises(ValueError):range_values('cfg',{'min':v,'max':9,'count':3})
    def test_boolean_is_not_number(self):
        with self.assertRaises(ValueError):range_values('cfg',{'min':True,'max':9,'count':3})
    def test_fractional_seed_rejected(self):
        with self.assertRaises(ValueError):range_values('seed',{'min':1.2,'max':4,'count':2})
    def test_out_of_bounds_not_clamped(self):
        for k,r in [('cfg',{'min':0,'max':7,'count':2}),('steps',{'min':20,'max':200,'count':2}),('strength',{'min':.2,'max':2,'count':2})]:
            with self.subTest(k=k),self.assertRaises(ValueError):range_values(k,r)
    def test_cap_before_cartesian_expansion(self):
        with self.assertRaisesRegex(ValueError,'576'):self.plan({'cfg':{'min':1,'max':20,'count':24},'steps':{'min':1,'max':120,'count':24}})
    def test_exactly_twentyfour_allowed(self):self.assertEqual(self.plan({'cfg':{'min':5,'max':9,'count':3},'steps':{'min':20,'max':50,'count':8}})['count'],24)
    def test_limit_cannot_increase(self):
        with self.assertRaises(ValueError):self.plan({'cfg':{'min':5,'max':9,'count':3}},max_jobs=500)
    def test_legacy_array_api(self):self.assertEqual(plan_image_test(self.params,{'cfg_values':[5,7,9],'steps_values':[20,30]},'generate')['count'],6)
    def test_legacy_dedup(self):self.assertEqual(plan_image_test(self.params,{'cfg_values':[5,5,7]},'generate')['count'],2)
    def test_invalid_array_no_fallback(self):
        with self.assertRaises(ValueError):plan_image_test(self.params,{'cfg_values':['a']},'generate')
    def test_json_strict(self):json.dumps(self.plan({'cfg':{'min':5,'max':9,'count':3}}),allow_nan=False)

class RouteUnitTests(unittest.TestCase):
    """Real route function bodies with mocked transport/DB. Not a Flask HTTP test."""
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'app.py'
        tree=ast.parse(path.read_text());names={'_prepare_image_test','image_auto_test_preview','image_auto_test'}
        nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
        for n in nodes:n.decorator_list=[]
        self.created=[];self.started=[]
        import uuid,time
        self.ns={'plan_image_test':plan_image_test,'request':types.SimpleNamespace(get_json=lambda **kw:self.data),
            'jsonify':lambda **kw:kw,'one':lambda *a:{'id':'p'},'task_from_tool':lambda tool:{'generate_image':'generate','edit_image':'edit','inpaint':'inpaint','reference':'reference'}.get(tool,''),
            'validate_image_request':lambda *a:None,'uuid':uuid,'time':time,
            'create_job':lambda *a:self.created.append(a) or str(len(self.created)), 'start_job':lambda id:self.started.append(id)}
        exec(compile(ast.Module(body=nodes,type_ignores=[]),str(path),'exec'),self.ns)
        self.data={'project_id':'p','tool':'generate_image','prompt':'A car','params':{'cfg':7,'steps':30,'seed':-1,'batch':8},'sweep':{'mode':'custom','ranges':{'cfg':{'min':5,'max':9,'count':3}}}}
    def call(self,name):return self.ns[name]()
    def test_preview_writes_nothing(self):
        r=self.call('image_auto_test_preview');self.assertEqual(r['plan']['count'],3);self.assertEqual(self.created,[]);self.assertEqual(self.started,[])
    def test_preview_exactly_matches_enqueue(self):
        r=self.call('image_auto_test_preview');self.data=r['request'];j,status=self.call('image_auto_test');self.assertEqual(status,202);self.assertEqual(j['count'],3)
        self.assertEqual([x[4]['seed'] for x in self.created],[v['seed'] for v in r['plan']['variants']]);self.assertEqual({x[4]['batch'] for x in self.created},{1})
    def test_changed_count_rejected_before_side_effect(self):
        self.data['expected_count']=9;r,status=self.call('image_auto_test');self.assertEqual(status,400);self.assertEqual(self.created,[])
    def test_large_product_no_partial_jobs(self):
        self.data['sweep']['ranges']['steps']={'min':10,'max':110,'count':24};r,status=self.call('image_auto_test');self.assertEqual(status,400);self.assertEqual(self.created,[])
    def test_bad_range_no_partial_jobs(self):
        self.data['sweep']['ranges']['cfg']['min']=11;r,status=self.call('image_auto_test');self.assertEqual(status,400);self.assertEqual(self.created,[])
    def test_missing_source_rejected(self):
        self.data['tool']='edit_image';r,status=self.call('image_auto_test_preview');self.assertEqual(status,400)
    def test_missing_mask_rejected(self):
        self.data['tool']='inpaint';self.data['params']['source_artifact_id']='src';r,status=self.call('image_auto_test_preview');self.assertEqual(status,400)
    def test_missing_reference_rejected(self):
        self.data['tool']='reference';r,status=self.call('image_auto_test_preview');self.assertEqual(status,400)
    def test_per_job_metadata(self):
        r=self.call('image_auto_test_preview');self.data=r['request'];self.call('image_auto_test')
        for i,a in enumerate(self.created,1):self.assertEqual(a[4]['test_index'],i);self.assertEqual(a[4]['test_total'],3);self.assertIn('Seed',a[4]['test_label'])

if __name__=='__main__':unittest.main()
