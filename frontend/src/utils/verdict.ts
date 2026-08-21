// Single source of truth for verdict colors across every page.
// Severity ladder: Pass < Flag < Advance Required < Block
export type VerdictTheme = 'green' | 'yellow' | 'orange' | 'red' | 'gray'

export function verdictTheme(verdict?: string | null): VerdictTheme {
	switch (verdict) {
		case 'Pass':
			return 'green'
		case 'Flag':
			return 'yellow'
		case 'Advance Required':
			return 'orange'
		case 'Block':
			return 'red'
		default:
			return 'gray'
	}
}

export function verdictTextClass(verdict?: string | null): string {
	return {
		green: 'text-green-600',
		yellow: 'text-yellow-600',
		orange: 'text-orange-600',
		red: 'text-red-600',
		gray: 'text-ink-gray-6',
	}[verdictTheme(verdict)]
}

export function verdictBarClass(verdict?: string | null): string {
	return {
		green: 'bg-green-500',
		yellow: 'bg-yellow-500',
		orange: 'bg-orange-500',
		red: 'bg-red-500',
		gray: 'bg-surface-gray-4',
	}[verdictTheme(verdict)]
}
