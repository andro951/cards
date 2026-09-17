from pathlib import Path


def replace(path, old, new, count=1):
    p=Path(path); text=p.read_text(encoding='utf-8')
    if old not in text:
        raise SystemExit(f'missing expected text in {path}: {old[:180]!r}')
    p.write_text(text.replace(old,new,count),encoding='utf-8')

replace('ProxyFoundry/foundry/server.py',
    "from .images import ingest_image, rarity_variants, sanitize_svg",
    "from .images import ingest_image, rarity_variants, sanitize_svg, decode_image")

old="""    def _log_face_state(self, label, deck, card, face, old_comp=None):
        comp=face.get('compiled') or {};data=comp.get('data') or {};key=comp.get('renderKey') or ''
        render=self.store.render_get(key) if key else None
        symbol=self.store.asset(comp.get('symbolId','')) if comp.get('symbolId') else None
        old_comp=old_comp or {};old_data=old_comp.get('data') or {}
        self.log.info(
            '%s deck=%s card=%s face=%s pipeline=%s oldGeneration=%s newGeneration=%s oldKey=%s newKey=%s cacheAsset=%s symbol=%s symbolPx=%sx%s ccVersion=%s zoom=%s x=%s y=%s oldZoom=%s oldX=%s oldY=%s',
            label, self._short(deck.get('id')), card.get('name'), face.get('name'), PIPELINE_VERSION,
            old_comp.get('generationVersion') or '-', comp.get('generationVersion') or '-',
            self._short(old_comp.get('renderKey')), self._short(key),
            self._short(render.get('asset_id') if render else ''), self._short(comp.get('symbolId')),
            (symbol or {}).get('width','-'), (symbol or {}).get('height','-'), data.get('version','-'),
            data.get('setSymbolZoom','-'), data.get('setSymbolX','-'), data.get('setSymbolY','-'),
            old_data.get('setSymbolZoom','-'), old_data.get('setSymbolX','-'), old_data.get('setSymbolY','-'))
"""
new="""    def _log_face_state(self, label, deck, card, face, old_comp=None):
        comp=face.get('compiled') or {};data=comp.get('data') or {};key=comp.get('renderKey') or ''
        render=self.store.render_get(key) if key else None
        symbol=self.store.asset(comp.get('symbolId','')) if comp.get('symbolId') else None
        old_comp=old_comp or {};old_data=old_comp.get('data') or {}
        self.log.info(
            '%s deck=%s card=%s face=%s pipeline=%s oldGeneration=%s newGeneration=%s oldKey=%s newKey=%s cacheAsset=%s symbol=%s symbolPx=%sx%s ccVersion=%s zoom=%s x=%s y=%s oldZoom=%s oldX=%s oldY=%s',
            label, self._short(deck.get('id')), card.get('name'), face.get('name'), PIPELINE_VERSION,
            old_comp.get('generationVersion') or '-', comp.get('generationVersion') or '-',
            self._short(old_comp.get('renderKey')), self._short(key),
            self._short(render.get('asset_id') if render else ''), self._short(comp.get('symbolId')),
            (symbol or {}).get('width','-'), (symbol or {}).get('height','-'), data.get('version','-'),
            data.get('setSymbolZoom','-'), data.get('setSymbolX','-'), data.get('setSymbolY','-'),
            old_data.get('setSymbolZoom','-'), old_data.get('setSymbolX','-'), old_data.get('setSymbolY','-'))
        if symbol and comp.get('symbolId'):
            try:
                image=decode_image(self.store.asset_path(comp['symbolId']).read_bytes());alpha=image.getchannel('A')
                alpha0=alpha.point(lambda value:255 if value>0 else 0).getbbox()
                alpha2=alpha.point(lambda value:255 if value>2 else 0).getbbox()
                def bbox_text(box):
                    return '-' if not box else f'{box[0]},{box[1]},{box[2]},{box[3]}:{box[2]-box[0]}x{box[3]-box[1]}'
                cw=float(data.get('width') or 0);ch=float(data.get('height') or 0);zoom=float(data.get('setSymbolZoom') or 0)
                sx=float(data.get('setSymbolX') or 0)*cw;sy=float(data.get('setSymbolY') or 0)*ch
                sw=float(symbol.get('width') or 0);sh=float(symbol.get('height') or 0)
                bounds=data.get('setSymbolBounds') or {};type_box=(data.get('text') or {}).get('type') or {}
                bx=float(bounds.get('x') or 0)*cw;by=float(bounds.get('y') or 0)*ch
                bw=float(bounds.get('width') or 0)*cw;bh=float(bounds.get('height') or 0)*ch
                ty=float(type_box.get('y') or 0)*ch;th=float(type_box.get('height') or 0)*ch
                self.log.info(
                    'SET_SYMBOL_GEOMETRY deck=%s face=%s key=%s storedPx=%sx%s alphaGt0=%s alphaGt2=%s boundsAnchorPx=%.3f,%.3f boundsSizePx=%.3fx%.3f drawExpectedPx=%.3f,%.3f,%.3fx%.3f typeBoxPxY=%.3f typeBoxPxH=%.3f typeBoxCenterPx=%.3f',
                    self._short(deck.get('id')), face.get('name'), self._short(key), int(sw), int(sh), bbox_text(alpha0), bbox_text(alpha2),
                    bx,by,bw,bh,sx,sy,sw*zoom,sh*zoom,ty,th,ty+th/2)
            except Exception as exc:
                self.log.warning('SET_SYMBOL_GEOMETRY_FAILED face=%s key=%s error=%s',face.get('name'),self._short(key),str(exc)[:500])
"""
replace('ProxyFoundry/foundry/server.py',old,new)

