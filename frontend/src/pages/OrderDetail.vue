<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<div v-if="doc">
			<UiPageHeader :title="doc.name" back-to="/orders" back-label="Orders">
				<template #badges>
					<UiStatusBadge :label="doc.display_status" />
					<UiStatusBadge :label="doc.payment_status" />
					<UiStatusBadge :label="doc.fulfillment_status" />
					
				</template>
				<template #actions>
					<Button @click="$router.push({ name: 'Assistant', query: { message: `Analyze fraud risk for ${doc.name}` } })">
						AI Risk Score
					</Button>
					<Button :link="`/app/sales-order/${doc.name}`">Open in Desk</Button>
					<Button v-if="canMarkAdvance" variant="solid" @click="openAdvance">
						Mark advance received
					</Button>
					<Button v-if="canMarkPaid" @click="confirmAction('markPaid')">Mark paid</Button>
					<Button v-if="canRecordOutcome" @click="showOutcome = true">Record delivery</Button>
					<Button v-if="canFulfill" variant="solid" @click="confirmAction('fulfill')">
						Fulfill
					</Button>
					<Button v-if="canCancel" theme="red" @click="confirmAction('cancel')">Cancel</Button>
				</template>
			</UiPageHeader>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<div class="space-y-6 lg:col-span-2">
					<div class="overflow-hidden rounded-lg border border-outline-gray-1">
						<table class="w-full text-base">
							<thead>
								<tr class="border-b border-outline-gray-1 text-left text-sm text-ink-gray-5">
									<th class="px-3 py-2 font-normal">Item</th>
									<th class="px-3 py-2 text-right font-normal">Qty</th>
									<th class="px-3 py-2 text-right font-normal">Rate</th>
									<th class="px-3 py-2 text-right font-normal">Amount</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="item in doc.items"
									:key="item.item_code"
									class="border-b border-outline-gray-1 last:border-b-0"
								>
									<td class="px-3 py-2 text-ink-gray-8">{{ item.item_name }}</td>
									<td class="px-3 py-2 text-right text-ink-gray-7">{{ item.qty }}</td>
									<td class="px-3 py-2 text-right text-ink-gray-7">{{ item.formatted_rate }}</td>
									<td class="px-3 py-2 text-right text-ink-gray-8">{{ item.formatted_amount }}</td>
								</tr>
							</tbody>
							<tfoot class="border-t border-outline-gray-1 text-base">
								<tr>
									<td colspan="3" class="px-3 pt-3 text-right text-ink-gray-6">Subtotal</td>
									<td class="px-3 pt-3 text-right text-ink-gray-8">{{ doc.formatted_total }}</td>
								</tr>
								<tr v-if="doc.formatted_discount">
									<td colspan="3" class="px-3 pt-1 text-right text-ink-gray-6">Discount</td>
									<td class="px-3 pt-1 text-right text-ink-gray-8">
										-{{ doc.formatted_discount }}
									</td>
								</tr>
								<tr>
									<td colspan="3" class="px-3 py-3 text-right font-medium text-ink-gray-8">
										Grand total
									</td>
									<td class="px-3 py-3 text-right font-semibold text-ink-gray-9">
										{{ doc.formatted_grand_total }}
									</td>
								</tr>
							</tfoot>
						</table>
					</div>

					<FraudOrderPanel :order="doc.name" />

					<FulfillmentPanel
						:order="doc.name"
						:docstatus="doc.docstatus"
						:collect-balance="collectBalance"
						@changed="order.reload()"
					/>

					<RelatedOrdersPanel :order="doc.name" />
				</div>

				<div class="space-y-6">
					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Customer</h2>
						<router-link
							v-if="doc.customer"
							:to="`/customers/${doc.customer}`"
							class="mt-2 block text-base text-ink-gray-8 hover:underline"
						>
							{{ doc.customer_name }}
						</router-link>
						<div v-if="doc.contact_email" class="text-base text-ink-gray-6">
							{{ doc.contact_email }}
						</div>
						<div v-if="doc.address" class="mt-2 text-p-sm text-ink-gray-6" v-html="doc.address" />
					</div>

					<FingerprintPanel :order="doc.name" />

					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Payment</h2>
						<dl class="mt-3 space-y-1.5 text-sm">
							<div class="flex justify-between gap-3">
								<dt class="text-ink-gray-5">Method</dt>
								<dd class="text-ink-gray-8">{{ paymentMethodLabel }}</dd>
							</div>
							<div v-if="doc.payment_method === 'advance'" class="flex justify-between gap-3">
								<dt class="text-ink-gray-5">Advance due</dt>
								<dd class="text-ink-gray-8">{{ doc.formatted_advance_amount }}</dd>
							</div>
							<div class="flex justify-between gap-3">
								<dt class="text-ink-gray-5">Received</dt>
								<dd class="text-ink-gray-8">{{ doc.formatted_payment_received }}</dd>
							</div>
							<div class="flex justify-between gap-3">
								<dt class="font-medium text-ink-gray-7">Outstanding</dt>
								<dd class="font-medium text-ink-gray-9">{{ doc.formatted_payment_balance }}</dd>
							</div>
						</dl>
						<p v-if="paymentHint" class="mt-2 text-p-sm text-ink-gray-5">{{ paymentHint }}</p>
					</div>

					<ReturnsPanel :order="doc.name" />

					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Timeline</h2>
						<ol class="mt-3">
							<li
								v-for="(event, index) in doc.timeline"
								:key="index"
								class="relative border-l border-outline-gray-2 pb-4 pl-4 last:border-transparent last:pb-0"
							>
								<span
									class="absolute -left-[4.5px] top-1 size-2 rounded-full bg-surface-gray-6"
								/>
								<div class="text-base text-ink-gray-8">{{ event.label }}</div>
								<div class="text-sm text-ink-gray-5">{{ formatDateTime(event.on) }}</div>
							</li>
						</ol>
					</div>
				</div>
			</div>
		</div>

		<div v-else class="flex justify-center py-20">
			<Spinner class="size-5" />
		</div>

		<Dialog v-model="showConfirm" :options="dialogOptions">
			<template #body-content>
				<p class="text-p-base text-ink-gray-7">{{ pending?.message }}</p>
			</template>
		</Dialog>

		<Dialog v-model="showAdvance" :options="advanceDialogOptions">
			<template #body-content>
				<div class="space-y-4">
					<p class="text-p-base text-ink-gray-7">
						Record the advance transferred to your account. The order ships as soon as it is
						recorded, and the courier then collects the remaining balance on delivery.
					</p>
					<FormControl v-model="advanceForm.amount" type="text" label="Amount received" />
					<FormControl
						v-model="advanceForm.mode"
						type="select"
						label="Mode of payment"
						:options="modeOptions"
					/>
					<FormControl
						v-model="advanceForm.reference"
						type="text"
						label="Transaction reference"
					/>
					<p class="text-p-sm text-ink-gray-5">
						Leave the reference blank if you have none, e.g. a bank transfer ID.
					</p>
				</div>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Dialog, FormControl, Spinner, call, createResource, toast } from 'frappe-ui'

