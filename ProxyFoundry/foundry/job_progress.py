"""Keep structured ZIP progress alongside ordinary three-argument progress messages."""
FIELDS=('phase','saveStage','savedBytes','totalBytes','saveElapsedSeconds','saveBytesPerSecond','saveEtaSeconds')

def update_fields(done,total,message):
    details=message if isinstance(message,dict) else {}
    return {'done':done,'total':total,'message':str(details.get('message','') if details else message),
            **{key:details[key] for key in FIELDS if key in details}}
