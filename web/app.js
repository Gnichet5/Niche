'use strict';
const $ = s => document.querySelector(s);
const token = $('meta[name="janus-token"]').content;
let busy = false, pendingImage = null, imageURL = null, jobID = null, pendingApproval = null, forgetID = null;
let speakEnabled = false, recognition = null, listening = false, noticeTimer;
function notice(text) { $('#notice').textContent = text; $('#notice').hidden = false; clearTimeout(noticeTimer); noticeTimer = setTimeout(() => $('#notice').hidden = true, 14000); }
async function api(path, data) {
  const response = await fetch('/api/' + path, {method: data === undefined ? 'GET' : 'POST', headers: {'X-Janus-Token': token, 'Content-Type': 'application/json'}, body: data === undefined ? undefined : JSON.stringify(data)});
  const result = await response.json(); if (!response.ok) throw new Error(result.error || 'Falha de comunicação.'); return result;
}
function setBusy(value) { busy = value; ['#send','#new-chat','#nav-memory','#refresh-memory','#attach','#dictate'].forEach(s => $(s).disabled = value); $('#progress').hidden = !value; if (!value) { $('#approval').hidden = true; $('#connection').textContent = 'Pronto para conversar'; } }
function view(memory) { $('#memory-view').hidden = !memory; $('#chat-view').hidden = memory; $('#nav-chat').classList.toggle('active', !memory); $('#nav-memory').classList.toggle('active', memory); $('#nav-chat').setAttribute('aria-current', memory ? 'false' : 'page'); $('#nav-memory').setAttribute('aria-current', memory ? 'page' : 'false'); $('#view-title').textContent = memory ? 'Memórias' : 'Conversa'; }
function textContent(node, text) {
  // Markdown básico criado com nós de texto, sem interpretar HTML do modelo.
  text.split(/(```[\s\S]*?```)/g).forEach(piece => {
    if (piece.startsWith('```')) { const pre=document.createElement('pre'); pre.textContent=piece.replace(/^```[^\n]*\n?/, '').replace(/```$/, ''); node.append(pre); }
    else piece.split(/(\*\*[^*]+\*\*)/g).forEach(part => { if (part.startsWith('**') && part.endsWith('**')) { const strong=document.createElement('strong'); strong.textContent=part.slice(2,-2); node.append(strong); } else node.append(document.createTextNode(part)); });
  });
}
function message(role, text, result) {
  $('#welcome').hidden = true; const article=document.createElement('article'); article.className='message '+role;
  if (role === 'assistant') { const label=document.createElement('div'); label.className='message-label'; label.textContent='JANUS'; article.append(label); }
  const content=document.createElement('div'); content.className='message-content'; textContent(content,text); article.append(content);
  if(result) { const details=document.createElement('details'), summary=document.createElement('summary'), pre=document.createElement('pre'); summary.textContent='Contexto e consumo desta resposta'; pre.textContent=`Modelo: ${result.model}\nFerramentas disponíveis: ${result.tools}/21\nChamadas: ${result.calls}\nMemória: ${result.memory}\nTokens: ${JSON.stringify(result.usage,null,2)}\nCampos indisponíveis: ${JSON.stringify(result.missing)}\nNão inclui embeddings ou chamadas sem resposta.\n\nAções:\n${JSON.stringify(result.actions,null,2)}`; details.append(summary,pre); article.append(details); }
  $('#messages').append(article); article.scrollIntoView({block:'nearest'});
}
function memories(result) {
  $('#memory-list').replaceChildren(); $('#memory-count').textContent=`${result.memories.length} de ${result.total} registros`;
  if(!result.memories.length) { $('#memory-list').textContent='Nenhuma memória encontrada.'; return; }
  result.memories.forEach(item=>{ const node=document.createElement('article'); node.className='memory-record'; const p=document.createElement('p'),button=document.createElement('button'); p.textContent=item.text; button.textContent='Esquecer memória'; button.onclick=()=>{if(busy)return;forgetID=item.id;$('#forget-dialog').showModal()}; node.append(p,button); $('#memory-list').append(node); });
}
function clearConversation() { $('#messages').replaceChildren(); $('#welcome').hidden=false; $('#conversation-label').textContent='Uma nova ideia começa aqui.'; removeImage(); }
async function poll() {
  try {
    const job=await api('status'); if(jobID && job.id!==jobID) throw new Error('A sessão foi alterada em outra aba. Recarregue a página.');
    $('#progress-text').textContent=job.status + (job.detail ? ' · '+job.detail : '');
    $('#connection').textContent=job.state==='approval'?'Aguardando aprovação':'Janus trabalhando';
    if(job.state==='approval') { pendingApproval=job.approval.id; $('#approval').hidden=false; $('#approval-name').textContent=job.approval.name; $('#approval-args').textContent=JSON.stringify(job.approval.arguments,null,2); }
    else $('#approval').hidden=true;
    if(job.state==='done') {
      setBusy(false); jobID=null;
      if(job.kind==='chat') { message('assistant',job.result.text,job.result); if(speakEnabled && 'speechSynthesis' in window){const utterance=new SpeechSynthesisUtterance(job.result.speech);utterance.lang='pt-BR';speechSynthesis.cancel();speechSynthesis.speak(utterance)} }
      else if(job.kind==='memories'||job.kind==='forget'){memories(job.result);if(job.kind==='forget')clearConversation()}
      else clearConversation();
      return;
    }
    if(job.state==='error') throw new Error(job.error);
    setTimeout(poll,700);
  } catch(error) { setBusy(false); jobID=null; notice(error.message+' Se houve uma ação, confira o resultado antes de reenviar.'); }
}
async function start(kind,data={}) { if(busy)return;setBusy(true);$('#progress-text').textContent='Preparando Janus…';try{const job=await api(kind,data);jobID=job.id;poll()}catch(error){setBusy(false);notice(error.message)} }
$('#chat-form').onsubmit=event=>{event.preventDefault();if(busy)return;const text=$('#message-input').value.trim();if(!text)return; if(listening)recognition.stop();view(false);message('user',text+(pendingImage?'\n[Imagem anexada]':''));$('#conversation-label').textContent=text.slice(0,60);$('#message-input').value='';const image=pendingImage;removeImage();start('chat',{text,image})};
$('#message-input').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#chat-form').requestSubmit()}};
document.querySelectorAll('[data-prompt]').forEach(b=>b.onclick=()=>{$('#message-input').value=b.dataset.prompt;$('#message-input').focus()});
$('#new-chat').onclick=()=>{if(!busy){view(false);start('reset')}};
$('#nav-chat').onclick=()=>view(false);
$('#nav-memory').onclick=()=>{view(true);start('memories')};
$('#refresh-memory').onclick=()=>start('memories');
$('#forget-cancel').onclick=()=>$('#forget-dialog').close();
$('#forget-confirm').onclick=()=>{$('#forget-dialog').close();start('forget',{id:forgetID})};
async function decide(allow){$('#approve').disabled=$('#deny').disabled=true;try{await api('approval',{id:pendingApproval,allow});$('#approval').hidden=true}catch(e){notice(e.message)}finally{$('#approve').disabled=$('#deny').disabled=false}}
$('#approve').onclick=()=>decide(true);$('#deny').onclick=()=>decide(false);
function removeImage(){pendingImage=null;if(imageURL)URL.revokeObjectURL(imageURL);imageURL=null;$('#attachment').hidden=true;$('#image-file').value='';$('#privacy').textContent='Tela não compartilhada · imagens só quando você anexar'}
$('#attach').onclick=()=>$('#image-file').click();$('#remove-image').onclick=removeImage;
$('#image-file').onchange=async()=>{const file=$('#image-file').files[0];if(!file)return;if(file.size>4000000||!['image/png','image/jpeg','image/webp'].includes(file.type)){notice('Escolha uma imagem PNG, JPEG ou WebP de até 4 MB.');return}const reader=new FileReader();reader.onload=()=>{removeImage();pendingImage=reader.result.split(',')[1];imageURL=URL.createObjectURL(file);$('#image-preview').src=imageURL;$('#image-name').textContent=file.name;$('#attachment').hidden=false;$('#privacy').textContent='Esta imagem será enviada ao Gemini junto com a mensagem'};reader.onerror=()=>notice('Não foi possível ler a imagem.');reader.readAsDataURL(file)};
$('#voice').onclick=()=>{if(!('speechSynthesis' in window)){notice('Este navegador não oferece leitura de voz.');return}speakEnabled=!speakEnabled;$('#voice').setAttribute('aria-pressed',String(speakEnabled));$('#voice').textContent=speakEnabled?'Voz ligada':'Voz desligada';if(!speakEnabled)speechSynthesis.cancel()};
const Recognition=window.SpeechRecognition||window.webkitSpeechRecognition;
$('#dictate').onclick=()=>{if(!Recognition){notice('Ditado indisponível neste navegador. Você pode digitar normalmente.');return}if(listening){recognition.stop();return}recognition=new Recognition();recognition.lang='pt-BR';recognition.interimResults=false;recognition.onstart=()=>{listening=true;$('#dictate').textContent='Parar ditado'};recognition.onend=()=>{listening=false;$('#dictate').textContent='Ditar'};recognition.onerror=e=>notice('Não foi possível usar o microfone: '+e.error);recognition.onresult=e=>{$('#message-input').value+=e.results[0][0].transcript;$('#message-input').focus()};recognition.start()};
let dark=matchMedia('(prefers-color-scheme: dark)').matches;try{const saved=localStorage.getItem('janus-theme');if(saved)dark=saved==='dark'}catch(_){}function theme(){document.documentElement.dataset.theme=dark?'dark':'light'}theme();$('#theme').onclick=()=>{dark=!dark;theme();try{localStorage.setItem('janus-theme',dark?'dark':'light')}catch(_){}};
api('status').then(job=>{if(['running','approval'].includes(job.state)){setBusy(true);jobID=job.id;poll()}}).catch(e=>notice(e.message));
