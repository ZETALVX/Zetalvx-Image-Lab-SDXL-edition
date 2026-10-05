# Modified in Zetalvx Image Lab - SDXL Edition 0.1.0.21; Apache-2.0; see CHANGELOG.md.
# Modified for Zetalvx 0.1.0.20 native entry/packaging; Apache-2.0 license and attribution retained in LICENSE and NOTICE.
#!/usr/bin/env python3
"""Isolated local-only worker; JSON-lines stdin/stdout, no network service."""
import base64,contextlib,ctypes,io,json,os,signal,sys,traceback
os.environ.update(HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',HF_HUB_DISABLE_TELEMETRY='1',TOKENIZERS_PARALLELISM='false')
if sys.platform.startswith('linux'):
    ctypes.CDLL(None).prctl(1,signal.SIGTERM)
    if str(os.getppid())!=os.environ.get('ZETALVX_VISION_PARENT',str(os.getppid())):sys.exit(1)
proto=sys.stdout

def emit(data):
    proto.write('ZETALVX_VISION_JSON '+json.dumps(data,ensure_ascii=False)+'\n');proto.flush()

def load(m):
    import torch,transformers
    from transformers import AutoProcessor, AutoConfig, BitsAndBytesConfig
    from pathlib import Path
    root=str(Path(m['model_path']).expanduser());proc=str(Path(m.get('processor_path') or root).expanduser())
    config=AutoConfig.from_pretrained(root,local_files_only=True,trust_remote_code=False)
    if not getattr(config,'vision_config',None):raise ValueError('Selected model has no vision_config; a text-only Qwen cannot caption images')
    names={'qwen2_5_vl':'Qwen2_5_VLForConditionalGeneration','qwen3_vl':'Qwen3VLForConditionalGeneration','qwen3_vl_moe':'Qwen3VLMoeForConditionalGeneration','qwen3_5':'Qwen3_5ForConditionalGeneration','qwen3_5_moe':'Qwen3_5MoeForConditionalGeneration'}
    cls=getattr(transformers,names.get(config.model_type,''),None) or getattr(transformers,'AutoModelForImageTextToText',None) or getattr(transformers,'AutoModelForMultimodalLM',None)
    if cls is None:raise ValueError('Vision AutoModel unavailable: install/update the separate Vision runtime, not the SDXL runtime')
    device=m.get('device','auto')
    if device=='cuda' and not torch.cuda.is_available():raise ValueError('CUDA requested but unavailable in the Vision runtime')
    dtype=m.get('dtype','auto');dtype=dtype if dtype=='auto' else getattr(torch,dtype)
    kwargs=dict(config=config,local_files_only=True,trust_remote_code=False,use_safetensors=True,dtype=dtype,device_map=('auto' if device=='auto' else device),attn_implementation='sdpa')
    q=m.get('quantization','native')
    if q!='native':
        if getattr(config,'quantization_config',None):raise ValueError('Pre-quantized model: select Native, do not quantize it a second time')
        if device=='cpu' or not torch.cuda.is_available():raise ValueError('This 4/8-bit loading mode requires CUDA. Use native CPU or GGUF instead.')
        kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=q=='int4',load_in_8bit=q=='int8',bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16)
    model=cls.from_pretrained(root,**kwargs).eval()
    processor=AutoProcessor.from_pretrained(proc,local_files_only=True,trust_remote_code=False)
    return model,processor

def infer(model,processor,m,d):
    import torch
    from PIL import Image
    image=Image.open(io.BytesIO(base64.b64decode(d['image'],validate=True))).convert('RGB')
    messages=[{'role':'user','content':[{'type':'image','image':image},{'type':'text','text':d['prompt']}]}]
    text=processor.apply_chat_template(messages,tokenize=False,add_generation_prompt=True,enable_thinking=not m.get('disable_thinking',True))
    inputs=processor(text=[text],images=[image],return_tensors='pt')
    if 'pixel_values' not in inputs:raise ValueError('Processor produced no pixel_values; configuration is not multimodal')
    inputs=inputs.to(model.device)
    args={'max_new_tokens':m['max_tokens'],'do_sample':m.get('temperature',0)>0}
    if args['do_sample']:args['temperature']=m['temperature']
    with torch.inference_mode():out=model.generate(**inputs,**args)
    return processor.batch_decode(out[:,inputs['input_ids'].shape[-1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)[0]

def main():
    from core.runtime_security import require_reviewed_torch
    require_reviewed_torch()
    try:
        first=json.loads(sys.stdin.readline());m=first['model']
        with contextlib.redirect_stdout(sys.stderr):model,processor=load(m)
        emit({'ok':True,'event':'loaded'})
        for line in sys.stdin:
            d=json.loads(line)
            if d.get('op')=='stop':break
            try:
                with contextlib.redirect_stdout(sys.stderr):caption=infer(model,processor,m,d)
                emit({'ok':True,'caption':caption,'request_id':d.get('request_id')})
            except Exception as e:
                emit({'ok':False,'error':type(e).__name__+': '+str(e)[:1200],'request_id':d.get('request_id')})
    except Exception as e:
        emit({'ok':False,'error':type(e).__name__+': '+str(e)[:1200]});sys.exit(1)

if __name__ == "__main__":
    main()
