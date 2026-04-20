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
import statusMixin from './mixins/statusMixin';
import ChecksView from './views/ChecksView.vue';
import CleanupView from './views/CleanupView.vue';
import ConfigurationView from './views/ConfigurationView.vue';
import ExternalLibrariesView from './views/ExternalLibrariesView.vue';
import FaceMatchView from './views/FaceMatchView.vue';
import StatusView from './views/StatusView.vue';

export default {
	mixins: [statusMixin, checksMixin, cleanupMixin, faceMatchMixin, externalLibrariesMixin],
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
			if (selectedOption === 'external_libraries' || selectedOption === 'external_libraries_exiftool') {
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
		getErrorMessage(err, fallback = 'Unknown error') {
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
			async getDsmRequestContext({ resume = true, requireResumeMessage = false } = {}) {
				if (resume) {
					await synocredential._instance.Resume();
				}
				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (requireResumeMessage && !kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
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
					synoToken,
					cookies,
				};
				if (kk_message) {
					payload.kk_message = kk_message;
				}

				const resp = await fetch(apiPath, {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify(payload),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}
				return data;
			},
			async callFileAnalysisApi(apiPath, body = {}, options = {}) {
				return this.callDsmApi(apiPath, body, options);
			},
			startNamedPolling(timerKey, callback, interval = 1000) {
				this.stopNamedPolling(timerKey);
				callback();
				this[timerKey] = window.setInterval(() => {
					callback();
				}, interval);
			},
			stopNamedPolling(timerKey) {
				if (this[timerKey]) {
					window.clearInterval(this[timerKey]);
					this[timerKey] = null;
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