replace('ProxyFoundry/foundry/server.py',
    "        if p == '/api/client-error':\n            self.app.log.error('Browser: %s', str(d.get('error', ''))[:8000]); return self.respond({'ok': True})\n",
    "        if p == '/api/client-error':\n            self.app.log.error('Browser: %s', str(d.get('error', ''))[:8000]); return self.respond({'ok': True})\n        if p == '/api/render-diagnostic':\n            diag=d.get('diagnostic') if isinstance(d.get('diagnostic'),dict) else {}\n            payload={'key':str(d.get('key') or '')[:64],'stage':str(d.get('stage') or '')[:80],'diagnostic':diag}\n            self.app.log.info('RUNTIME_SYMBOL %s',json.dumps(payload,ensure_ascii=False,separators=(',',':'))[:16000])\n            return self.respond({'ok':True})\n")

old="""  // The old pinned core predates Stations. Compose the genuine native Station
  // canvases after the frame, exactly where the current native core does.
  if(!String(window.drawCard).includes('stationPreFrameCanvas')){
    const nativeDrawImage=window.cardContext.drawImage;
    window.cardContext.drawImage=function(image,...args){
      const result=nativeDrawImage.call(this,image,...args);
      if(image===window.frameCanvas&&window.card?.station&&String(window.card.version).toLowerCase().includes('station')){
        for(const canvas of [window.stationPreFrameCanvas,window.stationPostFrameCanvas])
          if(canvas)nativeDrawImage.call(this,canvas,0,0,window.cardCanvas.width,window.cardCanvas.height);
      }
      return result;
    };
  }
"""
new="""  // Instrument the genuine canvas draw call so diagnostics record the exact
  // destination rectangle CardConjurer actually used for the set symbol.
  // The old pinned core also predates Stations; preserve the existing native
  // Station composition adapter without changing any card geometry.
  let lastSetSymbolDraw=null;
  const nativeDrawImage=window.cardContext.drawImage;
  const needsStationCompose=!String(window.drawCard).includes('stationPreFrameCanvas');
  window.cardContext.drawImage=function(image,...args){
    if(S.active&&image===window.setSymbol){
      lastSetSymbolDraw={phase:S.phase,args:args.map(v=>typeof v==='number'?v:Number(v)),imageWidth:image?.width||0,imageHeight:image?.height||0,naturalWidth:image?.naturalWidth||0,naturalHeight:image?.naturalHeight||0};
    }
    const result=nativeDrawImage.call(this,image,...args);
    if(needsStationCompose&&image===window.frameCanvas&&window.card?.station&&String(window.card.version).toLowerCase().includes('station')){
      for(const canvas of [window.stationPreFrameCanvas,window.stationPostFrameCanvas])
        if(canvas)nativeDrawImage.call(this,canvas,0,0,window.cardCanvas.width,window.cardCanvas.height);
    }
    return result;
  };
"""
replace('ProxyFoundry/site/runtime-bridge.js',old,new)

replace('ProxyFoundry/site/runtime-bridge.js',
    "  async function fontsReady(data){\n",
    "  function symbolRuntimeSnapshot(stage,key,data){\n    const image=window.setSymbol,card=window.card||{},cw=Number(card.width||data.width||0),ch=Number(card.height||data.height||0);\n    const zoom=Number(card.setSymbolZoom??data.setSymbolZoom??0),x=Number(card.setSymbolX??data.setSymbolX??0),y=Number(card.setSymbolY??data.setSymbolY??0);\n    const iw=Number(image?.width||0),ih=Number(image?.height||0);\n    post('diagnostic',{key,stage,diagnostic:{version:card.version||data.version||'',input:{x:data.setSymbolX??null,y:data.setSymbolY??null,zoom:data.setSymbolZoom??null},card:{x:card.setSymbolX??null,y:card.setSymbolY??null,zoom:card.setSymbolZoom??null,width:cw,height:ch},image:{src:String(image?.src||'').slice(0,220),width:iw,height:ih,naturalWidth:Number(image?.naturalWidth||0),naturalHeight:Number(image?.naturalHeight||0),complete:!!image?.complete},expectedDraw:{x:x*cw,y:y*ch,width:iw*zoom,height:ih*zoom},lastDraw:lastSetSymbolDraw}});\n  }\n  async function fontsReady(data){\n")

