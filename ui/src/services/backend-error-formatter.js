export function createBackendErrorFormatter(translate) {
	const avt = typeof translate === 'function'
		? translate
		: (_key, fallback) => fallback;

	function formatBackendError(backendError, fallback = 'Unknown error') {
		if (!backendError || typeof backendError !== 'object') {
			return typeof backendError === 'string' && backendError.trim()
				? backendError.trim()
				: fallback;
		}
		const message = String(backendError.message || fallback).trim();
		const details = backendError.details && typeof backendError.details === 'object'
			? backendError.details
			: null;
		if (!details) {
			return message;
		}
		const parts = [];
		const addPart = (labelKey, fallbackLabel, value) => {
			const text = String(value || '').trim();
			if (text) {
				parts.push(`${avt(labelKey, fallbackLabel)}: ${text}`);
			}
		};
		addPart('error:label_code', 'Code', details.code || details.reason);
		if (details.reason && details.reason !== details.code) {
			addPart('error:label_reason', 'Reason', details.reason);
		}
		addPart('error:label_phase', 'Phase', details.phase);
		addPart('error:label_file', 'File', details.image_path || details.target_path);
		addPart('error:label_changed_path', 'Changed path', details.changed_path);
		addPart('error:label_face_id', 'Face ID', details.face_id);
		addPart('error:label_item_id', 'Item ID', details.item_id);
		addPart('error:label_person_id', 'Person ID', details.person_id);
		if (details.retryable === true) {
			parts.push(avt('error:retryable', 'Retry may be possible after the current write has finished.'));
		}
		return parts.length ? `${message} (${parts.join(', ')})` : message;
	}

	function getErrorMessage(err, fallback = 'Unknown error') {
		if (err && err.backendError) {
			return formatBackendError(err.backendError, fallback);
		}
		if (err instanceof Error && err.message) {
			return err.message;
		}
		if (err && typeof err.message === 'string' && err.message.trim()) {
			return err.message.trim();
		}
		if (typeof err === 'string' && err.trim()) {
			return err.trim();
		}
		if (err && typeof err === 'object') {
			try {
				const serialized = JSON.stringify(err);
				if (serialized && serialized !== '{}') {
					return serialized;
				}
			} catch (_ignored) {
				// Fall back below.
			}
		}
		return fallback;
	}

	return {
		formatBackendError,
		getErrorMessage,
	};
}
