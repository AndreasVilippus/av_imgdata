const FACE_COORDINATE_DIGITS = 6;

export default {
	data() {
		return {
			faceMatchLoading: false,
			faceMatchProgress: {},
			faceMatchProgressTimer: null,
			faceMatchProgressRequestId: 0,
			faceMatchProgressRequestPending: false,
			faceMatchResult: null,
			faceMatchActionLocked: false,
			faceMatchSkippedFaceIds: [],
			faceMatchSkippedTargets: [],
			faceMatchPreviewMode: 'photo',
			faceMatchAutoAssignKnown: false,
			faceMatchSaveOnly: false,
			faceMatchUseStoredFindings: false,
			faceMatchTransferredCount: 0,
			faceMatchProgressBase: {
				persons_read: 0,
				images_read: 0,
				faces_read: 0,
				target_faces_read: 0,
				metadata_faces_read: 0,
			},
			faceMatchEditableName: '',
			faceMatchInitialEditableName: '',
			faceMatchSelectedPerson: null,
			faceMatchPersonSuggestions: [],
			faceMatchPersonSuggestLoading: false,
			faceMatchShowSuggestions: false,
			faceMatchSuggestTimer: null,
			faceMatchSuggestRequestId: 0,
			faceMatchFindingEntries: [],
			faceMatchFindingIndex: 0,
			faceMatchFindingEntriesTotal: 0,
			faceMatchFindingsStatus: {},
			faceMatchSkippedFindingKeys: [],
			selectedFaceMatchingAction: 'search_photo_face_in_file',
			addIconUrl: '',
			personDataToLeftIconUrl: '',
			personDataToRightIconUrl: '',
			nameMappingConfirm: {
				visible: false,
				message: '',
				resolver: null,
				context: '',
				skipFuturePrompts: false,
			},
		};
	},
	computed: {
		faceMatchIsFileSourceAction() {
			return ['search_file_face_in_sources', 'mark_missing_photos_faces', 'search_missing_faces_insightface'].includes(this.faceMatchCurrentAction);
		},
		faceMatchSupportsSaveOnly() {
			return ['search_photo_face_in_file', 'search_file_face_in_sources', 'mark_missing_photos_faces', 'search_missing_faces_insightface'].includes(this.selectedFaceMatchingAction);
		},
		hasInsightFaceForFaceMatch() {
			return !!(this.insightFacePipPackageStatus && this.insightFacePipPackageStatus.installed);
		},
		faceMatchReviewingStoredFindings() {
			return this.faceMatchUseStoredFindings || this.selectedFaceMatchingAction === 'load_photo_face_match_findings';
		},
		faceMatchCurrentAction() {
			if (this.faceMatchReviewingStoredFindings) {
				const entryAction = this.faceMatchResult && this.faceMatchResult.action;
				if (entryAction) {
					return String(entryAction);
				}
			}
			return this.selectedFaceMatchingAction;
		},
		isFaceOnlyPreview() {
			return this.faceMatchPreviewMode === 'face';
		},
		faceMatchDisplayedTransferredCount() {
			const progressCount = Number(this.faceMatchProgress && this.faceMatchProgress.transferred_count);
			const localCount = Number(this.faceMatchTransferredCount) || 0;
			if (!Number.isFinite(progressCount) || progressCount <= 0) {
				return localCount;
			}
			return Math.max(localCount, progressCount);
		},
		faceMatchDisplayedFindingsCount() {
			const progressCount = Number(this.faceMatchProgress && this.faceMatchProgress.findings_count);
			const resultCount = Number(this.faceMatchResult && this.faceMatchResult.findings_count);
			return Math.max(
				Number.isFinite(progressCount) ? progressCount : 0,
				Number.isFinite(resultCount) ? resultCount : 0
			);
		},
		faceMatchDisplayedSkippedCount() {
			const transferredCount = this.faceMatchDisplayedTransferredCount;
			let cursorCount = 0;
			if (this.faceMatchIsFileSourceAction) {
				cursorCount = Array.isArray(this.faceMatchSkippedTargets) ? this.faceMatchSkippedTargets.length : 0;
			} else {
				cursorCount = Array.isArray(this.faceMatchSkippedFaceIds) ? this.faceMatchSkippedFaceIds.length : 0;
			}
			return Math.max(0, cursorCount - transferredCount);
		},
		faceMatchDisplayedProgress() {
			const fields = ['persons_read', 'images_read', 'faces_read', 'target_faces_read', 'metadata_faces_read'];
			return fields.reduce((acc, field) => {
				const baseValue = Number(this.faceMatchProgressBase && this.faceMatchProgressBase[field]) || 0;
				const currentValue = Number(this.faceMatchProgress && this.faceMatchProgress[field]) || 0;
				acc[field] = Math.max(0, baseValue + currentValue);
				return acc;
			}, {});
		},
		faceMatchHasActiveProgressState() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const phase = this.faceMatchStatusPhase;
			if (progress.stale === true && progress.running !== true && progress.active !== true) {
				return false;
			}
			if (this.faceMatchLoading) {
				return true;
			}
			return !!(
				progress.active === true
				|| progress.running === true
				|| progress.stop_requested === true
				|| phase === 'preparing'
				|| phase === 'running'
				|| phase === 'stopping'
			);
		},
		faceMatchInteractionDisabled() {
			return !!(this.faceMatchHasActiveProgressState || this.faceMatchActionLocked);
		},
		faceMatchStatusPhase() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			return String(status.phase || progress.status_phase || '').trim().toLowerCase();
		},
		faceMatchFileProgressTotal() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const displayed = this.faceMatchDisplayedProgress || {};
			const current = this.faceMatchFileProgressCurrent;
			return Math.max(
				current,
				this.faceMatchNumberFrom(
					progress.total_images,
					progress.files_total,
					progress.total_files,
					progress.images_total,
					progress.target_faces_total,
					progress.metadata_faces_total,
					displayed.images_read,
					displayed.target_faces_read,
					displayed.metadata_faces_read
				)
			);
		},
		faceMatchFileProgressCurrent() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const displayed = this.faceMatchDisplayedProgress || {};
			return this.faceMatchNumberFrom(
				progress.images_read,
				progress.files_scanned,
				progress.files_read,
				progress.current,
				displayed.images_read,
				displayed.target_faces_read,
				displayed.metadata_faces_read
			);
		},
		faceMatchPersonsTotal() {
			const progressTotal = Math.max(0, Number(this.faceMatchProgress && this.faceMatchProgress.persons_total) || 0);
			const baseValue = Math.max(0, Number(this.faceMatchProgressBase && this.faceMatchProgressBase.persons_read) || 0);
			const checked = Math.max(0, Number(this.faceMatchDisplayedProgress && this.faceMatchDisplayedProgress.persons_read) || 0);
			if (!progressTotal) {
				return checked;
			}
			return Math.max(checked, baseValue + progressTotal, progressTotal);
		},
		faceMatchPersonsChecked() {
			const checked = Math.max(0, Number(this.faceMatchDisplayedProgress && this.faceMatchDisplayedProgress.persons_read) || 0);
			const total = this.faceMatchPersonsTotal;
			return total > 0 ? Math.min(checked, total) : checked;
		},
		faceMatchShowPersonsProgress() {
			return !this.faceMatchShowStoredFindingsProgress
				&& !this.faceMatchIsFileSourceAction
				&& this.faceMatchHasActiveProgressState;
		},
		faceMatchShowFileProgress() {
			return !this.faceMatchShowStoredFindingsProgress
				&& this.faceMatchIsFileSourceAction
				&& this.faceMatchHasActiveProgressState;
		},
		faceMatchShowStoredFindingsProgress() {
			return this.faceMatchReviewingStoredFindings
				&& (
					Number(this.faceMatchFindingEntriesTotal) > 0
					|| (Array.isArray(this.faceMatchFindingEntries) && this.faceMatchFindingEntries.length > 0)
				);
		},
		faceMatchStoredFindingsTotal() {
			return Math.max(
				0,
				Number(this.faceMatchFindingEntriesTotal) || 0,
				Array.isArray(this.faceMatchFindingEntries) ? this.faceMatchFindingEntries.length : 0
			);
		},
		faceMatchStoredFindingsChecked() {
			const total = this.faceMatchStoredFindingsTotal;
			if (!total) {
				return 0;
			}
			const currentOffset = Array.isArray(this.faceMatchFindingEntries) && this.faceMatchFindingEntries.length
				? Math.max(0, Number(this.faceMatchFindingIndex) || 0) + 1
				: 0;
			return Math.min(total, this.faceMatchStoredFindingsCompletedCount + currentOffset);
		},
		faceMatchStoredFindingsCompletedCount() {
			const total = this.faceMatchStoredFindingsTotal;
			if (!total) {
				return 0;
			}
			const remaining = Array.isArray(this.faceMatchFindingEntries)
				? this.faceMatchFindingEntries.length
				: 0;
			return Math.max(0, Math.min(total, total - remaining));
		},
		faceMatchFacesLabel() {
			if (this.faceMatchIsFileSourceAction) {
				return this.$avt('face_match:label_source_faces', 'Source faces');
			}
			return this.$avt('face_match:label_faces', 'Faces');
		},
		faceMatchMetadataLabel() {
			if (this.faceMatchIsFileSourceAction) {
				return this.$avt('face_match:label_metadata_faces', 'Metadata faces');
			}
			return this.$avt('face_match:label_metadata', 'Metadata');
		},
		faceMatchMetadataHint() {
			if (this.faceMatchIsFileSourceAction) {
				return this.$avt('face_match:label_metadata_faces_hint', 'Read face metadata from the scanned files');
			}
			return this.$avt('face_match:label_metadata_hint', 'Read metadata');
		},
		faceMatchProgressIconUrl() {
			if (this.faceMatchCurrentAction === 'mark_missing_photos_faces') {
				return this.resolveLocalIconUrl('face_search_empty.png');
			}
			return '';
		},
		showFaceMatchTargetFacesCounter() {
			return this.faceMatchIsFileSourceAction;
		},
		faceMatchStatusMessage() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: null;
			if (this.faceMatchResultSummary && this.faceMatchResultSummary.found) {
				if (progress && progress.message_key && String(progress.message_key).indexOf('face_match:result_') === 0) {
					return this.$avt(
						String(progress.message_key),
						progress.message || String(progress.message_key),
						progress.message_params && typeof progress.message_params === 'object'
							? progress.message_params
							: null
					);
				}
				return this.$avt('face_match:status_result_ready', 'Match found. Choose the next action.');
			}
			if (progress && progress.message_key) {
				return this.$avt(
					String(progress.message_key),
					progress.message || String(progress.message_key),
					progress.message_params && typeof progress.message_params === 'object'
						? progress.message_params
						: null
				);
			}
			if (progress && progress.message) {
				return progress.message;
			}
			return this.faceMatchLoading
				? this.$avt('face_match:status_search_running', 'Search running...')
				: this.$avt('face_match:status_idle', 'No action running.');
		},
		faceMatchStatusHeadline() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const key = String(progress.message_key || '').trim();
			const checkingLabel = this.$avt('face_match:status_phase_checking', 'Checking...');
			const phaseLabels = {
				'face_match:progress_checking_person': checkingLabel,
				'face_match:progress_unknown_persons_loaded': checkingLabel,
				'face_match:progress_known_persons_loaded': checkingLabel,
				'face_match:progress_checking_image': checkingLabel,
				'face_match:progress_checking_face': checkingLabel,
				'face_match:progress_match_candidates': checkingLabel,
				'face_match:progress_checking_metadata': checkingLabel,
				'face_match:progress_checking_file': checkingLabel,
				'face_match:progress_checking_insightface': checkingLabel,
				'face_match:progress_listing_files': checkingLabel,
				'face_match:progress_files_listed': checkingLabel,
			};
			return this.withFaceMatchStatusCounts(phaseLabels[key] || this.faceMatchStatusMessage);
		},
		faceMatchAuthRequired() {
			return !!(this.faceMatchProgress && this.faceMatchProgress.auth_required);
		},
		faceMatchIsPaused() {
			return !this.faceMatchLoading && (
				!!(this.faceMatchResult && this.faceMatchResult.searched)
				|| !!(this.faceMatchProgress && this.faceMatchProgress.paused)
			);
		},
		faceMatchCanRestartSavedFileSearch() {
			return !!(
				this.selectedFaceMatchingAction === 'search_photo_face_in_file'
				&& !this.faceMatchUseStoredFindings
				&& (this.faceMatchSaveOnly || this.hasFaceMatchStoredFindings)
				&& this.faceMatchIsPaused
				&& !this.faceMatchLoading
				&& !this.faceMatchAuthRequired
			);
		},
		faceMatchPrimaryButtonLabel() {
			if (this.faceMatchHasActiveProgressState) {
				return this.$avt('face_match:button_stop', 'Stop');
			}
			if (this.faceMatchAuthRequired) {
				return this.$avt('face_match:button_resume_login', 'Resume after login');
			}
			if (this.faceMatchCanRestartSavedFileSearch) {
				return this.$avt('face_match:button_restart', 'Restart');
			}
			return this.$avt('face_match:button_start', 'Start');
		},
		faceMatchResultSummary() {
			if (this.faceMatchLoading) {
				return { found: false, message: this.$avt('face_match:result_none', 'No result yet.') };
			}
			if (this.faceMatchIsFileSourceAction) {
				const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
				const sourceFace = this.faceMatchResult && (this.faceMatchResult.source_face || this.faceMatchResult.face);
				const matchedPerson = this.faceMatchEffectivePerson;
				if (metadataFace && sourceFace) {
					return {
						found: true,
						name: (sourceFace && sourceFace.name) || this.$avt('face_match:unknown_name', '(unnamed)'),
						source: this.getFaceMatchSourceLabel(sourceFace && sourceFace.source),
						format: this.getFaceMatchFormatLabel(sourceFace && (sourceFace.source_format || sourceFace.format)),
						photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
					};
				}
				if (this.faceMatchResult && this.faceMatchResult.searched) {
					return { found: false, message: this.$avt('face_match:result_no_match', 'No match found yet.') };
				}
				return { found: false, message: this.$avt('face_match:result_none', 'No result yet.') };
			}
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const match = this.faceMatchResult && this.faceMatchResult.match;
			const matchedPerson = this.faceMatchEffectivePerson;
			if (match && metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$avt('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$avt('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (this.faceMatchResult && this.faceMatchResult.searched) {
				return { found: false, message: this.$avt('face_match:result_no_match', 'No match found yet.') };
			}
			return { found: false, message: this.$avt('face_match:result_none', 'No result yet.') };
		},
		faceMatchTransferTooltip() {
			if (this.faceMatchAddsNewPhotosFaces) {
				if (this.faceMatchActionMode === 'create') {
					return this.$avt('face_match:transfer_tooltip_create_photos_face', 'Add face in Photos and create person from file');
				}
				return this.$avt('face_match:transfer_tooltip_assign_photos_face', 'Add face in Photos and assign name from file');
			}
			if (this.faceMatchActionMode === 'write_metadata') {
				return this.$avt('face_match:transfer_tooltip_write_metadata', 'Apply name to metadata');
			}
			if (this.faceMatchActionMode === 'create') {
				return this.$avt('face_match:transfer_tooltip_create', 'Create person and apply name from file');
			}
			return this.$avt('face_match:transfer_tooltip_assign', 'Apply name from file');
		},
		faceMatchActionMode() {
			if (!this.faceMatchResultSummary.found) {
				return '';
			}
			if (this.faceMatchIsFileSourceAction) {
				if (this.faceMatchAddsNewPhotosFaces) {
					return this.faceMatchResultSummary.photosPersonId ? 'assign' : 'create';
				}
				return 'write_metadata';
			}
			return this.faceMatchResultSummary.photosPersonId ? 'assign' : 'create';
		},
		faceMatchAddsNewPhotosFaces() {
			return !!(
				this.faceMatchIsFileSourceAction
				&& this.faceMatchResult
				&& this.faceMatchResult.add_new_faces_to_photos
			);
		},
		faceMatchShouldShowAddOverlay() {
			return this.faceMatchAddsNewPhotosFaces || this.faceMatchActionMode === 'create';
		},
		faceMatchEffectivePerson() {
			if (this.faceMatchSelectedPerson && this.faceMatchEditableNameMatchesPerson(this.faceMatchSelectedPerson)) {
				return this.faceMatchSelectedPerson;
			}
			const matchedPerson = this.faceMatchResult && this.faceMatchResult.matched_person;
			if (matchedPerson && this.faceMatchEditableNameMatchesPerson(matchedPerson)) {
				return matchedPerson;
			}
			return null;
		},
		faceMatchFileTitle() {
			if (this.faceMatchIsFileSourceAction) {
				return this.$avt('face_match:file_title', 'File');
			}
			const matchedPerson = this.faceMatchEffectivePerson;
			if (matchedPerson && matchedPerson.id && matchedPerson.name) {
				return `${this.$avt('face_match:file_title', 'File')} - ${matchedPerson.name}`;
			}
			return this.$avt('face_match:file_title', 'File');
		},
		faceMatchHasStoredNameMapping() {
			const mapping = this.faceMatchResult && this.faceMatchResult.name_mapping;
			return !!(mapping && mapping.source_name && mapping.target_name);
		},
		hasFaceMatchStoredFindings() {
			return this.faceMatchFindingsStatusMatchesCurrentAction()
				&& (Number(this.faceMatchFindingsStatus && this.faceMatchFindingsStatus.count) || 0) > 0;
		},
		faceMatchLeftTitle() {
			const action = String(this.faceMatchCurrentAction || '').trim().toLowerCase();
			if (action === 'search_file_face_in_sources') {
				return this.$avt('face_match:title_name_source', 'Name source');
			}
			if (action === 'mark_missing_photos_faces' || action === 'search_missing_faces_insightface') {
				return this.$avt('face_match:title_file_face_source', 'File face');
			}
			return this.$avt('face_match:photos_title', 'Photos');
		},
		faceMatchRightTitle() {
			const action = String(this.faceMatchCurrentAction || '').trim().toLowerCase();
			if (action === 'search_file_face_in_sources') {
				return this.$avt('face_match:title_file_face_target', 'File marking to name');
			}
			if (action === 'mark_missing_photos_faces' || action === 'search_missing_faces_insightface') {
				return this.$avt('face_match:title_photos_face_target', 'Photos face to create');
			}
			return this.faceMatchFileTitle;
		},
		faceMatchImageContextTitle() {
			const path = String(this.faceMatchResult && this.faceMatchResult.image_path || '').trim();
			if (!path) {
				return this.$avt('face_match:file_title', 'File');
			}
			const filename = path.split(/[\\/]/).filter(Boolean).pop() || path;
			return `${this.$avt('face_match:file_title', 'File')}: ${filename}`;
		},
		faceMatchImageContextPath() {
			return String(this.faceMatchResult && this.faceMatchResult.image_path || '').trim();
		},
		hasNextFaceMatch() {
			if (this.faceMatchReviewingStoredFindings) {
				return this.faceMatchFindingIndex + 1 < this.faceMatchFindingEntries.length;
			}
			return !!this.faceMatchResultSummary.found;
		},
	},
	watch: {
		selectedFaceMatchingAction(nextAction) {
			if (!['search_photo_face_in_file', 'search_file_face_in_sources', 'mark_missing_photos_faces', 'search_missing_faces_insightface'].includes(nextAction)) {
				this.faceMatchSaveOnly = false;
			}
			if (!this.faceMatchFindingsStatusMatchesAction(nextAction)) {
				this.faceMatchUseStoredFindings = false;
				this.resetFaceMatchFindingsReview();
			}
			if (nextAction === 'load_photo_face_match_findings') {
				this.faceMatchUseStoredFindings = true;
				this.selectedFaceMatchingAction = 'search_photo_face_in_file';
			}
			this.fetchFaceMatchFindingsStatus();
		},
		faceMatchUseStoredFindings(useStoredFindings) {
			if (useStoredFindings && !this.hasFaceMatchStoredFindings) {
				this.faceMatchUseStoredFindings = false;
				this.resetFaceMatchFindingsReview();
				return;
			}
			if (useStoredFindings) {
				this.faceMatchSaveOnly = false;
			} else {
				this.resetFaceMatchFindingsReview();
			}
		},
		faceMatchSaveOnly(saveOnly) {
			if (saveOnly) {
				this.faceMatchUseStoredFindings = false;
			}
		},
	},
	mounted() {
		this.addIconUrl = this.resolveLocalIconUrl('add_icon.png');
		this.personDataToLeftIconUrl = this.resolveLocalIconUrl('person_data_to_left.png');
		this.personDataToRightIconUrl = this.resolveLocalIconUrl('person_data_to_right.png');
		this.fetchFaceMatchFindingsStatus();
	},
	beforeDestroy() {
		if (this.faceMatchSuggestTimer) {
			window.clearTimeout(this.faceMatchSuggestTimer);
			this.faceMatchSuggestTimer = null;
		}
		this.resolveNameMappingConfirm(false);
		this.stopFaceMatchProgressPolling();
	},
	methods: {
		faceMatchNumberFrom(...values) {
			for (const value of values) {
				const numeric = Number(value);
				if (Number.isFinite(numeric) && numeric > 0) {
					return numeric;
				}
			}
			return 0;
		},
		normalizeFaceMatchAction(action) {
			const normalized = String(action || '').trim().toLowerCase();
			return normalized === 'load_photo_face_match_findings'
				? 'search_photo_face_in_file'
				: normalized;
		},
		getFaceMatchFindingsSourceAction() {
			const status = this.faceMatchFindingsStatus && typeof this.faceMatchFindingsStatus === 'object'
				? this.faceMatchFindingsStatus
				: {};
			const resultAction = this.faceMatchResult && this.faceMatchResult.action;
			const statusAction = status.action || status.source_action;
			if (this.faceMatchReviewingStoredFindings) {
				return this.normalizeFaceMatchAction(resultAction || statusAction || this.selectedFaceMatchingAction);
			}
			return this.normalizeFaceMatchAction(this.selectedFaceMatchingAction);
		},
		faceMatchFindingsStatusMatchesAction(action) {
			const selectedAction = this.normalizeFaceMatchAction(action || this.selectedFaceMatchingAction);
			const status = this.faceMatchFindingsStatus && typeof this.faceMatchFindingsStatus === 'object'
				? this.faceMatchFindingsStatus
				: {};
			const statusAction = this.normalizeFaceMatchAction(status.action || status.source_action);
			if (!selectedAction || !statusAction) {
				return true;
			}
			return selectedAction === statusAction;
		},
		faceMatchFindingsStatusMatchesSelectedAction() {
			return this.faceMatchFindingsStatusMatchesAction(this.selectedFaceMatchingAction);
		},
		faceMatchFindingsStatusMatchesCurrentAction() {
			return this.faceMatchFindingsStatusMatchesAction(this.getFaceMatchFindingsSourceAction());
		},
		getFaceMatchStatusCounterLabel(counter) {
			if (!counter || typeof counter !== 'object') {
				return '';
			}
			const labelKey = String(counter.label_key || '').trim();
			const fallback = String(counter.fallback_label || counter.key || '').trim();
			return labelKey ? this.$avt(labelKey, fallback) : fallback;
		},
		normalizeFaceMatchStatusCounter(counter) {
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
				label: this.getFaceMatchStatusCounterLabel(counter),
				value: Math.max(0, value),
				show_when_zero: !!counter.show_when_zero,
			};
		},
		getFaceMatchStatusCounters() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
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
		getFaceMatchStatusProgress() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			const status = progress.status && typeof progress.status === 'object'
				? progress.status
				: {};
			if (status.schema_version === 1 && status.progress && typeof status.progress === 'object') {
				return status.progress;
			}
			return {};
		},
			async refreshFaceMatchSessionState() {
				const findingsStatusPromise = this.fetchFaceMatchFindingsStatus();
				const pipPackagesPromise = typeof this.fetchPipPackagesStatus === 'function'
					? this.fetchPipPackagesStatus()
					: Promise.resolve();
				const progressPromise = this.fetchFaceMatchingProgress({ applyRunningState: false });
				await findingsStatusPromise;
				const progress = await progressPromise;
				if (this.isFaceMatchFindingsReviewActive() && this.getFaceMatchProgressMode(progress) === 'scan') {
					await pipPackagesPromise;
					return;
				}
				if (progress && typeof progress === 'object' && Object.keys(progress).length) {
					this.applyFaceMatchingProgress(progress);
				}
				if (progress.running) {
					this.faceMatchLoading = true;
					this.startFaceMatchProgressPolling();
					await pipPackagesPromise;
					return;
				}
				this.faceMatchLoading = false;
				await pipPackagesPromise;
			},
		isFaceMatchFindingsReviewActive() {
			return !!(
				this.faceMatchReviewingStoredFindings
				&& (
					this.faceMatchLoading
					|| this.faceMatchFindingEntries.length
					|| this.faceMatchResult
				)
			);
		},
		getFaceMatchProgressMode(progress) {
			const source = progress && typeof progress === 'object' ? progress : {};
			const status = source.status && typeof source.status === 'object' ? source.status : {};
			const statusMode = String(status.mode || '').trim().toLowerCase();
			if (status.schema_version === 1 && statusMode) {
				return statusMode;
			}
			const action = String(source.action || source.selected_action || '').trim();
			if (action === 'load_photo_face_match_findings') {
				return 'findings';
			}
			if (action || source.running || source.stop_requested) {
				return 'scan';
			}
			return '';
		},
		resetFaceMatchSelectionState() {
			this.faceMatchEditableName = '';
			this.faceMatchInitialEditableName = '';
			this.faceMatchSelectedPerson = null;
			this.clearFaceMatchSuggestions();
		},
		clearFaceMatchSuggestions() {
			this.faceMatchPersonSuggestions = [];
			this.faceMatchPersonSuggestLoading = false;
			this.faceMatchShowSuggestions = false;
		},
		async fetchFaceMatchFindingsStatus() {
			try {
				const data = await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_findings_status',
					{ action: this.getFaceMatchFindingsSourceAction() },
					{ resume: false, requireSynoToken: false }
				);
				this.faceMatchFindingsStatus = this.getResponseData(data);
				if (this.faceMatchReviewingStoredFindings && !this.hasFaceMatchStoredFindings) {
					this.faceMatchUseStoredFindings = false;
					this.resetFaceMatchFindingsReview();
				}
			} catch (err) {
				this.faceMatchFindingsStatus = this.faceMatchFindingsStatus && typeof this.faceMatchFindingsStatus === 'object'
					? this.faceMatchFindingsStatus
					: {};
			}
				},
				getFaceMatchErrorMessage(err, fallback = 'Unknown error') {
					if (typeof this.getErrorMessage === 'function') {
						return this.getErrorMessage(err, fallback);
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
				async reconcileStoredFaceMatchFindingsAfterMutationError(err) {
					const message = this.getFaceMatchErrorMessage(err);
					if (!this.faceMatchReviewingStoredFindings) {
						this.output = `Error: ${message}`;
						return;
					}
					this.output = `Error: ${message}`;
				try {
					await this.loadStoredFaceMatchFindings();
					} catch (refreshErr) {
						this.faceMatchProgress = {
							...(this.faceMatchProgress || {}),
							message: `Error: ${this.getFaceMatchErrorMessage(refreshErr)}`,
						};
					}
				},
			setFaceMatchMutationPending(messageKey, fallback, imagePath, personName = '') {
				const path = String(imagePath || '').trim();
				const name = String(personName || '').trim();
				this.output = this.$avt(messageKey, fallback, {
					path: path || '-',
					person: name || '-',
				});
			},
		resetFaceMatchFindingsReview() {
			this.faceMatchFindingEntries = [];
			this.faceMatchFindingIndex = 0;
			this.faceMatchFindingEntriesTotal = 0;
			this.faceMatchSkippedFindingKeys = [];
		},
		setFaceMatchProgressMessage(message, extra = {}) {
			this.faceMatchProgress = {
				...(this.faceMatchProgress || {}),
				...extra,
				message,
			};
		},
		async loadFaceMatchFindingAtIndex(index) {
			const entry = this.faceMatchFindingEntries[index];
			if (!entry) {
				this.faceMatchResult = null;
				return;
			}
			this.faceMatchResult = entry;
			this.faceMatchFindingIndex = index;
			this.syncFaceMatchEditableName();
			this.setFaceMatchProgressMessage(
				this.$avt('face_match:status_list_entry', 'List entry {current} of {total}.', {
					current: this.faceMatchStoredFindingsChecked,
					total: this.faceMatchStoredFindingsTotal || this.faceMatchFindingEntries.length,
				})
			);
		},
		getFaceMatchFindingKey(entry) {
			const source = entry && typeof entry === 'object' ? entry : {};
			if (source.id !== undefined && source.id !== null) {
				return `id:${source.id}`;
			}
			const face = source.metadata_face && typeof source.metadata_face === 'object'
				? source.metadata_face
				: source.face && typeof source.face === 'object'
					? source.face
					: {};
			const bbox = face.bbox && typeof face.bbox === 'object' ? face.bbox : {};
			return [
				'entry',
				String(source.action || ''),
				String(source.image_path || ''),
				String(face.source || ''),
				String(face.source_format || ''),
				String(face.name || ''),
				String(bbox.x1 ?? face.x ?? ''),
				String(bbox.y1 ?? face.y ?? ''),
				String(bbox.x2 ?? ''),
				String(bbox.y2 ?? ''),
				String(face.w ?? ''),
				String(face.h ?? ''),
			].join('|');
		},
		filterSkippedFaceMatchFindings(entries) {
			if (!Array.isArray(entries) || !entries.length) {
				return [];
			}
			const skipped = new Set(Array.isArray(this.faceMatchSkippedFindingKeys) ? this.faceMatchSkippedFindingKeys : []);
			if (!skipped.size) {
				return entries;
			}
			return entries.filter((entry) => !skipped.has(this.getFaceMatchFindingKey(entry)));
		},
		rememberSkippedFaceMatchFinding(entry) {
			const key = this.getFaceMatchFindingKey(entry);
			if (!key) {
				return;
			}
			if (!Array.isArray(this.faceMatchSkippedFindingKeys)) {
				this.faceMatchSkippedFindingKeys = [];
			}
			if (!this.faceMatchSkippedFindingKeys.includes(key)) {
				this.faceMatchSkippedFindingKeys.push(key);
			}
		},
		async skipStoredFaceMatchFinding() {
			const currentIndex = Math.max(0, Number(this.faceMatchFindingIndex) || 0);
			const currentEntry = this.faceMatchFindingEntries[currentIndex];
			if (!currentEntry || !this.hasNextFaceMatch) {
				return;
			}
			this.rememberSkippedFaceMatchFinding(currentEntry);
			const remainingEntries = this.faceMatchFindingEntries.filter((entry, index) => index !== currentIndex);
			this.faceMatchFindingEntries = remainingEntries;
			await this.loadFaceMatchFindingAtIndex(Math.min(currentIndex, remainingEntries.length - 1));
		},
			async loadStoredFaceMatchFindings({ refresh = false } = {}) {
				const autoApplying = !!this.faceMatchAutoAssignKnown;
				if (autoApplying) {
					this.faceMatchLoading = true;
					this.faceMatchProgress = {
						...(this.faceMatchProgress || {}),
						action: 'load_photo_face_match_findings',
						source_mode: 'findings',
						running: true,
						finished: false,
						message_key: 'face_match:progress_applying_known_findings',
						message: this.$avt('face_match:progress_applying_known_findings', 'Applying known persons from saved findings...'),
					};
					this.startFaceMatchProgressPolling();
				}
				let data;
				try {
					data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_action', {
						action: 'load_photo_face_match_findings',
						findings_action: this.getFaceMatchFindingsSourceAction(),
						auto: autoApplying,
						refresh: !!refresh,
					});
					if (autoApplying) {
						await this.fetchFaceMatchingProgress();
					}
				} finally {
					if (autoApplying) {
						this.faceMatchLoading = false;
						this.stopFaceMatchProgressPolling();
					}
				}
				const payload = this.getResponseDataObject(data, 'face_matches');
			const entries = this.filterSkippedFaceMatchFindings(Array.isArray(payload.entries) ? payload.entries : []);
			const remainingCount = Number(payload.count) || entries.length;
			const transferredCount = Math.max(0, Number(payload.transferred_count) || 0);
			this.faceMatchFindingEntries = entries;
			this.faceMatchFindingIndex = 0;
			this.faceMatchFindingEntriesTotal = Math.max(
				Number(this.faceMatchFindingEntriesTotal) || 0,
				remainingCount + transferredCount,
				entries.length
			);
			this.faceMatchTransferredCount = transferredCount;
			this.faceMatchFindingsStatus = {
				...(this.faceMatchFindingsStatus || {}),
				count: remainingCount,
				action: this.normalizeFaceMatchAction(payload.action || payload.requested_action || this.selectedFaceMatchingAction),
				requested_action: this.normalizeFaceMatchAction(payload.requested_action || this.selectedFaceMatchingAction),
				status: payload.status || '',
				transferred_count: transferredCount,
				save_only: !!payload.save_only,
				auto: !!payload.auto,
			};
			if (entries.length) {
				await this.loadFaceMatchFindingAtIndex(0);
			} else {
				this.faceMatchUseStoredFindings = false;
				this.faceMatchResult = null;
				this.faceMatchProgress = {
					...(this.faceMatchProgress || {}),
					message: this.$avt('face_match:status_findings_empty', 'No saved matches found.'),
				};
			}
		},
		getFaceMatchSourceLabel(source) {
			const normalized = String(source || '').trim().toLowerCase();
			if (!normalized) {
				return this.$avt('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'xmp_file') {
				return this.$avt('face_match:source_xmp_file', 'XMP sidecar file');
			}
			if (normalized === 'embedded_xmp_parsed') {
				return this.$avt('face_match:source_embedded_xmp', 'Embedded XMP');
			}
			if (normalized === 'embedded_xmp_exiftool') {
				return this.$avt('face_match:source_embedded_xmp_exiftool', 'Embedded XMP via ExifTool');
			}
			if (normalized === 'metadata') {
				return this.$avt('face_match:source_metadata', 'Metadata');
			}
			if (normalized === 'insightface') {
				return this.$avt('face_match:source_insightface', 'InsightFace');
			}
			return String(source || '')
				.replace(/[_-]+/g, ' ')
				.replace(/\s+/g, ' ')
				.trim()
				.replace(/\b\w/g, (char) => char.toUpperCase());
		},
		getFaceMatchFormatLabel(format) {
			const normalized = String(format || '').trim().toUpperCase();
			if (!normalized) {
				return this.$avt('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'ACD' || normalized === 'ACDSEE') {
				return this.$avt('face_match:format_acdsee', 'ACDSee');
			}
			if (normalized === 'MICROSOFT') {
				return this.$avt('face_match:format_microsoft', 'Microsoft People Tagging');
			}
			if (normalized === 'MWG_REGIONS') {
				return this.$avt('face_match:format_mwg_regions', 'MWG face regions');
			}
			if (normalized === 'INSIGHTFACE') {
				return this.$avt('face_match:format_insightface', 'InsightFace detection');
			}
			return String(format);
		},
		getFaceMatchBBox(face) {
			if (!face || typeof face !== 'object') {
				return null;
			}

			const normalized = this.normalizeFaceMatchFace(face);
			if (normalized) {
				return normalized;
			}

			if (face.bbox) {
				const topLeft = face.bbox.top_left;
				const bottomRight = face.bbox.bottom_right;
				let left = Number(topLeft && topLeft.x);
				let top = Number(topLeft && topLeft.y);
				let right = Number(bottomRight && bottomRight.x);
				let bottom = Number(bottomRight && bottomRight.y);

				if (![left, top, right, bottom].every(Number.isFinite)) {
					left = Number(face.bbox.x1);
					top = Number(face.bbox.y1);
					right = Number(face.bbox.x2);
					bottom = Number(face.bbox.y2);
				}

				if ([left, top, right, bottom].every(Number.isFinite)) {
					const width = right - left;
					const height = bottom - top;
					if (width > 0 && height > 0) {
						return { left, top, width, height };
					}
				}
			}

			const centerX = Number(face.x);
			const centerY = Number(face.y);
			const width = Number(face.w);
			const height = Number(face.h);

			if (![centerX, centerY, width, height].every(Number.isFinite)) {
				return null;
			}
			if (width <= 0 || height <= 0) {
				return null;
			}

			return {
				left: centerX - (width / 2),
				top: centerY - (height / 2),
				width,
				height,
			};
		},
		normalizeFaceMatchFace(face) {
			if (face && face.display_normalized) {
				return null;
			}
			const sourceFormat = String(face && face.source_format || '').trim().toUpperCase();
			const orientation = Number(face && face.orientation || 1);
			if (!['MWG_REGIONS', 'MICROSOFT'].includes(sourceFormat) || !Number.isFinite(orientation) || orientation === 1) {
				return null;
			}

			const centerX = Number(face.x);
			const centerY = Number(face.y);
			let width = Number(face.w);
			let height = Number(face.h);
			if (![centerX, centerY, width, height].every(Number.isFinite) || width <= 0 || height <= 0) {
				return null;
			}

			let normalizedX = centerX;
			let normalizedY = centerY;
			if (orientation === 2) {
				normalizedX = 1 - centerX;
			} else if (orientation === 3) {
				normalizedX = 1 - centerX;
				normalizedY = 1 - centerY;
			} else if (orientation === 4) {
				normalizedY = 1 - centerY;
			} else if (orientation === 5) {
				normalizedX = centerY;
				normalizedY = centerX;
				[width, height] = [height, width];
			} else if (orientation === 6) {
				normalizedX = 1 - centerY;
				normalizedY = centerX;
				[width, height] = [height, width];
			} else if (orientation === 7) {
				normalizedX = 1 - centerY;
				normalizedY = 1 - centerX;
				[width, height] = [height, width];
			} else if (orientation === 8) {
				normalizedX = centerY;
				normalizedY = 1 - centerX;
				[width, height] = [height, width];
			} else {
				return null;
			}

			return {
				left: normalizedX - (width / 2),
				top: normalizedY - (height / 2),
				width,
				height,
			};
		},
		getFaceMatchBoxStyle(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return null;
			}

			return {
				left: `${bbox.left * 100}%`,
				top: `${bbox.top * 100}%`,
				width: `${bbox.width * 100}%`,
				height: `${bbox.height * 100}%`,
			};
		},
		getChecksReferenceBoxStyle(face) {
			const style = this.getFaceMatchBoxStyle(face);
			if (!style) {
				return null;
			}
			return {
				...style,
				borderColor: '#009e05',
				boxShadow: 'none',
			};
		},
		getChecksAlertBoxStyle(face, primaryFace, state = 'alert') {
			const style = this.getFaceMatchBoxStyle(face);
			if (!style) {
				return null;
			}
			const primaryStyle = this.getFaceMatchBoxStyle(primaryFace);
			const isPrimary = primaryStyle && JSON.stringify(primaryStyle) === JSON.stringify(style);
			const isSuggested = state === 'suggested';
			return {
				...style,
				borderColor: isSuggested ? '#009e05' : '#d82020',
				boxShadow: !isSuggested && isPrimary ? '0 0 0 1px rgba(216, 32, 32, 0.2), 0 0 10px rgba(216, 32, 32, 0.45)' : 'none',
			};
		},
		getFaceMatchMaskStyles(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return [];
			}

			const left = Math.max(0, bbox.left);
			const top = Math.max(0, bbox.top);
			const right = Math.min(1, bbox.left + bbox.width);
			const bottom = Math.min(1, bbox.top + bbox.height);

			return [
				{ left: '0', top: '0', width: '100%', height: `${top * 100}%` },
				{ left: '0', top: `${top * 100}%`, width: `${left * 100}%`, height: `${Math.max(0, bottom - top) * 100}%` },
				{ left: `${right * 100}%`, top: `${top * 100}%`, width: `${Math.max(0, 1 - right) * 100}%`, height: `${Math.max(0, bottom - top) * 100}%` },
				{ left: '0', top: `${bottom * 100}%`, width: '100%', height: `${Math.max(0, 1 - bottom) * 100}%` },
			];
		},
		getFaceMatchCropStyle(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return null;
			}

			return {
				width: `${100 / bbox.width}%`,
				height: `${100 / bbox.height}%`,
				left: `-${(bbox.left / bbox.width) * 100}%`,
				top: `-${(bbox.top / bbox.height) * 100}%`,
			};
		},
		getRightFaceMatchFace() {
			if (!this.faceMatchResult) {
				return null;
			}
			if (this.faceMatchIsFileSourceAction) {
				return this.faceMatchResult.metadata_face || null;
			}
			if (!this.faceMatchResult.match) {
				return null;
			}
			return this.faceMatchResult.metadata_face || null;
		},
		getLeftFaceMatchFace() {
			if (!this.faceMatchResult) {
				return null;
			}
			if (this.faceMatchIsFileSourceAction) {
				return this.faceMatchResult.source_face || this.faceMatchResult.face || null;
			}
			return this.faceMatchResult.face || null;
		},
		getFaceMatchThumbnailUrl(image) {
			return this.getPhotoThumbnailUrl(image);
		},
		getCurrentFaceMatchImageFallbackUrl() {
			const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
			return imagePath
				? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(imagePath)}`
				: '';
		},
		getCurrentFaceMatchImageUrl() {
			const thumbnailUrl = this.getFaceMatchThumbnailUrl(this.faceMatchResult && this.faceMatchResult.image);
			if (thumbnailUrl) {
				return thumbnailUrl;
			}
			return this.getCurrentFaceMatchImageFallbackUrl();
		},
		handleFaceMatchImagePreviewError(event) {
			const image = event && event.target;
			const fallbackUrl = this.getCurrentFaceMatchImageFallbackUrl();
			if (!image || !fallbackUrl || image.dataset.avFallbackApplied === 'true') {
				return;
			}
			image.dataset.avFallbackApplied = 'true';
			image.src = fallbackUrl;
		},
		getFaceMatchPersonThumbnailUrl(person) {
			const personId = person && person.id;
			const thumbnail = (person && person.additional && person.additional.thumbnail)
				|| (person && person.thumbnail);
			const cacheKey = thumbnail && thumbnail.cache_key;
			const synoToken = this.getSynoToken();
			if (!personId || !cacheKey || !synoToken) {
				return '';
			}

			const params = new URLSearchParams();
			params.set('id', String(personId));
			params.set('cache_key', `"${cacheKey}"`);
			params.set('type', '"person"');
			params.set('size', '"sm"');
			params.set('SynoToken', synoToken);
			return `/synofoto/api/v2/t/Thumbnail/get?${params.toString()}`;
		},
		getFaceMatchPersonPreviewUrl(person) {
			return this.getFaceMatchPersonThumbnailUrl(person) || this.resolveLocalIconUrl('person_unknown.png');
		},
		getCurrentFaceMatchFaceId() {
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			return Number.isFinite(Number(faceId)) ? Number(faceId) : null;
		},
		getFaceMatchEditableNameDefault() {
			if (this.faceMatchIsFileSourceAction) {
				const sourceFace = this.faceMatchResult && (this.faceMatchResult.source_face || this.faceMatchResult.face);
				const sourceName = sourceFace && sourceFace.name ? String(sourceFace.name).trim() : '';
				return sourceName || '';
			}
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const fallbackName = metadataFace && metadataFace.name ? String(metadataFace.name).trim() : '';
			return fallbackName || '';
		},
		normalizeFaceMatchName(name) {
			return String(name || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
		},
		faceMatchEditableNameMatchesPerson(person) {
			if (!person || !person.name) {
				return false;
			}
			return this.normalizeFaceMatchName(this.faceMatchEditableName) === this.normalizeFaceMatchName(person.name);
		},
		syncFaceMatchEditableName() {
			const sourceName = this.getFaceMatchEditableNameDefault();
			const matchedPerson = this.faceMatchResult && this.faceMatchResult.matched_person;
			const matchedPersonName = matchedPerson && matchedPerson.name ? String(matchedPerson.name).trim() : '';
			this.faceMatchEditableName = matchedPersonName || sourceName;
			this.faceMatchInitialEditableName = sourceName;
			this.faceMatchSelectedPerson = matchedPerson && matchedPerson.id ? matchedPerson : null;
			this.clearFaceMatchSuggestions();
		},
		handleFaceMatchNameFocus() {
			if (this.faceMatchPersonSuggestions.length) {
				this.faceMatchShowSuggestions = true;
			}
		},
		handleFaceMatchNameInput() {
			const selectedPerson = this.faceMatchSelectedPerson;
			if (selectedPerson && !this.faceMatchEditableNameMatchesPerson(selectedPerson)) {
				this.faceMatchSelectedPerson = null;
			}
			this.scheduleFaceMatchSuggestions();
		},
		scheduleFaceMatchSuggestions() {
			if (this.faceMatchSuggestTimer) {
				window.clearTimeout(this.faceMatchSuggestTimer);
				this.faceMatchSuggestTimer = null;
			}
			const query = this.faceMatchEditableName.trim();
			if (!query || query.length < 1) {
				this.clearFaceMatchSuggestions();
				return;
			}
			this.faceMatchSuggestTimer = window.setTimeout(() => {
				this.fetchFaceMatchSuggestions(query);
			}, 200);
		},
			async fetchFaceMatchSuggestions(query) {
				const currentQuery = String(query || '').trim();
				if (!currentQuery) {
					this.clearFaceMatchSuggestions();
					return;
			}
				const requestId = this.faceMatchSuggestRequestId + 1;
				this.faceMatchSuggestRequestId = requestId;
				this.faceMatchPersonSuggestLoading = true;
				this.faceMatchShowSuggestions = true;
				try {
					const data = await this.callDsmApi(
						'/webman/3rdparty/AV_ImgData/index.cgi/api/face_person_suggest',
						{
							name_prefix: currentQuery,
							limit: 10,
						},
						{ requireResumeMessage: true }
					);
					if (this.faceMatchSuggestRequestId !== requestId) {
						return;
					}
				const root = this.getResponseData(data);
				this.faceMatchPersonSuggestions = Array.isArray(root.list) ? root.list : [];
				this.faceMatchShowSuggestions = this.faceMatchPersonSuggestions.length > 0;
			} catch (err) {
				if (this.faceMatchSuggestRequestId !== requestId) {
					return;
				}
				this.clearFaceMatchSuggestions();
			} finally {
				if (this.faceMatchSuggestRequestId === requestId) {
					this.faceMatchPersonSuggestLoading = false;
				}
			}
		},
		selectFaceMatchSuggestion(person) {
			if (!person || !person.id) {
				return;
			}
			this.faceMatchSelectedPerson = person;
			this.faceMatchEditableName = person.name || '';
			this.clearFaceMatchSuggestions();
		},
		resolveFaceMatchNameMappingPreference(targetName) {
			const sourceName = (this.faceMatchInitialEditableName || '').trim();
			const nextName = String(targetName || '').trim();
			if (!sourceName || !nextName) {
				return Promise.resolve({ saveMapping: false, sourceName: '' });
			}
			if (this.normalizeFaceMatchName(sourceName) === this.normalizeFaceMatchName(nextName)) {
				return Promise.resolve({ saveMapping: false, sourceName });
			}
			if (this.faceMatchHasStoredNameMapping) {
				return Promise.resolve({ saveMapping: false, sourceName });
			}
			return this.confirmFaceMatchNameMapping(sourceName, nextName).then((result) => ({
				saveMapping: !!(result && result.saveMapping),
				sourceName,
			}));
		},
		confirmFaceMatchNameMapping(sourceName, targetName, options = {}) {
			return new Promise((resolve) => {
				const context = String(options && options.context || 'face_match').trim() || 'face_match';
				this.nameMappingConfirm.visible = true;
				this.nameMappingConfirm.message = this.$avt(
					'face_match:confirm_save_mapping',
					'Should "{source}" always be mapped to "{target}"?',
					{ source: sourceName, target: targetName }
				);
				this.nameMappingConfirm.context = context;
				this.nameMappingConfirm.skipFuturePrompts = false;
				this.nameMappingConfirm.resolver = resolve;
			});
		},
		resolveNameMappingConfirm(value) {
			const resolver = this.nameMappingConfirm.resolver;
			const context = String(this.nameMappingConfirm.context || 'face_match').trim() || 'face_match';
			const skipFuturePrompts = !!this.nameMappingConfirm.skipFuturePrompts;
			this.nameMappingConfirm.visible = false;
			this.nameMappingConfirm.message = '';
			this.nameMappingConfirm.resolver = null;
			this.nameMappingConfirm.context = '';
			this.nameMappingConfirm.skipFuturePrompts = false;
			if (typeof resolver === 'function') {
				resolver({
					saveMapping: skipFuturePrompts && context === 'checks' ? false : !!value,
					skipFuturePrompts: skipFuturePrompts && context === 'checks',
				});
			}
		},
		async advanceFaceMatchFindingsAfterTransfer(data) {
			const findingsUpdate = this.getResponseDataObject(data, 'findings_update');
			const faceId = this.getCurrentFaceMatchFaceId();
			const currentIndex = Math.max(0, Number(this.faceMatchFindingIndex) || 0);
			const removedByBackend = !!(findingsUpdate && findingsUpdate.removed);
			const removedCount = Math.max(0, Number(findingsUpdate && findingsUpdate.removed_count) || 0);

			let remainingEntries = this.faceMatchFindingEntries.filter((entry, index) => {
				if (!entry || typeof entry !== 'object') {
					return true;
				}

				if (faceId) {
					const entryFaceId = Number(entry && entry.face && entry.face.face_id);
					if (Number.isFinite(entryFaceId) && entryFaceId === faceId) {
						return false;
					}
				}

				if (!faceId && removedByBackend && removedCount > 0 && index === currentIndex) {
					return false;
				}

				return true;
			});

			if (remainingEntries.length === this.faceMatchFindingEntries.length && removedByBackend && removedCount > 0) {
				remainingEntries = this.faceMatchFindingEntries.filter((entry, index) => index !== currentIndex);
			}

			this.faceMatchFindingEntries = remainingEntries;
			this.faceMatchFindingsStatus = {
				...(this.faceMatchFindingsStatus || {}),
				count: Number.isFinite(Number(findingsUpdate.remaining_count))
					? Math.max(0, Number(findingsUpdate.remaining_count))
					: remainingEntries.length,
				transferred_count: Number.isFinite(Number(findingsUpdate.transferred_count))
					? Math.max(0, Number(findingsUpdate.transferred_count))
					: (this.faceMatchTransferredCount + 1),
			};
			this.faceMatchTransferredCount = Number(this.faceMatchFindingsStatus.transferred_count) || 0;

			if (!remainingEntries.length) {
				this.faceMatchResult = null;
				this.faceMatchFindingIndex = 0;
				this.resetFaceMatchSelectionState();
				this.faceMatchUseStoredFindings = false;
				this.setFaceMatchProgressMessage(
					this.$avt('face_match:status_findings_empty', 'No saved matches found.')
				);
				return;
			}

			const nextIndex = Math.min(currentIndex, remainingEntries.length - 1);
			await this.loadFaceMatchFindingAtIndex(nextIndex);
		},
		buildNextSkippedFaceIds() {
			const currentFaceId = this.getCurrentFaceMatchFaceId();
			if (!currentFaceId) {
				return this.faceMatchSkippedFaceIds.slice();
			}
			const nextIds = this.faceMatchSkippedFaceIds.slice();
			if (!nextIds.includes(currentFaceId)) {
				nextIds.push(currentFaceId);
			}
			return nextIds;
		},
		buildNextSkippedTargets() {
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
			if (!metadataFace || !imagePath) {
				return this.faceMatchSkippedTargets.slice();
			}
			const token = [
				String(imagePath || '').trim(),
				String(metadataFace.source_format || '').trim().toUpperCase(),
				Number(metadataFace.x || 0).toFixed(FACE_COORDINATE_DIGITS),
				Number(metadataFace.y || 0).toFixed(FACE_COORDINATE_DIGITS),
				Number(metadataFace.w || 0).toFixed(FACE_COORDINATE_DIGITS),
				Number(metadataFace.h || 0).toFixed(FACE_COORDINATE_DIGITS),
			].join('|');
			const nextTargets = this.faceMatchSkippedTargets.slice();
			if (!nextTargets.includes(token)) {
				nextTargets.push(token);
			}
			return nextTargets;
		},
		syncFaceMatchTransferredCountFromProgress(progress) {
			const progressCount = Number(progress && progress.transferred_count);
			if (!Number.isFinite(progressCount) || progressCount <= 0) {
				return;
			}
			const localCount = Number(this.faceMatchTransferredCount) || 0;
			this.faceMatchTransferredCount = Math.max(localCount, progressCount);
		},
		invalidateFaceMatchProgressRequests() {
			this.faceMatchProgressRequestId += 1;
			this.faceMatchProgressRequestPending = false;
		},
		isFaceMatchProgressUpdateStale(current, next) {
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
		applyFaceMatchingProgress(progress, { authoritative = false } = {}) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			if (!authoritative && this.isFaceMatchProgressUpdateStale(this.faceMatchProgress, nextProgress)) {
				return false;
			}
			this.syncFaceMatchTransferredCountFromProgress(nextProgress);
			if (this.isFaceMatchFindingsReviewActive() && this.getFaceMatchProgressMode(nextProgress) === 'scan') {
				return true;
			}
			this.faceMatchProgress = nextProgress;
			const result = nextProgress && typeof nextProgress.result === 'object' ? nextProgress.result : null;
			if (result && Object.keys(result).length) {
				this.faceMatchResult = result;
				this.syncFaceMatchEditableName();
			} else if (!nextProgress.running && !nextProgress.paused) {
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
			}
			return true;
		},
		async fetchFaceMatchingProgress({ applyRunningState = true, allowConcurrent = false } = {}) {
			if (this.faceMatchProgressRequestPending && !allowConcurrent) {
				return {};
			}
			const requestId = this.faceMatchProgressRequestId + 1;
			this.faceMatchProgressRequestId = requestId;
			this.faceMatchProgressRequestPending = true;
			try {
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_progress', {}, { resume: false, requireSynoToken: false });
				if (this.faceMatchProgressRequestId !== requestId) {
					return {};
				}
				const progress = this.getResponseData(data);
				if (progress.running && !applyRunningState) {
					return progress;
				}
				const incompleteWorkerHandoff = !!(
					this.faceMatchLoading
					&& !progress.running
					&& !progress.finished
					&& !progress.paused
					&& !progress.auth_required
					&& !progress.stop_requested
					&& String(progress.operation_id || '').trim()
				);
				if (incompleteWorkerHandoff) {
					return progress;
				}
				if (!this.applyFaceMatchingProgress(progress)) {
					return {};
				}
				if (progress.paused && !progress.running) {
					this.faceMatchLoading = false;
				}
				if (!progress.running) {
					this.faceMatchLoading = false;
					await this.fetchFaceMatchFindingsStatus();
					this.stopFaceMatchProgressPolling();
				}
				return progress;
			} catch (err) {
				if (this.faceMatchProgressRequestId === requestId) {
					this.faceMatchProgress = {
						...(this.faceMatchProgress || {}),
						message: `Error: ${err.message}`,
					};
				}
				return {};
			} finally {
				if (this.faceMatchProgressRequestId === requestId) {
					this.faceMatchProgressRequestPending = false;
				}
			}
		},
		startFaceMatchProgressPolling() {
			this.startNamedPolling('faceMatchProgressTimer', () => this.fetchFaceMatchingProgress(), 1000, { skipIfPending: true });
		},
		stopFaceMatchProgressPolling() {
			this.stopNamedPolling('faceMatchProgressTimer');
		},
		getFaceMatchStatusCountSegments() {
			const segments = [
				`${this.$avt('face_match:label_images', 'Images')}: ${this.faceMatchDisplayedProgress.images_read}`,
				`${this.faceMatchFacesLabel}: ${this.faceMatchDisplayedProgress.faces_read}`,
			];
			if (this.showFaceMatchTargetFacesCounter) {
				segments.push(`${this.$avt('face_match:label_target_faces', 'Unknown faces')}: ${this.faceMatchDisplayedProgress.target_faces_read}`);
			}
			segments.push(`${this.faceMatchMetadataLabel}: ${this.faceMatchDisplayedProgress.metadata_faces_read}`);
			segments.push(`${this.$avt('face_match:label_findings', 'Findings')}: ${this.faceMatchDisplayedFindingsCount}`);
			segments.push(`${this.$avt('face_match:label_skipped', 'Skipped')}: ${this.faceMatchDisplayedSkippedCount}`);
			segments.push(`${this.$avt('face_match:label_transferred', 'Transferred')}: ${this.faceMatchDisplayedTransferredCount}`);
			return segments;
		},
		withFaceMatchStatusCounts(message) {
			const counters = this.getFaceMatchStatusCounters();
			if (!Array.isArray(counters) || !counters.length) {
				return message;
			}
			const suffix = counters
				.map((counter) => {
					const label = String(counter.label || this.getFaceMatchStatusCounterLabel(counter) || '').replace(/:$/, '').trim();
					return label ? `${label}: ${counter.value}` : String(counter.value);
				})
				.filter(Boolean)
				.join(' · ');
			return suffix ? `${message} | ${suffix}` : message;
		},
		async loadNextFaceMatch() {
			if (this.faceMatchInteractionDisabled) {
				return;
			}
			if (this.faceMatchReviewingStoredFindings) {
				if (!this.hasNextFaceMatch) {
					return;
				}
				await this.skipStoredFaceMatchFinding();
				return;
			}
			if (['search_file_face_in_sources', 'mark_missing_photos_faces', 'search_missing_faces_insightface'].includes(this.selectedFaceMatchingAction)) {
				this.faceMatchSkippedTargets = this.buildNextSkippedTargets();
			} else {
				this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
			}
			await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
		},
		async handlePrimaryFaceMatchButton() {
			if (this.faceMatchHasActiveProgressState) {
				await this.stopFaceMatchingAction();
				return;
			}
			await this.startFaceMatchingAction({
				resetSkippedFaceIds: !this.faceMatchAuthRequired,
				resumeFromProgress: this.faceMatchAuthRequired,
			});
		},
		async stopFaceMatchingAction() {
			try {
				await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_stop', {}, { resume: false, requireSynoToken: false });
			} catch (err) {
				// Best effort.
			}
			this.output = this.$avt('face_match:output_stopping', 'Stopping search...');
			await this.fetchFaceMatchingProgress();
		},
		async handleFaceMatchAction() {
			if (this.faceMatchInteractionDisabled || !this.faceMatchActionMode) {
				return;
			}
			this.faceMatchActionLocked = true;
			try {
				if (this.faceMatchActionMode === 'write_metadata') {
					await this.applyFaceMatchToMetadata();
					return;
				}
				if (this.faceMatchActionMode === 'create') {
					await this.createFaceMatchPerson();
					return;
				}
				await this.assignFaceMatchToPerson();
			} finally {
				this.faceMatchActionLocked = false;
			}
		},
			async createFaceMatchPerson() {
				const personName = (this.faceMatchEditableName || this.getFaceMatchEditableNameDefault()).trim();
				const isMetadataPhotosCreate = this.faceMatchAddsNewPhotosFaces;
				const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
				const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
				const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
				if ((!isMetadataPhotosCreate && !faceId) || !personName || (isMetadataPhotosCreate && (!metadataFace || !imagePath))) {
					this.output = this.$avt('face_match:error_missing_face_or_name', 'Error: Missing face ID or person name.');
					return;
				}
				const mappingPreference = await this.resolveFaceMatchNameMappingPreference(personName);

				try {
					this.setFaceMatchMutationPending(
						'face_match:output_create_metadata_face_starting',
						'Creating Photos person/face for {person}: {path}',
						imagePath,
						personName
					);
					const data = await this.callDsmApi(
						isMetadataPhotosCreate
							? '/webman/3rdparty/AV_ImgData/index.cgi/api/face_create_metadata_match'
							: '/webman/3rdparty/AV_ImgData/index.cgi/api/face_create_match',
						{
							face_id: faceId,
							image_path: imagePath,
							metadata_face: metadataFace,
							person_name: personName,
							save_mapping: mappingPreference.saveMapping,
							source_name: mappingPreference.sourceName,
						},
						{ requireResumeMessage: true }
					);
					this.output = JSON.stringify(data, null, 2);
					if (this.faceMatchReviewingStoredFindings) {
							await this.loadStoredFaceMatchFindings({ refresh: true });
					} else {
						this.faceMatchTransferredCount += 1;
						if (isMetadataPhotosCreate) {
							this.faceMatchSkippedTargets = this.buildNextSkippedTargets();
						} else {
							this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
						}
						await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
					}
				} catch (err) {
					await this.reconcileStoredFaceMatchFindingsAfterMutationError(err);
				}
			},
			async assignFaceMatchToPerson() {
				const matchedPersonId = this.faceMatchEffectivePerson && this.faceMatchEffectivePerson.id;
				const isMetadataPhotosAssign = this.faceMatchAddsNewPhotosFaces;
				const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
				const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
				const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
				const matchedPersonName = (this.faceMatchEditableName || '').trim();
				if (!matchedPersonId || (!isMetadataPhotosAssign && !faceId) || !matchedPersonName || (isMetadataPhotosAssign && (!metadataFace || !imagePath))) {
					this.output = this.$avt('face_match:error_missing_known_person', 'Error: Missing known person ID, face ID, or person name.');
					return;
				}
				const mappingPreference = await this.resolveFaceMatchNameMappingPreference(matchedPersonName);

				try {
					this.setFaceMatchMutationPending(
						isMetadataPhotosAssign
							? 'face_match:output_assign_metadata_face_starting'
							: 'face_match:output_assign_photos_face_starting',
						isMetadataPhotosAssign
							? 'Adding metadata face to Photos for {person}: {path}'
							: 'Assigning Photos face to {person}: {path}',
						imagePath,
						matchedPersonName
					);
					const data = await this.callDsmApi(
						isMetadataPhotosAssign
							? '/webman/3rdparty/AV_ImgData/index.cgi/api/face_assign_metadata_match'
							: '/webman/3rdparty/AV_ImgData/index.cgi/api/face_assign_match',
						{
							face_id: faceId,
							image_path: imagePath,
							metadata_face: metadataFace,
							person_id: matchedPersonId,
							person_name: matchedPersonName,
							save_mapping: mappingPreference.saveMapping,
							source_name: mappingPreference.sourceName,
						},
						{ requireResumeMessage: true }
					);
					this.output = JSON.stringify(data, null, 2);
					if (this.faceMatchReviewingStoredFindings) {
						await this.advanceFaceMatchFindingsAfterTransfer(data);
					} else {
						this.faceMatchTransferredCount += 1;
						if (isMetadataPhotosAssign) {
							this.faceMatchSkippedTargets = this.buildNextSkippedTargets();
						} else {
							this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
						}
						await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
					}
				} catch (err) {
					await this.reconcileStoredFaceMatchFindingsAfterMutationError(err);
				}
			},
			async applyFaceMatchToMetadata() {
				const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
				const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
				const personName = (this.faceMatchEditableName || '').trim();
				if (!metadataFace || !imagePath || !personName) {
					this.output = this.$avt('face_match:error_missing_face_or_name', 'Error: Missing face ID or person name.');
					return;
				}
				try {
					this.setFaceMatchMutationPending(
						'face_match:output_apply_metadata_face_starting',
						'Writing metadata face for {person}: {path}',
						imagePath,
						personName
					);
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_apply_metadata_match', {
						image_path: imagePath,
						metadata_face: metadataFace,
						person_name: personName,
					});
					this.output = JSON.stringify(data, null, 2);
					if (this.faceMatchReviewingStoredFindings) {
						await this.loadStoredFaceMatchFindings();
					} else {
						this.faceMatchTransferredCount += 1;
						this.faceMatchSkippedTargets = this.buildNextSkippedTargets();
						await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
					}
				} catch (err) {
					await this.reconcileStoredFaceMatchFindingsAfterMutationError(err);
				}
			},
		async startFaceMatchingAction(options = {}) {
			if (this.faceMatchLoading) {
				return;
			}
			this.stopFaceMatchProgressPolling();
			this.invalidateFaceMatchProgressRequests();
			if (this.faceMatchReviewingStoredFindings) {
				this.faceMatchLoading = true;
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
				try {
					await this.loadStoredFaceMatchFindings();
				} catch (err) {
					this.faceMatchResult = null;
					this.faceMatchProgress = {
						...(this.faceMatchProgress || {}),
						message: `Error: ${err.message}`,
					};
				} finally {
					this.faceMatchLoading = false;
				}
				return;
			}
			if (this.selectedFaceMatchingAction === 'search_missing_faces_insightface' && !this.hasInsightFaceForFaceMatch) {
				this.faceMatchProgress = {
					...(this.faceMatchProgress || {}),
					message_key: 'face_match:progress_insightface_missing',
					message: this.$avt('face_match:progress_insightface_missing', 'InsightFace is not installed.'),
				};
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
				return;
			}
			const resetSkippedFaceIds = options.resetSkippedFaceIds !== false;
			const resumeFromProgress = options.resumeFromProgress === true;
			if (resetSkippedFaceIds) {
				this.faceMatchSkippedFaceIds = [];
				this.faceMatchSkippedTargets = [];
				this.faceMatchTransferredCount = 0;
				this.faceMatchProgressBase = {
					persons_read: 0,
					images_read: 0,
					faces_read: 0,
					target_faces_read: 0,
					metadata_faces_read: 0,
				};
				this.resetFaceMatchFindingsReview();
			} else {
				const displayedProgress = this.faceMatchDisplayedProgress || {};
				this.faceMatchProgressBase = {
					persons_read: Math.max(0, Number(displayedProgress.persons_read) || 0),
					images_read: Math.max(0, Number(displayedProgress.images_read) || 0),
					faces_read: Math.max(0, Number(displayedProgress.faces_read) || 0),
					target_faces_read: Math.max(0, Number(displayedProgress.target_faces_read) || 0),
					metadata_faces_read: Math.max(0, Number(displayedProgress.metadata_faces_read) || 0),
				};
				const resumeCursor = this.faceMatchProgress && typeof this.faceMatchProgress.resume_cursor === 'object'
					? this.faceMatchProgress.resume_cursor
					: null;
				const cursorSkipFaceIds = resumeCursor && Array.isArray(resumeCursor.skip_face_ids)
					? resumeCursor.skip_face_ids
					: [];
				const cursorSkipTargets = resumeCursor && Array.isArray(resumeCursor.skip_targets)
					? resumeCursor.skip_targets
					: [];
				if (cursorSkipFaceIds.length) {
					const mergedFaceIds = [
						...this.faceMatchSkippedFaceIds,
						...cursorSkipFaceIds.map(value => Number(value)).filter(value => Number.isFinite(value) && value > 0),
					];
					this.faceMatchSkippedFaceIds = Array.from(new Set(mergedFaceIds));
				}
				if (cursorSkipTargets.length) {
					const mergedTargets = [
						...this.faceMatchSkippedTargets,
						...cursorSkipTargets.map(value => String(value || '').trim()).filter(value => value),
					];
					this.faceMatchSkippedTargets = Array.from(new Set(mergedTargets));
				}
			}

			this.faceMatchLoading = true;
			if (resetSkippedFaceIds) {
				const buildsFileList = [
					'search_file_face_in_sources',
					'mark_missing_photos_faces',
					'search_missing_faces_insightface',
				].includes(this.selectedFaceMatchingAction);
				this.faceMatchProgress = {
					running: true,
					action: this.selectedFaceMatchingAction,
					message_key: buildsFileList
						? 'face_match:status_preparing_scan'
						: 'face_match:status_starting',
					message: buildsFileList
						? this.$avt('face_match:status_preparing_scan', 'Face matching starts. Building file list...')
						: this.$avt('face_match:status_starting', 'Search starting...'),
				};
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
			}
			this.output = this.$avt('face_match:output_start_action', 'Starting action: {action}', { action: this.selectedFaceMatchingAction });
			try {
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_action', {
					action: this.selectedFaceMatchingAction,
					auto: this.faceMatchAutoAssignKnown,
					save_only: this.faceMatchUseStoredFindings ? false : this.faceMatchSaveOnly,
					resume_from_progress: resumeFromProgress,
					skip_face_ids: this.faceMatchSkippedFaceIds,
					skip_targets: this.faceMatchSkippedTargets,
				}, { requireResumeMessage: true });
				const faceMatches = this.getResponseDataObject(data, 'face_matches');
				if (!this.applyFaceMatchingProgress(faceMatches, { authoritative: true })) {
					return;
				}
				if (faceMatches && faceMatches.running) {
					this.faceMatchLoading = true;
					this.startFaceMatchProgressPolling();
				} else {
					this.faceMatchLoading = false;
					this.stopFaceMatchProgressPolling();
				}
				await this.fetchFaceMatchFindingsStatus();
				this.syncFaceMatchTransferredCountFromProgress(faceMatches);
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				if (resetSkippedFaceIds) {
					this.faceMatchResult = null;
					this.resetFaceMatchSelectionState();
				}
				this.faceMatchLoading = false;
				this.stopFaceMatchProgressPolling();
				this.output = `Error: ${err.message}`;
			}
		},
	},
};
