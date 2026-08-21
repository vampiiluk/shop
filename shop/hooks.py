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
	],
}

after_install = "shop.install.after_install"
after_migrate = "shop.install.after_migrate"

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
}

before_tests = "shop.install.before_tests"

export_python_type_annotations = True
require_type_annotated_api_methods = True
