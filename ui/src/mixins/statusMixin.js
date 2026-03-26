export default {
	data() {
		return {
			statusLoading: false,
			statusLoaded: false,
			fileAnalysisProgress: {},
			fileAnalysisProgressTimer: null,
			fileAnalysisProgressRequestId: 0,
			persons: {
				total: 0,
				known: 0,
				unknown: 0,
				mappings: 0,
			},
			system: {
				sharedFolder: '',
			},
			exiftoolStatus: {},
			personsIconUrl: '/webman/3rdparty/AV_ImgData/images/persons_known_unknown.png',
		};
	},
	computed: {
		isFileAnalysisRunning() {
			const progress = this.fileAnalysisProgress && typeof this.fileAnalysisProgress === 'object' ? this.fileAnalysisProgress : {};
			return !!progress.running && !progress.finished;
		},
		hasLocalExiftool() {
			return !!(this.exiftoolStatus && this.exiftoolStatus.local && this.exiftoolStatus.local.found);
		},
		knownRatioPercent() {
			if (!this.persons.total) {
				return 0;
			}
			return Math.max(0, Math.min(100, (this.persons.known / this.persons.total) * 100));
		},
	},
	mounted() {
		this.getStatus({ auto: true });
		this.fetchFileAnalysisProgress();
		this.fetchExiftoolStatus();
	},
	beforeDestroy() {
		this.stopFileAnalysisProgressPolling();
	},
	methods: {
		async refreshFileAnalysisSessionState() {
			await this.fetchFileAnalysisProgress();
			const progress = this.fileAnalysisProgress && typeof this.fileAnalysisProgress === 'object'
				? this.fileAnalysisProgress
				: {};
			if (progress.running) {
				this.startFileAnalysisProgressPolling();
			}
		},
		async fetchFileAnalysisProgress() {
			const requestId = this.fileAnalysisProgressRequestId + 1;
			this.fileAnalysisProgressRequestId = requestId;
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_progress');
				if (this.fileAnalysisProgressRequestId !== requestId) {
					return;
				}
				this.fileAnalysisProgress = this.getResponseData(data);
				if (!this.isFileAnalysisRunning) {
					this.stopFileAnalysisProgressPolling();
				}
			} catch (err) {
				this.stopFileAnalysisProgressPolling();
			}
		},
		async fetchExiftoolStatus() {
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_status');
				this.exiftoolStatus = this.getResponseData(data);
			} catch (err) {
				this.exiftoolStatus = {};
			}
		},
		getPerlStatusValue() {
			const perlInfo = this.exiftoolStatus && typeof this.exiftoolStatus === 'object'
				? this.exiftoolStatus.perl
				: null;
			if (perlInfo && perlInfo.available && perlInfo.version) {
				return String(perlInfo.version);
			}
			if (perlInfo && perlInfo.available) {
				return this.$t('status:yes', 'Yes');
			}
			return this.$t('status:not_available', 'Not available');
		},
		startFileAnalysisProgressPolling() {
			this.stopFileAnalysisProgressPolling();
			this.fetchFileAnalysisProgress();
			this.fileAnalysisProgressTimer = window.setInterval(() => {
				this.fetchFileAnalysisProgress();
			}, 1000);
		},
		stopFileAnalysisProgressPolling() {
			if (this.fileAnalysisProgressTimer) {
				window.clearInterval(this.fileAnalysisProgressTimer);
				this.fileAnalysisProgressTimer = null;
			}
		},
		formatAnalysisCountSummary(counterMap, kind) {
			if (!counterMap || typeof counterMap !== 'object') {
				return '-';
			}
			const entries = Object.entries(counterMap)
				.filter(([, value]) => Number(value) > 0)
				.sort((left, right) => String(left[0]).localeCompare(String(right[0])));
			if (!entries.length) {
				return '-';
			}
			return entries.map(([key, value]) => {
				const label = kind === 'source'
					? this.getFaceMatchSourceLabel(key)
					: (kind === 'format' ? this.getFaceMatchFormatLabel(key) : String(key));
				return `${label}: ${value}`;
			}).join(', ');
		},
		formatAnalysisTimestamp(value) {
			if (!value) {
				return '-';
			}
			const parsed = new Date(value);
			if (Number.isNaN(parsed.getTime())) {
				return String(value);
			}
			return parsed.toLocaleString();
		},
		hasAnalysisCheckValue(value) {
			return value !== null && value !== undefined && !Number.isNaN(Number(value));
		},
		getFileAnalysisStatusMessage(progress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			const analyzed = Number(current.files_analyzed) || 0;
			const total = Number(current.files_matched_total) || 0;

			if (current.stop_requested) {
				return this.$t('status:analyze_stopping', 'Stopping file analysis...');
			}
			if (current.running && current.phase === 'discovery') {
				return this.$t('status:progress_discovery_running', 'Scanning files...');
			}
			if (current.running && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_running',
					'Analyzing face metadata... {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'stopped' && current.phase === 'discovery') {
				return this.$t(
					'status:progress_discovery_stopped',
					'Discovery stopped. 0 of {total} files analyzed.',
					{ total }
				);
			}
			if (current.status === 'stopped' && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_stopped',
					'Analysis stopped. {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'finished' && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_finished',
					'Analysis finished. {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'failed' && !current.shared_folder) {
				return this.$t('status:progress_shared_folder_missing', 'Shared folder not found.');
			}
			if (current.status === 'failed') {
				return this.$t('status:progress_analysis_failed', 'File analysis failed.');
			}
			return current.message || this.$t('status:analyze_idle', 'No file analysis has been started yet.');
		},
		getFileAnalysisWarningMessage(progress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			if (!this.hasAnalysisCheckValue(current.files_with_dimension_issues)) {
				return '';
			}
			const mismatchCount = Number(current.files_with_mwg_dimension_mismatch) || 0;
			const orientationRiskCount = Number(current.files_with_mwg_orientation_transform_risk) || 0;
			if (mismatchCount > 0 && orientationRiskCount > 0) {
				return this.$t(
					'status:warning_mwg_mismatch_and_orientation',
					'Warning: {mismatch} files with MWG dimension mismatches and {risk} files with MWG orientation transform risk were found.',
					{ mismatch: mismatchCount, risk: orientationRiskCount }
				);
			}
			if (mismatchCount > 0) {
				return this.$t(
					'status:warning_mwg_mismatch',
					'Warning: {count} files with MWG dimension mismatches were found.',
					{ count: mismatchCount }
				);
			}
			if (orientationRiskCount > 0) {
				return this.$t(
					'status:warning_mwg_orientation_risk',
					'Warning: {count} files with MWG orientation transform risk were found.',
					{ count: orientationRiskCount }
				);
			}
			return '';
		},
		extractPersonsFromPayload(payload) {
			const data = this.getResponseData(payload);
			const personsSource = (data.persons && typeof data.persons === 'object') ? data.persons : {};
			const total = Number(personsSource.total) || 0;
			const known = Number(personsSource.known) || 0;
			const unknown = Number(personsSource.unknown) || Math.max(total - known, 0);
			return {
				total: Math.max(total, 0),
				known: Math.max(known, 0),
				unknown: Math.max(unknown, 0),
				mappings: Math.max(Number(personsSource.mappings) || 0, 0),
			};
		},
		extractSystemFromPayload(payload) {
			const data = this.getResponseData(payload);
			const systemSource = (data.system && typeof data.system === 'object') ? data.system : {};
			return {
				sharedFolder: String(systemSource.shared_folder || ''),
			};
		},
		async callStatusApi(apiPath, { auto = false, updatePersons = true } = {}) {
			this.statusLoading = true;
			if (!auto) {
				this.output = 'start synocredential resume flow...';
			}
			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch(apiPath, {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(backendError);
				}
				if (updatePersons) {
					this.persons = this.extractPersonsFromPayload(data);
					this.system = this.extractSystemFromPayload(data);
					this.statusLoaded = true;
				}
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				this.output = `Error: ${err.message}`;
			} finally {
				this.statusLoading = false;
			}
		},
		async getStatus(options = {}) {
			return this.callStatusApi('/webman/3rdparty/AV_ImgData/index.cgi/api/status', options);
		},
		async handleFilesAnalyze() {
			try {
				const current = this.isFileAnalysisRunning;
				if (current) {
					await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_stop');
					this.output = this.$t('status:analyze_stopping', 'Stopping file analysis...');
					await this.fetchFileAnalysisProgress();
					return;
				}
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_start');
				this.fileAnalysisProgress = this.getResponseData(data);
				if (this.fileAnalysisProgress && this.fileAnalysisProgress.running) {
					this.startFileAnalysisProgressPolling();
				}
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				this.output = `Error: ${err.message}`;
			}
		},
	},
};
