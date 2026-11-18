const el=id=>document.getElementById(id);
const status=msg=>{el("status").textContent=msg};
const token=()=>el("token").value.trim();
async function api(path,options={}){
 if(!token())throw new Error("Enter admin token");
 const response=await fetch(path,{...options,headers:{"Authorization":"Bearer "+token(),...(options.body?{"Content-Type":"application/json"}:{})},cache:"no-store"});
 const data=await response.json();
 if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));
 return data;
}
async function load(){
 try{const cars=await api("/api/admin/inventory");const root=el("vehicles");root.replaceChildren();
  if(!cars.length){const p=document.createElement("p");p.textContent="No inventory registered yet.";root.append(p)}
  for(const v of cars){
   const div=document.createElement("div");div.className="item";
   const name=document.createElement("strong");name.textContent=`${v.year} ${v.make} ${v.model} ${v.trim} — ${v.stock_number}`;
   const meta=document.createElement("p");meta.className="muted";meta.textContent=`VIN ${v.vin} · ${v.availability} · Last source observation ${v.source_observed_at}`;
   const link=document.createElement("a");link.href=v.vehicle_url;link.target="_blank";link.rel="noopener noreferrer";link.textContent="Dealer listing";link.style.color="#9acaff";
   const action=document.createElement("button");action.className=v.availability==="SOLD"?"secondary":"warn";
   action.textContent=v.availability==="SOLD"?"Reactivate vehicle":"Mark SOLD";
   action.onclick=async()=>{const sold=v.availability!=="SOLD";if(!confirm(`${sold?"Mark SOLD":"Reactivate"} ${v.stock_number}?`))return;
    try{await api("/api/admin/inventory/"+encodeURIComponent(v.stock_number)+"/status",
      {method:"POST",body:JSON.stringify({sold})});status("Status saved.");await load()}catch(e){status(e.message)}};
   div.append(name,meta,link,document.createTextNode("  "),action);root.append(div);
  }
  status("Inventory loaded: "+cars.length+" vehicles");
 }catch(e){status(e.message)}
}
el("load").onclick=load;el("refresh").onclick=load;
el("record").onsubmit=async event=>{
 event.preventDefault();
 try{const data=Object.fromEntries(new FormData(event.currentTarget).entries());
  for(const field of ["price","mileage"]){if(data[field]==="")delete data[field];else data[field]=Number(data[field])}
  data.year=Number(data.year);
  await api("/api/admin/inventory",{method:"POST",body:JSON.stringify(data)});
  status("Listing recorded.");event.currentTarget.reset();await load();
 }catch(e){status(e.message)}
};