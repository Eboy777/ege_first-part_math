// No offline cache: private pages and task state always come from the server.
self.addEventListener('push',event=>{
 let data={};try{data=event.data?.json()||{};}catch{}
 event.waitUntil(self.registration.showNotification(data.title||'Пятёрка · повторение',{body:data.body||'Пора закрепить изученные типы.',icon:'/static/learning_stage2/icon-192.png',tag:'pyaterka-reviews',data:{url:'/'}}));
});
self.addEventListener('notificationclick',event=>{
 event.notification.close();event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(async windows=>{
  const existing=windows.find(w=>new URL(w.url).origin===self.location.origin);
  if(existing){await existing.navigate('/');return existing.focus();}return clients.openWindow('/');
 }));
});
