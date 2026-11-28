/* Isolated design prototype. No network or production API calls. */
"use strict";
(function(root){
  const builtins = [
  {
    "id": "overwatch",
    "name": "Overwatch",
    "description": "Tactical operations center",
    "radius": 6,
    "light": {
      "bg": "#E9EDE5",
      "panel": "#FAFCF7",
      "sidebar": "#DCE4D8",
      "text": "#203126",
      "muted": "#4C6250",
      "accent": "#365E38",
      "onAccent": "#FFFFFF",
      "border": "#859985",
      "hero": "#D1DFC8"
    },
    "dark": {
      "bg": "#101713",
      "panel": "#1C2820",
      "sidebar": "#151E18",
      "text": "#E3ECDD",
      "muted": "#A4B5A0",
      "accent": "#A1CE88",
      "onAccent": "#142014",
      "border": "#526752",
      "hero": "#233829"
    }
  },
  {
    "id": "outpost",
    "name": "Outpost",
    "description": "Modern outdoors",
    "radius": 12,
    "light": {
      "bg": "#F2EFE6",
      "panel": "#FFFDF7",
      "sidebar": "#E6E8DC",
      "text": "#263F34",
      "muted": "#526653",
      "accent": "#416A45",
      "onAccent": "#FFFFFF",
      "border": "#899782",
      "hero": "#DEE8D5"
    },
    "dark": {
      "bg": "#17231C",
      "panel": "#23342A",
      "sidebar": "#1C2B22",
      "text": "#F3F0E4",
      "muted": "#B7C4AE",
      "accent": "#B8D59F",
      "onAccent": "#213322",
      "border": "#64775F",
      "hero": "#304B38"
    }
  },
  {
    "id": "essential",
    "name": "Essential",
    "description": "Clean consumer technology",
    "radius": 14,
    "light": {
      "bg": "#F4F6FA",
      "panel": "#FFFFFF",
      "sidebar": "#EEF1F6",
      "text": "#202B3A",
      "muted": "#526176",
      "accent": "#245FC3",
      "onAccent": "#FFFFFF",
      "border": "#8492A7",
      "hero": "#E3EAFA"
    },
    "dark": {
      "bg": "#141A24",
      "panel": "#202938",
      "sidebar": "#19212E",
      "text": "#F0F4FC",
      "muted": "#ACBBD0",
      "accent": "#91B5FF",
      "onAccent": "#17243A",
      "border": "#60718A",
      "hero": "#293C58"
    }
  },
  {
    "id": "fortress",
    "name": "Fortress",
    "description": "Industrial / rugged",
    "radius": 3,
    "light": {
      "bg": "#E9EBED",
      "panel": "#FAFAFA",
      "sidebar": "#DDE0E3",
      "text": "#242A30",
      "muted": "#505B66",
      "accent": "#795008",
      "onAccent": "#FFFFFF",
      "border": "#828C96",
      "hero": "#F3E6CA"
    },
    "dark": {
      "bg": "#202327",
      "panel": "#2B3035",
      "sidebar": "#15181B",
      "text": "#F0F1F2",
      "muted": "#B5C0CA",
      "accent": "#ECAA39",
      "onAccent": "#251B08",
      "border": "#66717B",
      "hero": "#3C3528"
    }
  }
];
  const keys = ["bg","panel","sidebar","text","muted","accent","onAccent","border","hero"];
  function luminance(hex){
    const v=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16)/255).map(x=>x<=0.04045?x/12.92:Math.pow((x+0.055)/1.055,2.4));
    return v[0]*0.2126+v[1]*0.7152+v[2]*0.0722;
  }
  function ratio(a,b){const x=luminance(a),y=luminance(b);return (Math.max(x,y)+0.05)/(Math.min(x,y)+0.05);}
  function validate(theme){
    if(!theme||typeof theme!=="object"||Array.isArray(theme))return false;
    if(Object.keys(theme).sort().join(",")!=="dark,description,id,light,name,radius")return false;
    if(typeof theme.id!=="string"||!/^[a-z][a-z0-9.-]{0,63}$/.test(theme.id)||typeof theme.name!=="string"||!theme.name.trim()||theme.name.length>48||typeof theme.description!=="string"||theme.description.length>160||!Number.isInteger(theme.radius)||theme.radius<0||theme.radius>16)return false;
    return ["light","dark"].every(mode=>{
      const p=theme[mode];
      if(!p||typeof p!=="object"||Array.isArray(p)||Object.keys(p).sort().join(",")!==keys.slice().sort().join(","))return false;
      if(!keys.every(k=>typeof p[k]==="string"&&/^#[0-9a-f]{6}$/i.test(p[k])))return false;
      return ["bg","panel","sidebar","hero"].every(k=>["text","muted","accent"].every(f=>ratio(p[f],p[k])>=4.5))&&ratio(p.onAccent,p.accent)>=4.5;
    });
  }
  function resolve(id,mode,systemDark,custom=[]){
    const list=builtins.concat(custom.filter(t=>validate(t)&&!builtins.some(b=>b.id===t.id)));
    const theme=list.find(t=>t.id===id)||builtins[0];
    const appearance=mode==="light"||mode==="dark"?mode:systemDark?"dark":"light";
    return {theme,appearance,tokens:theme[appearance]};
  }
  function apply(element,selection){
    for(const k of keys)element.style.setProperty("--"+k,selection.tokens[k]);
    element.style.setProperty("--radius",selection.theme.radius+"px");
    element.dataset.theme=selection.theme.id;
    element.dataset.mode=selection.appearance;
    element.style.colorScheme=selection.appearance;
  }
  const api={schemaVersion:1,builtins,validate,resolve,apply,ratio};
  if(typeof module!=="undefined"&&module.exports)module.exports=api;
  else root.AfterGridTheme=api;
})(typeof globalThis!=="undefined"?globalThis:this);
