"""Render a vehicle-specific inquiry page using escaped registry data."""
from html import escape

def render_vehicle(v: dict) -> str:
    def e(value):
        return escape(str(value if value is not None else ""), quote=True)
    name = f'{v["year"]} {v["make"]} {v["model"]} {v["trim"]}'.strip()
    price = "Contact us for current pricing" if v["price"] is None else "Request confirmed pricing"
    miles = "Ask for current mileage" if v["mileage"] is None else f'{v["mileage"]:,} miles (listing)'
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(name)} | Request Information</title>
<meta name="description" content="Request details on this vehicle from Extreme Autoplex.">
<link rel="stylesheet" href="/static/styles.css"></head>
<body data-stock="{e(v['stock_number'])}">
<header class="topbar"><div class="brand">EXTREME <span>AUTOPLEX</span></div><div class="location">Spring, TX</div></header>
<main>
<section class="hero">
<div class="media-card"><div class="placeholder-copy"><span>ACTUAL VEHICLE INFORMATION</span>
<strong style="font-size:34px">{e(v['make'])} {e(v['model'])}</strong>
<em>View the current listing for actual vehicle photos and details.</em></div>
<div class="media-note">Stock {e(v['stock_number'])} · VIN {e(v['vin'])}</div></div>
<div class="vehicle-copy"><div class="eyebrow">PUBLIC WEBSITE LISTING</div>
<h1 style="font-size:42px">{e(name)}</h1>
<p class="subhead">{e(miles)} · Stock {e(v['stock_number'])}</p>
<p>{e(price)}. Availability is based on the dealership website and can change before your inquiry is handled.</p>
<p><a href="{e(v['vehicle_url'])}" target="_blank" rel="noopener noreferrer">See vehicle photos and details on dealership website</a></p>
</div></section>
<section class="capture-wrap" id="lead-form"><div class="capture-card">
<div class="form-heading"><div class="eyebrow">GET THE DETAILS</div><h2>Interested in this vehicle?</h2>
<p>Ask for current information about this exact stock number. Your inquiry will be associated with this listing.</p></div>
<form id="leadForm">
<div class="grid two">
<label>First name<input name="first_name" autocomplete="given-name" required maxlength="60"></label>
<label>Last name<input name="last_name" autocomplete="family-name" required maxlength="60"></label>
</div><div class="grid two">
<label>Mobile number<input name="phone" type="tel" autocomplete="tel" required></label>
<label>Email<input name="email" type="email" autocomplete="email" required></label></div>
<div class="grid two">
<label>ZIP code<input name="zip_code" autocomplete="postal-code" required maxlength="10"></label>
<label>Do you have a trade?<select name="trade_status" required>
<option value="" disabled selected>Select one</option><option value="yes">Yes</option><option value="no">No</option><option value="unsure">Unsure</option>
</select></label></div>
<fieldset><legend>How should we contact you?</legend><div class="choice-row">
<label class="choice"><input type="radio" name="preferred_contact" value="text" checked>Text</label>
<label class="choice"><input type="radio" name="preferred_contact" value="call">Call</label>
<label class="choice"><input type="radio" name="preferred_contact" value="email">Email</label>
</div></fieldset>
<label class="consent"><input type="checkbox" name="consent_contact" required>
<span>I agree that Extreme Autoplex and its sales representative may contact me about this specific inquiry by my chosen method. Message/data rates may apply. Consent is not a condition of purchase.</span></label>
<label class="consent"><input type="checkbox" name="consent_marketing">
<span>Optional: I agree to receive future marketing messages about vehicles and offers. Reply STOP to opt out of texts.</span></label>
<div class="honeypot"><label>Website<input name="website" tabindex="-1" autocomplete="off"></label></div>
<button type="submit" class="cta" id="submitButton">REQUEST VEHICLE DETAILS</button>
<p class="micro">Submitting does not reserve or guarantee availability, pricing, financing or approval. See the <a href="https://www.extremeautoplex.com/privacy-policy/" target="_blank" rel="noopener">Privacy Policy</a>.</p>
<div class="form-status" id="formStatus" role="status"></div></form></div></section>
<footer><strong>Extreme Autoplex LLC</strong><p>Final availability and complete dealership-approved pricing must be confirmed before purchase.</p></footer>
</main><script src="/static/app.js"></script></body></html>"""
