"""PII censoring for data sent to external AI services.

Replaces names, emails, and phone numbers with deterministic hash-based tokens
so the same person always maps to the same token, preventing correlation across
calls without exposing identity.
"""

import hashlib
import re


def _tokenize(value: str, prefix: str = "") -> str:
	"""Deterministic short hash token from a string."""
	h = hashlib.sha256(value.lower().strip().encode()).hexdigest()[:8]
	return f"{prefix}{h}"


def censor_email(email: str | None) -> str:
	if not email:
		return ""
	user, _, domain = email.partition("@")
	if not domain:
		return _tokenize(email, "cust_")
	return f"{_tokenize(user, 'cust_')}@{domain}"


def censor_phone(phone: str | None) -> str:
	if not phone:
		return ""
	digits = re.sub(r"\D", "", phone)
	if len(digits) <= 4:
		return "+XXX****"
	last4 = digits[-4:] if len(digits) >= 4 else digits
	return f"+XXX****{last4}"


def censor_name(name: str | None) -> str:
	if not name:
		return "Customer"
	return f"Customer {_tokenize(name, '').upper()[:4]}"


def censor_pii(data: dict) -> dict:
	"""Return a shallow copy of *data* with PII fields censored.

	Fields that are kept intact (fraud-relevant):
	  - IP, fingerprint, address, city, country, province, landmark
	  - Score signals, velocity, device info, amounts, timestamps

	Fields that are censored:
	  - customer_name, contact_email, phone, email
	"""
	result = dict(data)

	if "customer_name" in result:
		result["customer_name"] = censor_name(result["customer_name"])
	if "contact_email" in result:
		result["contact_email"] = censor_email(result["contact_email"])
	if "email" in result:
		result["email"] = censor_email(result["email"])
	if "phone" in result:
		result["phone"] = censor_phone(result["phone"])

	return result


def censor_order_for_ai(order_data: dict, signals: dict | None = None) -> dict:
	"""Build a PII-safe order summary dict for Gemini analysis.

	Includes order details, items, full address (for Maps verification), and
	fraud signals — but censors all personally identifiable fields.
	"""
	censored = censor_pii(order_data)

	summary = {
		"order_id": censored.get("name"),
		"customer": censored.get("customer_name"),
		"amount": censored.get("grand_total"),
		"currency": censored.get("currency"),
		"payment_method": censored.get("payment_method"),
		"payment_status": censored.get("payment_status"),
		"items": censored.get("items", []),
		"delivery_address": " ".join(filter(None, [
			censored.get("line1"),
			censored.get("line2"),
			censored.get("city"),
			censored.get("province"),
			censored.get("pincode"),
			censored.get("country"),
		])),
		"landmark": censored.get("landmark"),
	}

	if censored.get("_pre_check_issues"):
		summary["pre_check_issues"] = censored["_pre_check_issues"]

	if signals:
		summary["fraud_signals"] = signals

	return summary


def censor_customer_for_ai(customer_data: dict) -> dict:
	"""Build a PII-safe customer summary for Gemini analysis."""
	censored = censor_pii(customer_data)

	return {
		"customer": censored.get("customer_name"),
		"email": censored.get("email"),
		"lifetime_spend": censored.get("total_spent"),
		"order_count": censored.get("order_count"),
		"addresses": censored.get("addresses", []),
	}
