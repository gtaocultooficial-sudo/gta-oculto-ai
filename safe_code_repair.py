import re, shutil, subprocess, time
from pathlib import Path

class SafeCodeRepair:
    def __init__(self, app_path):
        self.app=Path(app_path); self.backup_dir=self.app.parent/'workspace'/'code_backups'; self.backup_dir.mkdir(parents=True,exist_ok=True)
    def _backup(self):
        dst=self.backup_dir/f'app_before_repair_{time.strftime("%Y%m%d_%H%M%S")}.py'; shutil.copy2(self.app,dst); return dst
    def _validate(self):
        r=subprocess.run(['python','-m','py_compile',str(self.app)],capture_output=True,text=True,timeout=60); return r.returncode==0,(r.stdout+r.stderr)[-5000:]
    def apply(self, code):
        code=str(code); text=self.app.read_text(encoding='utf-8'); original=text; changed=False
        if code=='VARIANT_UNBOUND':
            new=text.replace('def select_visuals(paths, topic_title, count=10):','def select_visuals(paths, topic_title, count=10, variant=0):')
            new=new.replace('variant=int(variant or 0)','variant=int(variant or 0)')
            changed=new!=text
        elif code=='RESOLVER_DEADLINE':
            marker='def _article_url_candidates_from_search(title, source_name=\'\'):'
            if marker in text and 'resolver_deadline=time.monotonic()' not in text[text.index(marker):text.index(marker)+600]:
                new=text.replace(marker,marker+'\n    resolver_deadline=time.monotonic()+32',1); changed=new!=text
            else: new=text
        else: new=text
        if not changed: return False,'NO_SAFE_PATCH'
        backup=self._backup(); self.app.write_text(new,encoding='utf-8')
        ok,log=self._validate()
        if not ok:
            shutil.copy2(backup,self.app); return False,'ROLLBACK_AFTER_COMPILE_FAIL\n'+log
        return True,'PATCH_APPLIED_AND_COMPILED'