import FulfillmentPanel from '@/components/FulfillmentPanel.vue'
import ReturnsPanel from '@/components/ReturnsPanel.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'
import FraudOrderPanel from '@/components/FraudOrderPanel.vue'
import RelatedOrdersPanel from '@/components/RelatedOrdersPanel.vue'
import FingerprintPanel from '@/components/FingerprintPanel.vue'
import { formatDateTime } from '@/utils/format'

const props = defineProps<{ name: string }>()

const order = createResource({
	url: 'shop.api.orders.get_order',
	makeParams: () => ({ name: props.name }),
	auto: true,
	onError: () => toast.error('Could not load order'),
})

const doc = computed(() => order.data)

const canMarkPaid = computed(() => doc.value.docstatus === 1 && doc.value.payment_status !== 'Paid')
const canMarkAdvance = computed(
	() =>
		doc.value.docstatus === 1 &&
		doc.value.payment_method === 'advance' &&
		doc.value.payment_balance > 0 &&
		doc.value.payment_received < doc.value.advance_amount,
)
const paymentMethodLabel = computed(() => {
	const labels: Record<string, string> = {
		cod: 'Cash on delivery',
		gateway: 'Online payment',
		advance: 'Advance payment',
	}
	return labels[doc.value.payment_method] || doc.value.payment_method
})
const collectBalance = computed(() =>
	doc.value.courier_balance > 0 ? doc.value.formatted_courier_balance : '',
)
const paymentHint = computed(() => {
	const d = doc.value
	if (d.payment_method !== 'advance' || d.payment_balance <= 0) return ''
	return d.payment_received < d.advance_amount
		? 'Record the advance as soon as it arrives — the order ships once it is received.'
		: 'The courier collects the outstanding balance from the customer on delivery.'
})
const canFulfill = computed(
	() =>
		doc.value.docstatus === 1 &&
		!['Fulfilled', 'Cancelled'].includes(doc.value.fulfillment_status),
)
const canCancel = computed(() => doc.value.docstatus !== 2)

