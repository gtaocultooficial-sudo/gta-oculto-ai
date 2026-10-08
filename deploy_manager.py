import os, subprocess, requests
from pathlib import Path

class DeployManager:
    def __init__(self):
        self.api=os.getenv('RENDER_API_KEY'); self.service=os.getenv('RENDER_SERVICE_ID'); self.hook=os.getenv('RENDER_DEPLOY_HOOK_URL')
    def configured(self): return bool(self.hook or (self.api and self.service))
    def deploy(self):
        if self.hook:
            r=requests.post(self.hook,timeout=30); r.raise_for_status(); return {'ok':True,'method':'deploy_hook','status':r.status_code}
        if self.api and self.service:
            r=requests.post(f'https://api.render.com/v1/services/{self.service}/deploys',headers={'Authorization':f'Bearer {self.api}','Content-Type':'application/json'},json={},timeout=30); r.raise_for_status(); return {'ok':True,'method':'render_api','status':r.status_code,'body':r.json()}
        return {'ok':False,'reason':'deploy_not_configured'}
    def git_status(self):
        try: return subprocess.run(['git','status','--short'],capture_output=True,text=True,timeout=15).stdout
        except Exception as e: return str(e)
