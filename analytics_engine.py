import os, json, base64
from datetime import datetime, timedelta, timezone
class YouTubeAnalytics:
    def __init__(self): self.enabled=os.getenv('YOUTUBE_ANALYTICS_ENABLED','0').lower() in ('1','true','yes','on'); self.token_json=os.getenv('YOUTUBE_TOKEN_JSON','').strip()
    def collect(self, days=7, video_ids=None):
        # Prefer YouTube Analytics when its dedicated scope is available.
        # If the OAuth token only has youtube.upload, fall back to public video
        # statistics through the Data API.
        if not self.token_json:
            return {'ok':False,'reason':'ANALYTICS_NOT_CONFIGURED'}
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
        except Exception as analytics_error:
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds=Credentials.from_authorized_user_info(json.loads(raw),['https://www.googleapis.com/auth/youtube.upload'])
                yt=build('youtube','v3',credentials=creds,cache_discovery=False)
                ids=[str(x) for x in (video_ids or []) if str(x).strip() and not str(x).startswith('production:')][:50]
                if not ids:
                    return {'ok':False,'reason':'ANALYTICS_SCOPE_MISSING_AND_NO_TRACKED_VIDEOS','analytics_error':str(analytics_error)[:500]}
                resp=yt.videos().list(part='statistics,snippet,contentDetails',id=','.join(ids)).execute()
                rows=[]
                for item in resp.get('items',[]):
                    st=item.get('statistics',{}) or {}
                    sn=item.get('snippet',{}) or {}
                    cd=item.get('contentDetails',{}) or {}
                    rows.append([
                        item.get('id',''), float(st.get('viewCount',0) or 0),
                        float(st.get('likeCount',0) or 0), float(st.get('commentCount',0) or 0),
                        0, 0, 0, sn.get('publishedAt',''), cd.get('duration','')
                    ])
                return {'ok':True,'mode':'public_stats_fallback','rows':rows,
                        'headers':[{'name':'video'},{'name':'views'},{'name':'likes'},{'name':'comments'},
                                   {'name':'subscribersgained'},{'name':'averageviewduration'},
                                   {'name':'estimatedminuteswatched'},{'name':'publishedat'},{'name':'duration'}],
                        'start':str(datetime.now(timezone.utc).date()-timedelta(days=days)),
                        'end':str(datetime.now(timezone.utc).date()),
                        'analytics_error':str(analytics_error)[:500]}
            except Exception as fallback_error:
                return {'ok':False,'reason':str(analytics_error)[:700],
                        'fallback_error':str(fallback_error)[:700]}
