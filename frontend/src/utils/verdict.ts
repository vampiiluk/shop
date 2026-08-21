// Single source of truth for verdict colors across every page.
// frappe-ui Badge supports: gray | blue | green | amber | red | violet
// ('yellow' does NOT exist; 'orange' aliases to 'amber')
//
// Severity ladder:  Pass < Flag < Advance Required < Block
export type VerdictTheme = 'green' | 'amber' | 'violet' | 'red' | 'gray'

export function verdictTheme(verdict?: string | null): VerdictTheme {
	switch (verdict) {
		case 'Pass':
			return 'green'
		case 'Flag':
			return 'amber'
		case 'Advance Required':
			return 'violet'
		case 'Block':
			return 'red'
		default:
			return 'gray'
	}
}

export function verdictTextClass(verdict?: string | null): string {
	return {
		green: 'text-green-600',
		amber: 'text-amber-600',
		violet: 'text-violet-600',
		red: 'text-red-600',
		gray: 'text-ink-gray-6',
	}[verdictTheme(verdict)]
}

export function verdictBarClass(verdict?: string | null): string {
	return {
		green: 'bg-green-500',
		amber: 'bg-amber-500',
		violet: 'bg-violet-500',
		red: 'bg-red-500',
		gray: 'bg-surface-gray-4',
	}[verdictTheme(verdict)]
}
