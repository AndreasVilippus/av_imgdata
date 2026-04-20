export default {
	data() {
		return {
			selectedCleanupAction: 'normalize_names',
			cleanupTargets: {
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
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_progress', {
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
			this.startNamedPolling('cleanupProgressTimer', () => {
				this.fetchCleanupProgress();
			});
		},
		stopCleanupProgressPolling() {
			this.stopNamedPolling('cleanupProgressTimer');
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
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_start', {
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
				await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_stop', {
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
