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

const COOKIE_LOCALE_KEYS = ['language', 'lang', 'locale', 'SYNO_LANGUAGE'];

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

function collectCookieLocales(candidates) {
	try {
		const rawCookie = String(document && document.cookie || '');
		if (!rawCookie) {
			return;
		}
		const cookieMap = {};
		for (const entry of rawCookie.split(';')) {
			const separatorIndex = entry.indexOf('=');
			if (separatorIndex < 0) {
				continue;
			}
			const key = entry.slice(0, separatorIndex).trim();
			const value = entry.slice(separatorIndex + 1).trim();
			if (key) {
				cookieMap[key] = decodeURIComponent(value);
			}
		}
		for (const key of COOKIE_LOCALE_KEYS) {
			if (cookieMap[key]) {
				candidates.push(cookieMap[key]);
			}
		}
	} catch (err) {
		// Ignore cookie access restrictions.
	}
}

function collectQueryLocales(candidates) {
	try {
		const search = String(window && window.location && window.location.search || '');
		if (!search) {
			return;
		}
		const params = new URLSearchParams(search);
		for (const key of COOKIE_LOCALE_KEYS) {
			const value = params.get(key);
			if (value) {
				candidates.push(value);
			}
		}
	} catch (err) {
		// Ignore invalid or restricted query access.
	}
}

function collectStandardLocales(options = {}) {
	const allowNavigator = options.allowNavigator !== false;
	const candidates = [];
	try {
		collectQueryLocales(candidates);
		collectDsmGlobalLocales(window, candidates);
		if (window.parent && window.parent !== window) {
			collectDsmGlobalLocales(window.parent, candidates);
		}
		collectCookieLocales(candidates);
	} catch (err) {
		// Ignore locale access restrictions from embedded DSM contexts.
	}
	try {
		if (document && document.documentElement && document.documentElement.lang) {
			candidates.push(document.documentElement.lang);
		}
	} catch (err) {
		// Ignore locale access restrictions from embedded DSM contexts.
	}
	try {
		if (window.parent && window.parent.document && window.parent.document.documentElement) {
			candidates.push(window.parent.document.documentElement.lang);
		}
	} catch (err) {
		// Ignore cross-frame access restrictions.
	}

	if (allowNavigator) {
		try {
			if (navigator && Array.isArray(navigator.languages)) {
				candidates.push(...navigator.languages);
			}
		} catch (err) {
			// Ignore restricted navigator access.
		}
		try {
			if (navigator && navigator.language) {
				candidates.push(navigator.language);
			}
		} catch (err) {
			// Ignore restricted navigator access.
		}
	}
	return candidates;
}

function detectLocale(options = {}) {
	const candidates = collectStandardLocales(options);
	for (const candidate of candidates) {
		const locale = normalizeLocale(candidate);
		if (locale) {
			return locale;
		}
	}
	return FALLBACK_LOCALE;
}

function detectExplicitDsmLocale() {
	return detectLocale({ allowNavigator: false });
}

async function waitForDsmLocale(timeoutMs = 1500, intervalMs = 100) {
	const startedAt = Date.now();
	while (Date.now() - startedAt < timeoutMs) {
		const locale = detectExplicitDsmLocale();
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
	let locale = detectExplicitDsmLocale();
	if (!locale || locale === FALLBACK_LOCALE) {
		const delayedLocale = await waitForDsmLocale();
		if (delayedLocale) {
			locale = delayedLocale;
		}
	}
	if (!locale || locale === FALLBACK_LOCALE) {
		locale = detectLocale({ allowNavigator: true });
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
