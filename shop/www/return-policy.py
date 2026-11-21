"""Public return and replacement policy.

Merchant Center asks for a URL where the return policy can be read, and the
feed states a 14-day window on every offer. This page is the policy that
window refers to, so it has to describe what the shop actually does: returns
open when an order ships, the shop arranges the pickup, and the customer is
not charged for return shipping.
"""

no_cache = 1


def get_context(context):
	context.title = "Return & Replacement Policy"
	context.meta_description = (
		"How returns and replacements work at reloop: 14 days from shipping, "
		"return shipping paid by the customer, and a refund or replacement once "
		"the item is received."
	)
	context.canonical = "https://reloop.pk/return-policy/"
	return context
