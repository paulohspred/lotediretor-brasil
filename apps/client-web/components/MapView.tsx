'use client';
import {useEffect,useRef} from 'react';
import maplibregl from 'maplibre-gl';
export function MapView(){
  const ref=useRef<HTMLDivElement>(null);
  useEffect(()=>{
    if(!ref.current)return;
    const map=new maplibregl.Map({container:ref.current,center:[-47.88,-15.79],zoom:4,style:{version:8,sources:{
      osm:{type:'raster',tiles:['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],tileSize:256,attribution:'© OpenStreetMap'},
      parcels:{type:'vector',tiles:['/tiles/parcel/{z}/{x}/{y}'],minzoom:0,maxzoom:22},
      zones:{type:'vector',tiles:['/tiles/zone/{z}/{x}/{y}'],minzoom:0,maxzoom:22}
    },layers:[
      {id:'osm',type:'raster',source:'osm'},
      {id:'zones-fill',type:'fill',source:'zones','source-layer':'zone',paint:{'fill-color':'#20A475','fill-opacity':0.12}},
      {id:'zones-line',type:'line',source:'zones','source-layer':'zone',paint:{'line-color':'#356854','line-width':1}},
      {id:'parcels-line',type:'line',source:'parcels','source-layer':'parcel',paint:{'line-color':'#111827','line-width':1.2}}
    ]}});
    map.addControl(new maplibregl.NavigationControl(),'top-right');
    return()=>map.remove();
  },[]);
  return <div ref={ref} style={{width:'100%',height:'100%'}}/>;
}
