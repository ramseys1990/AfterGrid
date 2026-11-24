"use strict";
(async()=>{
  const message=document.getElementById("map-status");
  const form=document.getElementById("route-form"), routeMessage=document.getElementById("route-message");
  let map=null, pick=null, lastRoute=null, requestNumber=0, routeMode=null, mapPlans={waypoints:[],routes:[]}, canEdit=false;
  try{
    const archive=location.origin+"/maps/archive.pmtiles";
    const protocol=new pmtiles.Protocol();
    maplibregl.addProtocol("pmtiles",protocol.tile);
    const source=new pmtiles.PMTiles(archive);
    protocol.add(source);
    const header=await source.getHeader();
    const vector=header.tileType===1;
    const raster=[2,3,4,5].includes(header.tileType);
    if(!vector&&!raster)throw Error("Unsupported encoding; use Protomaps MVT or raster PMTiles.");
    const style={version:8,sources:{region:{type:vector?"vector":"raster",url:"pmtiles://"+archive,attribution:"© OpenStreetMap contributors; preserve original archive attribution"}},layers:[]};
    if(vector){
      const metadata=await source.getMetadata();
      const layers=new Set((metadata.vector_layers||[]).map(l=>l.id));
      if(!["roads","places","water"].every(l=>layers.has(l)))throw Error("Not a compatible Protomaps basemap. Use the native Maps viewer for other schemas.");
      style.glyphs=location.origin+"/map-assets/fonts/{fontstack}/{range}.pbf";
      style.sprite=location.origin+"/map-assets/sprites/v4/light";
      style.layers=basemaps.layers("region",basemaps.namedFlavor("light"),{lang:"en"});
    }else{style.layers=[{id:"region-raster",type:"raster",source:"region"}];}
    map=new maplibregl.Map({container:"map",style,center:[header.centerLon,header.centerLat],zoom:Math.min(header.maxZoom,Math.max(header.minZoom,header.centerZoom)),maxZoom:Math.min(22,header.maxZoom+3),hash:true});
    map.addControl(new maplibregl.NavigationControl(),"top-right");
    map.addControl(new maplibregl.ScaleControl());
    map.on("load",()=>{message.textContent="Local map loaded";document.body.dataset.mapReady="true";if(lastRoute)drawRoute(lastRoute);drawWaypoints();});
    map.on("error",event=>{message.textContent="Map resource error: "+(event.error?.message||"inspect local archive");});
    map.on("click",event=>{document.getElementById("coordinates").textContent=event.lngLat.lat.toFixed(6)+", "+event.lngLat.lng.toFixed(6);if(pick){const target=pick==="waypoint"?document.getElementById("waypoint-form").elements.coords:form.elements[pick];target.value=event.lngLat.lng.toFixed(6)+","+event.lngLat.lat.toFixed(6);pick=null;routeMessage.textContent="Location selected";}});
  }catch(e){message.textContent="Map unavailable: "+e.message+" Download or import a regional PMTiles archive first.";}
  function drawRoute(route){
    if(!map||!map.isStyleLoaded())return;
    const data={type:"Feature",geometry:{type:"LineString",coordinates:route.coordinates},properties:{}};
    if(map.getSource("route"))map.getSource("route").setData(data);
    else{map.addSource("route",{type:"geojson",data});map.addLayer({id:"route",type:"line",source:"route",paint:{"line-color":"#2963dd","line-width":5}});}
    const bounds=new maplibregl.LngLatBounds();for(const p of route.coordinates)bounds.extend(p);map.fitBounds(bounds,{padding:40,maxZoom:15});
  }
  function readPoint(value){const parts=value.split(",").map(s=>s.trim());if(parts.length!==2||parts.some(s=>!s||!Number.isFinite(Number(s))))throw Error("Use longitude, latitude");return parts.map(Number);}
  for(const field of ["start","end"])document.getElementById("route-"+field).addEventListener("click",()=>{if(!map){routeMessage.textContent="Map unavailable; enter coordinates manually.";return;}pick=field;routeMessage.textContent="Click the map to choose "+field;});
  document.getElementById("route-clear").addEventListener("click",()=>{requestNumber++;lastRoute=null;routeMode=null;pick=null;form.reset();document.getElementById("route-choices").replaceChildren();if(map?.getLayer("route")){map.removeLayer("route");map.removeSource("route");}document.getElementById("route-details").hidden=true;routeMessage.textContent="Route cleared";});
  form.addEventListener("submit",async event=>{
    event.preventDefault();const sequence=++requestNumber;
    const mode=form.elements.mode.value;
    routeMessage.textContent="Calculating on local routing engine…";
    try{
      const response=await fetch("/api/maps/route",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:readPoint(form.elements.start.value),end:readPoint(form.elements.end.value),mode,alternatives:Number(form.elements.alternatives.value)})});
      const result=await response.json();if(sequence!==requestNumber)return;
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Route request failed");
      const choices=document.getElementById("route-choices");choices.replaceChildren();
      const routes=[result,...(result.alternatives||[])];
      function selectRoute(index){
        const chosen=routes[index];lastRoute=chosen;routeMode=mode;drawRoute(chosen);
        routeMessage.textContent=(index?"Alternative "+index:"Primary route")+": "+chosen.distance_km.toFixed(2)+" km · "+Math.round(chosen.duration_seconds/60)+" min estimated. Verify current road conditions.";
        const list=document.getElementById("route-directions");list.replaceChildren();
        for(const step of chosen.instructions){const li=document.createElement("li");li.textContent=step;list.append(li);}
        document.getElementById("route-details").hidden=false;
        for(const [i,b] of [...choices.children].entries())b.setAttribute("aria-pressed",String(i===index));
      }
      routes.forEach((r,i)=>button(choices,(i?"Alternative "+i:"Primary")+" · "+r.distance_km.toFixed(2)+" km",()=>selectRoute(i)));
      selectRoute(0);
      if(routes.length===1&&Number(form.elements.alternatives.value)>0)routeMessage.textContent+=" No alternate returned by Valhalla.";
    }catch(e){if(sequence===requestNumber)routeMessage.textContent=e.message;}
  });
  const planMessage=document.getElementById("plan-message");
  async function planApi(path,body){
    const r=await fetch(path,body===undefined?{}:{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:"Plan request failed");return data;
  }
  function drawWaypoints(){
    if(!map||!map.isStyleLoaded())return;
    const data={type:"FeatureCollection",features:mapPlans.waypoints.map(w=>({type:"Feature",geometry:{type:"Point",coordinates:[w.lon,w.lat]},properties:{name:w.name,kind:w.kind}}))};
    if(map.getSource("waypoints"))map.getSource("waypoints").setData(data);
    else{map.addSource("waypoints",{type:"geojson",data});map.addLayer({id:"waypoints",type:"circle",source:"waypoints",paint:{"circle-radius":7,"circle-color":"#b74a30","circle-stroke-color":"#fff","circle-stroke-width":2}});
      map.on("click","waypoints",e=>{if(pick)return;const item=e.features?.[0];if(item)new maplibregl.Popup().setLngLat(item.geometry.coordinates).setText(item.properties.name+" · "+item.properties.kind).addTo(map);});
    }
  }
  function button(row,label,handler){const b=document.createElement("button");b.type="button";b.textContent=label;b.addEventListener("click",async()=>{try{await handler();}catch(e){planMessage.textContent=e.message;}});row.append(b);}
  function text(row,value){const n=document.createElement("span");n.textContent=value;row.append(n);}
  async function deletePlan(kind,id){if(confirm("Remove this shared "+kind+"?")){await planApi("/api/admin/maps/plans/delete",{kind,id});await refreshPlans();}}
  async function refreshPlans(){
    const status=await planApi("/api/status");canEdit=!!status.admin;
    document.getElementById("place-admin").hidden=!canEdit;
    if(canEdit)refreshPlaceIndex().catch(e=>{document.getElementById("place-index-status").textContent=e.message;});
    document.getElementById("plan-admin").hidden=!canEdit;
    mapPlans=await planApi("/api/maps/plans");drawWaypoints();
    const wl=document.getElementById("waypoints-list");wl.replaceChildren();
    for(const w of mapPlans.waypoints){
      const row=document.createElement("div");text(row,w.name+" · "+w.kind+" · "+w.lon+", "+w.lat);
      for(const field of ["start","end"])button(row,"Use as "+field,()=>{form.elements[field].value=w.lon+","+w.lat;});
      if(canEdit)button(row,"Delete",()=>deletePlan("waypoint",w.id));wl.append(row);
    }
    const rl=document.getElementById("routes-list");rl.replaceChildren();
    for(const r of mapPlans.routes){
      const row=document.createElement("div");text(row,r.name+" · "+r.mode);
      button(row,"View",async()=>{requestNumber++;document.getElementById("route-choices").replaceChildren();lastRoute=await planApi("/api/maps/plans/routes/"+r.id);routeMode=r.mode;drawRoute(lastRoute);document.getElementById("route-details").hidden=true;routeMessage.textContent="Saved route snapshot: "+r.name+" — no current routing or closure checks.";});
      for(const fmt of ["gpx","kml"]){const link=document.createElement("a");link.href="/api/maps/export/"+fmt+"?route_id="+r.id;link.textContent=fmt.toUpperCase();row.append(link);}
      if(canEdit)button(row,"Delete",()=>deletePlan("route",r.id));rl.append(row);
    }
    if(!wl.children.length)wl.textContent="No shared waypoints.";
    if(!rl.children.length)rl.textContent="No saved routes.";
  }
  document.getElementById("plans-refresh").addEventListener("click",()=>refreshPlans().catch(e=>{planMessage.textContent=e.message;}));
  document.getElementById("waypoint-pick").addEventListener("click",()=>{if(!map){planMessage.textContent="Enter coordinates manually.";return;}pick="waypoint";routeMessage.textContent="Click map to choose waypoint";});
  document.getElementById("waypoint-form").addEventListener("submit",async event=>{
    event.preventDefault();const f=event.currentTarget;
    try{await planApi("/api/admin/maps/waypoints",{name:f.elements.name.value,kind:f.elements.kind.value,coords:readPoint(f.elements.coords.value)});f.reset();await refreshPlans();planMessage.textContent="Waypoint saved.";}catch(e){planMessage.textContent=e.message;}
  });
  document.getElementById("save-route").addEventListener("submit",async event=>{
    event.preventDefault();const f=event.currentTarget;
    try{if(!lastRoute||!routeMode)throw Error("Calculate or display a route first");await planApi("/api/admin/maps/routes",{name:f.elements.name.value,mode:routeMode,coordinates:lastRoute.coordinates});f.reset();await refreshPlans();planMessage.textContent="Route snapshot saved.";}catch(e){planMessage.textContent=e.message;}
  });
  document.getElementById("import-plan").addEventListener("submit",async event=>{
    event.preventDefault();const f=event.currentTarget, file=f.elements.file.files[0];
    try{
      if(!file||file.size>1000000)throw Error("Choose a GPX or KML file no larger than 1 MB");
      const fmt=file.name.split(".").pop().toLowerCase();if(!["gpx","kml"].includes(fmt))throw Error("Choose GPX or KML");
      if(!confirm("Import the supported points and tracks into the shared LAN directory? All LAN users will be able to see them."))return;
      const response=await fetch("/api/admin/maps/import/"+fmt,{method:"POST",headers:{"Content-Type":"application/xml"},body:file});
      const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Import failed");
      await refreshPlans();f.reset();planMessage.textContent="Imported "+data.waypoints+" waypoints and "+data.routes+" route snapshots.";
    }catch(e){planMessage.textContent=e.message;}
  });
  async function refreshPlaceIndex(){
    const r=await planApi("/api/admin/maps/places");
    document.getElementById("place-index-status").textContent=r.state+" — "+(r.detail||"")+(r.ready?" · "+r.count+" indexed points":" · selected source not indexed");
    document.getElementById("place-build").disabled=!r.source_available||r.state==="building";
  }
  document.getElementById("place-status-refresh").addEventListener("click",()=>refreshPlaceIndex().catch(e=>{document.getElementById("place-index-status").textContent=e.message;}));
  document.getElementById("place-build").addEventListener("click",async()=>{
    if(!confirm("Build an offline search index? This uses CPU, RAM and disk. The selected PBF is not changed."))return;
    try{await planApi("/api/admin/maps/places/build",{});await refreshPlaceIndex();}catch(e){document.getElementById("place-index-status").textContent=e.message;}
  });
  document.getElementById("place-search").addEventListener("submit",async event=>{
    event.preventDefault();const root=document.getElementById("place-results"),msg=document.getElementById("place-message");root.replaceChildren();msg.textContent="Searching local points…";
    try{
      const r=await planApi("/api/maps/places?q="+encodeURIComponent(event.currentTarget.elements.q.value));
      msg.textContent=r.results.length?r.results.length+" matching points (up to 30)":"No matching indexed points";
      for(const p of r.results){
        const row=document.createElement("div");text(row,p.title+" · "+p.kind+(p.detail?" · "+p.detail:""));
        for(const field of ["start","end"])button(row,"Use as "+field,()=>{form.elements[field].value=p.lon+","+p.lat;});
        button(row,"Show on map",()=>{if(map)map.flyTo({center:[p.lon,p.lat],zoom:15});else msg.textContent=p.lon+", "+p.lat;});root.append(row);
      }
    }catch(e){msg.textContent=e.message;}
  });
  refreshPlans().catch(e=>{planMessage.textContent=e.message;});
})();
