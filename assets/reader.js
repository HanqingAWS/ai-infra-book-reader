(function(){
  // 单文件版和多网页版共用。多网页版的 <body data-page> 是 home 或 chNN；单文件版没有这个属性。
  var KEY='aiinfra.reader.';
  var store={get:function(k,d){try{var v=localStorage.getItem(KEY+k);return v===null?d:JSON.parse(v)}catch(e){return d}},
             set:function(k,v){try{localStorage.setItem(KEY+k,JSON.stringify(v))}catch(e){}}};
  var root=document.documentElement, body=document.body, PAGE=body.getAttribute('data-page')||'';
  function $(id){return document.getElementById(id)}
  function each(list,f){for(var i=0;i<list.length;i++)f(list[i],i)}

  // 公式：单文件版在浏览器里排版；多网页版在生成网页时已经排好，不带 katex.js
  if(window.katex) each(document.querySelectorAll('.math'),function(el){
    try{katex.render(el.textContent,el,{displayMode:el.classList.contains('display'),throwOnError:false,strict:false});}catch(e){}
  });

  // 颜色：浅色 → 护眼绿 → 深色，循环切换
  var THEMES=[['light','浅色'],['green','护眼'],['dark','深色']];
  var ti=Math.max(0,THEMES.map(function(t){return t[0]}).indexOf(store.get('theme','light')));
  function setTheme(i){ti=i;root.classList.remove('dark','green');if(THEMES[i][0]!=='light')root.classList.add(THEMES[i][0]);
    if($('themeName'))$('themeName').textContent=THEMES[i][1];store.set('theme',THEMES[i][0])}
  setTheme(ti);
  if($('themeBtn'))$('themeBtn').onclick=function(){setTheme((ti+1)%THEMES.length);toast('颜色：'+THEMES[ti][1])};
  var fs=store.get('fs',17); root.style.setProperty('--fs',fs+'px');
  function setFs(d){fs=Math.min(24,Math.max(13,fs+d));root.style.setProperty('--fs',fs+'px');store.set('fs',fs)}
  if($('fontUp'))$('fontUp').onclick=function(){setFs(1)};
  if($('fontDown'))$('fontDown').onclick=function(){setFs(-1)};

  // 首页：继续阅读、标出读过的章
  if(PAGE==='home'){
    var last=store.get('last',null), old=store.get('pos',null), m;
    if(!last&&old&&(m=/^c(\d\d)-/.exec(old))) last={page:'ch'+m[1]};  // 旧的单页版只记了小节 id
    each(document.querySelectorAll('.chapters a'),function(a){
      if(store.get('pos.'+a.getAttribute('data-page'),null)) a.classList.add('read');
    });
    var link=last&&document.querySelector('.chapters a[data-page="'+last.page+'"]'), r=$('resume');
    if(link&&r){
      r.href=link.getAttribute('href');
      var ne=link.querySelector('.num'), num=ne?ne.textContent:'';
      r.innerHTML='继续阅读<small></small>';
      r.querySelector('small').textContent=(num?num+' ':'')+link.querySelector('.name').textContent+(last.title?' · '+last.title:'');
      r.hidden=false;
    }
  }

  // 解读总开关
  var sw=$('noteSwitch');
  function setNotes(on,quiet){body.classList.toggle('notes-off',!on);if(sw)sw.setAttribute('aria-checked',on);store.set('notes',on);
    if(!quiet) toast(on?'已打开解读':'已关闭解读，只看原文')}
  setNotes(store.get('notes',true),true);
  if(sw){
    sw.onclick=function(){setNotes(body.classList.contains('notes-off'))};
    sw.onkeydown=function(e){if(e.key===' '||e.key==='Enter'){e.preventDefault();sw.onclick()}};
    document.addEventListener('keydown',function(e){
      if((e.key==='n'||e.key==='N')&&!e.metaKey&&!e.ctrlKey&&!e.altKey&&!/INPUT|TEXTAREA/.test(document.activeElement.tagName)) sw.onclick();
    });
  }

  // 单条解读收起（记录跨章节共用一份）
  var collapsed=store.get('collapsed',{});
  var notes=document.querySelectorAll('.note');
  function paint(n){var c=n.classList.contains('collapsed');var h=n.querySelector('.note-head');
    h.setAttribute('aria-expanded',!c);h.querySelector('.note-arrow').textContent=c?'展开':'收起'}
  var ex=$('expandAll');
  function anyCollapsed(){for(var i=0;i<notes.length;i++)if(notes[i].classList.contains('collapsed'))return true;return false}
  function syncEx(){if(ex)ex.textContent=anyCollapsed()?'全部展开':'全部收起'}
  each(notes,function(n){
    if(collapsed[n.dataset.note]) n.classList.add('collapsed');
    paint(n);
    n.querySelector('.note-head').onclick=function(){
      var c=n.classList.toggle('collapsed'); if(c) collapsed[n.dataset.note]=1; else delete collapsed[n.dataset.note];
      store.set('collapsed',collapsed); paint(n); syncEx();
    };
  });
  syncEx();
  if(ex) ex.onclick=function(){
    var expand=anyCollapsed();
    each(notes,function(n){n.classList.toggle('collapsed',!expand); if(expand) delete collapsed[n.dataset.note]; else collapsed[n.dataset.note]=1; paint(n)});
    store.set('collapsed',collapsed); syncEx(); if(body.classList.contains('notes-off')) setNotes(true);
  };

  // 目录
  var sb=$('sidebar');
  if($('menuBtn'))$('menuBtn').onclick=function(){body.classList.toggle('menu-open')};
  var links={}; each(document.querySelectorAll('.sidebar a'),function(a){
    var h=a.getAttribute('href'); if(h.charAt(0)==='#') links[h.slice(1)]=a;
    a.addEventListener('click',function(){body.classList.remove('menu-open')});
  });
  // 点正文空白处收起目录（手机）
  document.addEventListener('click',function(e){
    if(body.classList.contains('menu-open')&&sb&&!sb.contains(e.target)&&e.target!==$('menuBtn')) body.classList.remove('menu-open');
  });
  var heads=[].slice.call(document.querySelectorAll('main h1[id],main h2[id],main h3[id]'));
  if(!heads.length) return;
  var cur=null;
  function activate(){
    var y=window.scrollY+90, best=heads[0];
    for(var i=0;i<heads.length;i++){ if(heads[i].offsetTop<=y) best=heads[i]; else break; }
    if(best&&best!==cur){ if(cur&&links[cur.id]) links[cur.id].classList.remove('active');
      cur=best; var a=links[cur.id];
      if(a){a.classList.add('active');
        // 只滚目录栏自己，不带动整页
        if(sb&&(a.offsetTop<sb.scrollTop||a.offsetTop>sb.scrollTop+sb.clientHeight-40)) sb.scrollTop=a.offsetTop-sb.clientHeight/3;
      } }
  }

  // 进度与续读：多网页版每章各记各的位置
  var posKey=PAGE?'pos.'+PAGE:'pos';
  function save(){ if(!cur) return; store.set(posKey,cur.id);
    if(PAGE) store.set('last',{page:PAGE,id:cur.id,title:cur===heads[0]?'':cur.textContent.trim()}) }
  var bar=$('progress'), t=null, ticking=false;
  window.addEventListener('scroll',function(){
    if(ticking) return; ticking=true;
    requestAnimationFrame(function(){ticking=false;
      var h=document.documentElement.scrollHeight-innerHeight; if(bar) bar.style.width=(h>0?scrollY/h*100:0)+'%';
      activate(); clearTimeout(t); t=setTimeout(save,400);
    });
  },{passive:true});
  // 离开网页、切到后台时马上记一次（手机浏览器可能直接把后台网页关掉）
  function saveNow(){clearTimeout(t);activate();save()}
  window.addEventListener('pagehide',saveNow);
  document.addEventListener('visibilitychange',function(){if(document.visibilityState==='hidden')saveNow()});
  var pos=store.get(posKey,null), target=pos&&document.getElementById(pos);
  if(target&&!location.hash&&pos!==heads[0].id){
    setTimeout(function(){window.scrollTo({top:target.getBoundingClientRect().top+scrollY-60,behavior:'instant'});toast('已回到上次读到的位置')},60);
  }
  activate(); if(PAGE&&!target) save();

  function toast(m){var el=$('toast');if(!el)return;el.textContent=m;el.classList.add('show');
    clearTimeout(el._t);el._t=setTimeout(function(){el.classList.remove('show')},1600)}
})();
