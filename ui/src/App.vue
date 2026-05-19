<template>
	<v-app-instance class-name="SYNO.SDS.App.AV_ImgData.Instance">
		<v-app-window width="850" min-width="600" height="574" ref="appWindow" :resizable="true" syno-id="SYNO.SDS.App.AV_ImgData.Window">
			<div class="sm-shell">
				<div class="sm-body">
					<app-sidebar-nav :selected-option="selectedOption" @select="selectContent" />

					<main class="sm-content">
						<status-view v-if="selectedOption === 'status'" :vm="this" />
						<face-match-view v-if="selectedOption === 'face_match'" :vm="this" />
						<checks-view v-if="selectedOption === 'checks'" :vm="this" />
						<cleanup-view v-if="selectedOption === 'cleanup'" :vm="this" />
						<configuration-view v-if="selectedOption === 'configuration'" />
						<external-libraries-view
							v-if="selectedOption === 'external_libraries'"
							:vm="this"
							mode="info"
						/>
						<external-libraries-view
							v-if="selectedOption === 'external_libraries_exiftool'"
							:vm="this"
							mode="config"
						/>
						<external-libraries-view
							v-if="selectedOption === 'external_libraries_pip_packages'"
							:vm="this"
							mode="pip_packages"
						/>
					</main>
				</div>
			</div>
		</v-app-window>
	</v-app-instance>
</template>

<script>
import AppSidebarNav from './components/AppSidebarNav.vue';
import checksMixin from './mixins/checksMixin';
import cleanupMixin from './mixins/cleanupMixin';
import externalLibrariesMixin from './mixins/externalLibrariesMixin';
import faceMatchMixin from './mixins/faceMatchMixin';
import runtimePollingMixin from './mixins/runtimePollingMixin';
import statusMixin from './mixins/statusMixin';
import ChecksView from './views/ChecksView.vue';
import CleanupView from './views/CleanupView.vue';
import ConfigurationView from './views/ConfigurationView.vue';
import ExternalLibrariesView from './views/ExternalLibrariesView.vue';
import FaceMatchView from './views/FaceMatchView.vue';
import StatusView from './views/StatusView.vue';

