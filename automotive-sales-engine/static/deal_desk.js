const g=id=>document.getElementById(id);
let current=null;
const msg=text=>g("status").textContent=text;
async function request(path,options={}){
 const token=g("token").value.trim();if(!token)throw Error("Enter admin token");
 const {requireManager,...requestOptions}=options;
 const manager=requireManager?g("managerToken").value.trim():"";
 if(requireManager&&!manager)throw Error("Separate manager credential required for this recorded approval");
 const r=await fetch(path,{...requestOptions,cache:"no-store",headers:{
 "Authorization":"Bearer "+token,...(requestOptions.body?{"Content-Type":"application/json"}:{}),
 ...(requireManager?{"X-Management-Token":manager}:{})}});
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
  current=id;g("save").disabled=false;g("taskSave").disabled=false;
  g("buyer").textContent=d.lead.first_name+" · "+d.lead.vehicle_name+" · "+d.lead.stock_number;
  const recommendation=g("recommendation");recommendation.replaceChildren();
  const stage=document.createElement("p");stage.className="stage";stage.textContent=d.recommendation.stage+" · "+d.recommendation.code;
  const objective=document.createElement("p");objective.textContent=d.recommendation.objective;
  const reason=document.createElement("p");reason.className="sub";reason.textContent=d.recommendation.reason;
  recommendation.append(stage,objective,reason);
  if(d.outcome){const p=document.createElement("p");p.textContent="Recorded outcome: "+d.outcome.outcome;recommendation.append(p);g("save").disabled=true}
  const tasksNode=g("tasks");tasksNode.replaceChildren();
  for(const task of d.tasks||[]){
    const row=document.createElement("div");row.className="event";
    const title=document.createElement("strong");
    title.textContent=task.source+" · "+task.computed_status+" · "+task.required_action;
    const info=document.createElement("p");
    info.textContent=task.objective+" · due "+task.due_local_day+" · "+task.channel_policy;
    row.append(title,info);
    if(task.status!=="CANCELLED" && task.computed_status!=="FULFILLED"){
      const cancel=document.createElement("button");cancel.className="secondary";cancel.type="button";
      cancel.textContent="Cancel in engine";
      cancel.onclick=async()=>{
        const reason=prompt("Why is the task cancelled? Update the real CRM separately.");
        if(!reason)return;
        try{await request("/api/admin/tasks/"+encodeURIComponent(task.id)+"/cancel",
          {method:"POST",body:JSON.stringify({reason})});await openDeal(current);
          msg("Engine task cancelled. Update the dealership CRM separately.")}catch(err){msg(err.message)}
      };row.append(cancel);
    }
    tasksNode.append(row);
  }
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
async function refreshPulse(){
 try{
  const [metrics,due]=await Promise.all([
    request("/api/admin/metrics/funnel"),request("/api/admin/tasks/due")]);
  const m=metrics.overall;
  g("metrics").textContent=
    "Leads: "+m.leads+" · Personal contact: "+m.personally_contacted+
    " · Quotes: "+m.quotes_presented+" · Delivered SOLD: "+m.sold_delivered+
    " · Lost: "+m.lost+" · Lead-to-SOLD: "+
    (m.lead_to_sold_pct===null?"N/A":m.lead_to_sold_pct+"%");
  const overdue=due.filter(t=>t.computed_status==="OVERDUE");
  const today=due.filter(t=>t.computed_status==="DUE_TODAY");
  g("dueSummary").textContent="Recorded action queue: "+today.length+
     " due today · "+overdue.length+" overdue. CRM tasks appear only if manually entered.";
 }catch(e){msg(e.message)}
}
g("refreshMetrics").onclick=refreshPulse;
g("load").onclick=async()=>{await load();await refreshPulse()};
g("record").onsubmit=async e=>{
 e.preventDefault();if(!current)return;
 const data=Object.fromEntries(new FormData(e.target).entries());
 const local=g("occurred").value;
 if(!local){msg("Actual timestamp required.");return}
 const time=new Date(local);if(Number.isNaN(time.getTime())){msg("Invalid time");return}
 data.occurred_at=time.toISOString();
 data.idempotency_key=(globalThis.crypto?.randomUUID?.()||String(Date.now())+"-"+Math.random());
 try{const result=await request("/api/admin/leads/"+encodeURIComponent(current)+"/events",
   {method:"POST",body:JSON.stringify(data),requireManager:data.actor_type==="management"});
  if(!result.duplicate){e.target.reset();g("occurred").value=""}
  await openDeal(current);await load();msg("Event saved with recorded and actual timestamps.");
 }catch(err){msg(err.message)}
};
g("taskForm").onsubmit=async event=>{
  event.preventDefault();if(!current)return;
  const form=event.currentTarget;
  const data=Object.fromEntries(new FormData(form).entries());
  const due=new Date(g("task_due").value);
  if(Number.isNaN(due.getTime())){msg("Enter a valid CRM due time.");return}
  data.due_at=due.toISOString();
  data.source="CRM_MANUAL";
  try{
    await request("/api/admin/leads/"+encodeURIComponent(current)+"/tasks",
      {method:"POST",body:JSON.stringify(data)});
    form.reset();await openDeal(current);msg("CRM task recorded in this engine. DealerCenter was not changed.");
  }catch(err){msg(err.message)}
};