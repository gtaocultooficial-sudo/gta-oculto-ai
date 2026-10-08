import os, requests, json, time

class SocialPublisher:
    """Optional zero-cost adapters. Disabled until the owner supplies platform credentials."""
    def __init__(self):
        self.tiktok_enabled=os.getenv('TIKTOK_AUTO_PUBLISH','0').lower() in ('1','true','yes','on')
        self.instagram_enabled=os.getenv('INSTAGRAM_AUTO_PUBLISH','0').lower() in ('1','true','yes','on')
        self.tiktok_token=os.getenv('TIKTOK_ACCESS_TOKEN','').strip()
        self.tiktok_consent=os.getenv('TIKTOK_POST_CONSENT','0').lower() in ('1','true','yes','on')
        self.ig_token=os.getenv('INSTAGRAM_ACCESS_TOKEN','').strip()
        self.ig_user=os.getenv('INSTAGRAM_USER_ID','').strip()
    def status(self):
        return {'tiktok':self.tiktok_enabled and bool(self.tiktok_token and self.tiktok_consent),'instagram':self.instagram_enabled and bool(self.ig_token and self.ig_user)}
    def _result(self, platform, ok=False, reason=None, **extra):
        d={'ok':ok,'platform':platform}
        if reason: d['reason']=reason
        d.update(extra); return d
    def tiktok(self, video_url, metadata):
        if not self.tiktok_enabled: return self._result('tiktok',reason='TIKTOK_AUTO_PUBLISH_DISABLED')
        if not self.tiktok_token: return self._result('tiktok',reason='TIKTOK_ACCESS_TOKEN_MISSING')
        if not self.tiktok_consent: return self._result('tiktok',reason='TIKTOK_POST_CONSENT_REQUIRED')
        # Content Posting API: URL pull publishing. TikTok app/account permissions are required.
        try:
            info=requests.post('https://open.tiktokapis.com/v2/post/publish/creator_info/query/',headers={'Authorization':f'Bearer {self.tiktok_token}','Content-Type':'application/json'},timeout=30)
            creator=info.json() if info.ok else {}
            opts=((creator.get('data') or {}).get('privacy_level_options') or ['SELF_ONLY'])
            privacy=os.getenv('TIKTOK_PRIVACY','SELF_ONLY').strip() or 'SELF_ONLY'
            if privacy not in opts: privacy='SELF_ONLY' if 'SELF_ONLY' in opts else opts[0]
            r=requests.post('https://open.tiktokapis.com/v2/post/publish/video/init/',headers={'Authorization':f'Bearer {self.tiktok_token}','Content-Type':'application/json; charset=UTF-8'},json={'post_info':{'title':metadata.get('title','GTA 6')[:2200],'privacy_level':privacy,'disable_duet':False,'disable_comment':False,'disable_stitch':False,'is_aigc':True},'source_info':{'source':'PULL_FROM_URL','video_url':video_url}},timeout=60)
            data=r.json()
            return self._result('tiktok',r.ok and not data.get('error'),response=data)
        except Exception as e: return self._result('tiktok',reason=str(e)[:1000])
    def instagram(self, video_url, metadata):
        if not self.instagram_enabled: return self._result('instagram',reason='INSTAGRAM_AUTO_PUBLISH_DISABLED')
        if not self.ig_token or not self.ig_user: return self._result('instagram',reason='INSTAGRAM_CREDENTIALS_MISSING')
        try:
            caption=metadata.get('description') or metadata.get('title','GTA 6')
            r=requests.post(f'https://graph.facebook.com/v23.0/{self.ig_user}/media',params={'media_type':'REELS','video_url':video_url,'caption':caption[:2200],'access_token':self.ig_token},timeout=60)
            data=r.json()
            if not r.ok or data.get('error'): return self._result('instagram',reason=str(data.get('error') or data)[:1000])
            cid=data.get('id')
            p=requests.post(f'https://graph.facebook.com/v23.0/{self.ig_user}/media_publish',params={'creation_id':cid,'access_token':self.ig_token},timeout=60)
            pdata=p.json()
            return self._result('instagram',p.ok and not pdata.get('error'),container_id=cid,response=pdata)
        except Exception as e: return self._result('instagram',reason=str(e)[:1000])
    def publish(self, video_url, metadata):
        return {'tiktok':self.tiktok(video_url,metadata),'instagram':self.instagram(video_url,metadata),'status':self.status()}