replace('ProxyFoundry/site/runtime-bridge.js',
    "    clearStationState();S.active=true;S.clearErrors();S.phase='assets';const data=structuredClone(request.data);const storageKey='__pf_'+request.key;\n",
    "    clearStationState();lastSetSymbolDraw=null;S.active=true;S.clearErrors();S.phase='assets';const data=structuredClone(request.data);const storageKey='__pf_'+request.key;\n")

replace('ProxyFoundry/site/runtime-bridge.js',
    "      await readyImages(imagesFor(window.card,symbols));await fontsReady(window.card);\n      // Stop the native 500ms debounce and perform its own final redraw, in order.\n",
    "      await readyImages(imagesFor(window.card,symbols));await fontsReady(window.card);\n      symbolRuntimeSnapshot('after-load',request.key,data);\n      // Stop the native 500ms debounce and perform its own final redraw, in order.\n")

replace('ProxyFoundry/site/runtime-bridge.js',
    "      await window.drawText();await window.bottomInfoEdited();await window.watermarkEdited();window.drawFrames();window.drawCard();\n      await sleep(550);\n",
    "      await window.drawText();await window.bottomInfoEdited();await window.watermarkEdited();window.drawFrames();window.drawCard();\n      symbolRuntimeSnapshot('after-first-draw',request.key,data);\n      await sleep(550);\n")

replace('ProxyFoundry/site/runtime-bridge.js',
    "      await window.drawText();await window.bottomInfoEdited();window.drawFrames();window.drawCard();\n      const errors=S.errors.filter(x=>x.phase!=='bootstrap');\n",
    "      await window.drawText();await window.bottomInfoEdited();window.drawFrames();window.drawCard();\n      symbolRuntimeSnapshot('after-final-draw',request.key,data);\n      const errors=S.errors.filter(x=>x.phase!=='bootstrap');\n")

replace('ProxyFoundry/site/render.js',
    "      if(m.type==='failed'&&!ready){readyReject(new Error(m.error));return;}\n      if(!pending||m.key!==pending.key)return;\n",
    "      if(m.type==='failed'&&!ready){readyReject(new Error(m.error));return;}\n      if(m.type==='diagnostic'){api('/api/render-diagnostic',{key:m.key,stage:m.stage,diagnostic:m.diagnostic}).catch(()=>{});return;}\n      if(!pending||m.key!==pending.key)return;\n")

replace('ProxyFoundry/tests/test_server.py',
    "    assert 'zoom=' in log and 'newKey=' in log and 'cachePresent=' in log\n",
    "    assert 'zoom=' in log and 'newKey=' in log and 'cachePresent=' in log\n    assert 'SET_SYMBOL_GEOMETRY' in log and 'alphaGt2=' in log and 'drawExpectedPx=' in log\n")

marker="\n\ndef test_import_prepare_render_order_roundtrip(running):\n"
addition="""

def test_runtime_symbol_diagnostic_endpoint(running):
    app,s=running
    payload={'key':'a'*64,'stage':'after-final-draw','diagnostic':{'version':'m15Regular','image':{'width':869,'height':1057},'card':{'x':.87,'y':.57,'zoom':.109},'lastDraw':{'args':[1757,1606,94.7,115.2]}}}
    status,out,_=request(s,'/api/render-diagnostic',payload);assert status==200 and out['ok'] is True
    for h in list(app.log.handlers):h.flush()
    log=(app.store.home/'logs/app.log').read_text(encoding='utf-8')
    assert 'RUNTIME_SYMBOL' in log and 'after-final-draw' in log and '869' in log and '1757' in log


def test_runtime_symbol_source_instrumentation():
    root=Path(__file__).resolve().parents[1]
    bridge=(root/'site/runtime-bridge.js').read_text(encoding='utf-8')
    render=(root/'site/render.js').read_text(encoding='utf-8')
    for token in ['lastSetSymbolDraw','image===window.setSymbol','after-load','after-first-draw','after-final-draw','expectedDraw']:
        assert token in bridge
    assert "m.type==='diagnostic'" in render and '/api/render-diagnostic' in render
"""
p=Path('ProxyFoundry/tests/test_server.py');text=p.read_text(encoding='utf-8')
if marker not in text:raise SystemExit('missing test insertion marker')
p.write_text(text.replace(marker,addition+marker,1),encoding='utf-8')
