import os, base64, requests
from pathlib import Path

class DeployManager:
    def __init__(self):
        self.github_token=os.getenv('GITHUB_TOKEN','').strip()
        self.github_repo=os.getenv('GITHUB_REPO','').strip() # owner/repo
        self.github_branch=os.getenv('GITHUB_BRANCH','main').strip()
        self.render_key=os.getenv('RENDER_API_KEY','').strip()
        self.render_service=os.getenv('RENDER_SERVICE_ID','').strip()
        self.auto=os.getenv('GTA_AUTO_DEPLOY','0').lower() in ('1','true','yes','on')
    def status(self):
        return {'configured':bool(self.github_token and self.github_repo and self.render_key and self.render_service),'auto_deploy':self.auto}
    def _headers(self): return {'Authorization':f'Bearer {self.github_token}','Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'}
    def commit_file(self, local_path, repo_path, message):
        if not (self.github_token and self.github_repo): return {'ok':False,'reason':'GITHUB_NOT_CONFIGURED'}
        p=Path(local_path); content=base64.b64encode(p.read_bytes()).decode()
        url=f'https://api.github.com/repos/{self.github_repo}/contents/{repo_path}'
        r=requests.get(url,headers=self._headers(),params={'ref':self.github_branch},timeout=20)
        sha=r.json().get('sha') if r.ok else None
        body={'message':message,'content':content,'branch':self.github_branch}
        if sha: body['sha']=sha
        w=requests.put(url,headers=self._headers(),json=body,timeout=30)
        return {'ok':w.ok,'status':w.status_code,'response':w.json() if w.content else {}}
    def trigger_render(self, commit_id=None):
        if not (self.render_key and self.render_service): return {'ok':False,'reason':'RENDER_NOT_CONFIGURED'}
        url=f'https://api.render.com/v1/services/{self.render_service}/deploys'
        body={}
        if commit_id: body['commitId']=commit_id
        r=requests.post(url,headers={'Authorization':f'Bearer {self.render_key}','Accept':'application/json','Content-Type':'application/json'},json=body,timeout=30)
        return {'ok':r.ok,'status':r.status_code,'response':r.json() if r.content else {}}
    def deploy_candidate(self, local_path, repo_path='app.py', message='GTA OCULTO AI autonomous safe repair'):
        if not self.auto: return {'ok':False,'reason':'AUTO_DEPLOY_DISABLED'}
        commit=self.commit_file(local_path,repo_path,message)
        if not commit.get('ok'): return commit
        sha=((commit.get('response') or {}).get('commit') or {}).get('sha')
        dep=self.trigger_render(sha)
        return {'ok':dep.get('ok'), 'commit':commit, 'deploy':dep}
