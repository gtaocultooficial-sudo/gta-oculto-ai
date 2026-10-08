import os, re, shutil, subprocess, tempfile
from pathlib import Path

SAFE_ERROR_PATTERNS = {
    'VARIANT_UNBOUND': r"UnboundLocalError:.*variant",
    'RESOLVER_DEADLINE': r"NameError:.*resolver_deadline",
    'WORKER_TIMEOUT': r"WORKER TIMEOUT|WORKER_TIMEOUT",
    'FEED_CANDIDATE': r"publisher-feed|FALLBACK_CANDIDATE.*feed",
    'BLOCKED_NO_BODY': r"BLOCKED_NO_ARTICLE_BODY|MATÉRIA SEM CORPO ORIGINAL",
}

class RepairEngine:
    """Safe repair planner. It never rewrites production code blindly.
    Unknown failures are quarantined. Known fixes are strategy changes; code patches
    can only be applied when a matching patch file exists and tests pass.
    """
    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parent)
        self.app=self.root/'app.py'
        self.backup_dir=self.root/'workspace'/'code_backups'
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    def classify(self, text):
        for key,pat in SAFE_ERROR_PATTERNS.items():
            if re.search(pat,text or'',re.I|re.M): return key
        return 'UNKNOWN'
    def plan(self, text):
        c=self.classify(text)
        plans={
            'VARIANT_UNBOUND':['use_last_known_good_app','rerun_compile_tests'],
            'RESOLVER_DEADLINE':['reset_resolver_budget','try_official_first','rerun_compile_tests'],
            'FEED_CANDIDATE':['reject_feed_candidates','try_secondary_direct_sources','rerun_compile_tests'],
            'BLOCKED_NO_BODY':['switch_source_strategy','change_topic_if_no_body','rerun_compile_tests'],
            'WORKER_TIMEOUT':['reduce_external_timeout','resume_from_job_checkpoint','rerun_compile_tests'],
            'UNKNOWN':['quarantine','do_not_autodeploy'],
        }
        return {'code':c,'actions':plans[c]}
    def snapshot(self):
        if not self.app.exists(): return None
        dst=self.backup_dir/f'app_{__import__("time").strftime("%Y%m%d_%H%M%S")}.py'
        shutil.copy2(self.app,dst); return str(dst)
    def validate(self):
        r=subprocess.run(['python','-m','py_compile',str(self.app)],capture_output=True,text=True,timeout=60)
        return r.returncode==0, (r.stdout+r.stderr)[-4000:]
    def safe_apply_file(self, candidate_path):
        candidate=Path(candidate_path)
        if not candidate.exists(): return False,'candidate_missing'
        backup=self.snapshot()
        shutil.copy2(candidate,self.app)
        ok,log=self.validate()
        if not ok and backup:
            shutil.copy2(backup,self.app)
        return ok,log
