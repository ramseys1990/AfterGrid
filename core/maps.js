"use strict";
(async()=>{
  const message=document.getElementById("map-status");
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
    const map=new maplibregl.Map({container:"map",style,center:[header.centerLon,header.centerLat],zoom:Math.min(header.maxZoom,Math.max(header.minZoom,header.centerZoom)),maxZoom:Math.min(22,header.maxZoom+3),hash:true});
    map.addControl(new maplibregl.NavigationControl(),"top-right");
    map.addControl(new maplibregl.ScaleControl());
    map.on("load",()=>{message.textContent="Local map loaded";document.body.dataset.mapReady="true";});
    map.on("error",event=>{message.textContent="Map resource error: "+(event.error?.message||"inspect local archive");});
    map.on("click",event=>{document.getElementById("coordinates").textContent=event.lngLat.lat.toFixed(6)+", "+event.lngLat.lng.toFixed(6);});
  }catch(e){message.textContent="Map unavailable: "+e.message+" Download or import a regional PMTiles archive first.";}
})();
