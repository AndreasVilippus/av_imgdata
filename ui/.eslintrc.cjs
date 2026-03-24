module.exports = {
	root: true,
	env: {
		browser: true,
		es2021: true,
	},
	extends: [
		'eslint:recommended',
		'plugin:vue/essential',
	],
	parser: 'vue-eslint-parser',
	parserOptions: {
		ecmaVersion: 2022,
		sourceType: 'module',
	},
	globals: {
		SYNO: 'readonly',
		synocredential: 'readonly',
	},
	ignorePatterns: [
		'dist/',
		'node_modules/',
	],
	rules: {
		'no-console': 'warn',
		'vue/multi-word-component-names': 'off',
		'vue/html-indent': 'off',
		'vue/max-attributes-per-line': 'off',
		'vue/attributes-order': 'off',
		'vue/singleline-html-element-content-newline': 'off',
		'vue/html-self-closing': 'off',
	},
};
