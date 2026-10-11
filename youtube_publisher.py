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
            publish_at=str(metadata.get('publish_at') or '').strip()
            # YouTube requires scheduled videos to be private until the scheduled time.
            status={'privacyStatus':'private' if publish_at else os.getenv('YOUTUBE_PRIVACY','private'),'selfDeclaredMadeForKids':False}
            if publish_at:
                status['publishAt']=publish_at
            body={'snippet':{'title':metadata.get('title','GTA 6'),'description':metadata.get('description',''),'tags':metadata.get('tags',[]),'categoryId':'20'},'status':status}
            req=service.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(video_path),mimetype='video/mp4',resumable=True))
            resp=req.execute()
            return {'ok':True,'video_id':resp.get('id'),'privacy':body['status']['privacyStatus'],'scheduled_at':publish_at or None,'scheduled':bool(publish_at)}
        except Exception as e:
            detail=str(e)[:1000]
            if 'uploadLimitExceeded' in detail:
                return {'ok':False,'reason':'YOUTUBE_DAILY_UPLOAD_LIMIT: o YouTube bloqueou novos envios para este canal. O MP4 foi mantido no servidor; aguarde a liberação do limite e tente novamente.','retry_after_hours':24,'error_detail':detail}
            return {'ok':False,'reason':detail}
