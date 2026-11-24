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
  document.getElementById("route-clear").addEventListener("click",()=>{requestNumber++;lastRoute=null;routeMode=null;pick=null;form.reset();if(map?.getLayer("route")){map.removeLayer("route");map.removeSource("route");}document.getElementById("route-details").hidden=true;routeMessage.textContent="Route cleared";});
  form.addEventListener("submit",async event=>{
    event.preventDefault();const sequence=++requestNumber;
    const mode=form.elements.mode.value;
    routeMessage.textContent="Calculating on local routing engine…";
    try{
      const response=await fetch("/api/maps/route",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:readPoint(form.elements.start.value),end:readPoint(form.elements.end.value),mode})});
      const result=await response.json();if(sequence!==requestNumber)return;
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Route request failed");
      lastRoute=result;routeMode=mode;drawRoute(result);
      routeMessage.textContent=result.distance_km.toFixed(2)+" km · "+Math.round(result.duration_seconds/60)+" min estimated. Verify current road conditions.";
      const list=document.getElementById("route-directions");list.replaceChildren();
      for(const step of result.instructions){const li=document.createElement("li");li.textContent=step;list.append(li);}
      document.getElementById("route-details").hidden=false;
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
      button(row,"View",async()=>{requestNumber++;lastRoute=await planApi("/api/maps/plans/routes/"+r.id);routeMode=r.mode;drawRoute(lastRoute);document.getElementById("route-details").hidden=true;routeMessage.textContent="Saved route snapshot: "+r.name+" — no current routing or closure checks.";});
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
  refreshPlans().catch(e=>{planMessage.textContent=e.message;});
})();
