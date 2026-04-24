export default {
	data() {
		return {
			selectedChecksType: 'dimension_issues',
			selectedChecksAction: 'findings',
			checksSaveOnly: false,
			checksAutoApplySuggestedNames: false,
			checksAutoApplySuggestedDuplicates: false,
			checksLoading: false,
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
			return this.selectedChecksAction === 'scan'
				&& !!progress.running
				&& String(progress.source_mode || '').trim().toLowerCase() === 'scan'
				&& String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase();
		},
		checksPrimaryButtonLabel() {
			if (this.isChecksScanRunning) {
				return this.$t('checks:button_stop', 'Stop');
			}
			return this.checksLoading
				? this.$t('checks:button_loading', 'Loading...')
				: this.$t('checks:button_start', 'Start');
		},
		hasNextChecksItem() {
			if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
				return !!this.checksCurrentItem;
			}
			return this.checksCurrentIndex + 1 < this.checksEntries.length;
		},
	},
	watch: {
		selectedChecksAction(nextAction) {
			if (nextAction !== 'scan') {
				this.checksSaveOnly = false;
			}
			if (!this.checksLoading && !this.checksSessionSyncing) {
				this.resetChecksUiState();
			}
		},
		selectedChecksType() {
			if (!this.checksLoading && !this.checksSessionSyncing) {
				this.resetChecksUiState();
			}
		},
	},
	beforeDestroy() {
		this.stopChecksProgressPolling();
		this.resetChecksDuplicateAssignmentState();
	},
	methods: {
		resetChecksUiState() {
			this.stopChecksProgressPolling();
			this.checksEntries = [];
			this.checksCurrentIndex = 0;
			this.checksCurrentItem = null;
			this.checksActionLocked = false;
			this.checksProgress = {};
			this.checksStatusMessage = '';
			this.checksLoading = false;
			this.checksSkipNameMappingConfirm = false;
			this.resetChecksDuplicateAssignmentState();
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
		async callChecksApi(apiPath, body = {}, options = {}) {
			return this.callDsmApi(apiPath, body, options);
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
				return this.$t(
					'checks:popup_exiftool_required',
					'ExifTool is missing, but required for this action. Please configure or install ExifTool first.'
				);
			}
			if (warning === 'checks:warning_target_person_not_found') {
				const details = result && typeof result.details === 'object' ? result.details : {};
				return this.$t(
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
					parts.push(this.$t('checks:popup_error_code', 'Error code: {code}', { code: errorCode }));
				}
				if (Number.isFinite(returncode)) {
					parts.push(this.$t('checks:popup_return_code', 'Return code: {code}', { code: returncode }));
				}
				if (stderr) {
					parts.push(this.$t('checks:popup_error_stderr', 'Error output:\n{output}', { output: stderr }));
				} else if (stdout) {
					parts.push(this.$t('checks:popup_error_stdout', 'Command output:\n{output}', { output: stdout }));
				}
				return this.$t(
					'checks:popup_action_failed_details',
					'The metadata action failed.\n\n{details}',
					{ details: parts.join('\n\n') }
				);
			}
			return '';
		},
		getChecksReplaceRightTooltip(item) {
			if (this.isChecksPositionDeviation(item)) {
				return this.$t(
					'checks:tooltip_replace_right_position',
					'The face on the right takes the position from the left.'
				);
			}
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			const rightFace = item && item.right_face_target;
			if (this.isChecksPhotosFace(rightFace)) {
				return this.$t(
					'checks:tooltip_assign_right_name',
					'The Photos face on the right is assigned to the person from the left: {from} -> {to}',
					{ from: rightName, to: leftName }
				);
			}
			return this.$t(
				'checks:tooltip_replace_right_name',
				'The face on the right gets the name from the left: {from} -> {to}',
				{ from: rightName, to: leftName }
			);
		},
		getChecksReplaceLeftTooltip(item) {
			if (this.isChecksPositionDeviation(item)) {
				return this.$t(
					'checks:tooltip_replace_left_position',
					'The face on the left takes the position from the right.'
				);
			}
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			const leftFace = item && item.left_face_target;
			if (this.isChecksPhotosFace(leftFace)) {
				return this.$t(
					'checks:tooltip_assign_left_name',
					'The Photos face on the left is assigned to the person from the right: {from} -> {to}',
					{ from: leftName, to: rightName }
				);
			}
			return this.$t(
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
		applyChecksFindingsUpdate(findingsUpdate) {
			if (!findingsUpdate || typeof findingsUpdate !== 'object' || !Array.isArray(findingsUpdate.entries)) {
				return false;
			}
			this.checksEntries = findingsUpdate.entries;
			const findingsCount = Number(
				findingsUpdate.count !== undefined
					? findingsUpdate.count
					: findingsUpdate.entries.length
			);
			if (!this.checksProgress || typeof this.checksProgress !== 'object') {
				this.checksProgress = {};
			}
			this.checksProgress = {
				...this.checksProgress,
				findings_count: Number.isFinite(findingsCount) ? findingsCount : findingsUpdate.entries.length,
			};
			if (!this.checksEntries.length) {
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
				this.checksStatusMessage = this.$t('checks:status_empty', 'No matching entries found.');
				return true;
			}
			this.checksCurrentIndex = Math.min(this.checksCurrentIndex, this.checksEntries.length - 1);
			return true;
		},
		async refreshChecksSessionState() {
			const progress = await this.fetchChecksProgress({ applyFinishedState: true });
			const hasProgress = !!(progress && Object.keys(progress).length);
			if (!hasProgress) {
				return;
			}
			const matchesCurrentSelection = !!(
				String(progress.source_mode || '').trim().toLowerCase() === 'scan'
				&& String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase()
			);
			if (matchesCurrentSelection && progress.running) {
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
			if (matchesCurrentSelection || !progress.running) {
				this.checksLoading = false;
				this.stopChecksProgressPolling();
			}
		},
		applyChecksProgress(progress) {
			const nextProgress = progress && typeof progress === 'object' ? progress : {};
			this.checksProgress = nextProgress;
			const result = nextProgress.result && typeof nextProgress.result === 'object'
				? nextProgress.result
				: null;
			const item = result && result.item && typeof result.item === 'object' ? result.item : null;
			if (item && Object.keys(item).length) {
				this.checksCurrentItem = item;
				this.syncChecksDuplicateAssignmentState(item);
			} else if (this.selectedChecksAction === 'scan') {
				this.checksCurrentItem = null;
				this.resetChecksDuplicateAssignmentState();
			}
			if (nextProgress.message_key || nextProgress.message) {
				this.checksStatusMessage = this.$t(
					nextProgress.message_key || '',
					nextProgress.message || '',
					nextProgress.message_params && typeof nextProgress.message_params === 'object'
						? nextProgress.message_params
						: null
				);
			}
		},
		async fetchChecksProgress({ applyFinishedState = true } = {}) {
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
					this.applyChecksProgress(progress);
				}
				if (!progress.running) {
					this.checksLoading = false;
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
		async startChecksReview() {
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
			this.checksStatusMessage = this.$t('checks:status_loading', 'Loading checks...');
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_start', {
					source_mode: this.selectedChecksAction,
					check_type: this.selectedChecksType,
				});
				const root = this.getResponseData(data);
				const entries = Array.isArray(root.entries) ? root.entries : [];
				this.checksEntries = entries;
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
				this.checksStatusMessage = entries.length
					? this.$t('checks:status_loaded', '{count} entries loaded.', { count: entries.length })
					: this.$t('checks:status_empty', 'No matching entries found.');
				if (entries.length) {
					await this.loadChecksItemAtIndex(0);
				}
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksActionLocked = false;
				this.checksLoading = false;
			}
		},
		async loadChecksItemAtIndex(index) {
			let resolvedIndex = index;
			while (resolvedIndex < this.checksEntries.length) {
				const entry = this.checksEntries[resolvedIndex];
				if (!entry) {
					break;
				}
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_item', {
					entry,
					auto_apply_suggested_names: this.checksAutoApplySuggestedNames,
					auto_apply_suggested_duplicates: this.checksAutoApplySuggestedDuplicates,
				});
				const root = this.getResponseData(data);
				const findingsUpdated = this.applyChecksFindingsUpdate(root.findings_update);
				const autoAppliedCount = Number(root && root.auto_applied_count || 0);
				const item = root && root.item && typeof root.item === 'object' ? root.item : {};
				if (Object.keys(item).length) {
					this.checksActionLocked = false;
					this.checksCurrentItem = item;
					this.checksCurrentIndex = resolvedIndex;
					this.syncChecksDuplicateAssignmentState(item);
					return;
				}
				if (!this.checksEntries.length) {
					break;
				}
				if (findingsUpdated && (autoAppliedCount > 0 || !Object.keys(item).length)) {
					resolvedIndex = Math.min(resolvedIndex, this.checksEntries.length - 1);
					continue;
				}
				resolvedIndex += 1;
			}
			this.checksActionLocked = false;
			this.checksCurrentItem = null;
			this.resetChecksDuplicateAssignmentState();
			this.checksCurrentIndex = Math.min(resolvedIndex, Math.max(this.checksEntries.length - 1, 0));
			this.checksStatusMessage = this.$t('checks:status_empty', 'No matching entries found.');
		},
		async startChecksScan({ resumeFromProgress = false } = {}) {
			this.checksLoading = true;
			if (!resumeFromProgress) {
				this.checksEntries = [];
				this.checksCurrentIndex = 0;
				this.checksCurrentItem = null;
			}
			this.checksProgress = {
				message: this.$t('checks:status_preparing_scan', 'Checks scan starting. Building file list...'),
				files_scanned: 0,
				total_files: 0,
				findings_count: 0,
			};
			this.checksStatusMessage = this.$t('checks:status_preparing_scan', 'Checks scan starting. Building file list...');
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_start', {
					source_mode: 'scan',
					check_type: this.selectedChecksType,
					save_only: this.checksSaveOnly,
					resume_from_progress: resumeFromProgress,
					auto_apply_suggested_names: this.checksAutoApplySuggestedNames,
					auto_apply_suggested_duplicates: this.checksAutoApplySuggestedDuplicates,
				});
				const progress = this.getResponseData(data);
				this.applyChecksProgress(progress);
				if (progress.running) {
					this.startChecksProgressPolling();
				} else {
					this.checksLoading = false;
					this.stopChecksProgressPolling();
				}
			} catch (err) {
				this.checksLoading = false;
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
			this.checksStatusMessage = this.$t('checks:progress_stopping', 'Stopping checks scan...');
			await this.fetchChecksProgress();
		},
		async nextChecksReview() {
			if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
				if (!this.hasNextChecksItem) {
					return;
				}
				await this.startChecksScan({ resumeFromProgress: true });
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
					this.checksStatusMessage = this.$t(
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
				this.checksStatusMessage = this.$t('checks:status_face_deleted', 'Face removed from metadata.');
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.checksLoading = false;
			}
		},
		async replaceChecksMetadataFaceName(face, newName) {
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
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$t(
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
				this.applyChecksFindingsUpdate(result.findings_update);
				const operation = String(result.operation || '').trim().toLowerCase();
				this.checksStatusMessage = operation === 'photos_assign'
					? this.$t('checks:status_face_person_assigned', 'Photos face assigned to known person.')
					: this.$t('checks:status_face_name_replaced', 'Face name replaced in metadata.');
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
					this.checksStatusMessage = this.$t(
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
				this.checksStatusMessage = this.$t('checks:status_face_position_replaced', 'Face position replaced in metadata.');
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
					this.checksStatusMessage = this.$t(
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
				this.applyChecksFindingsUpdate(result.findings_update);
				this.checksStatusMessage = this.$t('checks:status_face_person_assigned', 'Known person assigned.');
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
				}
			}
		},
		getChecksTypeLabel(type) {
			const normalized = String(type || '').trim().toLowerCase();
			if (normalized === 'dimension_issues') {
				return this.$t('checks:type_dimension_issues', 'Dimension issues');
			}
			if (normalized === 'duplicate_faces') {
				return this.$t('checks:type_duplicate_faces', 'Duplicate face markings');
			}
			if (normalized === 'position_deviations') {
				return this.$t('checks:type_position_deviations', 'Deviating face positions');
			}
			if (normalized === 'name_conflicts') {
				return this.$t('checks:type_name_conflicts', 'Name conflicts');
			}
			return String(type || '');
		},
		getChecksLeftTitle(item) {
			if (item && item.review_type === 'dimension_issues') {
				return this.$t('checks:preview_left_dimension', 'Affected metadata');
			}
			return this.$t('checks:preview_left_pair', 'Left face');
		},
		getChecksRightTitle(item) {
			if (item && item.review_type === 'dimension_issues') {
				return this.$t('checks:preview_right_dimension', 'Reference metadata');
			}
			return this.$t('checks:preview_right_pair', 'Right face');
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
			return name || this.$t('face_match:unknown_name', '(unnamed)');
		},
		showChecksFaceName(item) {
			const reviewType = String(item && item.review_type || '').trim().toLowerCase();
			return reviewType === 'name_conflicts' || reviewType === 'duplicate_faces';
		},
		getChecksSourceModeLabel() {
			if (this.selectedChecksAction === 'scan') {
				return this.$t('checks:action_scan', 'Run check scan');
			}
			return this.$t('checks:action_findings', 'Use analysis findings');
		},
	},
};
