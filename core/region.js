"use strict";
(()=>{
  const canvas=document.getElementById("region-canvas");
  const form=document.getElementById("map-estimate");
  const preset=document.getElementById("region-preset"),view=document.getElementById("region-view");
  const ctx=canvas.getContext("2d");
  if(!ctx)return;
  const extents={world:[-180,-85,180,85],us:[-130,20,-60,55],southeast:[-91,24,-73,39],europe:[-15,30,45,72]};
  const presets={sc:[-83.4,31.9,-78.4,35.3],nc:[-84.4,33.7,-75.3,36.7],ga:[-85.7,30.3,-80.7,35.1],southeast:[-89,29,-75,37]};
  const fields=["west","south","east","north"];
  let land=[],box=null,anchor=null;
  function projection(lon,lat){const [w,s,e,n]=extents[view.value];return [(lon-w)/(e-w)*canvas.width,(n-lat)/(n-s)*canvas.height];}
  function coordinate(event){
    const r=canvas.getBoundingClientRect(),[w,s,e,n]=extents[view.value];
    const x=Math.min(1,Math.max(0,(event.clientX-r.left)/r.width));
    const y=Math.min(1,Math.max(0,(event.clientY-r.top)/r.height));
    return [w+x*(e-w),n-y*(n-s)];
  }
  function draw(){
    ctx.fillStyle="#bdd7e5";ctx.fillRect(0,0,canvas.width,canvas.height);
    ctx.fillStyle="#dce3cc";ctx.strokeStyle="#839181";ctx.lineWidth=.6;
    for(const feature of land){
      const g=feature.geometry;if(!g)continue;
      const polygons=g.type==="Polygon"?[g.coordinates]:g.type==="MultiPolygon"?g.coordinates:[];
      for(const polygon of polygons){
        ctx.beginPath();
        for(const ring of polygon){for(let i=0;i<ring.length;i++){const [x,y]=projection(...ring[i]);if(i)ctx.lineTo(x,y);else ctx.moveTo(x,y);}ctx.closePath();}
        ctx.fill("evenodd");ctx.stroke();
      }
    }
    if(box){const [x,y]=projection(box[0],box[3]),[x2,y2]=projection(box[2],box[1]);ctx.fillStyle="#184d6955";ctx.fillRect(x,y,x2-x,y2-y);ctx.strokeStyle="#123e61";ctx.lineWidth=2;ctx.strokeRect(x,y,x2-x,y2-y);}
  }
  function setBox(next){box=next;fields.forEach((field,i)=>form.elements[field].value=next[i].toFixed(4));draw();}
  function fromInputs(){const next=fields.map(f=>form.elements[f].value===""?NaN:Number(form.elements[f].value));box=next.every(Number.isFinite)&&next[0]<next[2]&&next[1]<next[3]?next:null;draw();}
  function selection(a,b){return [Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[0],b[0]),Math.max(a[1],b[1])];}
  canvas.addEventListener("pointerdown",event=>{if(event.button!==0)return;anchor=coordinate(event);canvas.setPointerCapture(event.pointerId);preset.value="";});
  canvas.addEventListener("pointermove",event=>{if(anchor){box=selection(anchor,coordinate(event));draw();}});
  canvas.addEventListener("pointerup",event=>{if(!anchor)return;const next=selection(anchor,coordinate(event));anchor=null;if(next[2]-next[0]>.0001&&next[3]-next[1]>.0001)setBox(next);else fromInputs();});
  canvas.addEventListener("pointercancel",()=>{anchor=null;fromInputs();});
  preset.addEventListener("change",()=>{if(presets[preset.value]){view.value="southeast";setBox(presets[preset.value]);}});
  view.addEventListener("change",draw);
  for(const field of fields)form.elements[field].addEventListener("input",()=>{preset.value="";fromInputs();});
  draw();
  fetch("/map-assets/land.geojson").then(r=>{if(!r.ok)throw Error();return r.json();}).then(data=>{if(!Array.isArray(data.features))throw Error();land=data.features;draw();}).catch(()=>{document.getElementById("region-help").textContent="Local overview unavailable. Use numeric fields or presets; selection still works on the coordinate grid.";});
})();
