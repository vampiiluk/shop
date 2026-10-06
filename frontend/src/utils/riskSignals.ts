/**
 * One label per signal the address scorer can emit.
 *
 * Shared by the score meter and the signal table on the verification report so
 * the two cannot drift into calling the same signal different things. The
 * scorer adds a key here for every weight it charges, and a key that reaches
 * the UI unlabelled is a signal the page is silently not showing, which is the
 * exact failure this page already had.
 */
export const SIGNAL_LABELS: Record<string, string> = {
	// What the customer typed
	address_short_line1: 'Address line too short',
	address_no_house_number: 'No house number in the address line',
	address_bad_pincode: 'Pincode is not 5 digits',
	address_unknown_city: 'City not in the delivery list',
	missing_landmark: 'No landmark given',
	address_prior_failures: 'Previous deliveries failed here',
	user_country_mismatch: 'Country does not match the shop',
	province_mismatch: 'Province does not match the city',

	// The geocoder
	geo_not_found: 'Geocoder found nothing',
	geo_wrong_country: 'Geocode resolved to another country',
	geo_city_mismatch: 'Geocode resolved to another city',
	geo_no_house_number: 'Geocode has no house number',
	geo_fallback_vague: 'Geocode was a vague fallback',
	geo_exact_match_bonus: 'Exact geocode match (reduces risk)',
	geo_provider_failed: 'Geocoder could not answer',
	geo_unavailable: 'Geocoder unavailable',

	// Google Maps
	gms_no_results: 'Maps found no matching place',
	gms_coords_mismatch_ors: 'Maps and geocoder disagree on the location',
	gms_results_bonus: 'Maps found the place (reduces risk)',
	gms_residential_area: 'Maps found no business here',
	landmark_gms_miss: 'Landmark not found on Maps',
	landmark_gms_hit_bonus: 'Landmark confirmed on Maps (reduces risk)',
}

/** The address score's own scale, and what the bands mean. */
export const ADDRESS_SCORE_MAX = 80

/**
 * Past this the address stops influencing the order.
 *
 * fraud.py folds the address into the order score with
 * `min(address_score, ADDRESS_SCORE_CAP)`, so everything above 35 changes
 * nothing about what happens to the order. The meter marks the line, because a
 * score of 70 and a score of 45 are not different verdicts and reading them as
 * if they were is how a capped number gets treated as a real one.
 */
export const ADDRESS_CONTRIBUTION_CAP = 35

export type Band = { name: string; theme: 'green' | 'amber' | 'orange' | 'red' }

/**
 * Display bands, anchored to behaviour rather than to round numbers.
 *
 * There is no threshold on the address score itself - it is a contribution to
 * the order score, not a verdict - so these are presentation only. 35 is the
 * cap and 40 is the order's review line, and the bands are cut to say something
 * useful about each side of those.
 */
export function addressBand(score: number): Band {
	if (score <= 0) return { name: 'Nothing found', theme: 'green' }
	if (score < 15) return { name: 'Low', theme: 'green' }
	if (score < ADDRESS_CONTRIBUTION_CAP) return { name: 'Medium', theme: 'amber' }
	return { name: 'High', theme: 'red' }
}

export function signalLabel(key: string): string {
	return SIGNAL_LABELS[key] || key.replace(/_/g, ' ')
}