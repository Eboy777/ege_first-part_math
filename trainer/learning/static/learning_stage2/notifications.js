(()=>{
 const button=document.querySelector('#enable-notifications'),status=document.querySelector('#notification-status');if(!button)return;
 const supported=isSecureContext&&'serviceWorker'in navigator&&'PushManager'in window&&'Notification'in window;
 const ios=/iPad|iPhone|iPod/.test(navigator.userAgent)||(navigator.platform==='MacIntel'&&navigator.maxTouchPoints>1);
 const installed=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
 if(!supported||(ios&&!installed)){button.hidden=true;status.textContent=ios?'Для уведомлений добавь сайт на экран «Домой» и открой его оттуда.':'Уведомления доступны в поддерживаемом браузере через HTTPS.';return;}
 let registration,subscription;
 const ready=(async()=>{registration=await navigator.serviceWorker.register('/sw.js');registration=await navigator.serviceWorker.ready;subscription=await registration.pushManager.getSubscription();if(subscription)await save(subscription.toJSON());button.textContent=subscription?'Выключить уведомления':'Настроить уведомления';})();
 ready.catch(()=>{status.textContent='Не удалось подготовить уведомления. Попробуй обновить страницу.';});
 async function save(data){const r=await fetch('/api/notifications/subscription',{method:'POST',headers:{'Content-Type':'application/json','X-CSRFToken':document.querySelector('[name=csrfmiddlewaretoken]').value},body:JSON.stringify(data)});if(!r.ok)throw Error();}
 button.onclick=async()=>{
  // Permission is requested only by the student's explicit tap.
  const permission=subscription?Promise.resolve('granted'):Notification.requestPermission();button.disabled=true;
  try{
   if(await permission!=='granted'){status.textContent='Уведомления не разрешены. Повторения всё равно видны на карте.';return;}
   await ready;
   if(subscription){await save({endpoint:subscription.endpoint,unsubscribe:true});await subscription.unsubscribe();subscription=null;button.textContent='Настроить уведомления';status.textContent='Уведомления выключены.';return;}
   const response=await fetch('/api/notifications/config');if(!response.ok)throw Error();const data=await response.json();
   const raw=atob(data.public_key.replace(/-/g,'+').replace(/_/g,'/')+'='.repeat((4-data.public_key.length%4)%4));
   subscription=await registration.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:Uint8Array.from(raw,c=>c.charCodeAt(0))});
   try{await save(subscription.toJSON());}catch(e){await subscription.unsubscribe();subscription=null;throw e;}
   button.textContent='Выключить уведомления';status.textContent='Готово. Напомним, когда придёт время повторения.';
  }catch{status.textContent='Не удалось включить уведомления. Повторения доступны на карте.';}finally{button.disabled=false;}
 };
})();
