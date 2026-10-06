<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<div class="flex flex-wrap items-baseline justify-between gap-2">
			<h2 class="text-base font-medium text-ink-gray-8">Where the providers pointed</h2>
			<div v-if="farApart" class="flex items-center gap-1.5 rounded-full bg-red-50 px-2.5 py-1 text-xs font-medium text-red-700">
				<span class="lucide-triangle-alert size-3.5" />
				{{ formatKm(distanceKm) }} apart — not the same place
			</div>
			<div v-else-if="distanceKm != null" class="text-xs text-ink-gray-5">
				{{ formatKm(distanceKm) }} apart
			</div>
		</div>

		<!-- Nothing believed to draw. Say which provider is missing and why,
			rather than leaving an empty box or silently showing one pin. -->
		<div v-if="!orsPin && !gmsPins.length" class="mt-3 text-sm text-ink-gray-5">
			<p v-if="orsRejected" class="text-ink-gray-6">
				No location is available, so nothing is plotted.
				<template v-if="rejectionLabel">{{ rejectionLabel }}</template>
			</p>
			<p v-else-if="!gmsEnabled">Google Maps lookups are switched off, and the geocoder returned nothing usable.</p>
			<p v-else>Neither provider returned a location for this address.</p>
		</div>

		<!-- One provider only. The honest version of a one-pin map. -->
		<div v-else-if="!orsPin || !gmsPins.length" class="mt-3">
			<div ref="singleEl" class="h-96 w-full overflow-hidden rounded-md border border-outline-gray-2" />
			<p class="mt-2 text-xs text-ink-gray-5">
				<template v-if="orsPin && !gmsPins.length">
					Only OpenRouteService returned a location, so there is nothing to compare it against.
					{{ gmsEnabled ? 'Google Maps found no matching place.' : 'Google Maps lookups are switched off.' }}
				</template>
				<template v-else>
					Only Google Maps returned a location — the one pin above is the whole of what is known.
				</template>
			</p>
			<!-- Named, because this is the case the page was opened for. The label
				the geocoder gave for a result we discarded is the most telling line on
				it, and it was only in the ORS table further up. -->
			<p v-if="!orsPin && orsRejected && rejectionLabel" class="mt-1 text-xs text-amber-700">
				{{ rejectionLabel }} Nothing was plotted for it.
			</p>
			<p v-else-if="!orsPin" class="mt-1 text-xs text-ink-gray-4">The geocoder returned no match, so there is nothing to compare it against.</p>
		</div>

		<!-- Both present but far apart: one map each. A single map framed to fit
			both would be a view of the whole planet, which tells you they differ
			and nothing about either of them. -->
		<div v-else-if="farApart" class="mt-3 grid gap-3 sm:grid-cols-2">
			<div>
				<div class="mb-1 flex items-center gap-1.5 text-xs text-ink-gray-6">
					<span class="size-2 rounded-full" :style="{ background: ORS_COLOR }" />
					OpenRouteService says
				</div>
				<div ref="orsEl" class="h-56 w-full overflow-hidden rounded-md border border-outline-gray-2" />
				<div class="mt-1 truncate text-xs text-ink-gray-5" :title="orsPin.label">{{ orsPin.label || orsPin.lat + ', ' + orsPin.lng }}</div>
			</div>
			<div>
				<div class="mb-1 flex items-center gap-1.5 text-xs text-ink-gray-6">
					<span class="size-2 rounded-full" :style="{ background: GMS_COLOR }" />
					Google Maps says
				</div>
				<div ref="gmsEl" class="h-56 w-full overflow-hidden rounded-md border border-outline-gray-2" />
				<div class="mt-1 truncate text-xs text-ink-gray-5" :title="gmsPins[0].label">{{ gmsPins[0].label }}</div>
			</div>
		</div>

		<!-- Both present and close: one map, both pins, and the line between
			them. This is the case worth seeing as a picture — the gap is the
			whole finding, and here it is a line you can see rather than a number. -->
		<div v-else class="mt-3">
			<div ref="combinedEl" class="h-96 w-full overflow-hidden rounded-md border border-outline-gray-2" />
			<div class="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
				<span class="flex items-center gap-1.5 text-ink-gray-6">
					<span class="size-2 rounded-full" :style="{ background: ORS_COLOR }" /> OpenRouteService
				</span>
				<span class="flex items-center gap-1.5 text-ink-gray-6">
					<span class="size-2 rounded-full" :style="{ background: GMS_COLOR }" /> Google Maps
				</span>
				<span v-if="tilesFailed" class="text-amber-600">Map tiles did not load — the pins and distance are still accurate.</span>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps<{
	orsLat?: number | null
	orsLng?: number | null
	orsLabel?: string
	orsRejected?: boolean
	rejectionLabel?: string
	gmsEnabled?: boolean
	gmsPins?: { lat: number; lng: number; label?: string }[]
}>()

const ORS_COLOR = '#2563eb'
const GMS_COLOR = '#059669'

// Past this the two pins are in different towns, and a single map framed to
// fit both becomes a view of a continent that answers none of the questions
// you opened the page with.
const FAR_KM = 25

const singleEl = ref<HTMLElement | null>(null)
const combinedEl = ref<HTMLElement | null>(null)
const orsEl = ref<HTMLElement | null>(null)
const gmsEl = ref<HTMLElement | null>(null)
const tilesFailed = ref(false)

const maps: L.Map[] = []

function valid(lat: any, lng: any): boolean {
	return (
		lat !== null && lat !== undefined && lng !== null && lng !== undefined
		&& Number.isFinite(Number(lat)) && Number.isFinite(Number(lng))
		&& Math.abs(Number(lat)) <= 90 && Math.abs(Number(lng)) <= 180
	)
}

