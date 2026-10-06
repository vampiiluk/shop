<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<!-- The number, its band, and where it sits on the scale. -->
		<div class="flex flex-wrap items-end justify-between gap-3">
			<div class="flex items-baseline gap-2">
				<span class="text-3xl font-bold leading-none" :class="themeText">{{ score }}</span>
				<span class="text-sm text-ink-gray-4">/ {{ max }}</span>
				<span
					class="ml-1 rounded-full px-2 py-0.5 text-xs font-medium"
					:class="themeChip"
				>{{ band.name }}</span>
			</div>
			<div class="text-right text-xs text-ink-gray-5">
				<div>
					Adds up to <span class="font-medium text-ink-gray-7">{{ Math.min(score, contributionCap) }}</span> of
					any order's fraud score
				</div>
				<div v-if="atCap" class="text-ink-gray-4">
					at the {{ contributionCap }}-point cap &mdash; anything past it changes nothing
				</div>
			</div>
		</div>

		<!-- The scale. The track is a shade darker past the cap so the inert part of
		     the range is visibly inert rather than reading as more risk still to
		     come, and the cap itself is marked.

		     bg-surface-gray-6, not bg-ink-gray-6/50. Two things about this
		     palette: it defines no bg-ink-* utilities at all (ink-gray is
		     text-only, greys for backgrounds are surface-gray-*), and its tokens
		     are bare oklch() values with no alpha placeholder, so Tailwind
		     cannot synthesise an opacity variant from them either way. Both
		     spellings compile to nothing and leave the element transparent,
		     which is why the cap line was invisible on the first pass - it was
		     never too faint, it was absent. -->
		<div class="relative mt-3">
			<!-- Layered rather than laid out in flow. As flex siblings the shaded
			     region came first and pushed the fill after itself, so an 8-out-of-80
			     score drew its bar at the right-hand end of the track. Each layer is
			     anchored to the left, or to the cap, and cannot displace the others
			     whatever the score is. -->
			<div class="h-2 overflow-hidden rounded-full bg-surface-gray-3">
				<div
					class="absolute inset-y-0 left-0 transition-all"
					:class="themeBar"
					:style="{ width: `${(Math.min(score, max) / max) * 100}%` }"
				/>
				<div
					class="absolute inset-y-0 right-0"
					:class="Math.min(score, max) < contributionCap ? 'bg-surface-gray-4' : ''"
					:style="{ left: `${(contributionCap / max) * 100}%` }"
				/>
			</div>
			<div
				class="absolute -top-0.5 bottom-[-2px] w-0.5 bg-surface-gray-6"
				:style="{ left: `calc(${((contributionCap / max) * 100).toFixed(2)}% - 1px)` }"
				:title="`${contributionCap}-point cap: past here the address no longer affects the order`"
			/>
		</div>

		<!-- Where the points went. Each bar is proportional to the largest single
		     contribution, so the biggest reason is always full width and the rest
		     are readable against it. -->
		<div v-if="rows.length" class="mt-5">
			<h3 class="text-sm font-medium text-ink-gray-7">Where the points came from</h3>
			<div class="mt-2 space-y-1.5">
				<div v-for="row in rows" :key="row.key" class="flex items-center gap-3">
					<span class="w-64 shrink-0 truncate text-xs text-ink-gray-6" :title="row.label">
						{{ row.label }}
					</span>
					<span class="min-w-0 flex-1">
						<span class="block h-1.5 overflow-hidden rounded-full bg-surface-gray-3">
							<span
								class="block h-full rounded-full"
								:class="row.points < 0 ? 'bg-green-500' : 'bg-amber-400'"
								:style="{ width: `${row.width}%` }"
							/>
						</span>
					</span>
					<span
						class="w-10 shrink-0 text-right text-xs font-medium tabular-nums"
						:class="row.points < 0 ? 'text-green-600' : 'text-ink-gray-7'"
					>{{ row.points > 0 ? `+${row.points}` : row.points }}</span>
				</div>
			</div>

			<p v-if="capped" class="mt-3 text-xs text-amber-700">
				These add up to {{ rawScore }}, above the {{ max }}-point ceiling, so the score shown
				is {{ score }}. Nothing is lost by being over &mdash; the order was already at the cap.
			</p>
		</div>

		<div v-else class="mt-3 text-sm text-ink-gray-5">
			No signal cost any points on this address.
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
	ADDRESS_CONTRIBUTION_CAP,
	ADDRESS_SCORE_MAX,
	addressBand,
	signalLabel,
} from '@/utils/riskSignals'

const props = withDefaults(
	defineProps<{
		score?: number | null
		breakdown?: { raw_score?: number; capped?: boolean; contributions?: { key: string; points: number }[] } | null
	}>(),
	{ score: 0, breakdown: null }
)

const max = ADDRESS_SCORE_MAX
const contributionCap = ADDRESS_CONTRIBUTION_CAP
const score = computed(() => Number(props.score) || 0)
const band = computed(() => addressBand(score.value))
const atCap = computed(() => score.value >= contributionCap)

const rawScore = computed(() => props.breakdown?.raw_score ?? score.value)
const capped = computed(() => !!props.breakdown?.capped)

// Bars are drawn relative to the largest contribution rather than to the score,
// so a 3-point signal is not an invisible sliver next to a 30-point one.
const rows = computed(() => {
	const list = (props.breakdown?.contributions || []).map((c) => ({
		key: c.key,
		label: signalLabel(c.key),
		points: Number(c.points) || 0,
	}))
	const peak = Math.max(...list.map((r) => Math.abs(r.points)), 1)
	return list.map((r) => ({ ...r, width: (Math.abs(r.points) / peak) * 100 }))
})

const themeText = computed(() =>
	({ green: 'text-ink-gray-9', amber: 'text-amber-600', orange: 'text-amber-700', red: 'text-red-600' })[band.value.theme]
)
const themeChip = computed(() =>
	({
		green: 'bg-green-50 text-green-700',
		amber: 'bg-amber-50 text-amber-700',
		orange: 'bg-amber-50 text-amber-700',
		red: 'bg-red-50 text-red-700',
	})[band.value.theme]
)
const themeBar = computed(() =>
	({
		green: 'bg-green-500',
		amber: 'bg-amber-400',
		orange: 'bg-amber-500',
		red: 'bg-red-500',
	})[band.value.theme]
)
</script>