export default {
	mixins: [runtimePollingMixin, statusMixin, checksMixin, cleanupMixin, faceMatchMixin, externalLibrariesMixin],
	components: {
		AppSidebarNav,
		ChecksView,
		CleanupView,
		ConfigurationView,
		ExternalLibrariesView,
		FaceMatchView,
		StatusView,
	},
	data() {
		return {
			selectedOption: 'status',
			output: '',
		};
	},
		methods: {
		close() {
			this.$refs.appWindow.close();
		},
		escapeRegExp(value) {
			return String(value || '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
		},
		resolveLocalIconUrl(filename) {
			if (!filename) {
				return '';
			}
			return `/webman/3rdparty/AV_ImgData/images/${filename}`;
		},
		selectContent(option) {
			this.selectedOption = option;
			const selectedOption = this.selectedOption;
			if (selectedOption === 'status' && !this.statusLoaded && !this.statusLoading) {
				this.getStatus({ auto: true });
			}
			if (selectedOption === 'status') {
				this.refreshFileAnalysisSessionState();
			}
			if (selectedOption === 'face_match') {
				this.refreshFaceMatchSessionState();
			}
			if (selectedOption === 'checks') {
				this.refreshChecksSessionState();
			}
			if (selectedOption === 'cleanup') {
				this.refreshCleanupSessionState();
			}
			if (selectedOption === 'external_libraries' || selectedOption === 'external_libraries_exiftool' || selectedOption === 'external_libraries_pip_packages') {
				this.loadExternalLibrariesConfig();
			}
		},
		readCookie(name) {
			const match = document.cookie.match(new RegExp('(?:^|; )' + this.escapeRegExp(name) + '=([^;]*)'));
			return match ? decodeURIComponent(match[1]) : '';
		},
		getResponseData(data) {
			return (data && typeof data.data === 'object' && data.data) ? data.data : {};
		},
		getResponseDataObject(data, key) {
			const root = this.getResponseData(data);
			return (root && typeof root[key] === 'object' && root[key]) ? root[key] : {};
		},
		getDsmApiEndpoint(apiPath) {
			try {
				const parsed = new URL(String(apiPath || ''), window.location.origin);
				const parts = parsed.pathname.split('/').filter(Boolean);
				return parts.length ? parts[parts.length - 1] : '';
			} catch (err) {
				const parts = String(apiPath || '').split('?')[0].split('/').filter(Boolean);
				return parts.length ? parts[parts.length - 1] : '';
			}
		},
		getDsmApiTimeoutMs(apiPath, options = {}) {
			const explicitTimeout = Number(options.timeoutMs);
			if (Number.isFinite(explicitTimeout) && explicitTimeout > 0) {
				return Math.max(1000, explicitTimeout);
			}
			const endpointTimeouts = {
				checks_item: 120000,
				checks_delete_metadata_face: 120000,
				checks_replace_metadata_face_name: 120000,
				checks_replace_metadata_face_position: 120000,
				checks_assign_face_person: 120000,
				checks_ignore_entry: 120000,
				face_assign_match: 120000,
				face_create_match: 120000,
				face_apply_metadata_match: 120000,
				face_assign_metadata_match: 120000,
				face_create_metadata_match: 120000,
				exiftool_install: 120000,
				exiftool_remove: 120000,
				insightface_model_delete: 120000,
			};
			return endpointTimeouts[this.getDsmApiEndpoint(apiPath)] || 15000;
		},
		formatBackendError(backendError, fallback = 'Unknown error') {
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
				if (!text) {
					return;
				}
				parts.push(`${this.$avt(labelKey, fallbackLabel)}: ${text}`);
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
				parts.push(this.$avt('error:retryable', 'Retry may be possible after the current write has finished.'));
			}
			return parts.length ? `${message} (${parts.join(', ')})` : message;
		},
		getErrorMessage(err, fallback = 'Unknown error') {
			if (err && err.backendError) {
				return this.formatBackendError(err.backendError, fallback);
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
		},
			collectDsmCookies() {
				return {
					_SSID: this.readCookie('_SSID'),
					id: this.readCookie('id'),
					did: this.readCookie('did'),
				};
			},
			async getDsmRequestContext({ resume = true, requireResumeMessage = false, requireSynoToken = true } = {}) {
				if (resume) {
					await synocredential._instance.Resume();
				}
				let kk_message = '';
				if (resume || requireResumeMessage) {
					const remote = synocredential._instance.GetRemoteKey();
					const params = synocredential._instance.GetResumeParams({}, remote) || {};
					kk_message = params.kk_message || '';
				}
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (requireResumeMessage && !kk_message) {
					throw new Error(this.$avt('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (requireSynoToken && !synoToken) {
					throw new Error(this.$avt('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				return {
					kk_message,
					synoToken,
					cookies,
				};
			},
			async callDsmApi(apiPath, body = {}, options = {}) {
				const {
					kk_message,
					synoToken,
					cookies,
				} = await this.getDsmRequestContext(options);
				const payload = {
					...body,
					cookies,
				};
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
				const timeoutMs = this.getDsmApiTimeoutMs(apiPath, options);
				const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

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
						const error = new Error(this.formatBackendError(backendError, `HTTP ${resp.status}`));
						error.backendError = backendError;
						throw error;
					}
					return data;
				} catch (err) {
					if (err && err.name === 'AbortError') {
						throw new Error(this.$avt('error:request_timeout', 'Backend request timed out.'));
					}
					throw err;
				} finally {
					window.clearTimeout(timeoutId);
				}
			},
			async callFileAnalysisApi(apiPath, body = {}, options = {}) {
				return this.callDsmApi(apiPath, body, options);
			},
			startNamedPolling(timerKey, callback, interval = 1000) {
				this.stopNamedPolling(timerKey);
				if (!this.__namedPollingPending) {
					this.__namedPollingPending = {};
				}
				if (!this.__namedPollingRunIds) {
					this.__namedPollingRunIds = {};
				}
				const runId = (Number(this.__namedPollingRunIds[timerKey]) || 0) + 1;
				this.__namedPollingRunIds[timerKey] = runId;
				const run = () => {
					if (this.__namedPollingPending[timerKey]) {
						return;
					}
					this.__namedPollingPending[timerKey] = true;
					Promise.resolve()
						.then(() => callback())
						.catch(() => {})
						.finally(() => {
							if (this.__namedPollingPending && this.__namedPollingRunIds && this.__namedPollingRunIds[timerKey] === runId) {
								this.__namedPollingPending[timerKey] = false;
							}
						});
				};
				run();
				this[timerKey] = window.setInterval(run, interval);
			},
			stopNamedPolling(timerKey) {
				if (this[timerKey]) {
					window.clearInterval(this[timerKey]);
					this[timerKey] = null;
				}
				if (this.__namedPollingPending) {
					this.__namedPollingPending[timerKey] = false;
				}
				if (this.__namedPollingRunIds) {
					this.__namedPollingRunIds[timerKey] = (Number(this.__namedPollingRunIds[timerKey]) || 0) + 1;
				}
			},
			formatCountSummary(counterMap) {
				if (!counterMap || typeof counterMap !== 'object') {
					return '-';
			}
			const entries = Object.entries(counterMap)
				.filter(([, value]) => Number(value) > 0)
				.sort((left, right) => String(left[0]).localeCompare(String(right[0])));
			if (!entries.length) {
				return '-';
			}
			return entries.map(([key, value]) => `${key}: ${value}`).join(', ');
		},
		getSynoToken() {
			return (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
		},
		getPhotoThumbnailUrl(image) {
			const itemId = image && image.id;
			const thumbnail = (image && image.additional && image.additional.thumbnail)
				|| (image && image.thumbnail);
			const cacheKey = thumbnail && thumbnail.cache_key;
			const synoToken = this.getSynoToken();
			if (!itemId || !cacheKey || !synoToken) {
				return '';
			}

			const params = new URLSearchParams();
			params.set('id', String(itemId));
			params.set('cache_key', `"${cacheKey}"`);
			params.set('type', '"unit"');
			params.set('size', '"sm"');
			params.set('SynoToken', synoToken);
			return `/synofoto/api/v2/t/Thumbnail/get?${params.toString()}`;
		},
	},
};
</script>
