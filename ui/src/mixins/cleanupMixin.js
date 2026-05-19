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
				return this.$avt('cleanup:button_stop', 'Stop');
			}
			return this.$avt('cleanup:button_start', 'Start');
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
		getCleanupStatusCounterLabel(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const labelKey = String(counter.label_key || '').trim();
			const fallback = String(counter.fallback_label || counter.key || '').trim();
			return labelKey ? this.$avt(labelKey, fallback) : fallback;
		},
		getCleanupStatusCounters() {
			const progress = this.cleanupProgress && typeof this.cleanupProgress === 'object'
				? this.cleanupProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && Array.isArray(status.counters)) {
				return status.counters
					.filter((counter) => counter && typeof counter === 'object')
					.filter((counter) => counter.show_when_zero || Number(counter.value) > 0)
					.map((counter) => ({
						key: String(counter.key || '').trim(),
						label: this.getCleanupStatusCounterLabel(counter),
						value: Math.max(0, Number(counter.value) || 0),
					}))
					.filter((counter) => counter.key);
			}
			return [];
		},
		getCleanupStatusProgress() {
			const progress = this.cleanupProgress && typeof this.cleanupProgress === 'object'
				? this.cleanupProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && status.progress && typeof status.progress === 'object') {
				return status.progress;
			}
			if (Number(progress.total_files) > 0) {
				return {
					kind: 'files',
					current: Number(progress.files_scanned) || 0,
					total: Number(progress.total_files) || 0,
					title_key: 'cleanup:label_images',
					fallback_title: 'Images',
					primary_label_key: 'cleanup:label_scanned',
					fallback_primary_label: 'scanned',
					secondary_label_key: 'cleanup:label_files_remaining',
					fallback_secondary_label: 'remaining',
				};
			}
			if (Number(progress.persons_total) > 0) {
				return {
					kind: 'persons',
					current: Number(progress.persons_scanned) || 0,
					total: Number(progress.persons_total) || 0,
					title_key: 'cleanup:label_persons',
					fallback_title: 'Persons',
					primary_label_key: 'cleanup:label_scanned',
					fallback_primary_label: 'scanned',
					secondary_label_key: 'cleanup:label_persons_remaining',
					fallback_secondary_label: 'remaining',
				};
			}
			return {};
		},
		getCleanupStatusProgressTitle() {
			const progress = this.getCleanupStatusProgress();
			return progress.title_key ? this.$avt(progress.title_key, progress.fallback_title || progress.kind) : (progress.fallback_title || progress.kind || '');
		},
		getCleanupStatusProgressPrimaryLabel() {
			const progress = this.getCleanupStatusProgress();
			const fallback = String(progress.fallback_primary_label || '').replace(':', '').toLowerCase();
			return progress.primary_label_key ? this.$avt(progress.primary_label_key, fallback).replace(':', '').toLowerCase() : fallback;
		},
		getCleanupStatusProgressSecondaryLabel() {
			const progress = this.getCleanupStatusProgress();
			return progress.secondary_label_key ? this.$avt(progress.secondary_label_key, progress.fallback_secondary_label || '') : (progress.fallback_secondary_label || '');
		},
		formatCleanupStatusCounter(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const label = String(counter.label || counter.key || '').replace(/:$/, '').trim();
			const value = Math.max(0, Number(counter.value) || 0);
			return label ? `${label}: ${value}` : String(value);
		},
		isCleanupProgressUpdateStale(current, next) {
			const currentProgress = current && typeof current === 'object' ? current : {};
			const nextProgress = next && typeof next === 'object' ? next : {};
			const currentOperationId = String(currentProgress.operation_id || '').trim();
			const nextOperationId = String(nextProgress.operation_id || '').trim();
			if (currentOperationId && !nextOperationId) {
				return true;
			}
			if (currentOperationId && nextOperationId && currentOperationId !== nextOperationId) {
				return false;
			}
			const currentRevision = Number(currentProgress.revision);
			const nextRevision = Number(nextProgress.revision);
			return Number.isFinite(currentRevision)
				&& Number.isFinite(nextRevision)
				&& currentRevision > 0
				&& nextRevision > 0
				&& nextRevision < currentRevision;
		},
		applyCleanupProgress(progress) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			if (this.isCleanupProgressUpdateStale(this.cleanupProgress, nextProgress)) {
				return false;
			}
			this.cleanupProgress = nextProgress;
			if (nextProgress.message_key || nextProgress.message) {
				this.cleanupStatusMessage = this.$avt(
					nextProgress.message_key || '',
					nextProgress.message || '',
					nextProgress.message_params && typeof nextProgress.message_params === 'object'
						? nextProgress.message_params
						: null
				);
			}
			return true;
		},
		async fetchCleanupProgress({ force = false } = {}) {
			return this.runOperationPollRequest(
				'cleanup_progress',
				async () => {
					const requestId = this.cleanupProgressRequestId + 1;
					this.cleanupProgressRequestId = requestId;
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_progress', {
						action: this.selectedCleanupAction,
					}, { resume: false, requireSynoToken: false });
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
				},
				{
					force,
					maxErrors: 3,
					onStopAfterErrors: (err) => {
						this.stopCleanupProgressPolling();
						this.cleanupLoading = false;
						this.cleanupStatusMessage = `Error: ${err.message}`;
						this.cleanupProgress = {
							...(this.cleanupProgress || {}),
							message: `Error: ${err.message}`,
						};
					},
				}
			);
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
			this.stopCleanupProgressPolling();
			this.cleanupProgressRequestId += 1;
			this.cleanupLoading = true;
			this.cleanupProgress = {
				running: true,
				action: this.selectedCleanupAction,
				message: this.$avt('cleanup:status_preparing', 'Cleanup starts. Preparing run...'),
			};
			this.cleanupStatusMessage = this.$avt('cleanup:status_preparing', 'Cleanup starts. Preparing run...');
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
				this.cleanupProgress = {
					...(this.cleanupProgress || {}),
					running: false,
					status: 'failed',
					message: `Error: ${err.message}`,
				};
				this.cleanupStatusMessage = `Error: ${err.message}`;
			}
		},
		async stopCleanupRun() {
			try {
				await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_stop', {
					action: this.selectedCleanupAction,
				}, { resume: false, requireSynoToken: false });
			} catch (err) {
				// Best effort.
			}
			this.cleanupStatusMessage = this.$avt('cleanup:progress_stopping', 'Cleanup is stopping...');
			await this.fetchCleanupProgress();
		},
		getCleanupTargetLabel(target) {
			const key = String(target || '').trim().toUpperCase();
			if (key === 'ACD') {
				return this.$avt('cleanup:target_acd', 'ACDSee');
			}
			if (key === 'MICROSOFT') {
				return this.$avt('cleanup:target_microsoft', 'Microsoft');
			}
			if (key === 'MWG_REGIONS') {
				return this.$avt('cleanup:target_mwg_regions', 'MWG regions');
			}
			return key;
		},
		getCleanupStatusHeadline() {
			const progress = this.cleanupProgress && typeof this.cleanupProgress === 'object'
				? this.cleanupProgress
				: {};
			const key = String(progress.message_key || '').trim();
			if (key === 'cleanup:progress_checking_person') {
				return this.$avt('cleanup:progress_checking_person_short', 'Checking person...');
			}
			if (key === 'cleanup:progress_checking_file') {
				return this.$avt('cleanup:progress_checking_file_short', 'Checking file...');
			}
			return this.cleanupStatusMessage;
		},
		getCleanupProgressStatus(kind) {
			const progress = this.cleanupProgress && typeof this.cleanupProgress === 'object'
				? this.cleanupProgress
				: {};
			const key = String(progress.message_key || '').trim();
			const headline = this.getCleanupStatusHeadline();
			if (kind === 'persons') {
				if (key === 'cleanup:progress_checking_person') {
					return headline;
				}
				if (!key && !(Number(progress.total_files) > 0)) {
					return headline;
				}
				return '';
			}
			if (kind === 'files') {
				if (key === 'cleanup:progress_checking_file') {
					return headline;
				}
				if (key !== 'cleanup:progress_checking_person' && Number(progress.total_files) > 0) {
					return headline;
				}
			}
			return '';
		},
	},
};
