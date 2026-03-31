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
						<configuration-view v-if="selectedOption === 'configuration'" />
					</main>
				</div>
			</div>
		</v-app-window>
	</v-app-instance>
</template>

<script>
import AppSidebarNav from './components/AppSidebarNav.vue';
import checksMixin from './mixins/checksMixin';
import faceMatchMixin from './mixins/faceMatchMixin';
import statusMixin from './mixins/statusMixin';
import ChecksView from './views/ChecksView.vue';
import ConfigurationView from './views/ConfigurationView.vue';
import FaceMatchView from './views/FaceMatchView.vue';
import StatusView from './views/StatusView.vue';

export default {
	mixins: [statusMixin, checksMixin, faceMatchMixin],
	components: {
		AppSidebarNav,
		ChecksView,
		ConfigurationView,
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
			if (option === 'status' && !this.statusLoaded && !this.statusLoading) {
				this.getStatus({ auto: true });
			}
			if (option === 'status') {
				this.refreshFileAnalysisSessionState();
				this.fetchExiftoolStatus();
			}
			if (option === 'face_match') {
				this.refreshFaceMatchSessionState();
			}
			if (option === 'checks') {
				this.refreshChecksSessionState();
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
		collectDsmCookies() {
			return {
				_SSID: this.readCookie('_SSID'),
				id: this.readCookie('id'),
				did: this.readCookie('did'),
			};
		},
		async callFileAnalysisApi(apiPath, body = {}) {
			await synocredential._instance.Resume();

			const remote = synocredential._instance.GetRemoteKey();
			const params = synocredential._instance.GetResumeParams({}, remote) || {};
			const kk_message = params.kk_message || '';
			const synoToken = this.getSynoToken();
			const cookies = this.collectDsmCookies();

			const resp = await fetch(apiPath, {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					'X-SYNO-TOKEN': synoToken,
				},
				body: JSON.stringify({
					...body,
					kk_message,
					synoToken,
					cookies,
				}),
			});
			const data = await resp.json().catch(() => ({}));
			if (!resp.ok || data.success === false) {
				const backendError = data.error || `HTTP ${resp.status}`;
				throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
			}
			return data;
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
