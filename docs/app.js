(function(){
  "use strict";
  var DATA = window.__DATA__ || {meta:{sections:[]},widgets:[],hero:[]};
  var WIDGETS = DATA.widgets;
  var SECTIONS = DATA.meta.sections;
  var $ = function(s,r){return (r||document).querySelector(s);};
  var el = function(tag,cls,html){var e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e;};
  var esc = function(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});};
  var shot = function(id,v){return "shots/"+id+"__"+v+".jpg";};

  /* ---- hero device carousel ---- */
  (function(){
    var screen=$("#heroScreen"), cap=$("#heroCap");
    var imgs=(DATA.hero||[]).slice();
    if(!screen||!imgs.length){var dev=document.querySelector(".device");if(dev)dev.style.display="none";return;}
    var nodes=imgs.map(function(src,i){
      var im=new Image(); im.src=src; im.alt="Widgets shown on a Corsair Xeneon Edge";
      if(i===0)im.className="on";
      screen.insertBefore(im,screen.firstChild); return im;
    });
    var idx=0;
    setInterval(function(){
      nodes[idx].classList.remove("on");
      idx=(idx+1)%nodes.length;
      nodes[idx].classList.add("on");
    },4200);
  })();

  /* ---- stats ---- */
  var totalSizes = WIDGETS.reduce(function(a,w){return a+(w.sizes?w.sizes.length:0);},0);
  var stats=[["105","Widgets"],[String(SECTIONS.length),"Categories"],[String(totalSizes),"Layout sizes"],["MIT","Open source"]];
  var statsEl=$("#stats");
  stats.forEach(function(s){var d=el("div","stat");d.appendChild(el("b",null,s[0]));d.appendChild(el("span",null,s[1]));statsEl.appendChild(d);});
  $("#count").textContent="105";
  $("#search").placeholder="Search "+WIDGETS.length+" widgets…";

  /* ---- pills ---- */
  var state={section:"__all",query:""};
  var pillsEl=$("#pills");
  function cssid(s){return s.replace(/[^a-z0-9]+/gi,"-").toLowerCase();}
  function mkPill(label,val){
    var p=el("button","pill"+(val==="__all"?" active":""),label);p.dataset.val=val;
    p.addEventListener("click",function(){
      state.section=val;
      Array.prototype.forEach.call(pillsEl.children,function(c){c.classList.toggle("active",c.dataset.val===val);});
      applyFilter();
      if(val!=="__all"){var s=document.getElementById("sec-"+cssid(val));if(s)s.scrollIntoView({behavior:"smooth",block:"start"});}
      else window.scrollTo({top:$("#toolbar").offsetTop-1,behavior:"smooth"});
    });
    return p;
  }
  pillsEl.appendChild(mkPill("All","__all"));
  SECTIONS.forEach(function(s){pillsEl.appendChild(mkPill(s.title,s.title));});

  /* ---- sections + cards ---- */
  var sectionsEl=$("#sections");
  SECTIONS.forEach(function(sec){
    var list=WIDGETS.filter(function(w){return w.section===sec.title;});
    var s=el("section","section");s.id="sec-"+cssid(sec.title);s.dataset.section=sec.title;
    var head=el("div","section-head");
    head.appendChild(el("h2",null,esc(sec.title)));
    head.appendChild(el("span","blurb",esc(sec.blurb)));
    head.appendChild(el("span","n",list.length+" widgets"));
    s.appendChild(head);
    var grid=el("div","grid");
    list.forEach(function(w){
      var card=el("div","card");card.dataset.id=w.id;
      var nsz=w.sizes.length;
      card.innerHTML=
        '<div class="thumb"><img loading="lazy" src="'+shot(w.id,"wide")+'" alt="'+esc(w.name)+' widget"></div>'+
        '<div class="meta"><span class="nm">'+esc(w.name)+'</span>'+
          '<span class="cnt">'+nsz+' size'+(nsz!==1?'s':'')+'</span><span class="expand">⤢</span></div>'+
        '<div class="desc">'+esc(w.desc)+'</div>';
      card.addEventListener("click",function(){openModal(w.id);});
      grid.appendChild(card);
    });
    s.appendChild(grid);
    var em=el("div","empty","No matches in this category.");em.style.display="none";grid.appendChild(em);
    s._empty=em;sectionsEl.appendChild(s);
  });
  var globalEmpty=el("div","empty","No widgets match your search.");globalEmpty.style.display="none";sectionsEl.appendChild(globalEmpty);

  /* ---- filtering ---- */
  function byId(id){for(var i=0;i<WIDGETS.length;i++)if(WIDGETS[i].id===id)return WIDGETS[i];return null;}
  function matches(w,q){return !q||(w.name+" "+w.desc+" "+w.id+" "+w.section).toLowerCase().indexOf(q)>=0;}
  function applyFilter(){
    var q=state.query.trim().toLowerCase(),anyGlobal=false;
    Array.prototype.forEach.call(sectionsEl.querySelectorAll(".section"),function(sec){
      var on=(state.section==="__all"||state.section===sec.dataset.section),shown=0;
      Array.prototype.forEach.call(sec.querySelectorAll(".card"),function(card){
        var vis=on&&matches(byId(card.dataset.id),q);
        card.style.display=vis?"":"none";if(vis){shown++;anyGlobal=true;}
      });
      sec.style.display=on?"":"none";
      if(sec._empty)sec._empty.style.display=(on&&shown===0)?"":"none";
    });
    globalEmpty.style.display=anyGlobal?"none":"";
    rebuildVisible();
  }
  var searchEl=$("#search");
  searchEl.addEventListener("input",function(){state.query=searchEl.value;applyFilter();});

  var visible=[];
  function rebuildVisible(){
    visible=[];
    Array.prototype.forEach.call(sectionsEl.querySelectorAll(".card"),function(card){if(card.style.display!=="none")visible.push(card.dataset.id);});
  }

  /* ---- modal gallery ---- */
  var modal=$("#modal"),mImg=$("#mImg"),mName=$("#mName"),mDesc=$("#mDesc"),
      mSection=$("#mSection"),mSizes=$("#mSizes"),mVariants=$("#mVariants"),
      mStage=$("#mStage"),mCap=$("#mCap");
  var cur=null,strip=[],sidx=0,lastFocus=null;

  function buildStrip(w){
    strip=[];
    strip.push({img:shot(w.id,"wide"),tag:"Solo",cap:"The widget on its own"});
    (w.scenes||[]).forEach(function(sc){
      var full=/full screen/.test(sc.label);
      strip.push({img:sc.file,tag:full?"Full screen":sc.label,
        cap:full?"Filling the whole 2560×720 screen":"Running at "+sc.label+", alongside other widgets"});
    });
    strip.push({img:shot(w.id,"std"),tag:"Solo",cap:"On its own · standard shape"});
    strip.push({img:shot(w.id,"compact"),tag:"Solo",cap:"On its own · compact shape"});
    mVariants.innerHTML="";
    strip.forEach(function(it,i){
      var b=el("div","variant"+(i===0?" active":""));b.dataset.i=i;
      b.innerHTML='<div class="vt"><img loading="lazy" src="'+it.img+'" alt=""></div><div class="vl">'+esc(it.tag)+'</div>';
      b.addEventListener("click",function(){setItem(i);});
      mVariants.appendChild(b);
    });
  }
  function setItem(i){
    sidx=i;mStage.classList.remove("zoom");
    mImg.src=strip[i].img;
    if(mCap)mCap.textContent=strip[i].cap;
    Array.prototype.forEach.call(mVariants.children,function(c){c.classList.toggle("active",+c.dataset.i===i);});
  }
  function openModal(id){
    var w=byId(id);if(!w)return;cur=w;lastFocus=document.activeElement;
    mSection.textContent=w.section;mName.textContent=w.name;mDesc.textContent=w.desc;
    mSizes.innerHTML="";(w.sizeLabels||[]).forEach(function(l){mSizes.appendChild(el("span","szchip",l));});
    buildStrip(w);setItem(0);
    modal.classList.add("open");modal.setAttribute("aria-hidden","false");document.body.style.overflow="hidden";
    $(".close",modal).focus();
  }
  function closeModal(){
    modal.classList.remove("open");modal.setAttribute("aria-hidden","true");document.body.style.overflow="";
    if(lastFocus&&lastFocus.focus)lastFocus.focus();
  }
  function step(dir){
    if(!cur)return;
    var list=visible.length?visible:WIDGETS.map(function(w){return w.id;});
    var i=list.indexOf(cur.id);if(i<0)i=0;i=(i+dir+list.length)%list.length;openModal(list[i]);
  }
  function cycleItem(d){setItem((sidx+d+strip.length)%strip.length);}
  mStage.addEventListener("click",function(e){if(e.target===mImg)mStage.classList.toggle("zoom");});
  $("#mPrev").addEventListener("click",function(){step(-1);});
  $("#mNext").addEventListener("click",function(){step(1);});
  Array.prototype.forEach.call(modal.querySelectorAll("[data-close]"),function(b){b.addEventListener("click",closeModal);});
  document.addEventListener("keydown",function(e){
    if(!modal.classList.contains("open"))return;
    if(e.key==="Escape")closeModal();
    else if(e.key==="ArrowLeft")step(-1);
    else if(e.key==="ArrowRight")step(1);
    else if(e.key==="ArrowUp"){e.preventDefault();cycleItem(-1);}
    else if(e.key==="ArrowDown"){e.preventDefault();cycleItem(1);}
    else if(/^[1-9]$/.test(e.key)){var n=+e.key-1;if(n<strip.length)setItem(n);}
  });

  rebuildVisible();
})();
