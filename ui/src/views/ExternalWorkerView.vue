<template>
	<section class="panel">
		<div class="panel-head">
			<div>
				<div class="sm-section-title">{{ $avt('external_worker:title', 'External worker') }}</div>
				<div class="config-card-desc">{{ $avt('external_worker:description', 'Configure the optional Worker API, register workers and inspect packaged worker downloads.') }}</div>
			</div>
		</div>

		<div class="config-actions config-actions-right">
			<v-button @click="loadAll" :disabled="loading || saving || enrolling || deletingWorkerId || faceDetectRunning" style="width: 160px;">{{ $avt('config:button_reload', 'Reload') }}</v-button>
			<v-button @click="saveConfig" :disabled="loading || saving || enrolling || deletingWorkerId || faceDetectRunning" style="width: 160px;">{{ $avt('config:button_save', 'Save') }}</v-button>
		</div>

		<div v-if="message" class="config-message">{{ message }}</div>
		<div v-if="loading" class="config-loading"><span class="sm-loader"></span>{{ $avt('external_worker:loading', 'Loading external worker settings...') }}</div>

		<div v-else class="config-layout">
			<section class="config-card">
				<div class="sm-section-title">{{ $avt('external_worker:section_api', 'Worker API') }}</div>
				<div class="config-card-desc">{{ $avt('external_worker:api_restart_hint', 'Changes to the Worker API activation require a package restart before the /worker-api route changes state.') }}</div>
				<div class="config-form-grid">
					<label class="config-checkbox"><input v-model="workerApi.ENABLED" type="checkbox" :disabled="saving" /><span>{{ $avt('external_worker:label_api_enabled', 'Enable Worker API') }}</span></label>
					<label class="config-field">
						<span class="config-field-label">{{ $avt('external_worker:label_state_path', 'Worker API state path') }}</span>
						<input v-model="workerApi.STATE_PATH" type="text" class="config-text-input" :disabled="saving" :placeholder="$avt('external_worker:placeholder_state_path', 'Empty = package var/worker-api-state.json')" />
						<span class="config-card-desc">{{ $avt('external_worker:hint_state_path', 'Optional override for the Worker API state file. Relative paths are resolved against the package var directory.') }}</span>
					</label>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('external_worker:section_registration', 'Register worker') }}</div>
				<div class="config-card-desc">{{ $avt('external_worker:registration_desc', 'Create a one-time registration code. Enter the code on the worker to receive its token and synchronize licensed models.') }}</div>
				<div class="config-form-grid external-worker-registration-form">
					<label class="config-field"><span class="config-field-label">{{ $avt('external_worker:worker_name', 'Worker name') }}</span><input v-model="enrollmentForm.enrollment_id" type="text" class="config-text-input" :disabled="enrolling" placeholder="windows-worker-01" /></label>
					<label class="config-field"><span class="config-field-label">{{ $avt('external_worker:expires_minutes', 'Code validity in minutes') }}</span><input v-model.number="enrollmentForm.expires_minutes" type="number" min="1" max="1440" class="config-text-input" :disabled="enrolling" /></label>
				</div>
				<div class="config-actions"><v-button @click="startEnrollment" :disabled="enrolling || !enrollmentForm.enrollment_id.trim()" style="width: 190px;">{{ enrolling ? $avt('external_worker:registering', 'Starting...') : $avt('external_worker:start_registration', 'Register worker') }}</v-button></div>
				<div v-if="activeEnrollment.enrollment_code" class="external-worker-code-box">
					<div>
						<div class="config-field-label">{{ $avt('external_worker:registration_code', 'Registration code') }}</div>
						<code>{{ activeEnrollment.enrollment_code }}</code>
						<div class="config-card-desc">{{ $avt('external_worker:registration_expires', 'Expires: {expires}', { expires: formatLocalTime(activeEnrollment.expires_at) }) }}</div>
					</div>
					<v-button @click="copyEnrollmentCode" style="width: 120px;">{{ $avt('external_worker:copy', 'Copy') }}</v-button>
				</div>
				<div v-if="enrollmentRows.length" class="external-worker-table-list">
					<div v-for="item in enrollmentRows" :key="item.enrollment_id + ':' + item.created_at" class="external-worker-list-row">
						<div><div class="external-worker-bundle-title">{{ item.enrollment_id }}</div><div class="config-card-desc">{{ item.worker_id || $avt('external_worker:not_connected', 'Not connected yet') }}</div><div class="config-card-desc">{{ $avt('external_worker:registration_expires', 'Expires: {expires}', { expires: formatLocalTime(item.expires_at) }) }}</div></div>
						<span class="external-worker-pill" :class="{ ok: item.status === 'enrolled', warn: item.status !== 'enrolled' }">{{ enrollmentStatusLabel(item.status) }}</span>
					</div>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('external_worker:registered_workers', 'Registered workers') }}</div>
				<div v-if="!workerRows.length" class="config-card-desc">{{ $avt('external_worker:no_registered_workers', 'No registered workers found.') }}</div>
				<div v-else class="external-worker-table-list">
					<div v-for="worker in workerRows" :key="worker.worker_id" class="external-worker-list-row">
						<div><div class="external-worker-bundle-title">{{ worker.worker_id }}</div><div class="config-card-desc">{{ worker.version || 'unknown' }} · {{ worker.capabilities.join(', ') || '-' }}</div><div class="config-card-desc">{{ $avt('external_worker:last_seen', 'Last seen: {time}', { time: formatLocalTime(worker.last_seen_at) }) }}</div></div>
						<div class="external-worker-worker-actions">
							<span class="external-worker-pill" :class="{ ok: worker.status === 'ready' || worker.status === 'registered', warn: worker.status !== 'ready' && worker.status !== 'registered' }">{{ worker.status }}</span>
							<v-button @click="deleteWorker(worker)" :disabled="Boolean(deletingWorkerId)" style="width: 120px;">{{ deletingWorkerId === worker.worker_id ? $avt('external_worker:deleting', 'Deleting...') : $avt('external_worker:delete', 'Delete') }}</v-button>
						</div>
					</div>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('external_worker:face_detect_title', 'Process image on external worker') }}</div>
				<div class="config-card-desc">{{ $avt('external_worker:face_detect_desc', 'Enter an absolute image path below the Synology Photos shared folder. The backend creates a face_native_detect job, waits for the worker result and normalizes the returned faces.') }}</div>
				<div class="config-form-grid">
					<label class="config-field cleanup-wide-field">
						<span class="config-field-label">{{ $avt('external_worker:face_detect_image_path', 'Image path on NAS') }}</span>
						<input v-model="faceDetectForm.image_path" type="text" class="config-text-input" :disabled="faceDetectRunning" placeholder="/volume1/photo/2026/2026.02/image.heic" />
					</label>
					<label class="config-field">
						<span class="config-field-label">{{ $avt('external_worker:face_detect_threshold', 'Minimum confidence') }}</span>
						<input v-model.number="faceDetectForm.det_thresh" type="number" min="0" max="1" step="0.05" class="config-text-input" :disabled="faceDetectRunning" />
					</label>
					<label class="config-field">
						<span class="config-field-label">{{ $avt('external_worker:face_detect_max_faces', 'Maximum faces') }}</span>
						<input v-model.number="faceDetectForm.max_num" type="number" min="0" step="1" class="config-text-input" :disabled="faceDetectRunning" />
					</label>
				</div>
				<div class="config-actions">
					<v-button @click="runFaceDetect" :disabled="faceDetectRunning || !faceDetectForm.image_path.trim() || !workerRows.length" style="width: 240px;">{{ faceDetectRunning ? $avt('external_worker:face_detect_running', 'Processing...') : $avt('external_worker:face_detect_start', 'Process on external worker') }}</v-button>
				</div>
				<div v-if="faceDetectResult.job_id" class="external-worker-result-box">
					<div class="face-match-status-stats">
						<span>{{ $avt('external_worker:face_detect_job', 'Job') }}: {{ faceDetectResult.job_id }}</span>
						<span>{{ $avt('external_worker:face_detect_faces', 'Faces') }}: {{ faceDetectResult.faces_count || 0 }}</span>
						<span>{{ $avt('external_worker:face_detect_target', 'Target') }}: {{ faceDetectResult.execution_target || '-' }}</span>
					</div>
					<pre>{{ formatFaceDetectResult(faceDetectResult.faces) }}</pre>
				</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ $avt('external_worker:section_downloads', 'Worker downloads in package') }}</div>
				<div class="config-card-desc">{{ $avt('external_worker:downloads_desc', 'The package installs external workers as archives under workers/. The source bundle directories stay outside the package.') }}</div>
				<div class="external-worker-status-grid">
					<div><span class="config-field-label">{{ $avt('external_worker:package_root', 'Package root') }}</span><div class="config-card-desc">{{ packageStatus.package_root || '-' }}</div></div>
					<div><span class="config-field-label">{{ $avt('external_worker:workers_root', 'Workers root') }}</span><div class="config-card-desc">{{ packageStatus.workers_root || '-' }}</div></div>
					<div><span class="config-field-label">{{ $avt('external_worker:archive_formats', 'Archive formats checked') }}</span><div class="config-card-desc">{{ archiveFormatsText }}</div></div>
				</div>
				<div v-if="packageStatus.build_process_requires_archives" class="config-message external-worker-warning">{{ $avt('external_worker:archive_build_required', 'Worker bundles are present, but no download archives were found. The build process still needs to create zip or tar archives for browser downloads.') }}</div>
				<div v-if="!bundleRows.length" class="config-card-desc">{{ $avt('external_worker:no_bundles', 'No worker bundle information found.') }}</div>
				<div v-else class="external-worker-bundle-list">
					<div v-for="bundle in bundleRows" :key="bundle.target" class="external-worker-bundle-row">
						<div><div class="external-worker-bundle-title">{{ bundle.target }}</div><div class="config-card-desc">{{ bundle.bundle_path }}</div><div class="config-card-desc">{{ $avt('external_worker:binary_status', 'Binary: {path} ({status})', { path: bundle.binary_relative_path || '-', status: binaryStatusLabel(bundle) }) }}</div></div>
						<div class="external-worker-bundle-actions"><span class="external-worker-pill" :class="{ ok: bundle.download_ready, warn: !bundle.download_ready }">{{ statusLabel(bundle) }}</span><a v-if="bundle.download_ready" class="external-worker-download-link" :href="bundle.download_url" :download="bundle.archive_name || undefined" target="_blank" rel="noopener">{{ $avt('external_worker:download', 'Download') }}</a></div>
					</div>
				</div>
			</section>
		</div>
	</section>
