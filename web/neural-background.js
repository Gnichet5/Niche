/* Rede ambiente: conexões por proximidade, memórias observadas apenas no DOM. */
'use strict';
(() => {
  const background = document.querySelector('.ambient-background');
  const canvas = document.querySelector('#neural-background');
  const list = document.querySelector('#memory-list');
  if (!background || !canvas || !list) return;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const transparency = matchMedia('(prefers-reduced-transparency: reduce)');
  const contrast = matchMedia('(forced-colors: active)');
  let ctx, frame = 0, previous = 0, time = 0, width = 0, height = 0, color;
  let memories = new Map();
  const makeNode = memory => ({x:Math.random(), y:Math.random(), vx:(Math.random()-.5)*.008, vy:(Math.random()-.5)*.008, phase:Math.random()*Math.PI*2, memory});
  const base = Array.from({length:10},()=>makeNode(false));
  const blocked = () => transparency.matches || contrast.matches;
  function draw(delta = 0) {
    ctx.clearRect(0,0,width,height);
    const nodes = [...base,...memories.values()];
    time += delta;
    for (const node of nodes) {
      node.x += node.vx*delta; node.y += node.vy*delta;
      if(node.x<.02 || node.x>.98) {node.vx*=-1;node.x=Math.max(.02,Math.min(.98,node.x));}
      if(node.y<.02 || node.y>.98) {node.vy*=-1;node.y=Math.max(.02,Math.min(.98,node.y));}
    }
    const reach = Math.max(140,Math.min(310,width*.30));
    ctx.strokeStyle=color; ctx.lineWidth=.8;
    for(let i=0;i<nodes.length;i++) for(let j=i+1;j<nodes.length;j++) {
      const a=nodes[i], b=nodes[j], distance=Math.hypot((a.x-b.x)*width,(a.y-b.y)*height);
      if(distance>=reach) continue;
      ctx.globalAlpha=(1-distance/reach)*.24;
      ctx.beginPath();ctx.moveTo(a.x*width,a.y*height);ctx.lineTo(b.x*width,b.y*height);ctx.stroke();
    }
    for(const node of nodes) {
      const pulse=reduced.matches?.5:(Math.sin(time*.65+node.phase)+1)/2;
      ctx.globalAlpha=(node.memory?.50:.20)+pulse*.20;
      ctx.fillStyle=color;ctx.shadowColor=color;ctx.shadowBlur=(node.memory?10:4)+pulse*4;
      ctx.beginPath();ctx.arc(node.x*width,node.y*height,node.memory?3.4:1.8,0,Math.PI*2);ctx.fill();
    }
    ctx.globalAlpha=1;ctx.shadowBlur=0;
    background.classList.add('neural-active');
  }
  function fail() {cancelAnimationFrame(frame);frame=0;background.classList.remove('neural-active'); if(ctx)ctx.clearRect(0,0,width,height);}
  function tick(now) {
    frame=0;
    try {
      if(document.hidden || blocked()) return;
      if(now-previous>=33) {draw(reduced.matches?0:Math.min((now-previous)/1000,.06));previous=now;}
      if(!reduced.matches)frame=requestAnimationFrame(tick);
    } catch (_) {fail();}
  }
  function sync() {
    // Stable content keys preserve surviving nodes when app.js rebuilds the list.
    const next = new Map(), duplicates = new Map();
    for(const record of [...list.querySelectorAll('.memory-record')].slice(0,18)) {
      const text=record.querySelector('p')?.textContent || record.textContent;
      const occurrence=duplicates.get(text)||0;duplicates.set(text,occurrence+1);
      const key=JSON.stringify([text,occurrence]);
      next.set(key,memories.get(key)||makeNode(true));
    }
    memories=next;
    if(ctx&&!blocked())draw();
  }
  function resume() {
    cancelAnimationFrame(frame);frame=0;
    if(blocked()){fail();return;}
    try {
      ctx=ctx||canvas.getContext('2d');if(!ctx)return;
      color=getComputedStyle(document.body).getPropertyValue('--accent').trim()||'#bda682';
      width=innerWidth;height=innerHeight;
      const dpr=Math.min(devicePixelRatio||1,2);
      canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);
      sync();previous=performance.now();
      if(!document.hidden&&!reduced.matches)frame=requestAnimationFrame(tick);
    } catch (_) {fail();}
  }
  new MutationObserver(()=>{try{sync();}catch(_){fail();}}).observe(list,{childList:true,subtree:true,characterData:true});
  new MutationObserver(resume).observe(document.body,{attributes:true,attributeFilter:['class']});
  for(const preference of [reduced,transparency,contrast])preference.addEventListener('change',resume);
  document.addEventListener('visibilitychange',resume);window.addEventListener('resize',resume);
  resume();
})();
