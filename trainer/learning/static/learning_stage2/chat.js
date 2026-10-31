(() => {
 const panel=document.querySelector('#chat');if(!panel)return;
 const list=document.querySelector('#chat-messages'),form=document.querySelector('#chat-form'),input=document.querySelector('#chat-text'),error=document.querySelector('#chat-error'),rule=document.querySelector('#chat-rule');
 const task=document.querySelector('#training-task'),type=task?.dataset.type||'';
 let attempt=task?.dataset.attempt||'',state={},quote=null,busy=false,older=null,correction=false;
 const csrf=()=>form.querySelector('[name=csrfmiddlewaretoken]').value;
 function el(tag,text,cls){const n=document.createElement(tag);if(text)n.textContent=text;if(cls)n.className=cls;return n;}
 function action(text,fn){const b=el('button',text,'action');b.type='button';b.onclick=fn;return b;}
 let animationVersion=0;
 function animateReply(node,text,version){
  if(matchMedia('(prefers-reduced-motion: reduce)').matches)return;
  const chars=Array.from(text),duration=Math.min(6000,Math.max(500,chars.length*12));let started;
  node.textContent='';node.classList.add('typing-text');
  function frame(now){if(version!==animationVersion)return;started??=now;const count=Math.min(chars.length,Math.floor((now-started)/duration*chars.length));node.textContent=chars.slice(0,count).join('');list.scrollTop=list.scrollHeight;if(count<chars.length)requestAnimationFrame(frame);else node.classList.remove('typing-text');}
  requestAnimationFrame(frame);
 }
 function bubble(m,animate=false){const n=el('div',null,'message '+m.role),text=el('span',m.text);n.append(text);if(animate&&m.role==='assistant')animateReply(text,m.text,animationVersion);n.dataset.id=m.id;n.dataset.text=m.text;if(m.attempt_id&&m.attempt_id!==attempt)n.prepend(el('div','К предыдущей задаче','small'));if(m.photo_url){const img=el('img');img.src=m.photo_url;img.alt='Прикреплённое фото задачи';n.prepend(img);}return n;}
 async function load(before=null,animateNew=false){
  const known=new Set([...list.querySelectorAll('.message[data-id]')].map(n=>n.dataset.id));
  const r=await fetch('/api/chat?type='+encodeURIComponent(type)+(before?'&before='+before:''));const data=await r.json();if(!r.ok)throw Error(data.error||'Не удалось загрузить чат.');
  if(!before){animationVersion++;list.replaceChildren();state=data;if(attempt!==(data.context.attempt_id||''))error.textContent='Задача изменилась в другой вкладке. Обнови страницу перед отправкой.';for(const m of data.messages)list.append(bubble(m,animateNew&&!known.has(String(m.id))));}
  else {const anchor=list.scrollHeight;for(const m of [...data.messages].reverse())list.prepend(bubble(m));list.scrollTop=list.scrollHeight-anchor;}
  older=data.messages[0]?.id||older;
  list.querySelector('.older')?.remove();if(data.has_older){const b=action('Загрузить более ранние сообщения',()=>load(older).catch(showError));b.classList.add('older');list.prepend(b);}
  if(!before){list.scrollTop=list.scrollHeight;renderPhoto(data.photo);rule.textContent=data.context.control?(data.context.assisted?'Для зачёта нужна новая контрольная задача.':'Отправляя сообщение, ты запрашиваешь помощь с текущей задачей. Для зачёта понадобится новая задача.'):'';}
 }
 function showError(e){error.textContent=e.message||String(e);}
 async function post(url,data,isFile=false){const response=await fetch(url,{method:'POST',headers:{'X-CSRFToken':csrf(),...(isFile?{}:{'Content-Type':'application/json'})},body:isFile?data:JSON.stringify(data)});let result;try{result=await response.json();}catch{throw Error('Не удалось обработать ответ сервера. Обнови страницу и попробуй ещё раз.');}if(response.status===401)throw Error('Сессия завершилась. Войди в аккаунт заново.');if(!response.ok)throw Error(result.error||'Не удалось отправить сообщение.');return result;}
 function setBusy(value){busy=value;
  list.querySelector('.typing-indicator')?.remove();
  if(value){const indicator=el('div',null,'message assistant typing-indicator');indicator.setAttribute('role','status');indicator.setAttribute('aria-label','ИИ печатает ответ');for(let i=0;i<3;i++)indicator.append(el('span'));list.append(indicator);list.scrollTop=list.scrollHeight;}
 form.querySelector('.send-button').disabled=value;form.querySelector('.attach-button').disabled=value;input.disabled=value;rule.textContent=value?'Наставник отвечает…':'';}
 async function send(text){if(busy)return;error.textContent='';const draft=input.value;input.value='';list.append(el('div',(quote?'Цитата: «'+quote.text+'»\n':'')+text,'message user'));list.scrollTop=list.scrollHeight;setBusy(true);try{const result=await post('/api/chat/send',{text,type,attempt,quote,operation:correction?'correct_photo':'send'});input.value='';quote=null;correction=false;document.querySelector('#chat-quote').hidden=true;await load(null,true);if(result.late)error.textContent='Ответ относится к предыдущей задаче.';}catch(e){input.value=draft;showError(e);await load().catch(()=>{});}finally{setBusy(false);if(state.context?.control)rule.textContent='Помощь с решением требует новой контрольной задачи.';input.focus();}}
 function renderPhoto(photo){const p=document.querySelector('#photo-confirm');p.replaceChildren();p.hidden=!photo;if(!photo)return;p.append(el('p',photo.text||'Распознавание не завершено. Можно исправить условие или отправить фото снова.'));if(photo.readable)p.append(action('Прочитано верно',async()=>{try{await post('/api/chat/confirm',{id:photo.id,version:photo.version});await load();await send('Условие на фото подтверждено. Помоги разобраться по одному шагу.');}catch(e){showError(e);}}));p.append(action('Отложить фото',async()=>{try{await post('/api/chat/photo-dismiss',{id:photo.id,version:photo.version});correction=false;await load();}catch(e){showError(e);}}));p.append(action('Исправить условие',()=>{correction=true;input.placeholder='Напиши исправленное условие…';input.focus();}));}
 form.onsubmit=e=>{e.preventDefault();if(input.value.trim())send(input.value.trim());};
 form.querySelector('.attach-button').onclick=()=>document.querySelector('#chat-photo').click();
 document.querySelector('#chat-photo').onchange=async e=>{const file=e.target.files[0];if(!file||busy)return;const data=new FormData();data.append('photo',file);data.append('type',type);data.append('attempt',attempt);setBusy(true);error.textContent='';try{await post('/api/chat/upload',data,true);await load(null,true);}catch(e){showError(e);}finally{setBusy(false);}};
 document.querySelector('#chat-open').addEventListener('click',()=>load().catch(showError));
 document.querySelector('#task-hint')?.addEventListener('click',async()=>{document.querySelector('#chat-open').click();try{await load();await send('Дай одну подсказку к текущей задаче.');}catch(e){showError(e);}});
 const refreshControl=()=>{if(state.context?.control&&state.context?.assisted&&task?.dataset.assisted!=='true')location.reload();};
 document.querySelector('#chat-close').addEventListener('click',refreshControl);document.querySelector('#chat-backdrop').addEventListener('click',refreshControl);document.addEventListener('keydown',e=>{if(e.key==='Escape')refreshControl();});
 // Floating quote control is adjacent to the selected text, never a permanent composer button.
 const q=el('button','✧ Спросить ИИ','selection-quote');q.hidden=true;document.body.append(q);let selection=null;
 q.onpointerdown=e=>e.preventDefault();
 document.addEventListener('selectionchange',()=>{const s=getSelection(),message=s?.anchorNode?.parentElement?.closest('#chat-messages .message');if(!s||s.isCollapsed||!message||!message.dataset.id||!s.toString().trim()){q.hidden=true;return;}const text=s.toString().trim();if(!message.dataset.text.includes(text)){q.hidden=true;return;}selection={id:Number(message.dataset.id),text};const r=s.getRangeAt(0).getBoundingClientRect();q.hidden=false;q.style.left=Math.max(8,Math.min(innerWidth-q.offsetWidth-8,r.left))+'px';q.style.top=Math.max(8,r.top-q.offsetHeight-8)+'px';});
 q.onclick=()=>{quote=selection;const box=document.querySelector('#chat-quote');box.replaceChildren(el('span',quote.text),action('×',()=>{quote=null;box.hidden=true;}));box.hidden=false;q.hidden=true;getSelection().removeAllRanges();input.focus();};
 window.addEventListener('scroll',()=>q.hidden=true,true);
 // Incorrect learning answers open the existing conversation; controls never auto-open.
 if(task?.dataset.incorrect==='true'&&Number(task.dataset.stage)<4)document.querySelector('#chat-open').click();
 // State is reloaded on opening; source context always comes from the current page and server.
})();
