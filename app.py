import os, importlib.util, threading
os.environ["GTA_AUTONOMOUS_DISABLE_LEGACY_WORKER"] = "1"
spec = importlib.util.spec_from_file_location("legacy_app", "app_legacy_V41_LATEST.py")
legacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(legacy)
from autonomous_engine import AutonomousEngine
engine = AutonomousEngine(legacy)
APP = legacy.APP

@APP.get("/api/autonomous")
def autonomous_status():
    return {"ok": True, "engine": "V42-FIXED", "running": engine.running, "memory": str(engine.memory.path), "max_attempts": engine.max_attempts, "deploy_configured": bool(os.getenv("RENDER_DEPLOY_HOOK_URL") or (os.getenv("RENDER_API_KEY") and os.getenv("RENDER_SERVICE_ID")))}

@APP.get("/api/autonomous/memory")
def autonomous_memory():
    return {"experiments": engine.memory.recent(50)}

# Replace only the queue endpoint. The validated V41.3/latest rendering core remains untouched.
@APP.post("/api/produce")
def produce_v42():
    from flask import request, jsonify
    import uuid
    data = request.get_json(silent=True) or {}
    topics, _, _ = legacy.research_official()
    topics = topics or legacy.FALLBACK_TOPICS
    topic = legacy.choose_topic(data, topics)
    jid = uuid.uuid4().hex[:10]
    job = {"id": jid, "title": topic["title"], "opportunity": topic, "status": "QUEUED", "stage": "FILA", "progress": 0, "log": "V42: tarefa recebida pelo agente autônomo.", "video": None, "cover": None, "created_at": legacy.now_iso()}
    with legacy.LOCK:
        jobs = legacy.load_jobs(); jobs[jid] = job; legacy.save_jobs(jobs)
    return jsonify(ok=True, job_id=jid, title=topic["title"])

threading.Thread(target=engine.loop, daemon=True).start()
app = APP
if __name__ == "__main__":
    APP.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
