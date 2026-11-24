"use strict";
(async()=>{
  const message=document.getElementById("map-status");
  const form=document.getElementById("route-form"), routeMessage=document.getElementById("route-message");
  let map=null, pick=null, lastRoute=null, requestNumber=0;
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
    map.on("load",()=>{message.textContent="Local map loaded";document.body.dataset.mapReady="true";if(lastRoute)drawRoute(lastRoute);});
    map.on("error",event=>{message.textContent="Map resource error: "+(event.error?.message||"inspect local archive");});
    map.on("click",event=>{document.getElementById("coordinates").textContent=event.lngLat.lat.toFixed(6)+", "+event.lngLat.lng.toFixed(6);if(pick){form.elements[pick].value=event.lngLat.lng.toFixed(6)+","+event.lngLat.lat.toFixed(6);pick=null;routeMessage.textContent="Location selected";}});
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
  document.getElementById("route-clear").addEventListener("click",()=>{requestNumber++;lastRoute=null;pick=null;form.reset();if(map?.getLayer("route")){map.removeLayer("route");map.removeSource("route");}document.getElementById("route-details").hidden=true;routeMessage.textContent="Route cleared";});
  form.addEventListener("submit",async event=>{
    event.preventDefault();const sequence=++requestNumber;
    routeMessage.textContent="Calculating on local routing engine…";
    try{
      const response=await fetch("/api/maps/route",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({start:readPoint(form.elements.start.value),end:readPoint(form.elements.end.value),mode:form.elements.mode.value})});
      const result=await response.json();if(sequence!==requestNumber)return;
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Route request failed");
      lastRoute=result;drawRoute(result);
      routeMessage.textContent=result.distance_km.toFixed(2)+" km · "+Math.round(result.duration_seconds/60)+" min estimated. Verify current road conditions.";
      const list=document.getElementById("route-directions");list.replaceChildren();
      for(const step of result.instructions){const li=document.createElement("li");li.textContent=step;list.append(li);}
      document.getElementById("route-details").hidden=false;
    }catch(e){if(sequence===requestNumber)routeMessage.textContent=e.message;}
  });
})();
