export default {
	data() {
		return {
			faceMatchLoading: false,
			faceMatchProgress: {},
			faceMatchProgressTimer: null,
			faceMatchProgressRequestId: 0,
			faceMatchResult: null,
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
			return !!(
				this.faceMatchLoading
				|| progress.running
				|| progress.stop_requested
				|| progress.message_key
				|| progress.message
				|| Object.keys(progress).length
			);
		},
		faceMatchNumberFrom(...values) {
			for (const value of values) {
				const numeric = Number(value);
				if (Number.isFinite(numeric) && numeric > 0) {
					return numeric;
				}
			}
			return 0;
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
			return Math.max(0, Number(this.faceMatchProgress && this.faceMatchProgress.persons_total) || 0);
		},
		faceMatchPersonsChecked() {
			const checked = Math.max(0, Number(this.faceMatchDisplayedProgress && this.faceMatchDisplayedProgress.persons_read) || 0);
			const total = this.faceMatchPersonsTotal;
			return total > 0 ? Math.min(checked, total) : checked;
		},
		faceMatchShowPersonsProgress() {
			return !this.faceMatchShowStoredFindingsProgress
				&& !this.faceMatchIsFileSourceAction
				&& (
					this.faceMatchPersonsTotal > 0
					|| this.faceMatchHasActiveProgressState
				);
		},
		faceMatchShowFileProgress() {
			return !this.faceMatchShowStoredFindingsProgress
				&& this.faceMatchIsFileSourceAction
				&& (
					this.faceMatchFileProgressTotal > 0
					|| this.faceMatchHasActiveProgressState
				);
		},
		faceMatchShowStoredFindingsProgress() {
			return this.faceMatchReviewingStoredFindings && this.faceMatchStoredFindingsTotal > 0;
		},
		faceMatchStoredFindingsTotal() {
			return Math.max(
				0,
				Number(this.faceMatchFindingEntriesTotal) || 0,
				Array.isArray(this.faceMatchFindingEntries) ? this.faceMatchFindingEntries.length : 0,
				Number(this.faceMatchFindingsStatus && this.faceMatchFindingsStatus.count) || 0
			);
		},
		faceMatchStoredFindingsChecked() {
			const total = this.faceMatchStoredFindingsTotal;
			if (!total) {
				return 0;
			}
			return Math.min(total, Math.max(0, Number(this.faceMatchFindingIndex) || 0) + 1);
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
		faceMatchPrimaryButtonLabel() {
			if (this.faceMatchLoading) {
				return this.$avt('face_match:button_stop', 'Stop');
			}
			if (this.faceMatchAuthRequired) {
				return this.$avt('face_match:button_resume_login', 'Resume after login');
			}
			if (this.faceMatchIsPaused) {
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
			return (Number(this.faceMatchFindingsStatus && this.faceMatchFindingsStatus.count) || 0) > 0;
		},
		faceMatchLeftTitle() {
			if (this.faceMatchIsFileSourceAction) {
				return this.$avt('face_match:label_source', 'Source');
			}
			return this.$avt('face_match:photos_title', 'Photos');
		},
		faceMatchRightTitle() {
			return this.faceMatchFileTitle;
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
			if (nextAction === 'load_photo_face_match_findings') {
				this.faceMatchUseStoredFindings = true;
				this.selectedFaceMatchingAction = 'search_photo_face_in_file';
			}
		},
		faceMatchUseStoredFindings(useStoredFindings) {
			if (useStoredFindings) {
				this.faceMatchSaveOnly = false;
			} else {
				this.resetFaceMatchFindingsReview();
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
		async refreshFaceMatchSessionState() {
			await this.fetchFaceMatchFindingsStatus();
			if (typeof this.fetchPipPackagesStatus === 'function') {
				await this.fetchPipPackagesStatus();
			}
			await this.fetchFaceMatchingProgress();
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: {};
			if (progress.running) {
				this.faceMatchLoading = true;
				this.startFaceMatchProgressPolling();
				return;
			}
			this.faceMatchLoading = false;
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
					{},
					{ resume: false, requireSynoToken: false }
				);
				this.faceMatchFindingsStatus = this.getResponseData(data);
				if (this.faceMatchReviewingStoredFindings && !this.hasFaceMatchStoredFindings) {
					this.faceMatchUseStoredFindings = false;
					this.resetFaceMatchFindingsReview();
				}
			} catch (err) {
				this.faceMatchFindingsStatus = {};
			}
		},
		resetFaceMatchFindingsReview() {
			this.faceMatchFindingEntries = [];
			this.faceMatchFindingIndex = 0;
			this.faceMatchFindingEntriesTotal = 0;
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
					current: index + 1,
					total: this.faceMatchStoredFindingsTotal || this.faceMatchFindingEntries.length,
				})
			);
		},
		async loadStoredFaceMatchFindings() {
			const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_action', {
				action: 'load_photo_face_match_findings',
				auto: this.faceMatchAutoAssignKnown,
			});
			const payload = this.getResponseDataObject(data, 'face_matches');
			const entries = Array.isArray(payload.entries) ? payload.entries : [];
			this.faceMatchFindingEntries = entries;
			this.faceMatchFindingIndex = 0;
			this.faceMatchFindingEntriesTotal = Number(payload.count) || entries.length;
			this.faceMatchTransferredCount = Number(payload.transferred_count) || 0;
			this.faceMatchFindingsStatus = {
				...(this.faceMatchFindingsStatus || {}),
				count: Number(payload.count) || entries.length,
				status: payload.status || '',
				transferred_count: Number(payload.transferred_count) || 0,
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
		getCurrentFaceMatchImageUrl() {
			const thumbnailUrl = this.getFaceMatchThumbnailUrl(this.faceMatchResult && this.faceMatchResult.image);
			if (thumbnailUrl) {
				return thumbnailUrl;
			}
			const imagePath = this.faceMatchResult && this.faceMatchResult.image_path;
			return imagePath
				? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(imagePath)}`
				: '';
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
			const remainingEntries = this.faceMatchFindingEntries.filter((entry) => {
				if (!faceId || !entry || typeof entry !== 'object') {
					return true;
				}
				const entryFaceId = Number(entry && entry.face && entry.face.face_id);
				return !Number.isFinite(entryFaceId) || entryFaceId !== faceId;
			});

			this.faceMatchFindingEntries = remainingEntries;
			this.faceMatchFindingsStatus = {
				...(this.faceMatchFindingsStatus || {}),
				count: Number(findingsUpdate.remaining_count) || remainingEntries.length,
				transferred_count: Number(findingsUpdate.transferred_count) || (this.faceMatchTransferredCount + 1),
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

			const nextIndex = Math.min(this.faceMatchFindingIndex, remainingEntries.length - 1);
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
				Number(metadataFace.x || 0).toFixed(6),
				Number(metadataFace.y || 0).toFixed(6),
				Number(metadataFace.w || 0).toFixed(6),
				Number(metadataFace.h || 0).toFixed(6),
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
		applyFaceMatchingProgress(progress) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			if (this.isFaceMatchProgressUpdateStale(this.faceMatchProgress, nextProgress)) {
				return false;
			}
			this.faceMatchProgress = nextProgress;
			this.syncFaceMatchTransferredCountFromProgress(nextProgress);
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
		async fetchFaceMatchingProgress() {
			const requestId = this.faceMatchProgressRequestId + 1;
			this.faceMatchProgressRequestId = requestId;
			try {
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_progress', {}, { resume: false, requireSynoToken: false });
				if (this.faceMatchProgressRequestId !== requestId) {
					return;
				}
				const progress = this.getResponseData(data);
				if (!this.applyFaceMatchingProgress(progress)) {
					return;
				}
				if (progress.paused && !progress.running) {
					this.faceMatchLoading = false;
				}
				if (!progress.running) {
					this.faceMatchLoading = false;
					await this.fetchFaceMatchFindingsStatus();
					this.stopFaceMatchProgressPolling();
				}
			} catch (err) {
				return;
			}
		},
		startFaceMatchProgressPolling() {
			this.startNamedPolling('faceMatchProgressTimer', () => {
				this.fetchFaceMatchingProgress();
			});
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
		withFaceMatchStatusCounts(text) {
			const segments = this.getFaceMatchStatusCountSegments();
			const normalized = String(text || '').trim();
			return normalized ? `${normalized} | ${segments.join(' | ')}` : segments.join(' | ');
		},
		async loadNextFaceMatch() {
			if (this.faceMatchReviewingStoredFindings) {
				if (!this.hasNextFaceMatch) {
					return;
				}
				await this.loadFaceMatchFindingAtIndex(this.faceMatchFindingIndex + 1);
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
			if (this.faceMatchLoading) {
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
			if (this.faceMatchActionMode === 'write_metadata') {
				await this.applyFaceMatchToMetadata();
				return;
			}
			if (this.faceMatchActionMode === 'create') {
				await this.createFaceMatchPerson();
				return;
			}
			await this.assignFaceMatchToPerson();
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
					await this.advanceFaceMatchFindingsAfterTransfer(data);
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
				this.output = `Error: ${err.message}`;
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
				this.output = `Error: ${err.message}`;
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
				this.output = `Error: ${err.message}`;
			}
		},
		async startFaceMatchingAction(options = {}) {
			if (this.faceMatchLoading) {
				return;
			}
			this.stopFaceMatchProgressPolling();
			this.faceMatchProgressRequestId += 1;
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
				this.faceMatchProgressBase = {
					persons_read: 0,
					images_read: 0,
					faces_read: 0,
					target_faces_read: 0,
					metadata_faces_read: 0,
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
				this.faceMatchProgress = {
					message: this.$avt('face_match:status_starting', 'Search starting...'),
				};
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
			}
			this.startFaceMatchProgressPolling();
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
				if (!this.applyFaceMatchingProgress(faceMatches)) {
					return;
				}
				if (faceMatches && faceMatches.running) {
					this.faceMatchLoading = true;
					this.startFaceMatchProgressPolling();
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