</template>

<script>
export default {
	name: 'ExternalWorkerView',
	data() {
		return {
			loading: false,
			saving: false,
			enrolling: false,
			deletingWorkerId: '',
			faceDetectRunning: false,
			message: '',
			configModel: this.createDefaultConfig(),
			workerApi: this.createDefaultWorkerApiConfig(),
			packageStatus: this.createDefaultPackageStatus(),
			enrollmentStatus: { enrollments: [], workers: [] },
			enrollmentForm: { enrollment_id: 'windows-worker-01', expires_minutes: 15 },
			activeEnrollment: {},
			faceDetectForm: { image_path: '', det_thresh: 0.5, max_num: 0, det_size: [640, 640] },
			faceDetectResult: {},
		};
	},
	computed: {
		bundleRows() { return Array.isArray(this.packageStatus.bundles) ? this.packageStatus.bundles : []; },
		enrollmentRows() { return Array.isArray(this.enrollmentStatus.enrollments) ? this.enrollmentStatus.enrollments : []; },
		workerRows() { return Array.isArray(this.enrollmentStatus.workers) ? this.enrollmentStatus.workers : []; },
		archiveFormatsText() { const formats = Array.isArray(this.packageStatus.archive_formats_checked) ? this.packageStatus.archive_formats_checked : []; return formats.length ? formats.join(', ') : '-'; },
	},
	mounted() { this.loadAll(); },
	methods: {
		createDefaultConfig() { return { worker_api: this.createDefaultWorkerApiConfig() }; },
		createDefaultWorkerApiConfig() { return { ENABLED: false, STATE_PATH: '' }; },
		createDefaultPackageStatus() { return { package_root: '', workers_root: '', workers_root_exists: false, archive_formats_checked: [], bundles: [], download_ready: false, build_process_requires_archives: false }; },
		formatLocalTime(value) { if (!value) return '-'; const parsed = new Date(value); return Number.isNaN(parsed.getTime()) ? String(value) : parsed.toLocaleString(); },
		readCookie(name) { const escapedName = String(name || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); const match = document.cookie.match(new RegExp('(?:^|; )' + escapedName + '=([^;]*)')); return match ? decodeURIComponent(match[1]) : ''; },
		getSynoToken() { return (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || ''; },
		collectDsmCookies() { return { _SSID: this.readCookie('_SSID'), id: this.readCookie('id'), did: this.readCookie('did') }; },
		async callApi(apiPath, body = {}) { const resp = await fetch(apiPath, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'X-SYNO-TOKEN': this.getSynoToken() }, body: JSON.stringify({ ...body, cookies: this.collectDsmCookies(), synoToken: this.getSynoToken() }) }); const data = await resp.json().catch(() => ({})); if (!resp.ok || data.success === false) { const backendError = data.error || `HTTP ${resp.status}`; throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError)); } return data; },
		normalizeWorkerApi(input) { const workerApi = (input && typeof input === 'object' && !Array.isArray(input)) ? input : {}; return { ENABLED: Boolean(workerApi.ENABLED), STATE_PATH: String(workerApi.STATE_PATH || '').trim() }; },
		normalizePackageStatus(input) { const status = (input && typeof input === 'object' && !Array.isArray(input)) ? input : {}; return { ...this.createDefaultPackageStatus(), ...status, archive_formats_checked: Array.isArray(status.archive_formats_checked) ? status.archive_formats_checked : [], bundles: Array.isArray(status.bundles) ? status.bundles : [], download_ready: Boolean(status.download_ready), build_process_requires_archives: Boolean(status.build_process_requires_archives) }; },
		statusLabel(bundle) { if (bundle.download_ready) return this.$avt('external_worker:status_archive_ready', 'Archive ready'); if (bundle.bundle_exists) return this.$avt('external_worker:status_archive_missing', 'Archive missing'); return this.$avt('external_worker:status_bundle_missing', 'Bundle missing'); },
		binaryStatusLabel(bundle) { if (!bundle.binary_exists) return this.$avt('external_worker:status_missing', 'missing'); if (bundle.binary_location === 'archive') return this.$avt('external_worker:status_present_in_archive', 'present in archive'); return this.$avt('external_worker:status_present', 'present'); },
		enrollmentStatusLabel(status) { if (status === 'enrolled') return this.$avt('external_worker:enrolled', 'Enrolled'); if (status === 'expired') return this.$avt('external_worker:expired', 'Expired'); return this.$avt('external_worker:waiting', 'Waiting'); },
		formatFaceDetectResult(faces) { return JSON.stringify(Array.isArray(faces) ? faces : [], null, 2); },
		async loadAll() { this.loading = true; this.message = ''; try { const configResponse = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_get'); const config = (configResponse && configResponse.data && configResponse.data.config) || {}; this.configModel = { ...config, worker_api: this.normalizeWorkerApi(config.worker_api) }; this.workerApi = this.normalizeWorkerApi(this.configModel.worker_api); await Promise.all([this.loadStatusOnly(), this.loadEnrollmentStatus()]); } catch (err) { this.message = `Error: ${err.message}`; } finally { this.loading = false; } },
		async saveConfig() { this.saving = true; this.message = ''; try { const payloadConfig = { ...this.configModel, worker_api: this.normalizeWorkerApi(this.workerApi) }; const data = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/config_save', { config: payloadConfig }); const config = (data && data.data && data.data.config) || payloadConfig; this.configModel = { ...config, worker_api: this.normalizeWorkerApi(config.worker_api) }; this.workerApi = this.normalizeWorkerApi(this.configModel.worker_api); this.message = this.$avt('external_worker:message_saved', 'External worker settings saved. Restart the package if the Worker API activation changed.'); await this.loadStatusOnly(); } catch (err) { this.message = `Error: ${err.message}`; } finally { this.saving = false; } },
		async startEnrollment() { this.enrolling = true; this.message = ''; try { const response = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/external_worker_enrollment_start', this.enrollmentForm); this.activeEnrollment = (response.data && response.data.enrollment) || {}; this.enrollmentStatus = (response.data && response.data.status) || { enrollments: [], workers: [] }; this.message = this.$avt('external_worker:registration_started', 'Registration started. Copy the one-time code to the worker.'); } catch (err) { this.message = `Error: ${err.message}`; } finally { this.enrolling = false; } },
		async copyEnrollmentCode() { try { await navigator.clipboard.writeText(String(this.activeEnrollment.enrollment_code || '')); this.message = this.$avt('external_worker:code_copied', 'Registration code copied.'); } catch (err) { this.message = `Error: ${err.message}`; } },
		async deleteWorker(worker) { const workerId = String(worker && worker.worker_id || '').trim(); if (!workerId) return; const prompt = this.$avt('external_worker:delete_confirm', 'Delete worker {worker}? Its bound tokens will be revoked and claimed jobs will be requeued.', { worker: workerId }); if (!window.confirm(prompt)) return; this.deletingWorkerId = workerId; this.message = ''; try { const response = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/external_worker_delete', { worker_id: workerId }); this.enrollmentStatus = (response.data && response.data.status) || { enrollments: [], workers: [] }; this.message = this.$avt('external_worker:deleted', 'Worker deleted. Bound tokens were removed.'); } catch (err) { this.message = `Error: ${err.message}`; } finally { this.deletingWorkerId = ''; } },
		async runFaceDetect() { this.faceDetectRunning = true; this.message = ''; this.faceDetectResult = {}; try { const response = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/external_worker_face_detect', this.faceDetectForm); this.faceDetectResult = (response && response.data) || {}; this.message = this.$avt('external_worker:face_detect_finished', 'External worker processing finished.'); await this.loadEnrollmentStatus(); } catch (err) { this.message = `Error: ${err.message}`; } finally { this.faceDetectRunning = false; } },
		async loadEnrollmentStatus() { const response = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/external_worker_enrollment_status'); this.enrollmentStatus = (response && response.data) || { enrollments: [], workers: [] }; },
		async loadStatusOnly() { const statusResponse = await this.callApi('/webman/3rdparty/AV_ImgData/index.cgi/api/external_worker_status'); this.packageStatus = this.normalizePackageStatus(statusResponse && statusResponse.data && statusResponse.data.package); },
	},
};
</script>

<style scoped>
.external-worker-status-grid { display: grid; gap: 12px; grid-template-columns: 1fr; margin: 12px 0; }
.external-worker-warning { margin: 12px 0; }
.external-worker-registration-form { grid-template-columns: minmax(0, 2fr) minmax(140px, 1fr); }
.external-worker-code-box { align-items: center; background: #f6f8fa; border: 1px solid #d7dde5; border-radius: 8px; display: flex; justify-content: space-between; margin-top: 14px; padding: 12px; }
.external-worker-code-box code { display: block; font-size: 15px; margin: 5px 0; overflow-wrap: anywhere; user-select: all; }
.external-worker-table-list, .external-worker-bundle-list { display: grid; gap: 10px; margin-top: 12px; }
.external-worker-list-row, .external-worker-bundle-row { align-items: center; border: 1px solid #d7dde5; border-radius: 8px; display: grid; gap: 12px; grid-template-columns: minmax(0, 1fr) auto; padding: 12px; }
.external-worker-bundle-title { font-weight: 600; margin-bottom: 4px; }
.external-worker-bundle-actions, .external-worker-worker-actions { align-items: flex-end; display: flex; flex-direction: column; gap: 8px; }
.external-worker-pill { border-radius: 999px; border: 1px solid #d7dde5; font-size: 12px; padding: 3px 8px; white-space: nowrap; }
.external-worker-pill.ok { background: #e9f6ed; border-color: #9fd0ad; color: #246b35; }
.external-worker-pill.warn { background: #fff6e5; border-color: #e6c371; color: #7a5512; }
.external-worker-download-link { color: #1266b0; text-decoration: none; }
.external-worker-download-link:hover { text-decoration: underline; }
.external-worker-result-box { border: 1px solid #d7dde5; border-radius: 8px; margin-top: 14px; padding: 12px; }
.external-worker-result-box pre { max-height: 360px; overflow: auto; white-space: pre-wrap; }
@media (max-width: 720px) { .external-worker-registration-form { grid-template-columns: 1fr; } .external-worker-code-box { align-items: stretch; flex-direction: column; gap: 10px; } }
</style>
