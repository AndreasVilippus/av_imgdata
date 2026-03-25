const FALLBACK_LOCALE = 'enu';
const LOCALE_MAP = {
	de: 'ger',
	en: 'enu',
};

const DSM_LOCALE_PATHS = [
	['SYNO', 'SDS', 'Session', 'language'],
	['SYNO', 'SDS', 'Session', 'lang'],
	['SYNO', 'SDS', 'Session', 'locale'],
];

function normalizeLocale(input) {
	const raw = String(input || '').trim().toLowerCase();
	if (!raw) {
		return '';
	}
	if (raw === 'ger' || raw === 'enu') {
		return raw;
	}
	const base = raw.split(/[-_]/)[0];
	return LOCALE_MAP[base] || '';
}

function getNestedValue(root, path) {
	try {
		let current = root;
		for (const key of path) {
			if (!current || typeof current !== 'object' || !(key in current)) {
				return '';
			}
			current = current[key];
		}
		return current;
	} catch (err) {
		return '';
	}
}

function collectDsmGlobalLocales(target, candidates) {
	for (const path of DSM_LOCALE_PATHS) {
		const value = getNestedValue(target, path);
		if (value) {
			candidates.push(value);
		}
	}
}

function collectDsmLocales() {
	const candidates = [];
	try {
		collectDsmGlobalLocales(window, candidates);
		if (window.parent && window.parent !== window) {
			collectDsmGlobalLocales(window.parent, candidates);
		}
	} catch (err) {
		// Ignore locale access restrictions from embedded DSM contexts.
	}
	return candidates;
}

function detectLocale() {
	const candidates = collectDsmLocales();
	for (const candidate of candidates) {
		const locale = normalizeLocale(candidate);
		if (locale) {
			return locale;
		}
	}
	return FALLBACK_LOCALE;
}

async function waitForDsmLocale(timeoutMs = 1500, intervalMs = 100) {
	const startedAt = Date.now();
	while (Date.now() - startedAt < timeoutMs) {
		const locale = detectLocale();
		if (locale && locale !== FALLBACK_LOCALE) {
			return locale;
		}
		await new Promise((resolve) => window.setTimeout(resolve, intervalMs));
	}
	return '';
}

function parseStringsFile(content) {
	const messages = {};
	let currentSection = '';
	const lines = String(content || '').split(/\r?\n/);

	for (const rawLine of lines) {
		const line = rawLine.trim();
		if (!line || line.startsWith('#') || line.startsWith(';')) {
			continue;
		}
		const sectionMatch = line.match(/^\[([^\]]+)\]$/);
		if (sectionMatch) {
			currentSection = sectionMatch[1].trim();
			continue;
		}
		const keyValueMatch = line.match(/^([^=]+)=(.*)$/);
		if (!keyValueMatch || !currentSection) {
			continue;
		}
		const key = keyValueMatch[1].trim();
		let value = keyValueMatch[2].trim();
		if (
			(value.startsWith('"') && value.endsWith('"')) ||
			(value.startsWith("'") && value.endsWith("'"))
		) {
			value = value.slice(1, -1);
		}
		messages[`${currentSection}:${key}`] = value.replace(/\\"/g, '"');
	}

	return messages;
}

async function loadLocaleMessages(locale) {
	const response = await fetch(`/webman/3rdparty/AV_ImgData/texts/${locale}/strings`, {
		credentials: 'include',
	});
	if (!response.ok) {
		throw new Error(`failed_to_load_locale_${locale}`);
	}
	const text = await response.text();
	return parseStringsFile(text);
}

export async function createI18n() {
	let locale = detectLocale();
	if (!locale || locale === FALLBACK_LOCALE) {
		const delayedLocale = await waitForDsmLocale();
		if (delayedLocale) {
			locale = delayedLocale;
		}
	}
	let messages = {};

	try {
		messages = await loadLocaleMessages(locale);
	} catch (err) {
		if (locale !== FALLBACK_LOCALE) {
			messages = await loadLocaleMessages(FALLBACK_LOCALE);
			return buildI18n(FALLBACK_LOCALE, messages);
		}
		throw err;
	}

	return buildI18n(locale, messages);
}

function buildI18n(locale, messages) {
	return {
		locale,
		messages,
		t(key, fallback = '', params = null) {
			const template = messages[key] || fallback || key;
			if (!params || typeof params !== 'object') {
				return template;
			}
			return template.replace(/\{([^}]+)\}/g, (_, token) => {
				const value = params[token];
				return value === undefined || value === null ? '' : String(value);
			});
		},
	};
}
