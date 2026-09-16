/* Rede decorativa de memórias reais. Posições estáveis; relações vêm do banco. */
'use strict';
(() => {
  const canvas = document.querySelector('#memory-network');
  const ctx = canvas.getContext('2d');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const contrast = matchMedia('(forced-colors: active)');
  const transparency = matchMedia('(prefers-reduced-transparency: reduce)');
  let nodes = [], edges = [], width = 0, height = 0, frame = 0, last = 0;
  let color = '', accent = '';
  function hash(text) { let h=2166136261; for(const c of text) h=Math.imul(h^c.charCodeAt(0),16777619); return h>>>0; }
  function colors() { const s=getComputedStyle(document.body); color=s.getPropertyValue('--text-secondary').trim(); accent=s.getPropertyValue('--accent').trim(); }
  function resize() {
    width=innerWidth; height=innerHeight;
    const dpr=Math.min(devicePixelRatio||1,2);
    canvas.width=Math.round(width*dpr); canvas.height=Math.round(height*dpr);
    ctx.setTransform(dpr,0,0,dpr,0,0); draw(performance.now());
  }
  function draw(time) {
    ctx.clearRect(0,0,width,height);
    if(contrast.matches || transparency.matches) return;
    const t=reduced.matches?0:time/16000;
    for(const n of nodes) {
      n.x=(.06+n.u*.88)*width + Math.sin(t+n.phase)* (reduced.matches?0:7);
      n.y=(.06+n.v*.88)*height + Math.cos(t+n.phase)* (reduced.matches?0:7);
    }
    ctx.lineWidth=.7;ctx.strokeStyle=color;
    for(const e of edges) {
      ctx.globalAlpha=.07+e.weight*.10;
      ctx.beginPath();ctx.moveTo(e.a.x,e.a.y);ctx.lineTo(e.b.x,e.b.y);ctx.stroke();
    }
    for(const n of nodes) {
      const fresh=!reduced.matches && time-n.born<4000;
      ctx.globalAlpha=fresh?.7:.32;ctx.fillStyle=fresh?accent:color;
      ctx.beginPath();ctx.arc(n.x,n.y,fresh?2.7:1.8,0,Math.PI*2);ctx.fill();
    }
    ctx.globalAlpha=1;
  }
  function tick(time) {
    frame=0;
    if(time-last>50){draw(time);last=time;}
    if(!document.hidden&&!reduced.matches&&!contrast.matches&&!transparency.matches&&nodes.length) frame=requestAnimationFrame(tick);
  }
  function resume() { cancelAnimationFrame(frame);colors();draw(performance.now());if(!document.hidden&&!reduced.matches&&nodes.length) frame=requestAnimationFrame(tick); }
  window.memoryNetwork = {update(data) {
    const previous=new Map(nodes.map(n=>[n.id,n]));
    nodes=(data.nodes||[]).slice(0,96).map(n=>previous.get(n.id)||{id:n.id,u:hash(n.id)/4294967295,v:hash(n.id+'y')/4294967295,phase:hash(n.id+'p')%628/100,born:performance.now()});
    const byId=new Map(nodes.map(n=>[n.id,n]));
    edges=(data.edges||[]).filter(e=>byId.has(e.source)&&byId.has(e.target)).map(e=>({a:byId.get(e.source),b:byId.get(e.target),weight:e.weight}));
    const status=document.querySelector('#network-status');
    status.textContent=data.unavailable?'Rede de memórias indisponível.':`Rede: ${nodes.length} de ${data.total||0} memórias · ${edges.length} conexões por similaridade`;
    resume();
  }};
  new MutationObserver(resume).observe(document.body,{attributes:true,attributeFilter:['class']});
  document.addEventListener('visibilitychange',resume);
  for(const preference of [reduced,contrast,transparency]) preference.addEventListener('change',resume);
  window.addEventListener('resize',resize);
  colors();resize();
})();
