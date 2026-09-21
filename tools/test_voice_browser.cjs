const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const root = process.argv[2] || path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'hub/voice_widget.py'), 'utf8').split('_HTML = """')[1].split('"""')[0];
const css = fs.readFileSync(path.join(root, 'hub/static/voice.css'), 'utf8');
const script = fs.readFileSync(path.join(root, 'hub/static/voice.js'), 'utf8');
const delay = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const browser = await chromium.launch({channel:'msedge', headless:true});
  try {
    const context = await browser.newContext({viewport:{width:390,height:844}});
    const page = await context.newPage();
    const errors = []; page.on('pageerror', e => errors.push(e.message));
    const calls = [], pending = [];
    let slow = false;
    await page.route('http://hub.test/**', async route => {
      const u = new URL(route.request().url());
      if (!u.pathname.startsWith('/api/')) return route.fulfill({contentType:'text/html',body:`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{background:#080c28;color:white} ${css}</style><button data-talk>TALK</button><h1>Mission board</h1>${html}<script>${script}</script>`});
      let j = {};
      if (u.pathname === '/api/voice/voices') j={voices:[{id:'hub-low',name:'Hub low'}],default:'hub-low'};
      else if (u.pathname === '/api/voice/status') j={whisper:true};
      else if (u.pathname === '/api/voice/transcribe') { calls.push({transcribed:true}); j={text:'interrupted request'}; }
      else if (u.pathname === '/api/voice/chat') {
        const b = route.request().postDataJSON(); calls.push(b);
        if (b.text === 'slow') await delay(350);
        if (b.text === 'hang') { await delay(1100); }
        j = b.text==='navigate' ? {say:'Opening missions.',action:{id:'open_page',args:{page:'missions'}},url:'/missions'}
          : b.text==='confirm' ? {say:'Run the plan?',action:{id:'run_plan',args:{mission:'a'}},confirm:true}
          : b.text==='status' ? {say:'Model status',action:{id:'status',args:{}},confirm:false}
          : {say:`Reply: ${b.text}`,action:null};
      } else if (u.pathname === '/api/voice/act') { calls.push({act:route.request().postDataJSON()}); j={say:'Action status'}; }
      else if (u.pathname === '/api/voice/speak') {
        calls.push({spoken:route.request().postDataJSON().text});
        if (slow) await delay(700);
        return route.fulfill({contentType:'audio/mpeg',body:Buffer.from('test')}).catch(()=>{});
      }
      await route.fulfill({contentType:'application/json',body:JSON.stringify(j)}).catch(()=>{});
    });
    await page.addInitScript(() => {
      localStorage.setItem('hubVoiceMute','1');
      window.micLevel=0; window.recCount=0; window.maxRec=0; window.audioStarts=0; window.audioStops=0; window.holdAudio=false;
      class Recorder {
        static isTypeSupported(){return true;}
        constructor(){this.state='inactive';this.mimeType='audio/webm';}
        start(){this.state='recording';window.recCount++;window.maxRec=Math.max(window.maxRec,window.recCount);}
        stop(){if(this.state==='inactive')return;this.state='inactive';window.recCount--;this.ondataavailable?.({data:new Blob(['voice'])});setTimeout(()=>this.onstop?.(),0);}
      }
      class AC {
        constructor(){this.state='running';}
        createAnalyser(){return {getByteTimeDomainData(b){b.fill(128+Math.round(window.micLevel*128));}};}
        createMediaStreamSource(){return {connect(){}};}
        resume(){return Promise.resolve();} close(){return Promise.resolve();}
        decodeAudioData(){return Promise.resolve({});}
        createBufferSource(){return {connect(){},start(){window.audioStarts++;if(!window.holdAudio)this.timer=setTimeout(()=>this.onended?.(),40);},stop(){window.audioStops++;clearTimeout(this.timer);this.onended?.();}};}
      }
      Object.defineProperty(window,'isSecureContext',{value:true});
      Object.defineProperty(navigator,'mediaDevices',{value:{getUserMedia:async()=>({active:true,getTracks:()=>[{stop(){}}]})}});
      window.MediaRecorder=Recorder; window.AudioContext=AC;
      // Shortened request deadlines exercise timeout recovery without a 45-second wait.
      const original = window.setTimeout;
      window.setTimeout=(fn,ms,...args)=>original(fn,ms===45000?800:ms,...args);
    });
    await page.goto('http://hub.test/');
    await page.evaluate(()=>window.HubVoice.open(false));
    assert(await page.locator('#v-mode-tts').isVisible());
    assert(await page.locator('#v-voice').isVisible());
    await page.click('#v-mode-voicebox');
    assert(await page.locator('#v-persona').isVisible());
    assert(!await page.locator('#v-voice').isVisible());
    assert((await page.locator('#v-hint').textContent()).includes('authorised Hub voice profile'));
    await page.click('#v-mode-tts');
    assert(await page.locator('#v-voice').isVisible());
    console.log('PASS themed TTS and Voicebox profile modes');
    await page.evaluate(()=>{ window.HubVoice.ask('slow'); });
    await page.waitForTimeout(40);
    await page.evaluate(()=>window.HubVoice.ask('new request'));
    await page.waitForTimeout(450);
    assert(!await page.locator('#v-log').textContent().then(s=>s.includes('Reply: slow')), 'An old response must not overwrite a new turn');
    console.log('PASS overlapping turns discard late replies');
    await page.evaluate(()=>window.HubVoice.ask('third'));
    assert.equal(await page.locator('#v-log .v-msg:visible').count(),2);
    await page.click('#v-history'); assert(await page.locator('#v-log .v-msg:visible').count()>2);
    await page.click('#v-history');
    await page.evaluate(()=>window.HubVoice.contextChanged('mission-b'));
    assert.equal(await page.locator('#v-log .v-msg').count(),0);
    assert(await page.locator('#voice').evaluate(el=>el.classList.contains('compact')));
    await page.evaluate(()=>window.HubVoice.ask('mission b'));
    assert.equal(calls.filter(c=>c.text==='mission b').at(-1).history.length,0);
    if (process.env.HUB_TEST_SCREENSHOT) await page.screenshot({path:process.env.HUB_TEST_SCREENSHOT});
    assert((await page.locator('#voice').boundingBox()).height<340, JSON.stringify(await page.locator('#voice').boundingBox()));
    console.log('PASS latest-only history, context reset, compact mobile panel');
    await page.evaluate(()=>window.HubVoice.ask('status'));
    assert.equal((await page.locator('#v-log').textContent()).includes('Model status'),false);
    assert((await page.locator('#v-log').textContent()).includes('Action status'));
    await page.evaluate(()=>window.HubVoice.ask('confirm'));
    assert(await page.locator('#v-yes').isVisible());
    await page.evaluate(()=>window.HubVoice.ask('different subject'));
    assert(!await page.locator('#v-yes').isVisible());
    assert.equal(calls.filter(c=>c.act?.id==='run_plan').length,0);
    console.log('PASS one action reply and stale confirmation cleared');
    await page.evaluate(()=>{window.HubVoice.ask('slow');}); await page.waitForTimeout(40);
    await page.click('#v-cancel'); await page.waitForTimeout(400);
    assert.equal(await page.locator('#v-state').textContent(),'Ready');
    await page.evaluate(()=>window.HubVoice.ask('hang'));
    assert.equal(await page.locator('#v-state').textContent(),'Ready');
    assert((await page.locator('#v-log').textContent()).includes('too long'));
    console.log('PASS stop reply and request timeout recover to Ready');
    await page.evaluate(()=>window.HubVoice.ask('navigate'));
    await page.waitForURL('**/missions');
    assert(await page.locator('#voice').isVisible());
    assert.equal(await page.locator('#v-log .v-msg').count(),2);
    await page.reload(); assert(!await page.locator('#voice').isVisible());
    await page.evaluate(()=>sessionStorage.setItem('hubVoiceSession',JSON.stringify({on:true,history:[{role:'assistant',text:'old conversation'}]})));
    await page.reload(); assert.equal(await page.locator('#v-log .v-msg').count(),0);
    console.log('PASS navigation carries one exchange once; old saved conversations do not reopen');
    await page.evaluate(()=>window.HubVoice.open(false));
    await page.click('#v-size');
    await page.click('#v-mute'); // unmute mock speech
    slow=true;
    await page.evaluate(()=>{window.HubVoice.ask('cancel speech');}); await page.waitForTimeout(80);
    await page.click('#v-cancel'); await page.waitForTimeout(760);
    assert.equal(await page.evaluate(()=>window.audioStarts),0);
    console.log('PASS cancelled speech request cannot start late audio');
    slow=false;
    await page.click('#v-mic'); await page.waitForTimeout(100);
    await page.evaluate(()=>{window.holdAudio=true;window.HubVoice.ask('long answer');});
    await page.waitForFunction(()=>window.audioStarts>0);
    await page.evaluate(()=>window.micLevel=.3); await page.waitForTimeout(350);
    await page.evaluate(()=>{window.micLevel=0;window.holdAudio=false;});
    await page.waitForFunction(()=>document.querySelector('#v-log').textContent.includes('Reply: interrupted request'),null,{timeout:5000});
    await page.waitForTimeout(120);
    assert.equal(await page.locator('#v-state').textContent(),'Listening…');
    assert(await page.evaluate(()=>window.audioStops>0));
    await page.click('#v-mic'); await page.click('#v-mic'); await page.waitForTimeout(160);
    await page.click('#v-close'); await page.waitForTimeout(100);
    assert.equal(await page.evaluate(()=>window.recCount),0);
    assert.equal(await page.evaluate(()=>window.maxRec),1);
    assert.deepEqual(errors,[]);
    console.log('PASS spoken interruption, continued listening, rapid stop/start, recorder cleanup');
    console.log('ALL browser checks passed');
  } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});


