export default {
	data() {
		return {
			faceMatchLoading: false,
			faceMatchProgress: {},
			faceMatchProgressBase: {},
			faceMatchProgressTimer: null,
			faceMatchProgressRequestId: 0,
			faceMatchResult: null,
			faceMatchSkippedFaceIds: [],
			faceMatchSkippedTargets: [],
			faceMatchPreviewMode: 'photo',
			faceMatchAutoAssignKnown: false,
			faceMatchSaveOnly: false,
			faceMatchTransferredCount: 0,
			faceMatchTransferredBaseCount: 0,
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
			faceMatchFindingsStatus: {},
			selectedFaceMatchingAction: 'search_photo_face_in_file',
			addIconUrl: '',
			personDataToLeftIconUrl: '',
			personDataToRightIconUrl: '',
			nameMappingConfirm: {
				visible: false,
				message: '',
				resolver: null,
			},
		};
	},
	computed: {
		faceMatchCurrentAction() {
			if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
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
			const baseCount = Number(this.faceMatchTransferredBaseCount) || 0;
			if (!Number.isFinite(progressCount) || progressCount <= 0) {
				return localCount;
			}
			if (baseCount > 0) {
				return Math.max(localCount, baseCount + progressCount);
			}
			return Math.max(localCount, progressCount);
		},
		faceMatchDisplayedProgress() {
			const fields = ['persons_read', 'images_read', 'faces_read', 'target_faces_read', 'metadata_faces_read'];
			return fields.reduce((acc, field) => {
				const baseValue = Number(this.faceMatchProgressBase && this.faceMatchProgressBase[field]) || 0;
				const currentValue = Number(this.faceMatchProgress && this.faceMatchProgress[field]) || 0;
				acc[field] = baseValue + currentValue;
				return acc;
			}, {});
		},
		showFaceMatchPersonsCounter() {
			return this.faceMatchCurrentAction !== 'search_file_face_in_sources';
		},
		showFaceMatchTargetFacesCounter() {
			return this.faceMatchCurrentAction === 'search_file_face_in_sources';
		},
		faceMatchStatusMessage() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: null;
			if (progress && progress.message_key) {
				const messageKey = String(progress.message_key);
				const persistentMessages = new Set([
					'face_match:progress_stopping',
					'face_match:progress_finished',
					'face_match:progress_shared_folder_missing',
					'face_match:progress_stopped',
					'face_match:progress_findings_empty',
					'face_match:progress_findings_saved',
					'face_match:progress_auto_assign_complete',
					'face_match:progress_auto_metadata_assign_complete',
					'face_match:progress_auth_required',
					'face_match:progress_failed',
					'face_match:result_none',
					'face_match:result_no_match',
					'face_match:result_named_match',
					'face_match:result_named_match_with_id',
					'face_match:result_named_source_match',
					'face_match:result_named_source_match_with_id',
					'face_match:status_list_entry',
					'face_match:status_findings_empty',
				]);
				if (this.faceMatchLoading && !persistentMessages.has(messageKey)) {
					return this.$t('face_match:status_search_running', 'Search running...');
				}
				return this.$t(
					messageKey,
					progress.message || messageKey,
					progress.message_params && typeof progress.message_params === 'object'
						? progress.message_params
						: null
				);
			}
			if (progress && progress.message) {
				return progress.message;
			}
			return this.faceMatchLoading
				? this.$t('face_match:status_search_running', 'Search running...')
				: this.$t('face_match:status_idle', 'No action running.');
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
				return this.$t('face_match:button_stop', 'Stop');
			}
			if (this.faceMatchAuthRequired) {
				return this.$t('face_match:button_resume_login', 'Resume after login');
			}
			if (this.faceMatchIsPaused) {
				return this.$t('face_match:button_restart', 'Restart');
			}
			return this.$t('face_match:button_start', 'Start');
		},
		faceMatchResultSummary() {
			if (this.faceMatchLoading) {
				return { found: false, message: this.$t('face_match:result_none', 'No result yet.') };
			}
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
				const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
				const sourceFace = this.faceMatchResult && (this.faceMatchResult.source_face || this.faceMatchResult.face);
				const matchedPerson = this.faceMatchEffectivePerson;
				if (metadataFace && sourceFace) {
					return {
						found: true,
						name: (sourceFace && sourceFace.name) || this.$t('face_match:unknown_name', '(unnamed)'),
						source: this.getFaceMatchSourceLabel(sourceFace && sourceFace.source),
						format: this.getFaceMatchFormatLabel(sourceFace && (sourceFace.source_format || sourceFace.format)),
						photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
					};
				}
				if (this.faceMatchResult && this.faceMatchResult.searched) {
					return { found: false, message: this.$t('face_match:result_no_match', 'No match found yet.') };
				}
				return { found: false, message: this.$t('face_match:result_none', 'No result yet.') };
			}
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const match = this.faceMatchResult && this.faceMatchResult.match;
			const matchedPerson = this.faceMatchEffectivePerson;
			if (match && metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$t('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$t('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (this.faceMatchResult && this.faceMatchResult.searched) {
				return { found: false, message: this.$t('face_match:result_no_match', 'No match found yet.') };
			}
			return { found: false, message: this.$t('face_match:result_none', 'No result yet.') };
		},
		faceMatchTransferTooltip() {
			if (this.faceMatchActionMode === 'write_metadata') {
				return this.$t('face_match:transfer_tooltip_write_metadata', 'Apply name to metadata');
			}
			if (this.faceMatchActionMode === 'create') {
				return this.$t('face_match:transfer_tooltip_create', 'Create person and apply name from file');
			}
			return this.$t('face_match:transfer_tooltip_assign', 'Apply name from file');
		},
		faceMatchActionMode() {
			if (!this.faceMatchResultSummary.found) {
				return '';
			}
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
				return 'write_metadata';
			}
			return this.faceMatchResultSummary.photosPersonId ? 'assign' : 'create';
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
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
				return this.$t('face_match:file_title', 'File');
			}
			const matchedPerson = this.faceMatchEffectivePerson;
			if (matchedPerson && matchedPerson.id && matchedPerson.name) {
				return `${this.$t('face_match:file_title', 'File')} - ${matchedPerson.name}`;
			}
			return this.$t('face_match:file_title', 'File');
		},
		faceMatchHasStoredNameMapping() {
			const mapping = this.faceMatchResult && this.faceMatchResult.name_mapping;
			return !!(mapping && mapping.source_name && mapping.target_name);
		},
		hasFaceMatchStoredFindings() {
			return (Number(this.faceMatchFindingsStatus && this.faceMatchFindingsStatus.count) || 0) > 0;
		},
		faceMatchLeftTitle() {
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
				return this.$t('face_match:label_source', 'Source');
			}
			return this.$t('face_match:photos_title', 'Photos');
		},
		faceMatchRightTitle() {
			return this.faceMatchFileTitle;
		},
		hasNextFaceMatch() {
			if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
				return this.faceMatchFindingIndex + 1 < this.faceMatchFindingEntries.length;
			}
			return !!this.faceMatchResultSummary.found;
		},
	},
	watch: {
		selectedFaceMatchingAction(nextAction) {
			if (nextAction !== 'search_photo_face_in_file' && nextAction !== 'search_file_face_in_sources') {
				this.faceMatchSaveOnly = false;
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
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_findings_status');
				this.faceMatchFindingsStatus = this.getResponseData(data);
			} catch (err) {
				this.faceMatchFindingsStatus = {};
			}
		},
		resetFaceMatchFindingsReview() {
			this.faceMatchFindingEntries = [];
			this.faceMatchFindingIndex = 0;
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
				this.$t('face_match:status_list_entry', 'List entry {current} of {total}.', {
					current: index + 1,
					total: this.faceMatchFindingEntries.length,
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
				this.faceMatchResult = null;
				this.faceMatchProgress = {
					...(this.faceMatchProgress || {}),
					message: this.$t('face_match:status_findings_empty', 'No saved matches found.'),
				};
			}
		},
		getFaceMatchSourceLabel(source) {
			const normalized = String(source || '').trim().toLowerCase();
			if (!normalized) {
				return this.$t('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'xmp_file') {
				return this.$t('face_match:source_xmp_file', 'XMP sidecar file');
			}
			if (normalized === 'embedded_xmp_parsed') {
				return this.$t('face_match:source_embedded_xmp', 'Embedded XMP');
			}
			if (normalized === 'embedded_xmp_exiftool') {
				return this.$t('face_match:source_embedded_xmp_exiftool', 'Embedded XMP via ExifTool');
			}
			if (normalized === 'metadata') {
				return this.$t('face_match:source_metadata', 'Metadata');
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
				return this.$t('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'ACD' || normalized === 'ACDSEE') {
				return this.$t('face_match:format_acdsee', 'ACDSee');
			}
			if (normalized === 'MICROSOFT') {
				return this.$t('face_match:format_microsoft', 'Microsoft People Tagging');
			}
			if (normalized === 'MWG_REGIONS') {
				return this.$t('face_match:format_mwg_regions', 'MWG face regions');
			}
			return String(format);
		},
		getFaceMatchBBox(face) {
			if (!face || typeof face !== 'object') {
				return null;
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
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
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
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
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
			if (this.faceMatchCurrentAction === 'search_file_face_in_sources') {
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
		captureFaceMatchProgressBase() {
			this.faceMatchProgressBase = { ...this.faceMatchDisplayedProgress };
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
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error('kk_message could not be read from ResumeParams');
				}
				if (!synoToken) {
					throw new Error('SYNO.SDS.Session.SynoToken is empty');
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_person_suggest', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						name_prefix: currentQuery,
						limit: 10,
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
			return this.confirmFaceMatchNameMapping(sourceName, nextName).then((saveMapping) => ({ saveMapping, sourceName }));
		},
		confirmFaceMatchNameMapping(sourceName, targetName) {
			return new Promise((resolve) => {
				this.nameMappingConfirm.visible = true;
				this.nameMappingConfirm.message = this.$t(
					'face_match:confirm_save_mapping',
					'Should "{source}" always be mapped to "{target}"?',
					{ source: sourceName, target: targetName }
				);
				this.nameMappingConfirm.resolver = resolve;
			});
		},
		resolveNameMappingConfirm(value) {
			const resolver = this.nameMappingConfirm.resolver;
			this.nameMappingConfirm.visible = false;
			this.nameMappingConfirm.message = '';
			this.nameMappingConfirm.resolver = null;
			if (typeof resolver === 'function') {
				resolver(!!value);
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
				this.setFaceMatchProgressMessage(
					this.$t('face_match:status_findings_empty', 'No saved matches found.')
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
			const baseCount = Number(this.faceMatchTransferredBaseCount) || 0;
			const totalCount = baseCount > 0
				? Math.max(localCount, baseCount + progressCount)
				: Math.max(localCount, progressCount);
			this.faceMatchTransferredCount = totalCount;
		},
		async fetchFaceMatchingProgress() {
			const requestId = this.faceMatchProgressRequestId + 1;
			this.faceMatchProgressRequestId = requestId;
			try {
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_progress', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					return;
				}
				if (this.faceMatchProgressRequestId !== requestId) {
					return;
				}
				const progress = this.getResponseData(data);
				this.faceMatchProgress = progress;
				this.syncFaceMatchTransferredCountFromProgress(progress);
				const result = progress && typeof progress.result === 'object' ? progress.result : null;
				if (result && Object.keys(result).length) {
					this.faceMatchResult = result;
					this.syncFaceMatchEditableName();
				} else if (!progress.running && !progress.paused) {
					this.faceMatchResult = null;
					this.resetFaceMatchSelectionState();
				}
				if (progress.paused && !progress.running) {
					this.faceMatchLoading = false;
				}
				if (!progress.running) {
					this.faceMatchLoading = false;
					this.stopFaceMatchProgressPolling();
				}
			} catch (err) {
				return;
			}
		},
		startFaceMatchProgressPolling() {
			this.stopFaceMatchProgressPolling();
			this.fetchFaceMatchingProgress();
			this.faceMatchProgressTimer = window.setInterval(() => {
				this.fetchFaceMatchingProgress();
			}, 1000);
		},
		stopFaceMatchProgressPolling() {
			if (this.faceMatchProgressTimer) {
				window.clearInterval(this.faceMatchProgressTimer);
				this.faceMatchProgressTimer = null;
			}
		},
		async loadNextFaceMatch() {
			if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
				if (!this.hasNextFaceMatch) {
					return;
				}
				await this.loadFaceMatchFindingAtIndex(this.faceMatchFindingIndex + 1);
				return;
			}
			if (this.selectedFaceMatchingAction === 'search_file_face_in_sources') {
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
				const synoToken = this.getSynoToken();
				await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_stop', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken,
					}),
				});
			} catch (err) {
				// Best effort.
			}
			this.output = this.$t('face_match:output_stopping', 'Stopping search...');
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
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			const personName = (this.faceMatchEditableName || this.getFaceMatchEditableNameDefault()).trim();
			if (!faceId || !personName) {
				this.output = this.$t('face_match:error_missing_face_or_name', 'Error: Missing face ID or person name.');
				return;
			}
			const mappingPreference = await this.resolveFaceMatchNameMappingPreference(personName);

			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_create_match', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						face_id: faceId,
						person_name: personName,
						save_mapping: mappingPreference.saveMapping,
						source_name: mappingPreference.sourceName,
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

				this.output = JSON.stringify(data, null, 2);
				if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
					await this.advanceFaceMatchFindingsAfterTransfer(data);
				} else {
					this.faceMatchTransferredCount += 1;
					this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
					await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
				}
			} catch (err) {
				this.output = `Error: ${err.message}`;
			}
		},
		async assignFaceMatchToPerson() {
			const matchedPersonId = this.faceMatchEffectivePerson && this.faceMatchEffectivePerson.id;
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			const matchedPersonName = (this.faceMatchEditableName || '').trim();
			if (!matchedPersonId || !faceId || !matchedPersonName) {
				this.output = this.$t('face_match:error_missing_known_person', 'Error: Missing known person ID, face ID, or person name.');
				return;
			}
			const mappingPreference = await this.resolveFaceMatchNameMappingPreference(matchedPersonName);

			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_assign_match', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						face_id: faceId,
						person_id: matchedPersonId,
						person_name: matchedPersonName,
						save_mapping: mappingPreference.saveMapping,
						source_name: mappingPreference.sourceName,
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

				this.output = JSON.stringify(data, null, 2);
				if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
					await this.advanceFaceMatchFindingsAfterTransfer(data);
				} else {
					this.faceMatchTransferredCount += 1;
					this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
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
				this.output = this.$t('face_match:error_missing_face_or_name', 'Error: Missing face ID or person name.');
				return;
			}
			try {
				const synoToken = this.getSynoToken();
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_apply_metadata_match', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						image_path: imagePath,
						metadata_face: metadataFace,
						person_name: personName,
						synoToken,
						cookies: this.collectDsmCookies(),
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}

				this.output = JSON.stringify(data, null, 2);
				if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
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
			if (this.selectedFaceMatchingAction === 'load_photo_face_match_findings') {
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
			const resetSkippedFaceIds = options.resetSkippedFaceIds !== false;
			const resumeFromProgress = options.resumeFromProgress === true;
			if (resetSkippedFaceIds) {
				this.faceMatchSkippedFaceIds = [];
				this.faceMatchSkippedTargets = [];
				this.faceMatchTransferredCount = 0;
				this.faceMatchTransferredBaseCount = 0;
				this.faceMatchProgressBase = {};
				this.resetFaceMatchFindingsReview();
			} else {
				this.captureFaceMatchProgressBase();
				this.faceMatchTransferredBaseCount = resumeFromProgress ? 0 : this.faceMatchTransferredCount;
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
					this.faceMatchSkippedFaceIds = cursorSkipFaceIds
						.map(value => Number(value))
						.filter(value => Number.isFinite(value) && value > 0);
				}
				if (cursorSkipTargets.length) {
					this.faceMatchSkippedTargets = cursorSkipTargets
						.map(value => String(value || '').trim())
						.filter(value => value);
				}
			}

			this.faceMatchLoading = true;
			this.faceMatchProgress = resetSkippedFaceIds ? {
				message: this.$t('face_match:status_starting', 'Search starting...'),
				persons_read: 0,
				images_read: 0,
				faces_read: 0,
				metadata_faces_read: 0,
				transferred_count: 0,
			} : {
				...(this.faceMatchProgress || {}),
				message: this.$t('face_match:status_starting', 'Search starting...'),
				transferred_count: 0,
			};
			this.faceMatchResult = null;
			this.resetFaceMatchSelectionState();
			this.startFaceMatchProgressPolling();
			this.output = this.$t('face_match:output_start_action', 'Starting action: {action}', { action: this.selectedFaceMatchingAction });
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

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_action', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						action: this.selectedFaceMatchingAction,
						auto: this.faceMatchAutoAssignKnown,
						save_only: this.faceMatchSaveOnly,
						resume_from_progress: resumeFromProgress,
						skip_face_ids: this.faceMatchSkippedFaceIds,
						skip_targets: this.faceMatchSkippedTargets,
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

				const faceMatches = this.getResponseDataObject(data, 'face_matches');
				this.faceMatchProgress = faceMatches;
				const result = faceMatches && typeof faceMatches.result === 'object' ? faceMatches.result : null;
				if (result && Object.keys(result).length) {
					this.faceMatchResult = result;
					this.syncFaceMatchEditableName();
				}
				if (faceMatches && faceMatches.running) {
					this.faceMatchLoading = true;
					this.startFaceMatchProgressPolling();
				}
				await this.fetchFaceMatchFindingsStatus();
				this.syncFaceMatchTransferredCountFromProgress(faceMatches);
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				this.faceMatchResult = null;
				this.resetFaceMatchSelectionState();
				this.faceMatchLoading = false;
				this.stopFaceMatchProgressPolling();
				this.output = `Error: ${err.message}`;
			}
		},
	},
};
