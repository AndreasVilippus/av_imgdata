export default {
	data() {
		return {
			selectedCleanupAction: 'normalize_names',
			cleanupTargets: {
				PHOTOS: true,
				ACD: true,
				MICROSOFT: true,
				MWG_REGIONS: true,
			},
			cleanupLoading: false,
			cleanupStatusMessage: '',
			cleanupProgress: {},
			cleanupProgressTimer: null,
			cleanupProgressRequestId: 0,
		};
	},
	computed: {
		cleanupPrimaryButtonLabel() {
			if (this.cleanupLoading) {
				return this.$t('cleanup:button_stop', 'Stop');
			}
			return this.$t('cleanup:button_start', 'Start');
		},
		selectedCleanupTargets() {
			return Object.entries(this.cleanupTargets)
				.filter(([, enabled]) => !!enabled)
				.map(([target]) => target);
		},
	},
	beforeDestroy() {
		this.stopCleanupProgressPolling();
	},
	methods: {
		async callCleanupApi(apiPath, body = {}) {
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
		applyCleanupProgress(progress) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			this.cleanupProgress = nextProgress;
			if (nextProgress.message_key || nextProgress.message) {
				this.cleanupStatusMessage = this.$t(
					nextProgress.message_key || '',
					nextProgress.message || '',
					nextProgress.message_params && typeof nextProgress.message_params === 'object'
						? nextProgress.message_params
						: null
				);
			}
		},
		async fetchCleanupProgress() {
			const requestId = this.cleanupProgressRequestId + 1;
			this.cleanupProgressRequestId = requestId;
			try {
				const data = await this.callCleanupApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_progress', {
					action: this.selectedCleanupAction,
				});
				if (this.cleanupProgressRequestId !== requestId) {
					return {};
				}
				const progress = this.getResponseData(data);
				if (progress && Object.keys(progress).length) {
					this.applyCleanupProgress(progress);
				}
				if (!progress.running) {
					this.cleanupLoading = false;
					this.stopCleanupProgressPolling();
				}
				return progress;
			} catch (err) {
				return {};
			}
		},
		startCleanupProgressPolling() {
			this.stopCleanupProgressPolling();
			this.fetchCleanupProgress();
			this.cleanupProgressTimer = window.setInterval(() => {
				this.fetchCleanupProgress();
			}, 1000);
		},
		stopCleanupProgressPolling() {
			if (this.cleanupProgressTimer) {
				window.clearInterval(this.cleanupProgressTimer);
				this.cleanupProgressTimer = null;
			}
		},
		async refreshCleanupSessionState() {
			const progress = await this.fetchCleanupProgress();
			if (progress && progress.running) {
				this.cleanupLoading = true;
				this.startCleanupProgressPolling();
				return;
			}
			this.cleanupLoading = false;
		},
		async handleCleanupAction() {
			if (this.cleanupLoading) {
				await this.stopCleanupRun();
				return;
			}
			await this.startCleanupRun();
		},
		async startCleanupRun() {
			this.cleanupLoading = true;
			this.cleanupStatusMessage = this.$t('cleanup:status_preparing', 'Cleanup starts. Preparing run...');
			try {
				const data = await this.callCleanupApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_start', {
					action: this.selectedCleanupAction,
					targets: this.selectedCleanupTargets,
				});
				const progress = this.getResponseData(data);
				this.applyCleanupProgress(progress);
				if (progress.running) {
					this.startCleanupProgressPolling();
				} else {
					this.cleanupLoading = false;
				}
			} catch (err) {
				this.cleanupLoading = false;
				this.cleanupStatusMessage = `Error: ${err.message}`;
			}
		},
		async stopCleanupRun() {
			try {
				await this.callCleanupApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_stop', {
					action: this.selectedCleanupAction,
				});
			} catch (err) {
				// Best effort.
			}
			this.cleanupStatusMessage = this.$t('cleanup:progress_stopping', 'Cleanup is stopping...');
			await this.fetchCleanupProgress();
		},
		getCleanupTargetLabel(target) {
			const key = String(target || '').trim().toUpperCase();
			if (key === 'PHOTOS') {
				return this.$t('cleanup:target_photos', 'Photos');
			}
			if (key === 'ACD') {
				return this.$t('cleanup:target_acd', 'ACDSee');
			}
			if (key === 'MICROSOFT') {
				return this.$t('cleanup:target_microsoft', 'Microsoft');
			}
			if (key === 'MWG_REGIONS') {
				return this.$t('cleanup:target_mwg_regions', 'MWG regions');
			}
			return key;
		},
	},
};
