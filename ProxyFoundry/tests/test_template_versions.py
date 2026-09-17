from foundry.compiler import Compiler,AUTO_TEMPLATE_VERSIONS,BUILTIN_TEMPLATE_VERSIONS
from foundry.domain import PIPELINE_VERSION,GENERATION_VERSION,render_key
from foundry.storage import Store


def test_pipeline_version_keeps_generation_compatibility_name():
    assert PIPELINE_VERSION == GENERATION_VERSION
    assert isinstance(PIPELINE_VERSION,str) and PIPELINE_VERSION


def test_auto_template_version_is_scoped_to_structural_group(tmp_path,monkeypatch):
    compiler=Compiler(Store(tmp_path))
    station=compiler.template_identity('station','auto')
    planeswalker=compiler.template_identity('planeswalker','auto')
    assert station[0]=='auto:station' and planeswalker[0]=='auto:planeswalker'
    assert station[1]==1 and planeswalker[1]==1
    monkeypatch.setitem(AUTO_TEMPLATE_VERSIONS,'station',2)
    station2=compiler.template_identity('station','auto')
    planeswalker2=compiler.template_identity('planeswalker','auto')
    assert station2[1]==2 and station2[2]==2
    assert planeswalker2==planeswalker
    data={'artSource':'/api/assets/art','frames':[]}
    assert render_key(data,'art',station[2]) != render_key(data,'art',station2[2])
    assert render_key(data,'art',planeswalker[2]) == render_key(data,'art',planeswalker2[2])


def test_named_builtin_template_versions_are_independent(tmp_path,monkeypatch):
    compiler=Compiler(Store(tmp_path))
    normal=compiler.template_identity('standard','normal')
    land=compiler.template_identity('land','land')
    monkeypatch.setitem(BUILTIN_TEMPLATE_VERSIONS,'normal',2)
    assert compiler.template_identity('standard','normal')[1]==2
    assert compiler.template_identity('land','land')==land
    assert normal[0]=='builtin:normal'


def test_custom_template_fingerprint_changes_only_for_edited_template(tmp_path):
    store=Store(tmp_path);compiler=Compiler(store)
    base={'width':1000,'height':1400,'frames':[],'text':{'title':{'text':''},'type':{'text':''}}}
    one=store.put('templates',{'name':'One','data':base,'groups':['standard'],'legendary':True,'mapping':{}})
    two=store.put('templates',{'name':'Two','data':base,'groups':['standard'],'legendary':True,'mapping':{}})
    one_before=compiler.template_identity('standard',one['id']);two_before=compiler.template_identity('standard',two['id'])
    changed=dict(one);changed['mapping']={'title':'title'};store.put('templates',changed,one['revision'])
    one_after=compiler.template_identity('standard',one['id']);two_after=compiler.template_identity('standard',two['id'])
    assert one_after[1]!=one_before[1]
    assert two_after==two_before
    assert one_after[2]==1  # custom data itself is already part of the render key


def test_saga_runtime_fix_invalidates_only_saga_auto_templates(tmp_path):
    compiler=Compiler(Store(tmp_path))
    assert compiler.template_identity('saga','auto')[1:]==(2,2)
    assert compiler.template_identity('saga-creature','auto')[1:]==(2,2)
    assert compiler.template_identity('standard','auto')[1:]==(1,1)
    assert compiler.template_identity('planeswalker','auto')[1:]==(1,1)
