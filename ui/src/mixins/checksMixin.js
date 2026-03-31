export default {
	data() {
		return {
			selectedChecksType: 'dimension_issues',
			selectedChecksAction: 'findings',
			checksSaveOnly: false,
			checksLoading: false,
			checksEntries: [],
			checksCurrentIndex: 0,
			checksStatusMessage: '',
			checksCurrentItem: null,
			checksProgress: {},
			checksProgressTimer: null,
			checksProgressRequestId: 0,
		};
	},
	computed: {
		checksPrimaryButtonLabel() {
			if (this.selectedChecksAction === 'scan' && this.checksLoading) {
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
			if (!this.checksLoading) {
				this.resetChecksUiState();
			}
		},
		selectedChecksType() {
			if (!this.checksLoading) {
				this.resetChecksUiState();
			}
		},
	},
	beforeDestroy() {
		this.stopChecksProgressPolling();
	},
	methods: {
		resetChecksUiState() {
			this.stopChecksProgressPolling();
			this.checksEntries = [];
			this.checksCurrentIndex = 0;
			this.checksCurrentItem = null;
			this.checksProgress = {};
			this.checksStatusMessage = '';
			this.checksLoading = false;
		},
		async callChecksApi(apiPath, body = {}) {
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
		canDeleteChecksFace(item, face) {
			return !!(item && item.image_path && face && typeof face === 'object' && face.source_format);
		},
		isChecksNameConflict(item) {
			return !!(item && item.review_type === 'name_conflicts');
		},
		canReplaceChecksFaceName(item, face, newName) {
			return this.isChecksNameConflict(item)
				&& !!(item && item.image_path)
				&& !!(face && typeof face === 'object' && face.source_format)
				&& !!String(newName || '').trim();
		},
		getChecksReplaceRightTooltip(item) {
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			return this.$t(
				'checks:tooltip_replace_right_name',
				'The face on the right gets the name from the left: {from} -> {to}',
				{ from: rightName, to: leftName }
			);
		},
		getChecksReplaceLeftTooltip(item) {
			const leftName = this.getChecksDisplayName(item && item.left_name);
			const rightName = this.getChecksDisplayName(item && item.right_name);
			return this.$t(
				'checks:tooltip_replace_left_name',
				'The face on the left gets the name from the right: {from} -> {to}',
				{ from: leftName, to: rightName }
			);
		},
		async refreshChecksSessionState() {
			const progress = await this.fetchChecksProgress({ applyFinishedState: false });
			const matchesCurrentSelection = !!(
				progress
				&& progress.running
				&& String(progress.source_mode || '').trim().toLowerCase() === 'scan'
				&& String(progress.check_type || '').trim().toLowerCase() === String(this.selectedChecksType || '').trim().toLowerCase()
				&& this.selectedChecksAction === 'scan'
			);
			if (matchesCurrentSelection) {
				this.checksLoading = true;
				this.startChecksProgressPolling();
				return;
			}
			this.resetChecksUiState();
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
			} else if (this.selectedChecksAction === 'scan') {
				this.checksCurrentItem = null;
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
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_progress', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
						check_type: this.selectedChecksType,
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					return;
				}
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
				return {};
			}
		},
		startChecksProgressPolling() {
			this.stopChecksProgressPolling();
			this.fetchChecksProgress();
			this.checksProgressTimer = window.setInterval(() => {
				this.fetchChecksProgress();
			}, 1000);
		},
		stopChecksProgressPolling() {
			if (this.checksProgressTimer) {
				window.clearInterval(this.checksProgressTimer);
				this.checksProgressTimer = null;
			}
		},
		async startChecksReview() {
			if (this.selectedChecksAction === 'scan' && this.checksLoading) {
				await this.stopChecksScan();
				return;
			}
			if (this.selectedChecksAction === 'scan') {
				await this.startChecksScan();
				return;
			}
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
				this.checksStatusMessage = `Error: ${err.message}`;
			} finally {
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
				});
				const item = this.getResponseDataObject(data, 'item');
				if (Object.keys(item).length) {
					this.checksCurrentItem = item;
					this.checksCurrentIndex = resolvedIndex;
					this.checksStatusMessage = this.$t('checks:status_entry', 'Entry {current} of {total}.', {
						current: this.checksCurrentIndex + 1,
						total: this.checksEntries.length,
					});
					return;
				}
				resolvedIndex += 1;
			}
			this.checksCurrentItem = null;
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
				this.checksStatusMessage = `Error: ${err.message}`;
			}
		},
		async stopChecksScan() {
			try {
				await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_stop', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
						check_type: this.selectedChecksType,
					}),
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
				this.checksStatusMessage = `Error: ${err.message}`;
			} finally {
				this.checksLoading = false;
			}
		},
		async deleteChecksMetadataFace(face) {
			if (!this.canDeleteChecksFace(this.checksCurrentItem, face)) {
				return;
			}
			this.checksLoading = true;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_delete_metadata_face', {
					image_path: this.checksCurrentItem.image_path,
					face,
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$t(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Face could not be deleted from metadata.'
					);
					return;
				}
				this.checksStatusMessage = this.$t('checks:status_face_deleted', 'Face removed from metadata.');
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${err.message}`;
			} finally {
				this.checksLoading = false;
			}
		},
		async replaceChecksMetadataFaceName(face, newName) {
			if (!this.canReplaceChecksFaceName(this.checksCurrentItem, face, newName)) {
				return;
			}
			this.checksLoading = true;
			let keepLoadingState = false;
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_replace_metadata_face_name', {
					image_path: this.checksCurrentItem.image_path,
					face,
					new_name: String(newName || '').trim(),
				});
				const result = this.getResponseData(data);
				if (result.warning) {
					this.checksStatusMessage = this.$t(
						result.warning,
						result.warning === 'checks:warning_exiftool_required'
							? 'This function requires ExifTool.'
							: 'Face name could not be replaced in metadata.'
					);
					return;
				}
				this.checksStatusMessage = this.$t('checks:status_face_name_replaced', 'Face name replaced in metadata.');
				if (this.selectedChecksAction === 'scan' && !this.checksSaveOnly) {
					keepLoadingState = true;
					await this.startChecksScan({ resumeFromProgress: true });
					return;
				}
				await this.loadChecksItemAtIndex(this.checksCurrentIndex);
			} catch (err) {
				this.checksStatusMessage = `Error: ${err.message}`;
			} finally {
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
			return !!(item && item.review_type === 'name_conflicts');
		},
		getChecksSourceModeLabel() {
			if (this.selectedChecksAction === 'scan') {
				return this.$t('checks:action_scan', 'Run check scan');
			}
			return this.$t('checks:action_findings', 'Use analysis findings');
		},
	},
};
