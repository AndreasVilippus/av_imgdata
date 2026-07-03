export default {
	data() {
		return {
			statusLoading: false,
			statusLoaded: false,
			fileAnalysisProgress: {},
			fileAnalysisProgressTimer: null,
			fileAnalysisProgressRequestId: 0,
			statusInsightFaceStatus: {},
			statusInsightFaceLoading: false,
			persons: {
				total: 0,
				known: 0,
				unknown: 0,
				visibleTotal: 0,
				visibleKnown: 0,
				visibleUnknown: 0,
				hiddenTotal: 0,
				hiddenKnown: 0,
				hiddenUnknown: 0,
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
		this.fetchStatusInsightFaceStatus();
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
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_progress', {}, { resume: false, requireSynoToken: false });
				if (this.fileAnalysisProgressRequestId !== requestId) {
					return {};
				}
				const progress = this.getResponseData(data);
				if (!this.isFileAnalysisProgressUpdateStale(this.fileAnalysisProgress, progress)) {
					this.fileAnalysisProgress = progress;
				}
				if (!this.isFileAnalysisRunning) {
					this.stopFileAnalysisProgressPolling();
				}
				return progress;
			} catch (err) {
				if (this.fileAnalysisProgressRequestId !== requestId) {
					return {};
				}
				this.fileAnalysisProgress = {
					...(this.fileAnalysisProgress || {}),
					message: `Error: ${err.message}`,
				};
				return {};
			}
		},
		async fetchExiftoolStatus() {
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/exiftool_status', {}, { resume: false, requireSynoToken: false });
				this.exiftoolStatus = this.getResponseData(data);
			} catch (err) {
				this.fileAnalysisProgress = {
					...(this.fileAnalysisProgress || {}),
					running: false,
					finished: true,
					status: 'failed',
					message: `Error: ${err.message}`,
				};
				this.output = `Error: ${err.message}`;
			}
		},
		async fetchStatusInsightFaceStatus() {
			this.statusInsightFaceLoading = true;
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/insightface_status', {}, { resume: false, requireSynoToken: false, timeoutMs: 120000 });
				this.statusInsightFaceStatus = this.getResponseData(data);
			} catch (err) {
				this.statusInsightFaceStatus = {
					error: err && err.message ? err.message : String(err || ''),
				};
			} finally {
				this.statusInsightFaceLoading = false;
			}
		},
		getStatusInsightFaceEntries() {
			const root = this.statusInsightFaceStatus && typeof this.statusInsightFaceStatus === 'object'
				? this.statusInsightFaceStatus
				: {};
			const insightFace = root.insightface && typeof root.insightface === 'object' ? { INSIGHTFACE: root.insightface } : {};
			return Object.entries(insightFace)
				.map(([key, value]) => ({
					key,
					...(value && typeof value === 'object' ? value : {}),
				}))
				.sort((left, right) => String(left.label || left.key).localeCompare(String(right.label || right.key)));
		},
		getStatusInsightFaceStatusBlocks(packageStatus) {
			return packageStatus && Array.isArray(packageStatus.status_blocks)
				? packageStatus.status_blocks.filter((block) => block && typeof block === 'object')
				: [];
		},
		getStatusInsightFaceStatusBlockLabel(block) {
			const labelKey = String(block && block.label_key || '').trim();
			const fallback = String(block && (block.fallback_label || block.key) || '').trim();
			return labelKey ? this.$avt(labelKey, fallback) : fallback;
		},
		getStatusInsightFaceStatusBlockValue(block) {
			const value = block && Object.prototype.hasOwnProperty.call(block, 'value') ? block.value : '';
			const text = String(value ?? '').trim();
			return text || this.$avt('status:not_available', 'Not available');
		},
		getPerlStatusValue() {
			const perlInfo = this.exiftoolStatus && typeof this.exiftoolStatus === 'object'
				? this.exiftoolStatus.perl
				: null;
			if (perlInfo && perlInfo.available && perlInfo.version) {
				return String(perlInfo.version);
			}
			if (perlInfo && perlInfo.available) {
				return this.$avt('status:yes', 'Yes');
			}
			return this.$avt('status:not_available', 'Not available');
		},
		startFileAnalysisProgressPolling() {
			this.startNamedPolling('fileAnalysisProgressTimer', () => {
				this.fetchFileAnalysisProgress();
			}, 1000, { skipIfPending: true });
		},
		stopFileAnalysisProgressPolling() {
			this.stopNamedPolling('fileAnalysisProgressTimer');
		},
		getFileAnalysisStatusCounterLabel(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const labelKey = String(counter.label_key || '').trim();
			const fallback = String(counter.fallback_label || counter.key || '').trim();
			return labelKey ? this.$avt(labelKey, fallback) : fallback;
		},
		getFileAnalysisStatusCounters() {
			const progress = this.fileAnalysisProgress && typeof this.fileAnalysisProgress === 'object'
				? this.fileAnalysisProgress
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
						label: this.getFileAnalysisStatusCounterLabel(counter),
						value: Math.max(0, Number(counter.value) || 0),
					}))
					.filter((counter) => counter.key);
			}
			return [];
		},
		getFileAnalysisStatusProgress() {
			const progress = this.fileAnalysisProgress && typeof this.fileAnalysisProgress === 'object'
				? this.fileAnalysisProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && status.progress && typeof status.progress === 'object') {
				return status.progress;
			}
			const legacy = progress.analysis_progress && typeof progress.analysis_progress === 'object'
				? progress.analysis_progress
				: {};
			if (Number(legacy.total) > 0) {
				return {
					kind: 'files',
					current: Number(legacy.current) || 0,
					total: Number(legacy.total) || 0,
					title_key: 'status:files_matched',
					fallback_title: 'Matching files',
					primary_label_key: 'status:files_analyzed',
					fallback_primary_label: 'Analyzed',
					secondary_label_key: 'status:files_to_analyze',
					fallback_secondary_label: 'to analyze',
				};
			}
			return {};
		},
		getFileAnalysisStatusProgressTitle() {
			const progress = this.getFileAnalysisStatusProgress();
			return progress.title_key ? this.$avt(progress.title_key, progress.fallback_title || progress.kind) : (progress.fallback_title || progress.kind || '');
		},
		getFileAnalysisStatusProgressPrimaryLabel() {
			const progress = this.getFileAnalysisStatusProgress();
			const fallback = String(progress.fallback_primary_label || '').replace(':', '').toLowerCase();
			return progress.primary_label_key ? this.$avt(progress.primary_label_key, fallback).replace(':', '').toLowerCase() : fallback;
		},
		getFileAnalysisStatusProgressSecondaryLabel() {
			const progress = this.getFileAnalysisStatusProgress();
			return progress.secondary_label_key ? this.$avt(progress.secondary_label_key, progress.fallback_secondary_label || '') : (progress.fallback_secondary_label || '');
		},
		formatFileAnalysisStatusCounter(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const label = String(counter.label || counter.key || '').replace(/:$/, '').trim();
			const value = Math.max(0, Number(counter.value) || 0);
			return label ? `${label}: ${value}` : String(value);
		},
		isFileAnalysisProgressUpdateStale(current, next) {
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

			if (current.message_key) {
				return this.$avt(
					String(current.message_key),
					current.message || String(current.message_key),
					current.message_params && typeof current.message_params === 'object'
						? current.message_params
						: null
				);
			}
			if (current.stop_requested) {
				return this.$avt('status:analyze_stopping', 'Stopping file analysis...');
			}
			if (current.running && current.phase === 'discovery') {
				return this.$avt('status:progress_discovery_running', 'Scanning files...');
			}
			if (current.running && current.phase === 'analysis') {
				return this.$avt('status:progress_analysis_running', 'Analyzing face metadata...');
			}
			if (current.status === 'stopped' && current.phase === 'discovery') {
				return this.$avt('status:progress_discovery_stopped', 'Discovery stopped.');
			}
			if (current.status === 'stopped' && current.phase === 'analysis') {
				return this.$avt('status:progress_analysis_stopped', 'Analysis stopped.');
			}
			if (current.status === 'finished' && current.phase === 'analysis') {
				return this.$avt('status:progress_analysis_finished', 'Analysis finished.');
			}
			if (current.status === 'failed' && !current.shared_folder) {
				return this.$avt('status:progress_shared_folder_missing', 'Shared folder not found.');
			}
			if (current.status === 'failed') {
				return this.$avt('status:progress_analysis_failed', 'File analysis failed.');
			}
			return current.message || this.$avt('status:analyze_idle', 'No file analysis has been started yet.');
		},
		getFileAnalysisWarningMessage(progress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			if (!this.hasAnalysisCheckValue(current.files_with_dimension_issues)) {
				return '';
			}
			const mismatchCount = Number(current.files_with_mwg_dimension_mismatch) || 0;
			const orientationRiskCount = Number(current.files_with_mwg_orientation_transform_risk) || 0;
			if (mismatchCount > 0 && orientationRiskCount > 0) {
				return this.$avt(
					'status:warning_mwg_mismatch_and_orientation',
					'Warning: {mismatch} files with MWG dimension mismatches and {risk} files with MWG orientation transform risk were found.',
					{ mismatch: mismatchCount, risk: orientationRiskCount }
				);
			}
			if (mismatchCount > 0) {
				return this.$avt(
					'status:warning_mwg_mismatch',
					'Warning: {count} files with MWG dimension mismatches were found.',
					{ count: mismatchCount }
				);
			}
			if (orientationRiskCount > 0) {
				return this.$avt(
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
				visibleTotal: Math.max(Number(personsSource.visible_total) || 0, 0),
				visibleKnown: Math.max(Number(personsSource.visible_known) || 0, 0),
				visibleUnknown: Math.max(Number(personsSource.visible_unknown) || 0, 0),
				hiddenTotal: Math.max(Number(personsSource.hidden_total) || 0, 0),
				hiddenKnown: Math.max(Number(personsSource.hidden_known) || 0, 0),
				hiddenUnknown: Math.max(Number(personsSource.hidden_unknown) || 0, 0),
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
					const data = await this.callDsmApi(apiPath, {}, { resume: false, requireSynoToken: false });
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
					await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_stop', {}, { resume: false, requireSynoToken: false });
					this.output = this.$avt('status:analyze_stopping', 'Stopping file analysis...');
					await this.fetchFileAnalysisProgress();
					return;
				}
				this.stopFileAnalysisProgressPolling();
				this.fileAnalysisProgressRequestId += 1;
				this.fileAnalysisProgress = {
					running: true,
					finished: false,
					phase: 'discovery',
					message: this.$avt('status:progress_discovery_running', 'Scanning files...'),
				};
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
