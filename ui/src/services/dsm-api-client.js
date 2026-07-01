const ENDPOINT_TIMEOUTS = {
	status: 120000,
	checks_item: 120000,
	checks_delete_metadata_face: 120000,
	checks_replace_metadata_face_name: 120000,
	checks_replace_metadata_face_position: 120000,
	checks_assign_face_person: 120000,
	checks_ignore_entry: 120000,
	checks_start: 120000,
	checks_progress: 120000,
	checks_findings_status: 120000,
	face_assign_match: 120000,
	face_create_match: 120000,
	face_apply_metadata_match: 120000,
	face_assign_metadata_match: 120000,
	face_create_metadata_match: 120000,
	face_matching_action: 120000,
	face_matching_progress: 120000,
	face_matching_stop: 120000,
	face_matching_findings_status: 120000,
	file_analysis_start: 120000,
	file_analysis_progress: 120000,
	cleanup_start: 120000,
	cleanup_progress: 120000,
	exiftool_status: 120000,
	exiftool_install: 120000,
	exiftool_remove: 120000,
	insightface_model_delete: 120000,
	pip_packages_status: 120000,
	pip_wheelhouse_packages: 120000,
	pip_wheelhouse_package_install: 900000,
	recognition_findings: 120000,
	recognition_review: 120000,
	recognition_suggestions_apply: 120000,
};

export function createDsmApiClient(host) {
	function readCookie(name) {
		const escapedName = String(name || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		const match = document.cookie.match(new RegExp('(?:^|; )' + escapedName + '=([^;]*)'));
		return match ? decodeURIComponent(match[1]) : '';
	}

	function getResponseData(data) {
		return (data && typeof data.data === 'object' && data.data) ? data.data : {};
	}

	function getResponseDataObject(data, key) {
		const root = getResponseData(data);
		return (root && typeof root[key] === 'object' && root[key]) ? root[key] : {};
	}

	function getSynoToken() {
		return (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
	}

	function collectDsmCookies() {
		return {
			_SSID: readCookie('_SSID'),
			id: readCookie('id'),
			did: readCookie('did'),
		};
	}

	function getDsmApiEndpoint(apiPath) {
		try {
			const parsed = new URL(String(apiPath || ''), window.location.origin);
			const parts = parsed.pathname.split('/').filter(Boolean);
			return parts.length ? parts[parts.length - 1] : '';
		} catch (err) {
			const parts = String(apiPath || '').split('?')[0].split('/').filter(Boolean);
			return parts.length ? parts[parts.length - 1] : '';
		}
	}

	function getDsmApiTimeoutMs(apiPath, options = {}) {
		const explicitTimeout = Number(options.timeoutMs);
		if (Number.isFinite(explicitTimeout) && explicitTimeout > 0) {
			return Math.max(1000, explicitTimeout);
		}
		return ENDPOINT_TIMEOUTS[getDsmApiEndpoint(apiPath)] || 15000;
	}

	async function getDsmRequestContext({ resume = true, requireResumeMessage = false, requireSynoToken = true } = {}) {
		if (resume) {
			await synocredential._instance.Resume();
		}
		let kk_message = '';
		if (resume || requireResumeMessage) {
			const remote = synocredential._instance.GetRemoteKey();
			const params = synocredential._instance.GetResumeParams({}, remote) || {};
			kk_message = params.kk_message || '';
		}
		const synoToken = getSynoToken();
		const cookies = collectDsmCookies();

		if (requireResumeMessage && !kk_message) {
			throw new Error(host.$avt('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
		}
		if (requireSynoToken && !synoToken) {
			throw new Error(host.$avt('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
		}

		return { kk_message, synoToken, cookies };
	}

	async function callDsmApi(apiPath, body = {}, options = {}) {
		const { kk_message, synoToken, cookies } = await getDsmRequestContext(options);
		const payload = { ...body, cookies };
		if (synoToken) {
			payload.synoToken = synoToken;
		}
		if (kk_message) {
			payload.kk_message = kk_message;
		}
		const headers = {
			'Content-Type': 'application/json',
			'Cache-Control': 'no-store, no-cache, max-age=0',
			'Pragma': 'no-cache',
		};
		if (synoToken) {
			headers['X-SYNO-TOKEN'] = synoToken;
		}
		const controller = new AbortController();
		const timeoutId = window.setTimeout(() => controller.abort(), getDsmApiTimeoutMs(apiPath, options));
		try {
			const resp = await fetch(apiPath, {
				method: 'POST',
				credentials: 'include',
				cache: 'no-store',
				headers,
				body: JSON.stringify(payload),
				signal: controller.signal,
			});
			const data = await resp.json().catch(() => ({}));
			if (!resp.ok || data.success === false) {
				const backendError = data.error || `HTTP ${resp.status}`;
				const error = new Error(host.formatBackendError(backendError, `HTTP ${resp.status}`));
				error.backendError = backendError;
				throw error;
			}
			return data;
		} catch (err) {
			if (err && err.name === 'AbortError') {
				throw new Error(host.$avt('error:request_timeout', 'Backend request timed out.'));
			}
			if (err instanceof TypeError) {
				throw new Error(host.$avt('error:network_request_failed', 'Backend request failed or was aborted before a response was received.'));
			}
			throw err;
		} finally {
			window.clearTimeout(timeoutId);
		}
	}

	return {
		callDsmApi,
		collectDsmCookies,
		getDsmApiEndpoint,
		getDsmApiTimeoutMs,
		getDsmRequestContext,
		getResponseData,
		getResponseDataObject,
		getSynoToken,
		readCookie,
	};
}
