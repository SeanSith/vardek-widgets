(function(){
  "use strict";
  var DATA = window.__DATA__ || {meta:{sections:[]},widgets:[]};
  var WIDGETS = DATA.widgets;
  var SECTIONS = DATA.meta.sections;
  var VARIANTS = [
    {key:"wide",  label:"Wide"},
    {key:"std",   label:"Standard"},
    {key:"compact",label:"Compact"}
  ];
  var $ = function(s,r){return (r||document).querySelector(s);};
  var el = function(tag,cls,html){var e=document.createElement(tag);if(cls)e.className=cls;if(html!=null)e.innerHTML=html;return e;};
  var esc = function(s){return String(s).replace(/[&<>"]/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c];});};
  var shot = function(id,v){return "shots/"+id+"__"+v+".jpg";};

  /* ---- stats ---- */
  var totalSizes = WIDGETS.reduce(function(a,w){return a+(w.sizes?w.sizes.length:0);},0);
  var stats = [
    ["105","Widgets"],
    [String(SECTIONS.length),"Categories"],
    [String(totalSizes),"Layout sizes"],
    ["MIT","Open source"]
  ];
  var statsEl = $("#stats");
  stats.forEach(function(s){
    var d=el("div","stat");
    d.appendChild(el("b",null,s[0]));
    d.appendChild(el("span",null,s[1]));
    statsEl.appendChild(d);
  });
  $("#count").textContent="105";
  $("#search").placeholder="Search "+WIDGETS.length+" widgets…";

  /* ---- filter state ---- */
  var state = {section:"__all", query:""};
  var cardIndex = {}; // id -> card element

  /* ---- pills ---- */
  var pillsEl = $("#pills");
  function mkPill(label,val){
    var p=el("button","pill"+(val==="__all"?" active":""),label);
    p.dataset.val=val;
    p.addEventListener("click",function(){
      state.section=val;
      Array.prototype.forEach.call(pillsEl.children,function(c){c.classList.toggle("active",c.dataset.val===val);});
      applyFilter();
      if(val!=="__all"){var s=document.getElementById("sec-"+cssid(val));if(s)s.scrollIntoView({behavior:"smooth",block:"start"});}
      else window.scrollTo({top:$("#toolbar").offsetTop-1,behavior:"smooth"});
    });
    return p;
  }
  function cssid(s){return s.replace(/[^a-z0-9]+/gi,"-").toLowerCase();}
  pillsEl.appendChild(mkPill("All","__all"));
  SECTIONS.forEach(function(s){pillsEl.appendChild(mkPill(s.title,s.title));});

  /* ---- sections + cards ---- */
  var sectionsEl = $("#sections");
  SECTIONS.forEach(function(sec){
    var list = WIDGETS.filter(function(w){return w.section===sec.title;});
    var s = el("section","section");
    s.id="sec-"+cssid(sec.title);
    s.dataset.section=sec.title;
    var head=el("div","section-head");
    head.appendChild(el("h2",null,esc(sec.title)));
    head.appendChild(el("span","blurb",esc(sec.blurb)));
    head.appendChild(el("span","n",list.length+" widgets"));
    s.appendChild(head);
    var grid=el("div","grid");
    list.forEach(function(w){
      var card=el("div","card");
      card.dataset.id=w.id;
      var nsz=w.sizes.length;
      card.innerHTML =
        '<div class="thumb"><img loading="lazy" src="'+shot(w.id,"wide")+'" alt="'+esc(w.name)+' widget"></div>'+
        '<div class="meta"><span class="nm">'+esc(w.name)+'</span>'+
          '<span class="cnt">'+nsz+' size'+(nsz!==1?'s':'')+'</span>'+
          '<span class="expand">⤢</span></div>'+
        '<div class="desc">'+esc(w.desc)+'</div>';
      card.addEventListener("click",function(){openModal(w.id);});
      grid.appendChild(card);
      cardIndex[w.id]=card;
    });
    s.appendChild(grid);
    // empty note per section (hidden unless filtered to nothing)
    var em=el("div","empty","No matches in this category.");em.style.display="none";
    grid.appendChild(em);
    s._empty=em;s._grid=grid;
    sectionsEl.appendChild(s);
  });
  var globalEmpty=el("div","empty","No widgets match your search.");
  globalEmpty.style.display="none";
  sectionsEl.appendChild(globalEmpty);

  /* ---- filtering ---- */
  function matches(w,q){
    if(!q)return true;
    return (w.name+" "+w.desc+" "+w.id+" "+w.section).toLowerCase().indexOf(q)>=0;
  }
  function applyFilter(){
    var q=state.query.trim().toLowerCase();
    var anyGlobal=false;
    Array.prototype.forEach.call(sectionsEl.querySelectorAll(".section"),function(sec){
      var secTitle=sec.dataset.section;
      var sectionOn = (state.section==="__all"||state.section===secTitle);
      var shown=0;
      Array.prototype.forEach.call(sec.querySelectorAll(".card"),function(card){
        var w=byId(card.dataset.id);
        var vis = sectionOn && matches(w,q);
        card.style.display = vis?"":"none";
        if(vis){shown++;anyGlobal=true;}
      });
      sec.style.display = sectionOn?"":"none";
      if(sec._empty)sec._empty.style.display = (sectionOn&&shown===0)?"":"none";
    });
    globalEmpty.style.display = anyGlobal?"none":"";
    rebuildVisible();
  }
  var searchEl=$("#search");
  searchEl.addEventListener("input",function(){state.query=searchEl.value;applyFilter();});

  /* ---- visible list for modal nav ---- */
  var visible=[];
  function rebuildVisible(){
    visible=[];
    Array.prototype.forEach.call(sectionsEl.querySelectorAll(".card"),function(card){
      if(card.style.display!=="none")visible.push(card.dataset.id);
    });
  }
  function byId(id){for(var i=0;i<WIDGETS.length;i++)if(WIDGETS[i].id===id)return WIDGETS[i];return null;}

  /* ---- modal ---- */
  var modal=$("#modal"), mImg=$("#mImg"), mName=$("#mName"), mDesc=$("#mDesc"),
      mSection=$("#mSection"), mSizes=$("#mSizes"), mVariants=$("#mVariants"),
      mStage=$("#mStage"), mZoomHint=$("#mZoomHint");
  var cur=null, curVar="wide", lastFocus=null;

  function buildVariants(w){
    mVariants.innerHTML="";
    VARIANTS.forEach(function(v){
      var b=el("div","variant"+(v.key===curVar?" active":""));
      b.dataset.var=v.key;
      b.innerHTML='<div class="vt"><img src="'+shot(w.id,v.key)+'" alt=""></div><div class="vl">'+v.label+'</div>';
      b.addEventListener("click",function(){setVariant(v.key);});
      mVariants.appendChild(b);
    });
  }
  function setVariant(k){
    curVar=k;
    mStage.classList.remove("zoom");
    mImg.src=shot(cur.id,k);
    Array.prototype.forEach.call(mVariants.children,function(c){c.classList.toggle("active",c.dataset.var===k);});
  }
  function openModal(id){
    var w=byId(id);if(!w)return;
    cur=w;curVar="wide";
    lastFocus=document.activeElement;
    mSection.textContent=w.section;
    mName.textContent=w.name;
    mDesc.textContent=w.desc;
    mSizes.innerHTML="";
    (w.sizeLabels||[]).forEach(function(l){mSizes.appendChild(el("span","szchip",l));});
    buildVariants(w);
    mStage.classList.remove("zoom");
    mImg.src=shot(w.id,"wide");
    modal.classList.add("open");
    modal.setAttribute("aria-hidden","false");
    document.body.style.overflow="hidden";
    $(".close",modal).focus();
  }
  function closeModal(){
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden","true");
    document.body.style.overflow="";
    if(lastFocus&&lastFocus.focus)lastFocus.focus();
  }
  function step(dir){
    if(!cur)return;
    var list=visible.length?visible:WIDGETS.map(function(w){return w.id;});
    var i=list.indexOf(cur.id);
    if(i<0)i=0;
    i=(i+dir+list.length)%list.length;
    openModal(list[i]);
  }
  // zoom toggle
  mStage.addEventListener("click",function(e){
    if(e.target===mImg){mStage.classList.toggle("zoom");}
  });
  $("#mPrev").addEventListener("click",function(){step(-1);});
  $("#mNext").addEventListener("click",function(){step(1);});
  Array.prototype.forEach.call(modal.querySelectorAll("[data-close]"),function(b){b.addEventListener("click",closeModal);});
  document.addEventListener("keydown",function(e){
    if(!modal.classList.contains("open"))return;
    if(e.key==="Escape")closeModal();
    else if(e.key==="ArrowLeft")step(-1);
    else if(e.key==="ArrowRight")step(1);
    else if(e.key==="1")setVariant("wide");
    else if(e.key==="2")setVariant("std");
    else if(e.key==="3")setVariant("compact");
    else if(e.key==="ArrowUp"){e.preventDefault();cycleVar(-1);}
    else if(e.key==="ArrowDown"){e.preventDefault();cycleVar(1);}
  });
  function cycleVar(d){
    var idx=VARIANTS.map(function(v){return v.key;}).indexOf(curVar);
    idx=(idx+d+VARIANTS.length)%VARIANTS.length;
    setVariant(VARIANTS[idx].key);
  }

  rebuildVisible();
})();
