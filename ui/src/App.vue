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
						<external-libraries-view v-if="selectedOption === 'external_libraries'" :vm="this" mode="info" />
						<external-libraries-view v-if="selectedOption === 'external_libraries_exiftool'" :vm="this" mode="config" />
						<external-libraries-view v-if="selectedOption === 'external_libraries_insightface'" :vm="this" mode="insightface" />
						<database-lists-view v-if="selectedOption === 'database_lists'" :vm="this" />
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
import databaseListsMixin from './mixins/databaseListsMixin';
import externalLibrariesMixin from './mixins/externalLibrariesMixin';
import faceMatchMixin from './mixins/faceMatchMixin';
import statusMixin from './mixins/statusMixin';
import { createBackendErrorFormatter } from './services/backend-error-formatter';
import { createDsmApiClient } from './services/dsm-api-client';
import { createRuntimePollingController } from './services/runtime-polling';
import ChecksView from './views/ChecksView.vue';
import CleanupView from './views/CleanupView.vue';
import ConfigurationView from './views/ConfigurationView.vue';
import DatabaseListsView from './views/DatabaseListsView.vue';
import ExternalLibrariesView from './views/ExternalLibrariesView.vue';
import FaceMatchView from './views/FaceMatchView.vue';
import StatusView from './views/StatusView.vue';

export default {
	mixins: [statusMixin, checksMixin, cleanupMixin, faceMatchMixin, externalLibrariesMixin, databaseListsMixin],
	components: {
		AppSidebarNav,
		ChecksView,
		CleanupView,
		ConfigurationView,
		DatabaseListsView,
		ExternalLibrariesView,
		FaceMatchView,
		StatusView,
	},
	data() {
		return {
			selectedOption: 'status',
			output: '',
			backendErrorFormatter: null,
			dsmApiClient: null,
			runtimePolling: null,
		};
	},
	created() {
		this.backendErrorFormatter = createBackendErrorFormatter((key, fallback) => this.$avt(key, fallback));
		this.dsmApiClient = createDsmApiClient(this);
		this.runtimePolling = createRuntimePollingController(this);
	},
	methods: {
		close() {
			this.$refs.appWindow.close();
		},
		resolveLocalIconUrl(filename) {
			return filename ? '/webman/3rdparty/AV_ImgData/images/' + filename : '';
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
			if (selectedOption === 'external_libraries' || selectedOption === 'external_libraries_exiftool' || selectedOption === 'external_libraries_insightface') {
				this.loadExternalLibrariesConfig();
			}
			if (selectedOption === 'database_lists') {
				this.loadDatabaseList();
			}
		},
		readCookie(name) {
			return this.dsmApiClient.readCookie(name);
		},
		getResponseData(data) {
			return this.dsmApiClient.getResponseData(data);
		},
		getResponseDataObject(data, key) {
			return this.dsmApiClient.getResponseDataObject(data, key);
		},
		getDsmApiEndpoint(apiPath) {
			return this.dsmApiClient.getDsmApiEndpoint(apiPath);
		},
		getDsmApiTimeoutMs(apiPath, options = {}) {
			return this.dsmApiClient.getDsmApiTimeoutMs(apiPath, options);
		},
		formatBackendError(backendError, fallback = 'Unknown error') {
			return this.backendErrorFormatter.formatBackendError(backendError, fallback);
		},
		getErrorMessage(err, fallback = 'Unknown error') {
			return this.backendErrorFormatter.getErrorMessage(err, fallback);
		},
		collectDsmCookies() {
			return this.dsmApiClient.collectDsmCookies();
		},
		async getDsmRequestContext(options = {}) {
			return this.dsmApiClient.getDsmRequestContext(options);
		},
		async callDsmApi(apiPath, body = {}, options = {}) {
			return this.dsmApiClient.callDsmApi(apiPath, body, options);
		},
		async callFileAnalysisApi(apiPath, body = {}, options = {}) {
			return this.callDsmApi(apiPath, body, options);
		},
		startNamedPolling(timerKey, callback, interval = 1000, options = {}) {
			this.runtimePolling.startNamedPolling(timerKey, callback, interval, options);
		},
		stopNamedPolling(timerKey) {
			this.runtimePolling.stopNamedPolling(timerKey);
		},
		formatCountSummary(counterMap) {
			if (!counterMap || typeof counterMap !== 'object') {
				return '-';
			}
			const entries = Object.entries(counterMap)
				.filter(([, value]) => Number(value) > 0)
				.sort((left, right) => String(left[0]).localeCompare(String(right[0])));
			return entries.length ? entries.map(([key, value]) => `${key}: ${value}`).join(', ') : '-';
		},
		getSynoToken() {
			return this.dsmApiClient.getSynoToken();
		},
		getPhotoThumbnailUrl() {
			return '';
		},
		getBackendImagePreviewUrl(path) {
			const normalized = String(path || '').trim();
			return normalized ? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(normalized)}` : '';
		},
		isBrowserImageCompatiblePath(path) {
			const normalized = String(path || '').trim().toLowerCase();
			const match = normalized.match(/\.([a-z0-9]+)(?:[?#].*)?$/);
			const extension = match ? match[1] : '';
			return ['jpg', 'jpeg', 'png', 'gif', 'webp', 'bmp', 'svg', 'avif'].indexOf(extension) >= 0;
		},
	},
};
</script>
