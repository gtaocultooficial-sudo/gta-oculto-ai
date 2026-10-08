import os, json, base64
from pathlib import Path

class YouTubePublisher:
    def __init__(self):
        self.enabled=os.getenv('YOUTUBE_AUTO_PUBLISH','0').lower() in ('1','true','yes','on')
        self.token_json=os.getenv('YOUTUBE_TOKEN_JSON','').strip()
    def _service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        scopes=['https://www.googleapis.com/auth/youtube.upload']
        raw=self.token_json
        if raw.startswith('base64:'): raw=base64.b64decode(raw[7:]).decode()
        creds=Credentials.from_authorized_user_info(json.loads(raw),scopes)
        return build('youtube','v3',credentials=creds,cache_discovery=False)
    def upload(self, video_path, metadata):
        if not self.enabled: return {'ok':False,'reason':'YOUTUBE_AUTO_PUBLISH_DISABLED'}
        if not self.token_json: return {'ok':False,'reason':'YOUTUBE_TOKEN_JSON_MISSING'}
        try:
            from googleapiclient.http import MediaFileUpload
            service=self._service()
            body={'snippet':{'title':metadata.get('title','GTA 6'),'description':metadata.get('description',''),'tags':metadata.get('tags',[]),'categoryId':'20'},'status':{'privacyStatus':os.getenv('YOUTUBE_PRIVACY','private'),'selfDeclaredMadeForKids':False}}
            req=service.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(video_path),mimetype='video/mp4',resumable=True))
            resp=req.execute()
            return {'ok':True,'video_id':resp.get('id'),'privacy':body['status']['privacyStatus']}
        except Exception as e: return {'ok':False,'reason':str(e)[:1000]}
