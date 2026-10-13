import os, json, base64
from datetime import datetime, timezone
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
            path=Path(video_path)
            if not path.is_file() or path.stat().st_size <= 0:
                return {'ok':False,'reason':'VIDEO_FILE_MISSING_OR_EMPTY'}
            publish_at=str(metadata.get('publish_at') or '').strip()
            if publish_at:
                try:
                    scheduled_dt=datetime.fromisoformat(publish_at.replace('Z','+00:00'))
                except ValueError:
                    return {'ok':False,'reason':'INVALID_PUBLISH_AT: informe data ISO 8601 válida com fuso horário'}
                if scheduled_dt.tzinfo is None or scheduled_dt.utcoffset() is None:
                    return {'ok':False,'reason':'INVALID_PUBLISH_AT: o agendamento precisa incluir fuso horário'}
                if scheduled_dt.astimezone(timezone.utc) <= datetime.now(timezone.utc):
                    return {'ok':False,'reason':'PUBLISH_AT_NOT_IN_FUTURE: horário agendado já passou'}
            from googleapiclient.http import MediaFileUpload
            service=self._service()
            # Fail-safe: uploads stay private unless YouTube receives a valid future publishAt.
            # Scheduled videos remain private until YouTube publishes them at that time.
            status={'privacyStatus':'private','selfDeclaredMadeForKids':False}
            if publish_at:
                status['publishAt']=scheduled_dt.isoformat()
            title=str(metadata.get('title') or '').strip()
            if not title:
                return {'ok':False,'reason':'VIDEO_TITLE_MISSING'}
            body={'snippet':{'title':title,'description':metadata.get('description',''),'tags':metadata.get('tags',[]),'categoryId':'20'},'status':status}
            req=service.videos().insert(part='snippet,status',body=body,media_body=MediaFileUpload(str(path),mimetype='video/mp4',resumable=True))
            resp=req.execute()
            return {'ok':True,'video_id':resp.get('id'),'privacy':body['status']['privacyStatus'],'scheduled_at':publish_at or None,'scheduled':bool(publish_at)}
        except Exception as e:
            detail=str(e)[:1000]
            if 'uploadLimitExceeded' in detail:
                return {'ok':False,'reason':'YOUTUBE_DAILY_UPLOAD_LIMIT: o YouTube bloqueou novos envios para este canal. O MP4 foi mantido no servidor; aguarde a liberação do limite e tente novamente.','retry_after_hours':24,'error_detail':detail}
            return {'ok':False,'reason':detail}
