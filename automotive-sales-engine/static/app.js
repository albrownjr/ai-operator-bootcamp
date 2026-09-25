const form=document.getElementById('leadForm');
const statusBox=document.getElementById('formStatus');
const submitButton=document.getElementById('submitButton');
const params=new URLSearchParams(window.location.search);

function tracking(){
  return{
    source:params.get('utm_source')||params.get('source')||'direct',
    medium:params.get('utm_medium')||params.get('medium')||'',
    campaign:params.get('utm_campaign')||params.get('campaign')||'',
    creative:params.get('utm_content')||params.get('creative')||'',
    utm_id:params.get('utm_id')||'',
    utm_term:params.get('utm_term')||'',
    fbclid:params.get('fbclid')||'',
    gclid:params.get('gclid')||'',
    referrer:document.referrer||'',
    landing_url:window.location.href
  };
}

form.addEventListener('submit',async(event)=>{
  event.preventDefault();
  statusBox.textContent='';
  if(!form.reportValidity()) return;

  const data=new FormData(form);
  const payload={
    first_name:data.get('first_name'),
    last_name:data.get('last_name'),
    phone:data.get('phone'),
    email:data.get('email'),
    zip_code:data.get('zip_code'),
    trade_status:data.get('trade_status'),
    preferred_contact:data.get('preferred_contact'),
    consent_contact:data.get('consent_contact')==='on',
    consent_marketing:data.get('consent_marketing')==='on',
    website:data.get('website')||'',
    ...tracking()
  };

  submitButton.disabled=true;
  submitButton.textContent='SENDING...';

  try{
    const response=await fetch('/api/leads',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    const result=await response.json();
    if(!response.ok) throw new Error(result.detail||'Unable to submit your request.');

    form.reset();
    statusBox.className='form-status success';
    statusBox.innerHTML='<strong>Request received.</strong> Your inquiry is attached to this exact Tahoe.';
    submitButton.textContent='REQUEST RECEIVED';

    window.dispatchEvent(new CustomEvent('vehicleLeadCaptured',{detail:result}));
  }catch(error){
    statusBox.className='form-status error';
    statusBox.textContent=error.message||'Something went wrong.';
    submitButton.disabled=false;
    submitButton.textContent='CHECK AVAILABILITY';
  }
});