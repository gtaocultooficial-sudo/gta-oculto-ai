import os, json, base64
from datetime import datetime, timedelta, timezone


class YouTubeAnalytics:
    def __init__(self):
        self.enabled=os.getenv('YOUTUBE_ANALYTICS_ENABLED','0').lower() in ('1','true','yes','on')
        self.token_json=os.getenv('YOUTUBE_TOKEN_JSON','').strip()

    def _video_details(self, raw, video_ids):
        """Read titles and durations for Analytics video IDs; metadata is optional."""
        ids=[str(x) for x in (video_ids or []) if str(x).strip()][:50]
        if not ids:
            return {}
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            creds=Credentials.from_authorized_user_info(
                json.loads(raw), ['https://www.googleapis.com/auth/youtube.upload']
            )
            yt=build('youtube','v3',credentials=creds,cache_discovery=False)
            details={}
            for i in range(0,len(ids),50):
                response=yt.videos().list(
                    part='snippet,contentDetails',
                    id=','.join(ids[i:i+50])
                ).execute()
                for item in response.get('items',[]):
                    snippet=item.get('snippet',{}) or {}
                    content=item.get('contentDetails',{}) or {}
                    details[str(item.get('id',''))]={
                        'title':str(snippet.get('title','') or ''),
                        'published_at':str(snippet.get('publishedAt','') or ''),
                        'duration':str(content.get('duration','') or '')
                    }
            return details
        except Exception:
            # Analytics metrics remain useful even if title enrichment is denied.
            return {}

    def collect(self, days=7, video_ids=None):
        # Prefer YouTube Analytics when its dedicated read-only scope is granted.
        # If it is absent, public Data API stats can only be fetched for known IDs.
        if not self.token_json:
            return {'ok':False,'reason':'ANALYTICS_NOT_CONFIGURED'}
        try:
            from google.oauth2.credentials import Credentials
            from googleapiclient.discovery import build
            raw=self.token_json
            if raw.startswith('base64:'):
                raw=base64.b64decode(raw[7:]).decode()
            scopes=['https://www.googleapis.com/auth/yt-analytics.readonly']
            creds=Credentials.from_authorized_user_info(json.loads(raw),scopes)
            svc=build('youtubeAnalytics','v2',credentials=creds,cache_discovery=False)
            end=datetime.now(timezone.utc).date()
            start=end-timedelta(days=days)
            response=svc.reports().query(
                ids='channel==MINE',
                startDate=str(start),
                endDate=str(end),
                metrics='views,likes,subscribersGained,averageViewDuration,estimatedMinutesWatched',
                dimensions='video',
                sort='-views',
                maxResults=50
            ).execute()
            rows=[list(row) for row in (response.get('rows') or [])]
            headers=list(response.get('columnHeaders') or [])
            ids=[str(row[0]) for row in rows if row]
            details=self._video_details(raw,ids)
            if rows and not any(str(h.get('name','')).lower()=='title' for h in headers if isinstance(h,dict)):
                headers.append({'name':'title'})
                for row in rows:
                    row.append(details.get(str(row[0]),{}).get('title',''))
            return {
                'ok':True,
                'rows':rows,
                'headers':headers,
                'start':str(start),
                'end':str(end)
            }
        except Exception as analytics_error:
            try:
                from google.oauth2.credentials import Credentials
                from googleapiclient.discovery import build
                creds=Credentials.from_authorized_user_info(
                    json.loads(raw), ['https://www.googleapis.com/auth/youtube.upload']
                )
                yt=build('youtube','v3',credentials=creds,cache_discovery=False)
                ids=[str(x) for x in (video_ids or []) if str(x).strip() and not str(x).startswith('production:')][:50]
                if not ids:
                    return {
                        'ok':False,
                        'reason':'ANALYTICS_SCOPE_MISSING_AND_NO_TRACKED_VIDEOS',
                        'analytics_error':str(analytics_error)[:500]
                    }
                response=yt.videos().list(
                    part='statistics,snippet,contentDetails',
                    id=','.join(ids)
                ).execute()
                rows=[]
                for item in response.get('items',[]):
                    stats=item.get('statistics',{}) or {}
                    snippet=item.get('snippet',{}) or {}
                    content=item.get('contentDetails',{}) or {}
                    rows.append([
                        item.get('id',''),
                        float(stats.get('viewCount',0) or 0),
                        float(stats.get('likeCount',0) or 0),
                        float(stats.get('commentCount',0) or 0),
                        0,0,0,
                        snippet.get('publishedAt',''),
                        content.get('duration',''),
                        snippet.get('title','')
                    ])
                return {
                    'ok':True,
                    'mode':'public_stats_fallback',
                    'rows':rows,
                    'headers':[
                        {'name':'video'},{'name':'views'},{'name':'likes'},{'name':'comments'},
                        {'name':'subscribersgained'},{'name':'averageviewduration'},
                        {'name':'estimatedminuteswatched'},{'name':'publishedat'},
                        {'name':'duration'},{'name':'title'}
                    ],
                    'start':str(datetime.now(timezone.utc).date()-timedelta(days=days)),
                    'end':str(datetime.now(timezone.utc).date()),
                    'analytics_error':str(analytics_error)[:500]
                }
            except Exception as fallback_error:
                return {
                    'ok':False,
                    'reason':str(analytics_error)[:700],
                    'fallback_error':str(fallback_error)[:700]
                }
