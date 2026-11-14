from melodyvault.sources.models import Candidate
from melodyvault.catalog.models import CatalogError
from melodyvault.licensing.source_evidence import check_license


class JamendoProvider:
    name='jamendo'
    policy_url='https://developer.jamendo.com/v3.0/tracks'
    def __init__(self,client_id=''):self.client_id=client_id;self.enabled=bool(client_id)
    def get_metadata(self,external_id,http):
        if not self.enabled:raise CatalogError('Jamendo未配置官方client_id')
        data=http.json('https://api.jamendo.com/v3.0/tracks/',{'client_id':self.client_id,'format':'json','id':external_id,'include':'licenses'})
        if data.get('headers',{}).get('status')!='success':raise CatalogError('Jamendo API error')
        return [check_license(Candidate(self.name,str(i['id']),i['name'],i.get('artist_name',''),i.get('shareurl',''),
            i.get('duration'),license_url=i.get('license_ccurl',''),audio_url=i.get('audiodownload',''),file_format='mp3',
            evidence={'policy_url':self.policy_url}),download_allowed=i.get('audiodownload_allowed') is True) for i in data.get('results',[])]
    def search(self,query,http):
        if not self.enabled:raise CatalogError('Jamendo未配置官方client_id')
        results={}
        for artist,title in list(dict.fromkeys([(query.artist,query.title),(query.artist_names[-1],query.titles[-1])])):
            data=http.json('https://api.jamendo.com/v3.0/tracks/',{'client_id':self.client_id,'format':'json','limit':20,
                'artist_name':artist,'namesearch':title+(' '+query.version_words[0] if query.version_words else ''),'include':'licenses'})
            if data.get('headers',{}).get('status')!='success':raise CatalogError('Jamendo API: '+str(data.get('headers',{}).get('error_message','未知错误')))
            for item in data.get('results',[]):
                c=Candidate(self.name,str(item['id']),item['name'],item.get('artist_name',''),item.get('shareurl',''),
                    item.get('duration'),license_url=item.get('license_ccurl',''),audio_url=item.get('audiodownload',''),
                    evidence={'track_id':item['id'],'audiodownload_allowed':item.get('audiodownload_allowed'),
                              'license_ccurl':item.get('license_ccurl'),'policy_url':self.policy_url})
                results[c.external_id]=check_license(c,download_allowed=item.get('audiodownload_allowed') is True,restricted=item.get('audiodownload_allowed') is False)
        return list(results.values())
