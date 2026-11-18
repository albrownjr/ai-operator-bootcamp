const g=id=>document.getElementById(id);
let current=null;
const msg=text=>g("status").textContent=text;
async function request(path,options={}){
 const token=g("token").value.trim();if(!token)throw Error("Enter admin token");
 const r=await fetch(path,{...options,cache:"no-store",headers:{
 "Authorization":"Bearer "+token,...(options.body?{"Content-Type":"application/json"}:{})}});
 const data=await r.json();if(!r.ok)throw Error(typeof data.detail==="string"?data.detail:JSON.stringify(data.detail));return data;
}
async function load(){
 try{
  const leads=await request("/api/admin/leads");
  const root=g("leads");root.replaceChildren();
  if(!leads.length){const p=document.createElement("p");p.textContent="No leads yet.";root.append(p)}
  for(const lead of leads){
   const b=document.createElement("button");b.type="button";b.className="lead";
   b.textContent=lead.first_name+" "+lead.last_name+" · "+lead.vehicle_name;
   const note=document.createElement("div");note.className="sub";note.textContent=lead.opportunity_status+" · "+lead.next_action+" · "+lead.created_at;
   b.append(note);b.onclick=()=>openDeal(lead.id);root.append(b);
  }
  msg("Loaded "+leads.length+" leads.");
 }catch(e){msg(e.message)}
}
async function openDeal(id){
 try{
  const d=await request("/api/admin/leads/"+encodeURIComponent(id)+"/deal");
  current=id;g("save").disabled=false;
  g("buyer").textContent=d.lead.first_name+" · "+d.lead.vehicle_name+" · "+d.lead.stock_number;
  const recommendation=g("recommendation");recommendation.replaceChildren();
  const stage=document.createElement("p");stage.className="stage";stage.textContent=d.recommendation.stage+" · "+d.recommendation.code;
  const objective=document.createElement("p");objective.textContent=d.recommendation.objective;
  const reason=document.createElement("p");reason.className="sub";reason.textContent=d.recommendation.reason;
  recommendation.append(stage,objective,reason);
  if(d.outcome){const p=document.createElement("p");p.textContent="Recorded outcome: "+d.outcome.outcome;recommendation.append(p);g("save").disabled=true}
  const root=g("timeline");root.replaceChildren();
  if(!d.timeline.length){const p=document.createElement("p");p.textContent="No actual personal contact documented yet.";root.append(p)}
  for(const e of d.timeline){
   const item=document.createElement("div");item.className="event";
   const head=document.createElement("strong");head.textContent=e.event_type+" · "+e.actor_type+" · "+e.occurred_at;
   const p=document.createElement("p");p.textContent=e.statement;
   const foot=document.createElement("div");foot.className="sub";foot.textContent="Source: "+e.source+" · Recorded "+e.recorded_at;
   item.append(head,p,foot);root.append(item);
  }
 }catch(e){msg(e.message)}
}
g("load").onclick=load;
g("record").onsubmit=async e=>{
 e.preventDefault();if(!current)return;
 const data=Object.fromEntries(new FormData(e.target).entries());
 const local=g("occurred").value;
 if(!local){msg("Actual timestamp required.");return}
 const time=new Date(local);if(Number.isNaN(time.getTime())){msg("Invalid time");return}
 data.occurred_at=time.toISOString();
 data.idempotency_key=(globalThis.crypto?.randomUUID?.()||String(Date.now())+"-"+Math.random());
 try{const result=await request("/api/admin/leads/"+encodeURIComponent(current)+"/events",
   {method:"POST",body:JSON.stringify(data)});
  if(!result.duplicate){e.target.reset();g("occurred").value=""}
  await openDeal(current);await load();msg("Event saved with recorded and actual timestamps.");
 }catch(err){msg(err.message)}
};