"""A continuous, blocking generation screen with an adaptive estimate."""
from test_review_export import review_browser

def test_estimate_never_resets_and_adapts_to_card_speed(review_browser):
    page,_=review_browser
    result=page.evaluate('''async()=>{
      const {GenerationEstimate}=await import('/site/generation-progress.js');
      let now=0;const value=new GenerationEstimate(100,()=>now);
      const samples=[value.read()];now=10000;samples.push(value.update('prepare',50,100));
      now=20000;samples.push(value.update('prepare',100,100));samples.push(value.update('render',0,100));
      now=30000;samples.push(value.update('render',10,100));
      now=90000;samples.push(value.update('render',20,100));
      now=110000;samples.push(value.update('render',100,100));samples.push(value.update('finish'));
      return samples;
    }''')
    assert result[0]['percent']==0
    assert all(a['percent']<=b['percent']<100 for a,b in zip(result,result[1:]))
    assert result[5]['seconds']>result[4]['seconds']

def test_generation_overlay_blocks_dismissal_and_releases_after_cancel(review_browser):
    page,_=review_browser
    page.evaluate('''async()=>{
      window.generation=await import('/site/generation-progress.js');
      window.owner={controller:new AbortController()};
      window.screenTest=new generation.GenerationScreen('Example deck',120);screenTest.attach(owner);
      screenTest.update('prepare',20,120);
    }''')
    screen=page.locator('#generation-screen')
    assert screen.is_visible() and screen.locator('progress').count()==1
    assert screen.evaluate('(node)=>node.getBoundingClientRect().height===innerHeight')
    page.screenshot(path=str(__import__('pathlib').Path(__file__).resolve().parents[1]/'test-results/generation-loading.png'))
    page.keyboard.press('Escape')
    assert screen.is_visible()
    screen.click(position={'x':5,'y':5})
    assert screen.is_visible()
    screen.get_by_role('button',name='Cancel',exact=True).click()
    assert page.evaluate('owner.controller.signal.aborted')
    page.evaluate('screenTest.close()')
    assert screen.count()==0 and page.evaluate('generation.generationScreen.active===null')

def test_overlay_cleanup_on_failure_and_success(review_browser):
    page,_=review_browser
    result=page.evaluate('''async()=>{
      const g=await import('/site/generation-progress.js');
      let failed=false;
      try{await g.withGenerationScreen('Fail',1,async()=>{throw Error('disk failed');});}
      catch(error){failed=error.message==='disk failed'&&!document.querySelector('#generation-screen');}
      await g.withGenerationScreen('Success',1,async screen=>{screen.update('render',1,1);});
      return failed&&!g.generationScreen.active&&!document.querySelector('#generation-screen');
    }''')
    assert result