import os, json, base64
from datetime import datetime, timedelta, timezone
class YouTubeAnalytics:
    def __init__(self): self.enabled=os.getenv('YOUTUBE_ANALYTICS_ENABLED','0').lower() in ('1','true','yes','on'); self.token_json=os.getenv('YOUTUBE_TOKEN_JSON','').strip()
    def collect(self, days=7):
        if not (self.enabled and self.token_json): return {'ok':False,'reason':'ANALYTICS_NOT_CONFIGURED'}
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            raw=self.token_json
            if raw.startswith('base64:'): raw=base64.b64decode(raw[7:]).decode()
            scopes=['https://www.googleapis.com/auth/yt-analytics.readonly']
            creds=Credentials.from_authorized_user_info(json.loads(raw),scopes)
            svc=build('youtubeAnalytics','v2',credentials=creds,cache_discovery=False)
            end=datetime.now(timezone.utc).date(); start=end-timedelta(days=days)
            res=svc.reports().query(ids='channel==MINE',startDate=str(start),endDate=str(end),metrics='views,likes,subscribersGained,averageViewDuration,estimatedMinutesWatched',dimensions='video',sort='-views',maxResults=50).execute()
            return {'ok':True,'rows':res.get('rows',[]),'headers':res.get('columnHeaders',[]),'start':str(start),'end':str(end)}
        except Exception as e: return {'ok':False,'reason':str(e)[:1000]}
