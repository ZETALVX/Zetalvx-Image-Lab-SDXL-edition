from pathlib import Path

IMAGE_PROVIDERS={"sdxl"}
LEVEL_RANK={"native":3,"fallback":2,"experimental":1,"unavailable":0}

def task_from_tool(tool):
    return {
        "generate_image":"generate",
        "edit_image":"edit",
        "img2img":"edit",
        "inpaint":"inpaint",
        "reference":"reference",
        "multi_image":"multi_image",
        "refine_image":"refine",
    }.get(tool,tool)

def task_support(model,task):
    provider=model.get("provider")
    cfg=model.get("config") or {}
    caps=set(model.get("capabilities") or [])
    if provider not in IMAGE_PROVIDERS:
        return {"level":"unavailable","rank":0,"executable":False,"reason":"Not an image-generation provider."}

    if provider=="sdxl":
        if task=="generate":
            return _s("native","Native SDXL text-to-image pipeline.")
        if task=="edit":
            return _s("fallback","SDXL img2img: the source image influences the new generation through Strength.")
        if task=="reference":
            return _s("fallback","Reference fallback: the first reference is used as SDXL img2img source.")
        if task=="multi_image":
            return _s("experimental","Multiple references are composed into a contact sheet, then used as SDXL img2img input.")
        if task=="inpaint":
            cp=str(cfg.get("inpaint_checkpoint") or "")
            if cp and Path(cp).exists():
                return _s("native","Dedicated SDXL inpainting checkpoint configured.")
            return _s("fallback","Generic masked img2img: SDXL edits the image, then only the painted mask area is composited back.")

    return {"level":"unavailable","rank":0,"executable":False,"reason":"Task unavailable in the SDXL edition."}

def _s(level,reason,executable=True):
    return {"level":level,"rank":LEVEL_RANK[level],"executable":bool(executable),"reason":reason}

def support_matrix(model):
    return {t:task_support(model,t) for t in ("generate","edit","inpaint","reference","multi_image")}

def resolve_strategy(model,tool,params=None):
    task=task_from_tool(tool)
    support=task_support(model,task)
    if support["level"]=="unavailable":
        raise RuntimeError(support["reason"])
    provider=model.get("provider")
    cfg=model.get("config") or {}
    strategy={"task":task,"worker_task":task,"support":support}

    if provider=="sdxl":
        if task=="edit":
            strategy.update(worker_task="edit",source_mode="source")
        elif task=="reference":
            strategy.update(worker_task="edit",source_mode="first_reference")
        elif task=="multi_image":
            strategy.update(worker_task="edit",source_mode="contact_sheet")
        elif task=="inpaint":
            cp=str((params or {}).get("inpaint_checkpoint_override") or cfg.get("inpaint_checkpoint") or "")
            if cp and Path(cp).exists():
                strategy.update(worker_task="inpaint",source_mode="source")
            else:
                strategy.update(worker_task="generic_inpaint",source_mode="source")

    return strategy
