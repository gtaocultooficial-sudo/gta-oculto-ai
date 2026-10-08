from audit_engine import caption_audit, repair_captions

def test_repair_removes_connector_breaks():
    narration='A Rockstar confirmou uma informação importante sobre GTA 6 no Xbox Cloud Gaming. O ponto principal é entender o que realmente foi confirmado.'
    bad=['A ROCKSTAR CONFIRMOU UMA','INFORMAÇÃO IMPORTANTE SOBRE','GTA 6 NO PC VIA','XBOX CLOUD GAMING, CONFIRMA','O PONTO PRINCIPAL É','ENTENDER O QUE REALMENTE FOI']
    before=caption_audit(bad,narration)['score']
    fixed=repair_captions(bad,narration,6)
    after=caption_audit(fixed,narration)['score']
    assert fixed
    assert after >= before

def test_internal_metadata_penalized():
    r=caption_audit(['RADAR SCORE 96','GTA 6 CONFIRMOU ISSO'], 'GTA 6 confirmou isso.')
    assert 'internal_metadata' in r['issues']
