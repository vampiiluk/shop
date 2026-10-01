import vue from '@vitejs/plugin-vue'
import frappeui from 'frappe-ui/vite'
import path from 'path'
import { defineConfig } from 'vite'

export default defineConfig({
	plugins: [
		frappeui({
			frappeProxy: true,
			jinjaBootData: true,
			lucideIcons: true,
			buildConfig: {
				indexHtmlPath: '../shop/www/shop.html',
				outDir: '../shop/public/frontend',
				target: 'es2015',
			},
		}),
		vue(),
	],
	build: {
		target: 'es2015',
		// Keep the previous build's hashed files.
		//
		// Frappe serves everything under /assets with `max-age=31536000,
		// immutable`, which includes this app's index.html. A desk that loaded
		// yesterday therefore holds a year-long cached copy of index.html, and
		// that file names the entry chunk and, through it, the lazily imported
		// page chunks by hash. The entry chunk often comes out byte-identical
		// between builds - only its imports change - so its hash does not move
		// and the cached copy is never revalidated. Emptying the output
		// directory then deletes the chunks that cached page is still asking
		// for, and the product editor fails to load at all.
		//
		// Leaving the old files in place costs a few MB of disk and means a
		// browser that has not hard-refreshed keeps working against the bundle
		// it was actually served.
		emptyOutDir: false,
	},
	resolve: {
		alias: {
			'@': path.resolve(__dirname, 'src'),
		},
	},
	server: {
		allowedHosts: true,
	},
	optimizeDeps: {
		include: ['frappe-ui > feather-icons', 'engine.io-client', 'socket.io-client'],
		esbuildOptions: {
			plugins: [
				{
					name: 'stub-lucide-icons-in-dep-scan',
					setup(build) {
						build.onResolve({ filter: /^~icons\/lucide\// }, ({ path }) => ({
							path,
							namespace: 'stub-lucide-icon',
						}))
						build.onLoad({ filter: /.*/, namespace: 'stub-lucide-icon' }, () => ({
							contents: 'export default {}',
						}))
					},
				},
			],
		},
	},
})
