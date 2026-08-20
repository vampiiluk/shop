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