// A rejected geocode is deliberately not plotted, even though its coordinates
// are still in the stored JSON. The map is a picture of where we believe the
// customer is; a pin we discarded would turn a known-bad answer into the most
// glanceable thing on the page.
const orsPin = computed(() =>
	valid(props.orsLat, props.orsLng)
		? { lat: Number(props.orsLat), lng: Number(props.orsLng), label: props.orsLabel || '' }
		: null
)

const gmsPins = computed(() =>
	(props.gmsPins || [])
		.filter((p) => valid(p.lat, p.lng))
		.map((p) => ({ lat: Number(p.lat), lng: Number(p.lng), label: [p.label, `${p.lat}, ${p.lng}`].filter(Boolean).join(' — ') }))
)

const orsRejected = computed(() => !!props.orsRejected && !orsPin.value)

const distanceKm = computed<number | null>(() => {
	if (!orsPin.value || !gmsPins.value.length) return null
	return haversine(orsPin.value, gmsPins.value[0])
})

const farApart = computed(() => distanceKm.value != null && distanceKm.value >= FAR_KM)

function haversine(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
	const R = 6371
	const toRad = (d: number) => (d * Math.PI) / 180
	const dLat = toRad(b.lat - a.lat)
	const dLng = toRad(b.lng - a.lng)
	const s =
		Math.sin(dLat / 2) ** 2
		+ Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2
	return 2 * R * Math.asin(Math.min(1, Math.sqrt(s)))
}

function formatKm(km: number | null): string {
	if (km == null) return '—'
	if (km < 1) return `${Math.round(km * 1000)} m`
	if (km < 10) return `${km.toFixed(1)} km`
	return `${Math.round(km).toLocaleString()} km`
}

// A divIcon rather than Leaflet's default marker: the default resolves its PNGs
// relative to the stylesheet and silently renders nothing under a hashed asset
// bundle. This also lets each provider carry its own colour.
function pin(color: string, letter: string) {
	return L.divIcon({
		className: '',
		html: `<div style="width:18px;height:18px;border-radius:9999px;background:${color};border:2.5px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.4)"></div>`,
		iconSize: [18, 18],
		iconAnchor: [9, 9],
	})
}

function baseMap(el: HTMLElement, opts: { scrollWheelZoom?: boolean } = {}): L.Map {
	const m = L.map(el, {
		zoomControl: false,
		attributionControl: false,
		scrollWheelZoom: opts.scrollWheelZoom ?? false,
	})
	L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
		maxZoom: 19,
		attribution: '&copy; OpenStreetMap contributors',
	}).on('tileerror', () => { tilesFailed.value = true }).addTo(m)
	L.control.attribution({ prefix: false, position: 'bottomright' }).addTo(m)
	L.control.zoom({ position: 'topright' }).addTo(m)
	// Click to enable wheel zoom. A map that eats page scroll is worse than
	// one you have to click first.
	m.on('click', () => m.scrollWheelZoom.enable())
	m.on('mouseout', () => m.scrollWheelZoom.disable())
	maps.push(m)
	return m
}

function render() {
	maps.splice(0).forEach((m) => m.remove())
	tilesFailed.value = false

	if (farApart.value && orsEl.value && gmsEl.value) {
		const a = baseMap(orsEl.value)
		L.marker([orsPin.value!.lat, orsPin.value!.lng], { icon: pin(ORS_COLOR, 'O') })
			.addTo(a).bindPopup(orsPin.value!.label || 'OpenRouteService geocode')
		a.setView([orsPin.value!.lat, orsPin.value!.lng], 15)

		const b = baseMap(gmsEl.value)
		gmsPins.value.forEach((p) => {
			L.marker([p.lat, p.lng], { icon: pin(GMS_COLOR, 'G') }).addTo(b).bindPopup(p.label)
		})
		b.setView([gmsPins.value[0].lat, gmsPins.value[0].lng], 15)
		return
	}

	if ((!orsPin.value || !gmsPins.value.length) && singleEl.value) {
		const m = baseMap(singleEl.value)
		const pins = orsPin.value ? [orsPin.value] : gmsPins.value
		pins.forEach((p) => {
			L.marker([p.lat, p.lng], { icon: pin(orsPin.value ? ORS_COLOR : GMS_COLOR, 'x') })
				.addTo(m).bindPopup(p.label || `${p.lat}, ${p.lng}`)
		})
		m.setView([pins[0].lat, pins[0].lng], 15)
		return
	}

	if (combinedEl.value && orsPin.value && gmsPins.value.length) {
		const m = baseMap(combinedEl.value)
		gmsPins.value.forEach((p) => {
			L.marker([p.lat, p.lng], { icon: pin(GMS_COLOR, 'G') }).addTo(m).bindPopup(p.label)
		})
		L.marker([orsPin.value.lat, orsPin.value.lng], { icon: pin(ORS_COLOR, 'O') })
			.addTo(m).bindPopup(orsPin.value.label || 'OpenRouteService geocode')

		const line = L.polyline(
			[[orsPin.value.lat, orsPin.value.lng], [gmsPins.value[0].lat, gmsPins.value[0].lng]],
			{ color: ORS_COLOR, weight: 2, opacity: 0.65, dashArray: '5 5' }
		).addTo(m)
		line.bindTooltip(formatKm(distanceKm.value), { sticky: true })

		const bounds = L.latLngBounds([[orsPin.value.lat, orsPin.value.lng], [gmsPins.value[0].lat, gmsPins.value[0].lng]])
		// pad() so neither pin sits under the zoom control or the attribution
		m.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 })
	}
}

onMounted(render)
watch([orsPin, gmsPins, farApart], render, { deep: true })
onBeforeUnmount(() => maps.splice(0).forEach((m) => m.remove()))
</script>