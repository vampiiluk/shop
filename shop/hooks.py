app_name = "shop"
app_title = "Shop"
app_publisher = "Frappe"
app_description = "B2C e-commerce storefront powered by Frappe Builder and ERPNext"
app_email = "suraj@frappe.io"
app_license = "mit"

use_json_request_body = True

required_apps = ["erpnext", "payments", "builder"]

add_to_apps_screen = [
	{
		"name": "shop",
		"logo": "/assets/shop/frontend/shop-logo.svg",
		"title": "Shop",
		"route": "/shop",
		"has_permission": "shop.api.admin.check_app_permission",
	}
]

website_route_rules = [
	{"from_route": "/shop/<path:app_path>", "to_route": "shop"},
]

override_doctype_class = {
	"Payment Request": "shop.overrides.payment_request.ShopPaymentRequest",
}

doc_events = {
	"POS Coupon": {
		"validate": "shop.integrations.pos_coupon_sync.sync_pos_coupon_to_erpnext",
		"on_update": "shop.integrations.pos_coupon_sync.write_pos_coupon_links",
		"on_trash": "shop.integrations.pos_coupon_sync.delete_pos_coupon_from_erpnext",
	},
}

custom_fields = {
	"Coupon Code": [
		{
			"fieldname": "custom_sync_to_pos",
			"label": "Sync to POS",
			"fieldtype": "Check",
			"default": "1",
			"insert_after": "pricing_rule",
			"description": "Mirror this coupon to POS Coupons so the same code can be used in POS Next.",
		}
	],
	"Sales Order": [
		{
			"fieldname": "custom_device_fingerprint",
			"label": "Device Fingerprint",
			"fieldtype": "Data",
			"hidden": 1,
			"read_only": 1,
			"description": "FingerprintJS visitor ID captured at checkout (fraud signal).",
		},
		{
			"fieldname": "custom_fp_request_id",
			"label": "Fingerprint Request ID",
			"fieldtype": "Data",
			"hidden": 1,
			"read_only": 1,
			"description": "Fingerprint Identification request ID for server-side verification.",
		},
		{
			"fieldname": "custom_fraud_score",
			"label": "Fraud Score",
			"fieldtype": "Int",
			"hidden": 1,
			"read_only": 1,
		},
		{
			"fieldname": "custom_fraud_signals",
			"label": "Fraud Signals",
			"fieldtype": "Code",
			"hidden": 1,
			"read_only": 1,
		},
		{
			"fieldname": "custom_fraud_verdict",
			"label": "Fraud Verdict",
			"fieldtype": "Select",
			"hidden": 1,
			"read_only": 1,
			"options": "\nPass\nFlag\nAdvance Required\nBlock",
		},
		{
			"fieldname": "custom_fraud_state",
			"label": "Fraud State",
			"fieldtype": "Select",
			"hidden": 1,
			"read_only": 1,
			"options": "\nProcessing\nDone",
			"description": "Processing = address verification still queued; score/verdict not final yet.",
		},
		{
			"fieldname": "custom_payment_method",
			"label": "Payment Method",
			"fieldtype": "Data",
			"hidden": 1,
			"read_only": 1,
			"description": "cod / gateway, captured at checkout for fraud re-evaluation.",
		},
		{
			"fieldname": "custom_fp_event",
			"label": "Fingerprint Event",
			"fieldtype": "Long Text",
			"hidden": 1,
			"read_only": 1,
			"description": "Raw Fingerprint Identification event captured at checkout.",
		},
		{
			"default": "Pending",
			"fieldname": "custom_delivery_outcome",
			"label": "Delivery Outcome",
			"fieldtype": "Select",
			"options": "Pending\nDelivered\nFailed\nRTO",
		},
		{
			"fieldname": "custom_ai_risk_score",
			"label": "AI Risk Score",
			"fieldtype": "Int",
			"read_only": 1,
			"description": "Gemini AI fraud risk score (0-100). Computed on demand.",
		},
		{
			"fieldname": "custom_ai_risk_reasoning",
			"label": "AI Risk Reasoning",
			"fieldtype": "Long Text",
			"hidden": 1,
			"read_only": 1,
		},
		{
			"fieldname": "custom_ai_domain_scores",
			"label": "AI Domain Scores",
			"fieldtype": "Long Text",
			"hidden": 1,
			"read_only": 1,
			"description": "JSON: per-domain sub-scores from the AI risk analysis.",
		},
		{
			"fieldname": "custom_ai_risk_analyzed_on",
			"label": "AI Analyzed On",
			"fieldtype": "Datetime",
			"read_only": 1,
		},
		{
			"fieldname": "custom_ai_risk_confidence",
			"label": "AI Confidence",
			"fieldtype": "Data",
			"read_only": 1,
			"insert_after": "custom_ai_risk_analyzed_on",
		},
		{
			"fieldname": "custom_ai_maps_results",
			"label": "AI Maps Verification",
			"fieldtype": "Small Text",
			"read_only": 1,
			"description": "Top Google Maps matches for the delivery address.",
			"insert_after": "custom_ai_risk_confidence",
		},
		{
			"fieldname": "custom_ai_maps_json",
			"label": "AI Maps JSON",
			"fieldtype": "Code",
			"options": "JSON",
			"read_only": 1,
			"description": "Structured Maps verification data.",
			"insert_after": "custom_ai_maps_results",
		},
		{
			"fieldname": "custom_ai_maps_status",
			"label": "Maps Verification Status",
			"fieldtype": "Select",
			"options": "\nPending\nComplete\nFailed\nDisabled",
			"default": "Disabled",
			"read_only": 1,
			"description": "GMS background job status: Pending=running, Complete=done, Failed=error, Disabled=not triggered.",
			"insert_after": "custom_ai_maps_json",
		},
		{
			"fieldname": "custom_address_hash",
			"label": "Address Hash",
			"fieldtype": "Data",
			"hidden": 1,
			"read_only": 1,
			"description": "MD5 hash of address fields for linking to Shop Address Verification cache.",
			"insert_after": "custom_ai_maps_status",
		},
	],
	"Customer": [
		{
			"fieldname": "custom_device_fingerprint",
			"label": "Device Fingerprint",
			"fieldtype": "Data",
			"hidden": 1,
			"read_only": 1,
			"description": "Last FingerprintJS visitor ID seen for this customer.",
		},
		{
			"default": "0",
			"fieldname": "custom_failed_deliveries",
			"label": "Failed Deliveries",
			"fieldtype": "Int",
			"hidden": 1,
			"read_only": 1,
			"description": "Running count of failed/RTO deliveries; auto-blacklists at the configured threshold.",
		},
	],
	"Address": [
		{
			"fieldname": "custom_landmark",
			"label": "Nearest Landmark",
			"fieldtype": "Data",
			"description": "Famous landmark so courier riders can find the address.",
		},
		{
			"fieldname": "custom_alt_phone",
			"label": "Alternative Phone",
			"fieldtype": "Data",
			"description": "Backup number for delivery riders if the primary is unreachable.",
		},
		{
			"fieldname": "custom_address_hash",
			"label": "Address Verification Hash",
			"fieldtype": "Data",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"allow_in_quick_entry": 0,
			"description": "Links this address to its Shop Address Verification record.",
			"insert_after": "custom_alt_phone",
		},
		{
			"fieldname": "address_verification_section",
			"label": "Address Verification",
			"fieldtype": "Section Break",
			"insert_after": "custom_address_hash",
		},
		{
			"fieldname": "custom_verification_status",
			"label": "Verification Status",
			"fieldtype": "Select",
			"options": "\nPending\nComplete\nPartial\nFailed\nSkipped",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "address_verification_section",
		},
		{
			"fieldname": "custom_address_risk_score",
			"label": "Address Risk Score",
			"fieldtype": "Int",
			"read_only": 1,
			"no_copy": 1,
			"description": "Combined ORS + GMS verification risk (lower is better).",
			"insert_after": "custom_verification_status",
		},
		{
			"fieldname": "column_break_addr_verif",
			"fieldtype": "Column Break",
			"insert_after": "custom_address_risk_score",
		},
		{
			"fieldname": "custom_ors_confidence",
			"label": "Geocode Confidence",
			"fieldtype": "Data",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "column_break_addr_verif",
		},
		{
			"fieldname": "custom_latitude",
			"label": "Latitude",
			"fieldtype": "Float",
			"precision": "6",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_ors_confidence",
		},
		{
			"fieldname": "custom_longitude",
			"label": "Longitude",
			"fieldtype": "Float",
			"precision": "6",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_latitude",
		},
		{
			"fieldname": "custom_gms_result_count",
			"label": "Maps Results",
			"fieldtype": "Int",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_longitude",
		},
		{
			"fieldname": "custom_last_verified_on",
			"label": "Last Verified On",
			"fieldtype": "Datetime",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_gms_result_count",
		},
		{
			"fieldname": "custom_address_verification",
			"label": "Verification Record",
			"fieldtype": "Link",
			"options": "Shop Address Verification",
			"read_only": 1,
			"no_copy": 1,
			"insert_after": "custom_last_verified_on",
		},
	],
	"Shop Settings": [
		{
			"fieldname": "maps_provider",
			"label": "Maps Provider",
			"fieldtype": "Select",
			"options": "\nGoogle Maps Scraper\nORS Geocoding\nNone",
			"default": "Google Maps Scraper",
			"description": "Source for address verification. Scraper uses local GMS binary.",
			"insert_after": "landmark_required",
		},
		{
			"fieldname": "gms_depth",
			"label": "GMS Search Depth",
			"fieldtype": "Int",
			"default": '5',
			"description": "How deep to search on Google Maps (higher = more results, slower).",
			"insert_after": "maps_provider",
		},
		{
			"fieldname": "gms_concurrency",
			"label": "GMS Concurrency",
			"fieldtype": "Int",
			"default": '4',
			"description": "Parallel browser tabs used by the Google Maps Scraper (1-8). Higher is faster but heavier.",
			"insert_after": "gms_depth",
		},
		{
			"fieldname": "geocode_cache_ttl",
			"label": "Cache TTL (days)",
			"fieldtype": "Int",
			"default": '30',
			"description": "How long ORS + GMS results are cached before re-verification.",
			"insert_after": "gms_concurrency",
		},
		{
			"fieldname": "queue_schedule",
			"label": "Queue Schedule",
			"fieldtype": "Select",
			"default": "Every 20 Minutes",
			"options": "Every 10 Minutes\nEvery 20 Minutes\nHourly",
			"description": "How often the scheduler drains the verification queue.",
			"insert_after": "geocode_cache_ttl",
		},
	],
}

after_install = "shop.install.after_install"
after_migrate = "shop.install.after_migrate"

doc_events = {
	"Address": {
		"on_update": "shop.integrations.verification.on_address_update",
	},
}

on_session_creation = "shop.storefront.cart.merge_guest_cart"

shop_fulfillment_providers = {
	"manual": "shop.fulfillment.providers.manual.ManualProvider",
	"amazon_mcf": "shop.fulfillment.providers.amazon.AmazonProvider",
}

shop_carrier_tracking_urls = {
	"Delhivery": "https://www.delhivery.com/track/package/{tracking_number}",
	"Bluedart": "https://www.bluedart.com/tracking/{tracking_number}",
	"DTDC": "https://www.dtdc.in/tracking/{tracking_number}",
}

scheduler_events = {
	"daily": [
		"shop.storefront.cart.cleanup_carts",
	],
	"hourly": [
		"shop.fulfillment.service.sync_open_shipments",
	],
	"cron": {
		"*/10 * * * *": [
			"shop.integrations.verification.scheduled_queue_run",
		],
		"*/20 * * * *": [
			"shop.integrations.verification.scheduled_queue_run",
		],
	},
}

before_tests = "shop.install.before_tests"

export_python_type_annotations = True
require_type_annotated_api_methods = True
