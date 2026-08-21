import frappe

@frappe.whitelist()
def get_customer_fraud_profile(customer: str):
	"""Returns fingerprint matches and other fraud details for a customer."""
	orders = frappe.db.sql("""
		SELECT custom_device_fingerprint, shipping_address_name
		FROM `tabSales Order`
		WHERE customer = %s
	""", (customer,), as_dict=True)
	
	contacts = frappe.db.sql("""
		SELECT email_id
		FROM `tabContact` c
		JOIN `tabDynamic Link` dl ON dl.parent = c.name
		WHERE dl.link_doctype = 'Customer' AND dl.link_name = %s
	""", (customer,), as_dict=True)
	
	fingerprints = set()
	emails = set()
	address_names = set()
	
	for o in orders:
		if o.custom_device_fingerprint:
			fingerprints.add(o.custom_device_fingerprint)
		if o.shipping_address_name:
			address_names.add(o.shipping_address_name)
			
	for c in contacts:
		if c.email_id:
			emails.add(c.email_id.strip().lower())
			
	addresses = []
	if address_names:
		address_records = frappe.db.sql(f"""
			SELECT address_line1, address_line2, city, state, pincode, country
			FROM `tabAddress`
			WHERE name IN %s
		""", (tuple(address_names),), as_dict=True)
		for a in address_records:
			parts = [a.address_line1, a.address_line2, a.city, a.state, a.pincode, a.country]
			addresses.append(", ".join([str(p) for p in parts if p]))

	# Deduplicate addresses string list
	addresses = list(set(addresses))
			
	linked = []
	if fingerprints:
		fps = tuple(fingerprints)
		linked = frappe.db.sql(f"""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE custom_device_fingerprint IN %s
			AND customer != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (fps, customer), as_dict=True)
		
	return {
		"fingerprints": list(fingerprints),
		"emails": list(emails),
		"addresses": addresses,
		"linked_orders": linked,
	}

@frappe.whitelist()
def get_order_fraud_profile(order: str):
	"""Returns fingerprint/location matches for an order."""
	# Auto-recalculate to reflect real-time RTO history and City stats
	# Time-sensitive metrics (velocity, risky hour) are anchored by so.creation
	try:
		recalculate_order_fraud(order)
	except Exception:
		pass
		
	so = frappe.db.get_value("Sales Order", order, 
		["customer", "custom_device_fingerprint", "custom_fraud_score", "custom_fraud_verdict", "custom_fraud_signals", "shipping_address_name"], 
		as_dict=True)
		
	if not so:
		return {}
		
	# Find other orders with same fingerprint
	fp_matches = []
	if so.custom_device_fingerprint:
		fp_matches = frappe.db.sql("""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE custom_device_fingerprint = %s
			AND name != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (so.custom_device_fingerprint, order), as_dict=True)
		
	# Find other orders to the same address
	address_matches = []
	if so.shipping_address_name:
		address_matches = frappe.db.sql("""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE shipping_address_name = %s
			AND name != %s
			ORDER BY creation DESC
			LIMIT 20
		""", (so.shipping_address_name, order), as_dict=True)
		
	return {
		"fingerprint": so.custom_device_fingerprint,
		"score": so.custom_fraud_score,
		"verdict": so.custom_fraud_verdict,
		"signals": so.custom_fraud_signals,
		"fp_matches": fp_matches,
		"address_matches": address_matches
	}

@frappe.whitelist()
def recalculate_order_fraud(order: str):
	"""Manually recalculates the fraud score for a sales order."""
	import json
	from shop.integrations.fraud import evaluate_risk
	
	so = frappe.get_doc("Sales Order", order)
	if not so:
		frappe.throw("Sales Order not found")
		
	# Reconstruct customer and address dicts
	customer = {
		"email": so.contact_email,
		"phone": so.contact_mobile,
		"full_name": so.customer_name
	}
	
	address = {}
	if so.shipping_address_name:
		addr_doc = frappe.get_doc("Address", so.shipping_address_name)
		address = {
			"address_line1": addr_doc.address_line1,
			"address_line2": addr_doc.address_line2,
			"city": addr_doc.city,
			"state": addr_doc.state,
			"country": addr_doc.country,
			"pincode": addr_doc.pincode,
			"landmark": addr_doc.custom_landmark,
			"alt_phone": addr_doc.custom_alt_phone,
		}
		
	payment_method = "cod"
	
	# Evaluate
	fraud_res = evaluate_risk(
		customer, 
		address, 
		payment_method, 
		so.custom_device_fingerprint or "", 
		""
	)
	
	# Update SO
	frappe.db.set_value("Sales Order", so.name, {
		"custom_fraud_score": fraud_res.score,
		"custom_fraud_verdict": fraud_res.verdict,
		"custom_fraud_signals": json.dumps(fraud_res.signals)
	})
	
	return {"status": "success"}

@frappe.whitelist()
def get_related_orders(order: str):
	"""Finds related orders based on fingerprint, email, phone, and address."""
	so = frappe.db.get_value("Sales Order", order, 
		["customer", "contact_email", "contact_mobile", "shipping_address_name", "custom_device_fingerprint"], 
		as_dict=True)
	if not so:
		return {}

	matches = {}
	
	def add_matches(field, val, label):
		if not val: return
		rows = frappe.db.sql(f"""
			SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
			FROM `tabSales Order`
			WHERE {field} = %s AND name != %s
			ORDER BY creation DESC LIMIT 5
		""", (val, order), as_dict=True)
		for r in rows:
			if r.name not in matches:
				matches[r.name] = r
				matches[r.name]["match_reasons"] = [label]
			else:
				matches[r.name]["match_reasons"].append(label)

	add_matches("custom_device_fingerprint", so.custom_device_fingerprint, "Device Fingerprint")
	add_matches("contact_email", so.contact_email, "Email")
	
	if so.contact_mobile:
		from shop.integrations.fraud import normalize_phone
		norm = normalize_phone(so.contact_mobile)
		if norm:
			rows = frappe.db.sql("""
				SELECT name, customer, custom_fraud_score, custom_fraud_verdict, creation
				FROM `tabSales Order`
				WHERE REPLACE(REPLACE(REPLACE(REPLACE(contact_mobile, ' ', ''), '-', ''), '+', ''), '(', '') LIKE %s
				AND name != %s
				ORDER BY creation DESC LIMIT 5
			""", (f"%{norm}", order), as_dict=True)
			for r in rows:
				if r.name not in matches:
					matches[r.name] = r
					matches[r.name]["match_reasons"] = ["Phone"]
				else:
					if "Phone" not in matches[r.name]["match_reasons"]:
						matches[r.name]["match_reasons"].append("Phone")

	add_matches("shipping_address_name", so.shipping_address_name, "Address")

	return {
		"fingerprint": so.custom_device_fingerprint,
		"related": sorted(matches.values(), key=lambda x: x.creation, reverse=True)
	}
