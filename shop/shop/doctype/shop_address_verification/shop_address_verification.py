from frappe.model.document import Document


class ShopAddressVerification(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		address_hash: DF.Data | None
		address_line1: DF.SmallText | None
		address_risk_json: DF.Code | None
		address_risk_score: DF.Int
		address_risk_status: DF.Literal["Pending", "Complete", "Failed", "Skipped"]
		city: DF.Data | None
		country: DF.Data | None
		gms_result_count: DF.Int
		gms_result_json: DF.Code | None
		gms_result_text: DF.SmallText | None
		gms_status: DF.Literal["Pending", "Complete", "Failed", "Skipped", "Disabled"]
		landmark: DF.Data | None
		last_verified_on: DF.Datetime | None
		latitude: DF.Float
		linked_fingerprints: DF.SmallText | None
		linked_orders: DF.SmallText | None
		linked_phones: DF.SmallText | None
		longitude: DF.Float
		ors_confidence: DF.Float
		ors_match_type: DF.Data | None
		ors_result_json: DF.Code | None
		ors_status: DF.Literal["Pending", "Complete", "Failed", "Skipped"]
		pincode: DF.Data | None
		source: DF.Literal["Order Placement", "Manual", "Bulk Import"]
		status: DF.Literal["Pending", "Complete", "Partial", "Failed"]
	# end: auto-generated types

	pass