const actions = {
	markPaid: {
		title: 'Mark as paid',
		message: `Record a payment entry for ${props.name}?`,
		buttonLabel: 'Mark paid',
		theme: 'gray',
		method: 'shop.api.orders.mark_paid',
		success: 'Order marked as paid',
		failure: 'Could not mark order as paid',
	},
	fulfill: {
		title: 'Fulfill order',
		message: `Create and submit a delivery note for ${props.name}?`,
		buttonLabel: 'Fulfill',
		theme: 'gray',
		method: 'shop.api.orders.fulfill',
		success: 'Order fulfilled',
		failure: 'Could not fulfill order',
	},
	cancel: {
		title: 'Cancel order',
		message: `This will cancel ${props.name}. This action cannot be undone.`,
		buttonLabel: 'Cancel order',
		theme: 'red',
		method: 'shop.api.orders.cancel_order',
		success: 'Order cancelled',
		failure: 'Could not cancel order',
	},
} as const

type ActionKey = keyof typeof actions

const showConfirm = ref(false)
const pending = ref<(typeof actions)[ActionKey] | null>(null)

function confirmAction(key: ActionKey) {
	pending.value = actions[key]
	showConfirm.value = true
}

const dialogOptions = computed(() => ({
	title: pending.value?.title,
	actions: [
		{
			label: pending.value?.buttonLabel,
			theme: pending.value?.theme,
			variant: 'solid',
			onClick: runPending,
		},
	],
}))

async function runPending() {
	if (!pending.value) return
	try {
		await call(pending.value.method, { name: props.name })
		toast.success(pending.value.success)
		order.reload()
	} catch (error) {
		toast.error(pending.value.failure)
	} finally {
		showConfirm.value = false
	}
}

const showAdvance = ref(false)
const advanceForm = ref({ amount: '', mode: '', reference: '' })
const modes = createResource({ url: 'shop.api.orders.payment_modes', auto: true })
const modeOptions = computed(() => [
	{ label: 'Not specified', value: '' },
	...((modes.data as string[]) || []).map((mode) => ({ label: mode, value: mode })),
])
const advanceDialogOptions = computed(() => ({
	title: 'Mark advance received',
	actions: [
		{
			label: 'Record advance',
			theme: 'blue',
			variant: 'solid',
			onClick: submitAdvance,
		},
	],
}))

function openAdvance() {
	const remaining = Number(
		(doc.value.advance_amount - doc.value.payment_received).toFixed(2),
	)
	advanceForm.value = { amount: String(remaining > 0 ? remaining : ''), mode: '', reference: '' }
	showAdvance.value = true
}

async function submitAdvance() {
	const amount = parseFloat(String(advanceForm.value.amount).replace(/,/g, ''))
	if (!amount || Number.isNaN(amount)) {
		toast.error('Enter a valid amount')
		return
	}
	try {
		await call('shop.api.orders.mark_advance_received', {
			name: props.name,
			amount,
			mode_of_payment: advanceForm.value.mode || undefined,
			reference_no: advanceForm.value.reference || undefined,
		})
		toast.success('Advance received — order ships now')
		showAdvance.value = false
		order.reload()
	} catch (error) {
		toast.error('Could not record the advance')
	}
}
</script>
