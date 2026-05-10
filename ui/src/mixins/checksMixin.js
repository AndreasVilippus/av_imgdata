export default {
	data() {
		return {
			selectedChecksType: 'dimension_issues',
			selectedChecksAction: 'findings',
			checksSaveOnly: false,
			checksAutoApplySuggestedNames: false,
			checksAutoApplySuggestedDuplicates: false,
			checksLoading: false,
			checksStartRequestInFlight: false,
			checksStopRequestInFlight: false,
			checksStopRequested: false,
			checksFindingsActionRunning: false,
			checksEntries: [],
			checksCurrentIndex: 0,
			checksStatusMessage: '',
			checksCurrentItem: null,
			checksActionLocked: false,
			checksProgress: {},
			checksProgressTimer: null,
			checksProgressRequestId: 0,
			checksSessionSyncing: false,
			checksSkipNameMappingConfirm: false,
			checksFindingsStatusLoaded: false,
			checksFindingsStatus: {},
			checksDuplicateAssignments: {
				left: this.createChecksDuplicateAssignmentState(),
				right: this.createChecksDuplicateAssignmentState(),
			},
		};
	},
	computed: {
		isChecksScanRunning() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			const progressType = String(progress.check_type || '').trim().toLowerCase();
			return !!progress.running
				&& String(progress.source_mode || '').trim().toLowerCase() === 'scan'
				&& progressType !== '__never__';
		},
		isChecksFindingsActionRunning() {
			return this.selectedChecksAction === 'findings'
				&& !!this.checksFindingsActionRunning;
		},
		isChecksReviewStopping() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			return !!(
				this.checksStopRequested
				|| this.checksStopRequestInFlight
				|| (progress.running && progress.stop_requested)
			);
		},
		isChecksReviewActive() {
			return !!(
				this.isChecksScanRunning
				|| this.isChecksFindingsActionRunning
				|| this.checksStartRequestInFlight
				|| (this.selectedChecksAction === 'findings' && this.checksLoading)
			);
		},
		checksCanRestartSavedScan() {
			return !!(
				this.selectedChecksAction === 'scan'
				&& this.checksSaveOnly
				&& !this.isChecksReviewActive
				&& !this.isChecksReviewStopping
				&& !this.checksLoading
			);
		},
		checksPrimaryButtonLabel() {
			if (this.isChecksReviewActive || this.isChecksReviewStopping) {
				return this.$avt('checks:button_stop', 'Stop');
			}
			if (this.checksLoading) {
				return this.$avt('checks:button_loading', 'Loading...');
			}
			if (this.checksCanRestartSavedScan) {
				return this.$avt('checks:button_restart', 'Restart');
			}
			return this.$avt('checks:button_start', 'Start');
		},
		shouldShowChecksScanProgressCard() {
			return !!(
				this.isChecksScanRunning
				|| (
					this.selectedChecksAction === 'scan'
					&& (
						this.checksLoading
						|| (this.checksProgress && Object.keys(this.checksProgress).length)
					)
				)
			);
		},
		shouldShowChecksListProgressCard() {
			return this.selectedChecksAction !== 'scan' && this.checksEntries.length > 0;
		},
		shouldShowChecksStandaloneStatusMessage() {
			return !this.shouldShowChecksScanProgressCard
				&& !this.shouldShowChecksListProgressCard;
		},
		hasNextChecksItem() {
			if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
				return !!this.checksCurrentItem;
			}
			return this.checksCurrentIndex + 1 < this.checksEntries.length;
		},
		checksStoredFindingsCount() {
			const statuses = this.checksFindingsStatus && typeof this.checksFindingsStatus === 'object'
				? this.checksFindingsStatus
				: {};
			const current = statuses[String(this.selectedChecksType || '').trim().toLowerCase()];
			return Math.max(0, Number(current && current.count) || 0);
		},
		hasChecksStoredFindings() {
			return this.checksStoredFindingsCount > 0;
		},
	},
	watch: {
		selectedChecksAction(nextAction) {
			if (nextAction !== 'scan') {
				this.checksSaveOnly = false;
			}
			this.checksProgressRequestId += 1;
			if (!this.checksLoading && !this.checksSessionSyncing) {
				this.resetChecksUiState();
			}
		},
		selectedChecksType() {
			this.checksProgressRequestId += 1;
			if (!this.checksLoading && !this.checksSessionSyncing) {
				this.resetChecksUiState();
			}
		},
	},
	mounted() {
		this.fetchChecksFindingsStatus();
	},
	beforeDestroy() {
		this.stopChecksProgressPolling();
		this.resetChecksDuplicateAssignmentState();
	},
	methods: {
		resetChecksUiState() {
			this.stopChecksProgressPolling();
			this.checksProgressRequestId += 1;
			this.checksEntries = [];
			this.checksCurrentIndex = 0;
			this.checksCurrentItem = null;
			this.checksActionLocked = false;
			this.checksProgress = {};
			this.checksStatusMessage = '';
			this.checksLoading = false;
			this.checksStartRequestInFlight = false;
			this.checksStopRequestInFlight = false;
			this.checksStopRequested = false;
			this.checksFindingsActionRunning = false;
			this.checksSkipNameMappingConfirm = false;
			this.resetChecksDuplicateAssignmentState();
		},
		async fetchChecksFindingsStatus() {
			try {
				const data = await this.callChecksApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/checks_findings_status',
					{},
					{ resume: false, requireSynoToken: false }
				);
				const root = this.getResponseData(data);
				this.checksFindingsStatus = root.statuses && typeof root.statuses === 'object'
					? root.statuses
					: {};
				this.checksFindingsStatusLoaded = true;
			} catch (err) {
				this.checksFindingsStatus = {};
				this.checksFindingsStatusLoaded = true;
			}
		},
		createChecksDuplicateAssignmentState() {
			return {
				name: '',
				selectedPerson: null,
				suggestions: [],
				suggestLoading: false,
				showSuggestions: false,
				suggestTimer: null,
				suggestRequestId: 0,
			};
		},
		resetChecksDuplicateAssignmentState() {
			for (const side of ['left', 'right']) {
				const current = this.checksDuplicateAssignments && this.checksDuplicateAssignments[side];
				if (current && current.suggestTimer) {
					window.clearTimeout(current.suggestTimer);
				}
			}
			this.checksDuplicateAssignments = {
				left: this.createChecksDuplicateAssignmentState(),
				right: this.createChecksDuplicateAssignmentState(),
			};
		},
		syncChecksDuplicateAssignmentState(item) {
			if (!this.isChecksDuplicateFaces(item)) {
				this.resetChecksDuplicateAssignmentState();
				return;
			}
			this.resetChecksDuplicateAssignmentState();
			this.checksDuplicateAssignments.left.name = String(item && item.left_name || '').trim();
			this.checksDuplicateAssignments.right.name = String(item && item.right_name || '').trim();
		},
		applyChecksProgressUpdate(progress) {
			if (!progress || typeof progress !== 'object') {
				return false;
			}
			const sourceMode = String(progress.source_mode || '').trim().toLowerCase();
			const checkType = String(progress.check_type || '').trim().toLowerCase();
			this.checksProgress = {
				...(this.checksProgress && typeof this.checksProgress === 'object' ? this.checksProgress : {}),
				...progress,
			};
			if (sourceMode === 'scan' && progress.running) {
				if (checkType) {
					this.selectedChecksType = checkType;
				}
				if (this.selectedChecksAction !== 'scan') {
					this.selectedChecksAction = 'scan';
				}
				this.checksLoading = false;
				this.checksStartRequestInFlight = false;
				this.checksFindingsActionRunning = false;
				this.startChecksProgressPolling();
			}
			return true;
		},
		async callChecksApi(apiPath, body = {}, options = {}) {
			const response = await this.callDsmApi(apiPath, body, options);
			const apiPathText = String(apiPath || '');
			if (apiPathText.includes('checks_start') || apiPathText.includes('checks_progress')) {
				try {
					const root = this.getResponseData(response);
					this.applyChecksProgressUpdate(root);
				} catch (err) {
					// Keep the original API response behavior unchanged.
				}
			}
			return response;
		},
		getChecksImageUrl(item) {
			const imagePath = item && item.image_path ? String(item.image_path).trim() : '';
			if (!imagePath) {
				return '';
			}
			return `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(imagePath)}`;
		},
		getChecksDeleteFaceBaseIconUrl() {
			return this.resolveLocalIconUrl('face.png');
		},
		getChecksDeleteFaceOverlayIconUrl() {
			return this.resolveLocalIconUrl('del_icon.png');
		},
		getChecksReplaceRightIconUrl() {
			return this.resolveLocalIconUrl('person_replace_right.png');
		},
		getChecksReplaceLeftIconUrl() {
			return this.resolveLocalIconUrl('person_replace_left.png');
		},
		getChecksPositionRightIconUrl() {
			return this.resolveLocalIconUrl('face_to_right.png');
		},
		getChecksPositionLeftIconUrl() {
			return this.resolveLocalIconUrl('face_to_left.png');
		},
		getChecksSyncFaceBaseIconUrl() {
			return this.resolveLocalIconUrl('person_known.png');
		},
		getChecksSyncFaceOverlayIconUrl() {
			return this.resolveLocalIconUrl('sync_icon.png');
		},
		getChecksProgressIconUrl() {
			if (String(this.selectedChecksType || '').trim().toLowerCase() === 'name_conflicts') {
				return this.resolveLocalIconUrl('persons_conflict.png');
			}
			return '';
		},
		getChecksTypeOptions() {
			return ['dimension_issues', 'duplicate_faces', 'position_deviations', 'name_conflicts'];
		},
		isChecksMetadataFace(face) {
			const sourceFormat = String(face && face.source_format || '').trim().toUpperCase();
			return ['ACD', 'MICROSOFT', 'MWG_REGIONS'].includes(sourceFormat);
		},
		isChecksPhotosFace(face) {
			return String(face && face.source_format || '').trim().toUpperCase() === 'PHOTOS';
		},
		canDeleteChecksFace(item, face) {
			return !this.checksActionLocked
				&& !!(item && item.image_path)
				&& this.isChecksMetadataFace(face);
		},
		isChecksDuplicateFaces(item) {
			return !!(item && item.review_type === 'duplicate_faces');
		},
		isChecksNameConflict(item) {
			return !!(item && item.review_type === 'name_conflicts');
		},
		isChecksPositionDeviation(item) {
			return !!(item && item.review_type === 'position_deviations');
		},
		canReplaceChecksFaceName(item, face, newName) {
			return !this.checksActionLocked
				&& this.isChecksNameConflict(item)
				&& !!(item && item.image_path)
				&& !!(face && typeof face === 'object' && face.source_format)
				&& !!String(newName || '').trim();
		},
		canReplaceChecksFacePosition(item, face, sourceFace) {
			return !this.checksActionLocked
				&& this.isChecksPositionDeviation(item)
				&& !!(item && item.image_path)
				&& this.isChecksMetadataFace(face)
				&& !!(sourceFace && typeof sourceFace === 'object' && sourceFace.source_format);
		},
		canIgnoreChecksItem(item = this.checksCurrentItem) {
			const reviewType = String(item && item.review_type || '').trim().toLowerCase();
			return ['duplicate_faces', 'position_deviations', 'name_conflicts'].includes(reviewType);
		},
		getCurrentChecksEntry() {
			if (this.selectedChecksAction === 'scan') {
				const progress = this.checksProgress && typeof this.checksProgress === 'object'
					? this.checksProgress
					: {};
				const result = progress.result && typeof progress.result === 'object'
					? progress.result
					: {};
				return result.entry && typeof result.entry === 'object' ? result.entry : null;
			}
			const entry = this.checksEntries[this.checksCurrentIndex];
			return entry && typeof entry === 'object' ? entry : null;
		},
		getChecksDuplicateAssignment(side) {
			return this.checksDuplicateAssignments && this.checksDuplicateAssignments[side]
				? this.checksDuplicateAssignments[side]
				: this.createChecksDuplicateAssignmentState();
		},
		handleChecksDuplicateNameFocus(side) {
			const state = this.getChecksDuplicateAssignment(side);
			if (state.suggestions.length) {
				state.showSuggestions = true;
			}
		},
		handleChecksDuplicateNameInput(side) {
			const state = this.getChecksDuplicateAssignment(side);
			const selectedPerson = state.selectedPerson;
			if (selectedPerson && this.normalizeFaceMatchName(state.name) !== this.normalizeFaceMatchName(selectedPerson.name)) {
				state.selectedPerson = null;
			}
			this.scheduleChecksDuplicateSuggestions(side);
		},
		scheduleChecksDuplicateSuggestions(side) {
			const state = this.getChecksDuplicateAssignment(side);
			if (state.suggestTimer) {
				window.clearTimeout(state.suggestTimer);
				state.suggestTimer = null;
			}
			const query = String(state.name || '').trim();
			if (!query) {
				state.suggestions = [];
				state.showSuggestions = false;
				state.suggestLoading = false;
				return;
			}
			state.suggestTimer = window.setTimeout(() => {
				this.fetchChecksDuplicateSuggestions(side, query);
			}, 200);
		},
		async fetchChecksDuplicateSuggestions(side, query) {
			const state = this.getChecksDuplicateAssignment(side);
			const currentQuery = String(query || '').trim();
			if (!currentQuery) {
				state.suggestions = [];
				state.showSuggestions = false;
				state.suggestLoading = false;
				return;
			}
			const requestId = state.suggestRequestId + 1;
			state.suggestRequestId = requestId;
			state.suggestLoading = true;
			state.showSuggestions = true;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_person_suggest', {
					name_prefix: currentQuery,
					limit: 10,
				});
				if (state.suggestRequestId !== requestId) {
					return;
				}
				const root = this.getResponseData(data);
				state.suggestions = Array.isArray(root.list) ? root.list : [];
				state.showSuggestions = state.suggestions.length > 0;
			} catch (err) {
				if (state.suggestRequestId !== requestId) {
					return;
				}
				state.suggestions = [];
				state.showSuggestions = false;
			} finally {
				if (state.suggestRequestId === requestId) {
					state.suggestLoading = false;
				}
			}
		},
		selectChecksDuplicateSuggestion(side, person) {
			if (!person || !person.id) {
				return;
			}
			const state = this.getChecksDuplicateAssignment(side);
			state.selectedPerson = person;
			state.name = person.name || '';
			state.suggestions = [];
			state.showSuggestions = false;
			state.suggestLoading = false;
		},
		canAssignChecksFaceToPerson(item, side) {
			if (!this.isChecksDuplicateFaces(item) || this.checksActionLocked || this.checksLoading || !item || !item.image_path) {
				return false;
			}
			const state = this.getChecksDuplicateAssignment(side);
			return !!(state.selectedPerson && state.selectedPerson.id && String(state.name || '').trim());
		},
		showChecksPopup(message) {
			if (typeof window !== 'undefined' && typeof window.alert === 'function') {
				window.alert(message);
			}
		},
		getChecksWarningPopupMessage(result) {
			const warning = String(result && result.warning || '').trim();
			if (warning === 'checks:warning_exiftool_required') {
				return this.$avt(
					'checks:popup_exiftool_required',
					'ExifTool is missing, but required for this action. Please configure or install ExifTool first.'
				);
			}
			if (warning === 'checks:warning_target_person_not_found') {
				const details = result && typeof result.details === 'object' ? result.details : {};
				return this.$avt(
					'checks:popup_target_person_not_found',
					'No Photos person could be found for "{name}".',
					{ name: details.requested_name || details.lookup_name || '' }
				);
			}
			const details = result && typeof result.details === 'object' ? result.details : null;
			const stderr = String(details && details.stderr || '').trim();
			const stdout = String(details && details.stdout || '').trim();
			const errorCode = String(details && details.error || '').trim();
			const returncode = Number(details && details.returncode);
			if (stderr || stdout || errorCode) {
				const parts = [];
				if (errorCode) {
					parts.push(this.$avt('checks:popup_error_code', 'Error code: {code}', { code: errorCode }));
				}
				if (Number.isFinite(returncode)) {
					parts.push(this.$avt('checks:popup_return_code', 'Return code: {code}', { code: returncode }));
				}
				if (stderr) {
					parts.push(this.$avt('checks:popup_error_stderr', 'Error output:\n{output}', { output: stderr }));
				} else if (stdout) {
					parts.push(this.$avt('checks:popup_error_stdout', 'Command output:\n{output}', { output: stdout }));
				}
				return this.$avt(
					'checks:popup_action_failed_details',
					'The metadata action failed.\n\n{details}',
					{ details: parts.join('\n\n') }
				);
			}
			return '';
		},
		getChecksReplaceRightTooltip(item) {
			if (this.isChecksPositionDeviation(item)) {
				return this.$avt(
					'checks:tooltip_replace_right_position',
					'The face on the right takes the position from the left.'
				);
			}
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			const rightFace = item && item.right_face_target;
			if (this.isChecksPhotosFace(rightFace)) {
				return this.$avt(
					'checks:tooltip_assign_right_name',
					'The Photos face on the right is assigned to the person from the left, or the person is created if missing: {from} -> {to}',
					{ from: rightName, to: leftName }
				);
			}
			return this.$avt(
				'checks:tooltip_replace_right_name',
				'The face on the right gets the name from the left: {from} -> {to}',
				{ from: rightName, to: leftName }
			);
		},
		getChecksReplaceLeftTooltip(item) {
			if (this.isChecksPositionDeviation(item)) {
				return this.$avt(
					'checks:tooltip_replace_left_position',
					'The face on the left takes the position from the right.'
				);
			}
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			const leftFace = item && item.left_face_target;
			if (this.isChecksPhotosFace(leftFace)) {
				return this.$avt(
					'checks:tooltip_assign_left_name',
					'The Photos face on the left is assigned to the person from the right, or the person is created if missing: {from} -> {to}',
					{ from: leftName, to: rightName }
				);
			}
			return this.$avt(
				'checks:tooltip_replace_left_name',
				'The face on the left gets the name from the right: {from} -> {to}',
				{ from: leftName, to: rightName }
			);
		},
		checksRenameUsesStoredMapping(item, face, newName) {
			if (!this.isChecksNameConflict(item) || !face || !newName) {
				return false;
			}
			const faceName = String(face.name || '').trim();
			const targetName = String(newName || '').trim();
			if (!faceName || !targetName) {
				return false;
			}
			const leftName = String(item.left_name || '').trim();
			const rightName = String(item.right_name || '').trim();
			const faceFormat = String(face.source_format || '').trim().toUpperCase();
			const leftFormat = String(item.left_format || '').trim().toUpperCase();
			const rightFormat = String(item.right_format || '').trim().toUpperCase();
			if (faceFormat === rightFormat && faceName === rightName && targetName === leftName) {
				return String(item.left_state || '') === 'suggested';
			}
			if (faceFormat === leftFormat && faceName === leftName && targetName === rightName) {
				return String(item.right_state || '') === 'suggested';
			}
			return false;
		},
		applyChecksFindingsUpdate(findingsUpdate, { resolvedDelta = 0, ignoredDelta = 0, skippedDelta = 0 } = {}) {
			if (!findingsUpdate || typeof findingsUpdate !== 'object') {
				return false;
			}
			const sourceMode = String(findingsUpdate.source_mode || '').trim().toLowerCase();
			if (findingsUpdate.refresh_skipped || findingsUpdate.snapshot_mode || sourceMode === 'snapshot') {
				return false;
			}
			const currentProgress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			const nextResolvedCount = Math.max(0, (Number(currentProgress.resolved_count) || 0) + Math.max(0, Number(resolvedDelta) || 0));
			const nextIgnoredCount = Math.max(0, (Number(currentProgress.ignored_count) || 0) + Math.max(0, Number(ignoredDelta) || 0));
			const nextSkippedCount = Math.max(0, (Number(currentProgress.skipped_count) || 0) + Math.max(0, Number(skippedDelta) || 0));
			const hasFullEntries = Array.isArray(findingsUpdate.entries);
			const hasImageEntries = Array.isArray(findingsUpdate.image_entries);
			if (!hasFullEntries && !hasImageEntries && findingsUpdate.count === undefined) {
				return false;
			}
			if (hasFullEntries) {
				this.checksEntries = findingsUpdate.entries;
			} else if (hasImageEntries) {
				const imagePath = String(findingsUpdate.image_path || '').trim();
				if (imagePath) {
					const replacementEntries = findingsUpdate.image_entries.filter((entry) => entry && typeof entry === 'object');
					const insertAt = this.checksEntries.findIndex((entry) => String(entry && entry.image_path || '').trim() === imagePath);
					this.checksEntries = this.checksEntries.filter((entry) => String(entry && entry.image_path || '').trim() !== imagePath);
					if (replacementEntries.length) {
						const targetIndex = insertAt >= 0 ? insertAt : Math.min(this.checksCurrentIndex, this.checksEntries.length);
						this.checksEntries.splice(targetIndex, 0, ...replacementEntries);
					}
				}
			}
			const findingsCount = Number(
				findingsUpdate.count !== undefined
					? findingsUpdate.count
					: this.checksEntries.length
			);
			if (!this.checksProgress || typeof this.checksProgress !== 'object') {
				this.checksProgress = {};
			}
			this.checksFindingsStatus = {
				...(this.checksFindingsStatus || {}),
				[String(this.selectedChecksType || '').trim().toLowerCase()]: {
					status: String(findingsUpdate.status || ''),
					count: Number.isFinite(findingsCount) ? findingsCount : this.checksEntries.length,
					save_only: !!findingsUpdate.save_only,
				},
			};
			this.checksFindingsStatusLoaded = true;
			this.checksProgress = {
				...this.checksProgress,
				source_mode: 'findings',
				check_type: String(this.selectedChecksType || '').trim().toLowerCase(),
				findings_count: Number.isFinite(findingsCount) ? findingsCount : this.checksEntries.length,
				resolved_count: nextResolvedCount,
				ignored_count: nextIgnoredCount,
				skipped_count: nextSkippedCount,
			};
			if (!this.checksEntries.length) {
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
				this.checksStatusMessage = this.$avt('checks:status_empty', 'No matching entries found.');
				return true;
			}
			this.checksCurrentIndex = Math.min(this.checksCurrentIndex, this.checksEntries.length - 1);
			return true;
		},
		getStatusCounterLabel(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const labelKey = String(counter.label_key || '').trim();
			const fallback = String(counter.fallback_label || counter.key || '').trim();
			return labelKey ? this.$avt(labelKey, fallback) : fallback;
		},
		normalizeStatusCounter(counter) {
			if (!counter || typeof counter !== 'object') {
				return null;
			}
			const key = String(counter.key || '').trim();
			const value = Number(counter.value);
			if (!key || !Number.isFinite(value)) {
				return null;
			}
			if (!counter.show_when_zero && value <= 0) {
				return null;
			}
			return {
				key,
				label: this.getStatusCounterLabel(counter),
				value: Math.max(0, value),
				show_when_zero: !!counter.show_when_zero,
			};
		},
		getChecksStatusProgress() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && status.progress && typeof status.progress === 'object') {
				return status.progress;
			}
			return {};
		},
		getChecksStatusProgressTitle() {
			const progress = this.getChecksStatusProgress();
			return progress.title_key ? this.$avt(progress.title_key, progress.fallback_title || progress.kind) : (progress.fallback_title || progress.kind);
		},
		getChecksStatusProgressPrimaryLabel() {
			const progress = this.getChecksStatusProgress();
			const fallback = String(progress.fallback_primary_label || '').replace(':', '').toLowerCase();
			return progress.primary_label_key ? this.$avt(progress.primary_label_key, fallback).replace(':', '').toLowerCase() : fallback;
		},
		getChecksStatusProgressSecondaryLabel() {
			const progress = this.getChecksStatusProgress();
			return progress.secondary_label_key ? this.$avt(progress.secondary_label_key, progress.fallback_secondary_label || '') : (progress.fallback_secondary_label || '');
		},
		formatChecksStatusCounter(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const label = String(counter.label || this.getStatusCounterLabel(counter) || '').replace(/:$/, '').trim();
			const value = counter.value;
			return label ? `${label}: ${value}` : String(value);
		},
		getChecksCountersStatusSuffix() {
			const counters = this.getRelevantChecksStatusCounters();
			if (!Array.isArray(counters) || !counters.length) {
				return '';
			}
			return counters
				.map((counter) => this.formatChecksStatusCounter(counter))
				.filter(Boolean)
				.join(' · ');
		},
		getChecksSaveOnlyFindingsCount(progress = this.checksProgress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			const sourceMode = String(current.source_mode || '').trim().toLowerCase();
			const isRunningSaveOnlyScan = sourceMode === 'scan' && !!current.running && !!current.save_only;
			const scanValues = [
				Number(current.findings_count),
				Number(current.last_flush_count),
				Number(current.saved_findings_count),
				Number(current.found_count),
			].filter((value) => Number.isFinite(value));
			if (isRunningSaveOnlyScan) {
				return scanValues.length ? Math.max(0, ...scanValues) : 0;
			}
			const values = [
				...scanValues,
				Number(this.checksStoredFindingsCount),
			].filter((value) => Number.isFinite(value));
			return values.length ? Math.max(0, ...values) : 0;
		},
		getChecksProgressStatusText() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object' ? this.checksProgress : {};
			const sourceMode = String(progress.source_mode || '').trim().toLowerCase();
			const action = String(this.selectedChecksAction || '').trim().toLowerCase();
			const isSaveOnlyScan = (action === 'scan' || sourceMode === 'scan') && (this.checksSaveOnly || !!progress.save_only);
			const headline = String(this.getChecksStatusHeadline() || '').trim();
			if (!isSaveOnlyScan) {
				return headline;
			}
			const findings = this.getChecksSaveOnlyFindingsCount(progress);
			const skipped = Math.max(0, Number(progress.skipped_count || progress.skip_count) || 0);
			const findingsLabel = this.$avt('checks:counter_findings', 'Findings').replace(/:$/, '').trim();
			const skippedLabel = this.$avt('checks:counter_skipped', 'Skipped').replace(/:$/, '').trim();
			const parts = [`${findingsLabel}: ${findings}`];
			if (skipped > 0) {
				parts.push(`${skippedLabel}: ${skipped}`);
			}
			const base = headline || this.$avt('checks:status_scan_running', 'Check scan is running.');
			return `${base} | ${parts.join(' | ')}`;
		},
		getRelevantChecksStatusCounters() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && Array.isArray(status.counters)) {
				return status.counters
					.filter((counter) => counter && typeof counter === 'object')
					.filter((counter) => counter.show_when_zero || Number(counter.value) > 0);
			}
			return [];
		},
		getChecksListResolvedCount() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			return (Number(progress.resolved_count) || 0)
				+ (Number(progress.ignored_count) || 0)
				+ (Number(progress.skipped_count) || 0);
		},
		getChecksListTotalCount() {
			return this.checksEntries.length + this.getChecksListResolvedCount();
		},
		getChecksListCurrentCount() {
			if (!this.checksEntries.length) {
				return this.getChecksListResolvedCount();
			}
			return this.getChecksListResolvedCount() + this.checksCurrentIndex + 1;
		},
		matchesSelectedChecksType(value) {
			return String(value || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase();
		},
		async refreshChecksSessionState() {
			const progress = await this.fetchChecksProgress({
				applyFinishedState: true,
				adoptResultItem: true,
				loadResultItem: true,
			});
			const hasProgress = !!(progress && Object.keys(progress).length);
			if (!hasProgress) {
				return;
			}
			const result = progress && progress.result && typeof progress.result === 'object'
				? progress.result
				: null;
			const hasRestorableResult = !!(
				result
				&& (
					(result.item && typeof result.item === 'object' && Object.keys(result.item).length)
					||
					(result.entry && typeof result.entry === 'object' && Object.keys(result.entry).length)
				)
			);
			const matchesCurrentSelection = !!(
				String(progress.source_mode || '').trim().toLowerCase() === 'scan'
				&& String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase()
			);
			if (matchesCurrentSelection && (progress.running || hasRestorableResult)) {
				this.checksSessionSyncing = true;
				try {
					if (this.selectedChecksAction !== 'scan') {
						this.selectedChecksAction = 'scan';
					}
				} finally {
					this.checksSessionSyncing = false;
				}
				this.checksLoading = true;
				this.startChecksProgressPolling();
				return;
			}
			const runningProgress = progress && progress.running
				? progress
				: await this.findRunningChecksScanProgress(String(this.selectedChecksType || '').trim().toLowerCase());
			if (this.adoptRunningChecksScanProgress(runningProgress)) {
				return;
			}
			if (matchesCurrentSelection || !progress.running) {
				this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				this.stopChecksProgressPolling();
			}
		},
		async findRunningChecksScanProgress(skipCheckType = '') {
			const skippedType = String(skipCheckType || '').trim().toLowerCase();
			const checkTypes = this.getChecksTypeOptions().filter((checkType) => checkType !== skippedType);
			for (const checkType of checkTypes) {
				try {
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_progress', {
						check_type: checkType,
					});
					const progress = this.getResponseData(data);
					const isRunningScan = !!(
						progress
						&& progress.running
						&& String(progress.source_mode || '').trim().toLowerCase() === 'scan'
						&& String(progress.check_type || '').trim().toLowerCase() === checkType
					);
					if (isRunningScan) {
						return progress;
					}
				} catch (err) {
					// Ignore unavailable progress for other check types.
				}
			}
			return null;
		},
		adoptRunningChecksScanProgress(progress) {
			const runningProgress = progress && typeof progress === 'object' ? progress : {};
			if (!runningProgress.running || String(runningProgress.source_mode || '').trim().toLowerCase() !== 'scan') {
				return false;
			}
			const runningType = String(runningProgress.check_type || '').trim().toLowerCase();
			if (!this.getChecksTypeOptions().includes(runningType)) {
				return false;
			}
			this.checksSessionSyncing = true;
			try {
				if (runningType !== String(this.selectedChecksType || '').trim().toLowerCase()) {
					this.selectedChecksType = runningType;
				}
				if (this.selectedChecksAction !== 'scan') {
					this.selectedChecksAction = 'scan';
				}
			} finally {
				this.checksSessionSyncing = false;
			}
			this.applyChecksProgress(runningProgress, { adoptResultItem: true });
			this.checksLoading = true;
			this.startChecksProgressPolling();
			return true;
		},
		applyChecksProgress(progress, { adoptResultItem = true } = {}) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			if (nextProgress.check_type && !this.matchesSelectedChecksType(nextProgress.check_type)) {
				return;
			}
			if (this.isChecksProgressUpdateStale(this.checksProgress, nextProgress)) {
				return;
			}
			nextProgress.findings_count = Number(nextProgress.findings_count) || 0;
			nextProgress.resolved_count = Number(nextProgress.resolved_count) || 0;
			nextProgress.ignored_count = Number(nextProgress.ignored_count) || 0;
			this.checksProgress = nextProgress;
			if (nextProgress.running && nextProgress.stop_requested) {
				this.checksStopRequested = true;
				this.checksStopRequestInFlight = false;
			}
			if (!nextProgress.running) {
				this.checksStopRequested = false;
				this.checksStopRequestInFlight = false;
				this.checksStartRequestInFlight = false;
			}
			const result = nextProgress.result && typeof nextProgress.result === 'object'
				? nextProgress.result
				: null;
			const item = result && result.item && typeof result.item === 'object' ? result.item : null;
			if (
				adoptResultItem
				&&
				item
				&& Object.keys(item).length
				&& this.matchesSelectedChecksType(item.review_type)
			) {
				this.checksCurrentItem = item;
				this.syncChecksDuplicateAssignmentState(item);
			} else if (this.selectedChecksAction === 'scan') {
				this.checksCurrentItem = null;
				this.resetChecksDuplicateAssignmentState();
			}
			if (nextProgress.message_key || nextProgress.message) {
				this.checksStatusMessage = this.$avt(
					nextProgress.message_key || '',
					nextProgress.message || '',
					nextProgress.message_params && typeof nextProgress.message_params === 'object'
						? nextProgress.message_params
						: null
				);
			}
		},
		isChecksProgressUpdateStale(current, next) {
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
		async ensureChecksResultItemLoaded(progress) {
			if (this.checksStopRequested) {
				return;
			}
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			if (nextProgress.check_type && !this.matchesSelectedChecksType(nextProgress.check_type)) {
				return;
			}
			const result = nextProgress.result && typeof nextProgress.result === 'object'
				? nextProgress.result
				: null;
			const entry = result && result.entry && typeof result.entry === 'object'
				? result.entry
				: null;
			const item = result && result.item && typeof result.item === 'object'
				? result.item
				: null;
			if (!entry || !this.matchesSelectedChecksType(entry.review_type) || (item && Object.keys(item).length)) {
				return;
			}
			const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_item', {
				entry,
				auto_apply_suggested_names: this.checksAutoApplySuggestedNames,
				auto_apply_suggested_duplicates: this.checksAutoApplySuggestedDuplicates,
			});
			const root = this.getResponseData(data);
			if (this.checksStopRequested || root.stop_requested) {
				this.checksStopRequested = true;
				this.checksStatusMessage = this.$avt('checks:status_stop_requested', 'Stop requested. The current check action will stop shortly.');
				return;
			}
			this.applyChecksFindingsUpdate(root.findings_update);
			const resolvedItem = root && root.item && typeof root.item === 'object' ? root.item : {};
			if (Object.keys(resolvedItem).length && this.matchesSelectedChecksType(resolvedItem.review_type)) {
				this.checksCurrentItem = resolvedItem;
				this.syncChecksDuplicateAssignmentState(resolvedItem);
			}
		},
		async fetchChecksProgress({ applyFinishedState = true, adoptResultItem = true, loadResultItem = true } = {}) {
			const requestId = this.checksProgressRequestId + 1;
			this.checksProgressRequestId = requestId;
			try {
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_progress', {
					check_type: this.selectedChecksType,
				});
				if (this.checksProgressRequestId !== requestId) {
					return {};
				}
				const progress = this.getResponseData(data);
				if (progress.running || applyFinishedState) {
					this.applyChecksProgress(progress, { adoptResultItem });
				}
				if (!progress.running && loadResultItem) {
					await this.ensureChecksResultItemLoaded(progress);
				}
				if (!progress.running) {
					this.checksLoading = false;
					if (this.selectedChecksAction === 'findings') {
						this.checksFindingsActionRunning = false;
					}
					this.stopChecksProgressPolling();
				}
				return progress;
			} catch (err) {
				if (this.checksProgressRequestId !== requestId) {
					return {};
				}
				const progress = this.checksProgress && typeof this.checksProgress === 'object'
					? this.checksProgress
					: {};
				if (!progress.running) {
					this.checksLoading = false;
					if (this.selectedChecksAction === 'findings') {
						this.checksFindingsActionRunning = false;
					}
					this.stopChecksProgressPolling();
				}
				return {};
			}
		},
		startChecksProgressPolling() {
			this.startNamedPolling('checksProgressTimer', () => {
				this.fetchChecksProgress();
			});
		},
		stopChecksProgressPolling() {
			this.stopNamedPolling('checksProgressTimer');
		},
		getChecksStatusHeadline() {
			const progress = this.checksProgress && typeof this.checksProgress === 'object'
				? this.checksProgress
				: {};
			const key = String(progress.message_key || '').trim();
			const openFindings = Number(progress.findings_count) || 0;
			const resolvedNames = Number(progress.resolved_count) || 0;
			const ignoredConflicts = Number(progress.ignored_count) || 0;
			const skippedFindings = Number(progress.skipped_count) || 0;
			const segments = [
				`${this.$avt('checks:label_findings_count', 'Findings:')} ${openFindings}`,
			];
			if (this.selectedChecksType === 'name_conflicts') {
				segments.splice(0, 1);
				segments.push(`${this.$avt('checks:label_resolved_names_count', 'Resolved names:')} ${resolvedNames}`);
				segments.push(`${this.$avt('checks:label_ignored_names_count', 'Ignored conflicts:')} ${ignoredConflicts}`);
				segments.push(`${this.$avt('checks:label_skipped_findings_count', 'Skipped:')} ${skippedFindings}`);
				if (this.selectedChecksAction !== 'scan') {
					return segments.join(' | ');
				}
			}
			const withCounts = (text) => {
				const normalized = String(text || '').trim();
				return normalized ? `${normalized} | ${segments.join(' | ')}` : segments.join(' | ');
			};
			if (key === 'checks:progress_scanning') {
				return withCounts(this.$avt('checks:progress_scanning_short', 'Scanning files...'));
			}
			if (key === 'checks:progress_result_found') {
				return withCounts(this.$avt('checks:progress_result_found_short', 'Check finding found.'));
			}
			if (key === 'checks:progress_findings_saved') {
				return withCounts(this.$avt('checks:progress_findings_saved_short', 'Findings list saved.'));
			}
			return withCounts(this.checksStatusMessage);
		},
		async stopChecksReview() {
			if (this.checksStopRequestInFlight || this.checksStopRequested) {
				return null;
			}
			this.checksStopRequested = true;
			this.checksStopRequestInFlight = true;
			this.checksFindingsActionRunning = false;
			this.checksActionLocked = false;
			this.checksStartRequestInFlight = false;
			this.checksStatusMessage = this.$avt('checks:status_stop_requested', 'Stop requested. The current check action will stop shortly.');
			try {
				const data = await this.callChecksApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/checks_stop',
					{ check_type: this.selectedChecksType },
					{ resume: false, requireSynoToken: false }
				);
				const progress = this.getResponseData(data);
				if (progress && typeof progress === 'object' && Object.keys(progress).length) {
					this.applyChecksProgress(progress, { adoptResultItem: false });
					if (progress.running) {
						this.checksLoading = true;
						this.startChecksProgressPolling();
						return null;
					}
				}
			} catch (err) {
				// For findings-list processing the local stop flag is decisive.
			}
			if (this.selectedChecksAction === 'scan') {
				this.startChecksProgressPolling();
			} else {
				this.checksLoading = false;
				this.checksStopRequestInFlight = false;
				this.checksStopRequested = false;
			}
			return null;
		},
		applyChecksStartProgress(progress) {
			if (!progress || typeof progress !== 'object') {
				return;
			}
			const sourceMode = String(progress.source_mode || '').trim().toLowerCase();
			const checkType = String(progress.check_type || '').trim().toLowerCase();
			if (sourceMode !== 'scan' || checkType !== String(this.selectedChecksType || '').trim().toLowerCase()) {
				return;
			}
			this.checksProgress = {
				...(this.checksProgress && typeof this.checksProgress === 'object' ? this.checksProgress : {}),
				...progress,
			};
			if (progress.running) {
				this.checksLoading = false;
				this.startChecksProgressPolling();
			}
		},
		async startChecksReview() {
			if (this.isChecksReviewStopping) {
				return null;
			}
			if (this.isChecksReviewActive) {
				return this.stopChecksReview();
			}
			this.checksStopRequested = false;
			this.checksStopRequestInFlight = false;

			if (this.isChecksScanRunning) {
				await this.stopChecksScan();
				return;
			}
			if (this.selectedChecksAction === 'scan') {
				await this.startChecksScan();
				return;
			}
			this.stopChecksProgressPolling();
			this.checksProgressRequestId += 1;
			this.checksProgress = {};
			this.checksEntries = [];
			this.checksCurrentIndex = 0;
			this.checksCurrentItem = null;
			this.checksActionLocked = false;
			this.resetChecksDuplicateAssignmentState();
			this.checksLoading = true;
			if (this.selectedChecksAction === 'findings') {
				this.checksFindingsActionRunning = true;
			}
			this.checksStatusMessage = this.$avt('checks:status_loading', 'Loading checks...');
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_start', {
					source_mode: this.selectedChecksAction,
					check_type: this.selectedChecksType,
				});
				const root = this.getResponseData(data);
			this.applyChecksStartProgress(root);
				const entries = Array.isArray(root.entries) ? root.entries : [];
				this.checksEntries = entries;
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
				this.checksProgress = {
					source_mode: 'findings',
					check_type: this.selectedChecksType,
					findings_count: entries.length,
					resolved_count: 0,
					ignored_count: 0,
					skipped_count: 0,
				};
				this.checksStatusMessage = entries.length
					? this.$avt('checks:status_loaded', '{count} entries loaded.', { count: entries.length })
					: this.$avt('checks:status_empty', 'No matching entries found.');
				if (entries.length) {
					await this.loadChecksItemAtIndex(0);
				}
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				this.checksLoading = false;
				this.checksStopRequestInFlight = false;
				this.checksStopRequested = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
			}
		},
		async loadChecksItemAtIndex(index) {
			let resolvedIndex = index;
			while (resolvedIndex < this.checksEntries.length) {
				if (this.checksStopRequested) {
					this.checksStatusMessage = this.$avt('checks:status_stop_requested', 'Stop requested. The current check action will stop shortly.');
					break;
				}
				const entry = this.checksEntries[resolvedIndex];
				if (!entry) {
					break;
				}
				if (!this.matchesSelectedChecksType(entry.review_type)) {
					resolvedIndex += 1;
					continue;
				}
				this.checksCurrentIndex = resolvedIndex;
				this.checksStatusMessage = this.$avt(
					'checks:status_processing_finding',
					'Processing entry {current} of {total}: {image}',
					{
						current: resolvedIndex + 1,
						total: this.getChecksListTotalCount(),
						image: String(entry.image_name || entry.image_path || '').trim(),
					}
				);
				if (typeof this.$nextTick === 'function') {
					await this.$nextTick();
				}
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_item', {
					entry,
					auto_apply_suggested_names: this.checksAutoApplySuggestedNames,
					auto_apply_suggested_duplicates: this.checksAutoApplySuggestedDuplicates,
				});
				const root = this.getResponseData(data);
				if (this.checksStopRequested || root.stop_requested) {
					this.checksStopRequested = true;
					this.checksStatusMessage = this.$avt('checks:status_stop_requested', 'Stop requested. The current check action will stop shortly.');
					break;
				}
				const autoAppliedCount = Number(root && root.auto_applied_count || 0);
				const item = root && root.item && typeof root.item === 'object' ? root.item : {};
				const findingsUpdated = this.applyChecksFindingsUpdate(root.findings_update, {
					resolvedDelta: Math.max(0, autoAppliedCount),
					skippedDelta: !Object.keys(item).length && autoAppliedCount <= 0 ? 1 : 0,
				});
				if (Object.keys(item).length && this.matchesSelectedChecksType(item.review_type)) {
					this.checksActionLocked = false;
					this.checksCurrentItem = item;
					this.checksCurrentIndex = resolvedIndex;
					this.syncChecksDuplicateAssignmentState(item);
					return;
				}
				if (!this.checksEntries.length) {
					break;
				}
				if (!Object.keys(item).length && autoAppliedCount <= 0 && !findingsUpdated) {
					const currentProgress = this.checksProgress && typeof this.checksProgress === 'object'
						? this.checksProgress
						: {};
					this.checksProgress = {
						...currentProgress,
						source_mode: 'findings',
						check_type: String(this.selectedChecksType || '').trim().toLowerCase(),
						findings_count: Number(currentProgress.findings_count) || this.checksEntries.length,
						skipped_count: (Number(currentProgress.skipped_count) || 0) + 1,
					};
					this.checksStatusMessage = this.$avt(
						'checks:status_finding_skipped',
						'Entry {current} skipped. Continuing with the next finding...',
						{ current: resolvedIndex + 1 }
					);
					resolvedIndex += 1;
					continue;
				}
				if (findingsUpdated && (autoAppliedCount > 0 || !Object.keys(item).length)) {
					this.checksStatusMessage = this.$avt(
						'checks:status_finding_refreshed',
						'Entry {current} checked. Continuing with the next finding...',
						{ current: resolvedIndex + 1 }
					);
					resolvedIndex = Math.min(resolvedIndex, this.checksEntries.length - 1);
					continue;
				}
				resolvedIndex += 1;
			}
			this.checksActionLocked = false;
			this.checksCurrentItem = null;
			this.resetChecksDuplicateAssignmentState();
			this.checksCurrentIndex = Math.min(resolvedIndex, Math.max(this.checksEntries.length - 1, 0));
			this.checksStatusMessage = this.$avt('checks:status_empty', 'No matching entries found.');
		},
		async startChecksScan({ resumeFromProgress = false, advanceCurrentResult = false } = {}) {
			if (!resumeFromProgress) {
				this.stopChecksProgressPolling();
				this.checksProgressRequestId += 1;
				this.checksLoading = true;
				this.checksStartRequestInFlight = true;
				this.checksStopRequestInFlight = false;
				this.checksStopRequested = false;
				this.checksEntries = [];
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
				this.checksProgress = {
					running: true,
					source_mode: 'scan',
					check_type: this.selectedChecksType,
					message: this.$avt('checks:status_preparing_scan', 'Checks scan starting. Building file list...'),
					files_scanned: 0,
					total_files: 0,
					findings_count: 0,
					resolved_count: 0,
					ignored_count: 0,
				};
				this.checksStatusMessage = this.$avt('checks:status_preparing_scan', 'Checks scan starting. Building file list...');
				let runningProgress = {};
				try {
					runningProgress = await this.findRunningChecksScanProgress();
				} catch (err) {
					this.checksLoading = false;
					this.checksStartRequestInFlight = false;
					this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
					return;
				}
				if (this.adoptRunningChecksScanProgress(runningProgress)) {
					this.checksStartRequestInFlight = false;
					return;
				}
			}
			this.checksLoading = true;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_start', {
					source_mode: 'scan',
					check_type: this.selectedChecksType,
					save_only: this.checksSaveOnly,
					resume_from_progress: resumeFromProgress,
					advance_current_result: advanceCurrentResult,
					auto_apply_suggested_names: this.checksAutoApplySuggestedNames,
					auto_apply_suggested_duplicates: this.checksAutoApplySuggestedDuplicates,
				});
				const progress = this.getResponseData(data);
				this.checksStartRequestInFlight = false;
				if (this.checksStopRequested) {
					this.checksLoading = false;
					this.stopChecksProgressPolling();
					return;
				}
				if (progress.blocked_by_running_scan && this.adoptRunningChecksScanProgress(progress)) {
					return;
				}
				this.applyChecksProgress(progress);
				if (!progress.running) {
					await this.ensureChecksResultItemLoaded(progress);
				}
				if (progress.running) {
					this.startChecksProgressPolling();
				} else {
					this.checksLoading = false;
					if (this.selectedChecksAction === 'findings') {
						this.checksFindingsActionRunning = false;
					}
					this.stopChecksProgressPolling();
				}
			} catch (err) {
				this.checksLoading = false;
				this.checksStartRequestInFlight = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				this.stopChecksProgressPolling();
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			}
		},
		async stopChecksScan() {
			try {
				await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_stop', {
					check_type: this.selectedChecksType,
				});
			} catch (err) {
				// Best effort.
			}
			this.checksStatusMessage = this.$avt('checks:progress_stopping', 'Stopping checks scan...');
			await this.fetchChecksProgress();
		},
		async nextChecksReview() {
			if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
				if (!this.hasNextChecksItem) {
					return;
				}
				await this.startChecksScan({ resumeFromProgress: true, advanceCurrentResult: true });
				return;
			}
			if (!this.hasNextChecksItem) {
				return;
			}
			this.checksLoading = true;
			try {
				await this.loadChecksItemAtIndex(this.checksCurrentIndex + 1);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
			}
		},
		async ignoreChecksCurrentItem() {
			const item = this.checksCurrentItem;
			const entry = this.getCurrentChecksEntry();
			if (!this.canIgnoreChecksItem(item) || !entry) {
				return;
			}
			this.checksActionLocked = true;
			this.checksLoading = true;
			let keepLoadingState = false;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_ignore_entry', {
					check_type: String(item.review_type || '').trim().toLowerCase(),
					image_path: item.image_path,
					entry,
				});
				const root = this.getResponseData(data);
				this.applyChecksFindingsUpdate(root.findings_update, { ignoredDelta: 1 });
				this.checksStatusMessage = this.$avt('checks:status_item_ignored', 'Entry added to ignore list.');
				if (root.config && typeof this.normalizeConfig === 'function') {
					this.configModel = this.normalizeConfig(root.config);
				}
				if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
					keepLoadingState = true;
					await this.startChecksScan({ resumeFromProgress: true });
					return;
				}
				if (!this.checksEntries.length) {
					this.checksCurrentItem = null;
					this.resetChecksDuplicateAssignmentState();
					return;
				}
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				if (!keepLoadingState) {
					this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				}
			}
		},
		async deleteChecksMetadataFace(face) {
			if (!this.canDeleteChecksFace(this.checksCurrentItem, face)) {
				return;
			}
			this.checksActionLocked = true;
			this.checksLoading = true;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_delete_metadata_face', {
					image_path: this.checksCurrentItem.image_path,
					face,
					review_type: this.checksCurrentItem.review_type,
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$avt(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Face could not be deleted from metadata.'
					);
					const popupMessage = this.getChecksWarningPopupMessage(result);
					if (popupMessage) {
						this.showChecksPopup(popupMessage);
					}
					return;
				}
				this.applyChecksFindingsUpdate(result.findings_update);
				this.checksStatusMessage = this.$avt('checks:status_face_deleted', 'Face removed from metadata.');
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
			}
		},
		async replaceChecksMetadataFaceName(face, newName, options = {}) {
			if (!this.canReplaceChecksFaceName(this.checksCurrentItem, face, newName)) {
				return;
			}
			this.checksActionLocked = true;
			this.checksLoading = true;
			let keepLoadingState = false;
			try {
				const sourceName = String(face && face.name || '').trim();
				const targetName = String(newName || '').trim();
				let saveMapping = false;
				if (
					!this.checksSkipNameMappingConfirm
					&&
					sourceName
					&& targetName
					&& this.normalizeFaceMatchName(sourceName) !== this.normalizeFaceMatchName(targetName)
					&& !this.checksRenameUsesStoredMapping(this.checksCurrentItem, face, targetName)
				) {
					const mappingDecision = await this.confirmFaceMatchNameMapping(sourceName, targetName, { context: 'checks' });
					saveMapping = !!(mappingDecision && mappingDecision.saveMapping);
					if (mappingDecision && mappingDecision.skipFuturePrompts) {
						this.checksSkipNameMappingConfirm = true;
					}
				}
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_replace_metadata_face_name', {
					image_path: this.checksCurrentItem.image_path,
					face,
					new_name: targetName,
					save_mapping: saveMapping,
					source_name: sourceName,
					create_missing_person: !!options.createMissingPerson,
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$avt(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Face name could not be replaced in metadata.'
					);
					const popupMessage = this.getChecksWarningPopupMessage(result);
					if (popupMessage) {
						this.showChecksPopup(popupMessage);
					}
					return;
				}
				this.applyChecksFindingsUpdate(result.findings_update, { resolvedDelta: 1 });
				const operation = String(result.operation || '').trim().toLowerCase();
				if (operation === 'photos_create') {
					this.checksStatusMessage = this.$avt('checks:status_face_person_created', 'Photos person created from face.');
				} else if (operation === 'photos_assign') {
					this.checksStatusMessage = this.$avt('checks:status_face_person_assigned', 'Photos face assigned to known person.');
				} else {
					this.checksStatusMessage = this.$avt('checks:status_face_name_replaced', 'Face name replaced in metadata.');
				}
				if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
					keepLoadingState = true;
					await this.startChecksScan({ resumeFromProgress: true });
					return;
				}
				if (!this.checksEntries.length) {
					this.checksCurrentItem = null;
					this.resetChecksDuplicateAssignmentState();
					return;
				}
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				if (!keepLoadingState) {
					this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				}
			}
		},
		async replaceChecksMetadataFacePosition(face, sourceFace) {
			if (!this.canReplaceChecksFacePosition(this.checksCurrentItem, face, sourceFace)) {
				return;
			}
			this.checksActionLocked = true;
			this.checksLoading = true;
			let keepLoadingState = false;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_replace_metadata_face_position', {
					image_path: this.checksCurrentItem.image_path,
					face,
					source_face: sourceFace,
					review_type: this.checksCurrentItem.review_type,
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$avt(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Face position could not be replaced in metadata.'
					);
					const popupMessage = this.getChecksWarningPopupMessage(result);
					if (popupMessage) {
						this.showChecksPopup(popupMessage);
					}
					return;
				}
				this.applyChecksFindingsUpdate(result.findings_update);
				this.checksStatusMessage = this.$avt('checks:status_face_position_replaced', 'Face position replaced in metadata.');
				if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
					keepLoadingState = true;
					await this.startChecksScan({ resumeFromProgress: true });
					return;
				}
				if (!this.checksEntries.length) {
					this.checksCurrentItem = null;
					this.resetChecksDuplicateAssignmentState();
					return;
				}
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				if (!keepLoadingState) {
					this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				}
			}
		},
		async assignChecksFaceToPerson(side) {
			const item = this.checksCurrentItem;
			if (!this.isChecksDuplicateFaces(item)) {
				return;
			}
			const state = this.getChecksDuplicateAssignment(side);
			const face = side === 'left' ? item.left_face_target : item.right_face_target;
			if (!this.canAssignChecksFaceToPerson(item, side) || !face) {
				return;
			}
			this.checksActionLocked = true;
			this.checksLoading = true;
			let keepLoadingState = false;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_assign_face_person', {
					image_path: item.image_path,
					face,
					person_id: state.selectedPerson.id,
					person_name: String(state.name || '').trim(),
					review_type: item.review_type,
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$avt(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Person could not be assigned.'
					);
					const popupMessage = this.getChecksWarningPopupMessage(result);
					if (popupMessage) {
						this.showChecksPopup(popupMessage);
					}
					return;
				}
				this.applyChecksFindingsUpdate(result.findings_update, { resolvedDelta: 1 });
				this.checksStatusMessage = this.$avt('checks:status_face_person_assigned', 'Known person assigned.');
				if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
					keepLoadingState = true;
					await this.startChecksScan({ resumeFromProgress: true });
					return;
				}
				if (!this.checksEntries.length) {
					this.checksCurrentItem = null;
					this.resetChecksDuplicateAssignmentState();
					return;
				}
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				if (!keepLoadingState) {
					this.checksLoading = false;
				if (this.selectedChecksAction === 'findings') {
					this.checksFindingsActionRunning = false;
				}
				}
			}
		},
		getChecksTypeLabel(type) {
			const normalized = String(type || '').trim().toLowerCase();
			if (normalized === 'dimension_issues') {
				return this.$avt('checks:type_dimension_issues', 'Dimension issues');
			}
			if (normalized === 'duplicate_faces') {
				return this.$avt('checks:type_duplicate_faces', 'Duplicate face markings');
			}
			if (normalized === 'position_deviations') {
				return this.$avt('checks:type_position_deviations', 'Deviating face positions');
			}
			if (normalized === 'name_conflicts') {
				return this.$avt('checks:type_name_conflicts', 'Name conflicts');
			}
			return String(type || '');
		},
		getChecksLeftTitle(item) {
			if (item && item.review_type === 'dimension_issues') {
				return this.$avt('checks:preview_left_dimension', 'Affected metadata');
			}
			return this.$avt('checks:preview_left_pair', 'Left face');
		},
		getChecksRightTitle(item) {
			if (item && item.review_type === 'dimension_issues') {
				return this.$avt('checks:preview_right_dimension', 'Reference metadata');
			}
			return this.$avt('checks:preview_right_pair', 'Right face');
		},
		getChecksPairLabel(item) {
			if (!item) {
				return '-';
			}
			const left = this.getChecksDisplayName(item.left_name);
			const right = this.getChecksDisplayName(item.right_name);
			const leftFormat = item.left_format ? this.getFaceMatchFormatLabel(item.left_format) : '';
			const rightFormat = item.right_format ? this.getFaceMatchFormatLabel(item.right_format) : '';
			return `${left}${leftFormat ? ` (${leftFormat})` : ''} / ${right}${rightFormat ? ` (${rightFormat})` : ''}`;
		},
		getChecksDisplayName(name) {
			return name || this.$avt('face_match:unknown_name', '(unnamed)');
		},
		showChecksFaceName(item) {
			const reviewType = String(item && item.review_type || '').trim().toLowerCase();
			return reviewType === 'name_conflicts' || reviewType === 'duplicate_faces';
		},
		getChecksSourceModeLabel() {
			if (this.selectedChecksAction === 'scan') {
				return this.$avt('checks:action_scan', 'Run check scan');
			}
			return this.$avt('checks:action_findings', 'Process saved findings list');
		},
	},
};
