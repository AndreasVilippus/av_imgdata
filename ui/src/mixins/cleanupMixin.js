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
				cleanupRuntimeAction: '',
			faceFrameOptionsDialogVisible: false,
			faceFrameOptions: {
				operation_mode: 'immediate',
				selection_mode: 'review_all',
				sources: {
					photos: true,
					acd: true,
					microsoft: true,
					mwg_regions: true,
				},
				profile: 'normal',
				strategy: 'insightface_scaled',
				changed_since_days: 0,
				det_size: [640, 640],
				det_thresh: 0.5,
				max_num: 0,
				min_width_ratio: 0,
				min_height_ratio: 0,
				min_area_ratio: 0,
			},
			faceFrameFindings: [],
			faceFrameFindingsLoading: false,
			faceFrameCurrentIndex: 0,
			faceFrameDecisionLoading: false,
			faceFrameApplyLoading: false,
			recognitionOptions: {
				operation_mode: 'immediate',
				selection_mode: 'review_all',
				include_hidden_persons: false,
				min_faces_per_person: 3,
				exclude_outliers: true,
				rebuild_all: false,
				changed_since_days: 30,
				safe_score: 0.55,
				review_score: 0.45,
				min_margin: 0.08,
				outlier_similarity_threshold: 0.35,
				det_size: [640, 640],
				det_thresh: 0.5,
				max_num: 0,
				min_width_ratio: 0.015,
				min_height_ratio: 0.015,
			},
			recognitionFindings: [],
			recognitionFindingsLoading: false,
			recognitionCurrentIndex: 0,
			recognitionDecisionLoading: false,
		};
	},
	created() {
		this.loadStoredFaceFrameStartOptions();
	},
	watch: {
		selectedCleanupAction(value) {
			this.refreshCleanupSessionState();
			if (value === 'standardize_face_frames') {
				this.fetchFaceFrameFindings();
			}
			if (this.isRecognitionReviewAction) {
				this.fetchRecognitionFindings();
			}
		},
	},
	computed: {
			cleanupPrimaryButtonLabel() {
			if (this.cleanupLoading) {
				return this.$avt('cleanup:button_stop', 'Stop');
			}
			if (
				(this.selectedCleanupAction === 'standardize_face_frames' && this.faceFrameOptions.operation_mode === 'findings')
				|| (this.isRecognitionReviewAction && this.recognitionOptions.operation_mode === 'findings')
			) {
				return this.$avt('cleanup:face_frames_operation_findings', 'Process saved findings list');
			}
			return this.$avt('cleanup:button_start', 'Start');
			},
			activeCleanupAction() {
				return String(this.cleanupRuntimeAction || this.selectedCleanupAction || 'normalize_names');
			},
			faceMatchRecognitionActionSelected() {
				return this.selectedFaceMatchingAction === 'recognition_analyze_unknown_faces';
			},
			selectedRecognitionAction() {
				return this.faceMatchRecognitionActionSelected
					? 'recognition_analyze_unknown_faces'
					: this.activeCleanupAction;
			},
			isRecognitionCleanupAction() {
				return [
					'recognition_build_profiles',
					'recognition_check_reference_outliers',
					'recognition_analyze_unknown_faces',
				].includes(this.selectedRecognitionAction);
			},
			isRecognitionReviewAction() {
				return [
					'recognition_check_reference_outliers',
					'recognition_analyze_unknown_faces',
				].includes(this.selectedRecognitionAction);
			},
			isRecognitionOutlierAction() {
				return this.selectedRecognitionAction === 'recognition_check_reference_outliers';
			},
		recognitionManualReviewEnabled() {
			return this.isRecognitionReviewAction && this.recognitionOptions.operation_mode !== 'save_only';
		},
		recognitionReviewFindings() {
			return this.recognitionFindings.filter((finding) => (
				String(finding.selection_state || 'review').toLowerCase() === 'review'
				&& ['pending', 'internal_only'].includes(String(finding.write_state || 'pending').toLowerCase())
			));
		},
		recognitionCurrentFinding() {
			return this.recognitionReviewFindings[this.recognitionCurrentIndex] || null;
		},
		cleanupCanStart() {
			if (this.cleanupLoading || this.selectedCleanupAction !== 'standardize_face_frames') {
				return true;
			}
			return Object.values(this.faceFrameOptions.sources || {}).some((enabled) => !!enabled);
		},
		faceFrameManualReviewEnabled() {
			return this.selectedCleanupAction === 'standardize_face_frames'
				&& this.faceFrameOptions.operation_mode !== 'save_only';
		},
		faceFrameReviewFindings() {
			return this.faceFrameFindings.filter((finding) => (
				String(finding.write_state || 'pending').toLowerCase() === 'pending'
				&& String(finding.selection_state || 'review').toLowerCase() === 'review'
			));
		},
		faceFrameCurrentFinding() {
			return this.faceFrameReviewFindings[this.faceFrameCurrentIndex] || null;
		},
		faceFrameSelectedCount() {
			return this.faceFrameFindings.filter((finding) => finding.selection_state === 'selected' && finding.write_state !== 'written').length;
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
		updateRecognitionOption(key, value) {
			this.recognitionOptions = {
				...this.recognitionOptions,
				[key]: value,
			};
		},
		updateFaceFrameOption(key, value) {
			this.faceFrameOptions = {
				...this.faceFrameOptions,
				[key]: value,
			};
		},
		updateFaceFrameSource(key, value) {
			this.updateFaceFrameOption('sources', {
				...this.faceFrameOptions.sources,
				[key]: value,
			});
		},
		updateFaceFrameDetSize(index, value) {
			const detSize = Array.isArray(this.faceFrameOptions.det_size)
				? [...this.faceFrameOptions.det_size]
				: [640, 640];
			detSize[index] = value;
			this.updateFaceFrameOption('det_size', detSize);
		},
		cloneFaceFrameOptions(options = this.faceFrameOptions) {
			return JSON.parse(JSON.stringify(options || {}));
		},
		getFaceFrameStartOptionsStorageKey() {
			return 'av_imgdata.cleanup.standardize_face_frames.options';
		},
		loadStoredFaceFrameStartOptions() {
			if (typeof window === 'undefined' || !window.localStorage) {
				return;
			}
			try {
				const stored = JSON.parse(window.localStorage.getItem(this.getFaceFrameStartOptionsStorageKey()) || '{}');
				if (!stored || typeof stored !== 'object' || Array.isArray(stored)) {
					return;
				}
				this.faceFrameOptions = {
					...this.faceFrameOptions,
					...stored,
					sources: {
						...(this.faceFrameOptions.sources || {}),
						...(stored.sources && typeof stored.sources === 'object' ? stored.sources : {}),
					},
					det_size: Array.isArray(stored.det_size) ? [...stored.det_size] : this.faceFrameOptions.det_size,
				};
			} catch (err) {
				// Ignore broken local storage state and keep the packaged defaults.
			}
		},
		persistFaceFrameStartOptions() {
			if (typeof window === 'undefined' || !window.localStorage) {
				return;
			}
			try {
				window.localStorage.setItem(
					this.getFaceFrameStartOptionsStorageKey(),
					JSON.stringify(this.cloneFaceFrameOptions())
				);
			} catch (err) {
				// Starting the scan must not depend on browser storage availability.
			}
		},
		openFaceFrameOptionsDialog() {
			this.faceFrameOptionsDialogVisible = true;
		},
		closeFaceFrameOptionsDialog() {
			this.faceFrameOptionsDialogVisible = false;
		},
		async confirmFaceFrameOptionsDialog() {
			this.persistFaceFrameStartOptions();
			this.faceFrameOptionsDialogVisible = false;
			await this.startCleanupRun({ skipFaceFrameOptionsDialog: true });
		},
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
			async fetchCleanupProgress() {
				const requestId = this.cleanupProgressRequestId + 1;
				this.cleanupProgressRequestId = requestId;
				const action = String(this.cleanupRuntimeAction || this.selectedCleanupAction || 'normalize_names');
				try {
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_progress', {
						action,
					}, { resume: false, requireSynoToken: false });
					if (this.cleanupProgressRequestId !== requestId) {
						return {};
					}
					const progress = this.getResponseData(data);
					if (progress && Object.keys(progress).length) {
						this.applyCleanupProgress(progress);
					}
					if (!progress.running) {
						const finishedAction = action;
						this.cleanupLoading = false;
						this.stopCleanupProgressPolling();
						if (this.selectedCleanupAction === 'standardize_face_frames') {
							this.fetchFaceFrameFindings();
						}
						if ([
							'recognition_check_reference_outliers',
							'recognition_analyze_unknown_faces',
						].includes(finishedAction)) {
							this.fetchRecognitionFindings();
						}
						this.cleanupRuntimeAction = '';
					}
					return progress;
				} catch (err) {
					if (this.cleanupProgressRequestId === requestId) {
						this.cleanupStatusMessage = `Error: ${err.message}`;
						this.cleanupProgress = {
							...(this.cleanupProgress || {}),
							message: `Error: ${err.message}`,
						};
					}
					return {};
				}
			},
			startCleanupProgressPolling() {
				this.startNamedPolling('cleanupProgressTimer', () => {
					this.fetchCleanupProgress();
				}, 1000, { skipIfPending: true });
			},
			stopCleanupProgressPolling() {
				this.stopNamedPolling('cleanupProgressTimer');
			},
			async refreshCleanupSessionState() {
				const progress = await this.fetchCleanupProgress();
				if (progress && progress.running) {
					this.cleanupLoading = true;
					this.cleanupRuntimeAction = String(progress.action || this.cleanupRuntimeAction || this.selectedCleanupAction || '');
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
				if (this.selectedCleanupAction === 'standardize_face_frames') {
					this.openFaceFrameOptionsDialog();
					return;
				}
				await this.startCleanupRun();
			},
			async startCleanupRun() {
				const options = arguments[0] && typeof arguments[0] === 'object' ? arguments[0] : {};
				const cleanupAction = String(options.actionOverride || this.selectedCleanupAction || 'normalize_names');
				const isRecognitionAction = [
					'recognition_build_profiles',
					'recognition_check_reference_outliers',
					'recognition_analyze_unknown_faces',
				].includes(cleanupAction);
				const isRecognitionReviewAction = [
					'recognition_check_reference_outliers',
					'recognition_analyze_unknown_faces',
				].includes(cleanupAction);
				if (
					cleanupAction === 'standardize_face_frames'
					&& !options.skipFaceFrameOptionsDialog
				) {
					this.openFaceFrameOptionsDialog();
					return;
				}
				if (isRecognitionReviewAction && this.recognitionOptions.operation_mode === 'findings') {
					await this.fetchRecognitionFindings();
					this.cleanupStatusMessage = this.recognitionReviewFindings.length
						? this.$avt('cleanup:recognition_review_required', 'Manual review required for the next recognition finding.')
						: this.$avt('cleanup:recognition_no_review_findings', 'No recognition findings require manual review.');
					return;
				}
				if (
					cleanupAction === 'standardize_face_frames'
					&& this.faceFrameOptions.operation_mode === 'findings'
				) {
					this.persistFaceFrameStartOptions();
					await this.fetchFaceFrameFindings();
					this.cleanupStatusMessage = this.faceFrameReviewFindings.length
						? this.$avt('cleanup:face_frames_review_required', 'Manual review required for the next face-frame finding.')
						: this.$avt('cleanup:face_frames_findings_empty', 'No saved face-frame findings.');
					return;
				}
				this.stopCleanupProgressPolling();
				this.cleanupProgressRequestId += 1;
				this.cleanupLoading = true;
				this.cleanupRuntimeAction = cleanupAction;
				this.cleanupProgress = {
					running: true,
					action: cleanupAction,
					message: this.$avt('cleanup:status_preparing', 'Cleanup starts. Preparing run...'),
				};
				this.cleanupStatusMessage = this.$avt('cleanup:status_preparing', 'Cleanup starts. Preparing run...');
				try {
					const cleanupOptions = cleanupAction === 'standardize_face_frames'
						? {
							...this.faceFrameOptions,
							resume_existing: !!options.resumeExisting,
						}
						: (isRecognitionAction ? {
							...this.recognitionOptions,
							resume_existing: !!options.resumeExisting,
						} : {});
					if (cleanupAction === 'standardize_face_frames') {
						this.persistFaceFrameStartOptions();
					}
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_start', {
						action: cleanupAction,
						targets: this.selectedCleanupTargets,
						options: cleanupOptions,
					});
					const progress = this.getResponseData(data);
					this.applyCleanupProgress(progress);
					if (progress.running) {
						this.startCleanupProgressPolling();
					} else {
						this.cleanupLoading = false;
						this.cleanupRuntimeAction = '';
					}
				} catch (err) {
					this.cleanupLoading = false;
					this.cleanupRuntimeAction = '';
					this.cleanupProgress = {
						...(this.cleanupProgress || {}),
						running: false,
						status: 'failed',
						message: `Error: ${err.message}`,
					};
					this.cleanupStatusMessage = `Error: ${err.message}`;
				}
			},
		async fetchFaceFrameFindings() {
			this.faceFrameFindingsLoading = true;
			try {
				const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_face_frames_findings', {
					operation_mode: this.faceFrameOptions.operation_mode,
				}, { resume: false, requireSynoToken: false });
				const payload = this.getResponseData(data);
				this.faceFrameFindings = payload && Array.isArray(payload.entries) ? payload.entries : [];
				this.faceFrameCurrentIndex = Math.min(this.faceFrameCurrentIndex, Math.max(0, this.faceFrameReviewFindings.length - 1));
				this.syncFaceFrameFindingsProgress();
			} catch (err) {
				this.faceFrameFindings = [];
			} finally {
				this.faceFrameFindingsLoading = false;
			}
		},
			async fetchRecognitionFindings() {
				this.recognitionFindingsLoading = true;
				try {
					const data = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/recognition_findings', {
						action: this.selectedRecognitionAction,
						operation_mode: this.recognitionOptions.operation_mode,
					}, { resume: false, requireSynoToken: false });
					const payload = this.getResponseData(data);
					this.recognitionFindings = payload && Array.isArray(payload.entries) ? payload.entries : [];
					this.recognitionCurrentIndex = Math.min(this.recognitionCurrentIndex, Math.max(0, this.recognitionReviewFindings.length - 1));
			} catch (err) {
				this.recognitionFindings = [];
			} finally {
				this.recognitionFindingsLoading = false;
			}
		},
		getRecognitionImageUrl(path) {
			const normalized = String(path || '').trim();
			return normalized ? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(normalized)}` : '';
		},
		getRecognitionApplyIconUrl() {
			return this.resolveLocalIconUrl('face_to_left.png');
		},
		getRecognitionPersonName(finding) {
			return String((finding && (finding.best_person_name || finding.person_name)) || this.$avt('face_match:unknown_name', '(unnamed)'));
		},
		async acceptRecognitionCurrent() {
			await this.decideRecognitionCurrent(this.isRecognitionOutlierAction ? 'excluded' : 'selected', {
				apply: !this.isRecognitionOutlierAction,
			});
		},
		async decideRecognitionCurrent(decision, options = {}) {
			const finding = this.recognitionCurrentFinding;
			if (!finding || this.recognitionDecisionLoading) {
				return;
			}
				this.recognitionDecisionLoading = true;
				try {
					const itemId = this.isRecognitionOutlierAction ? finding.outlier_id : finding.suggestion_id;
					await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/recognition_review', {
						action: this.selectedRecognitionAction,
						item_id: itemId,
						decision,
						operation_mode: this.recognitionOptions.operation_mode,
					});
				if (options.apply) {
					await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/recognition_suggestions_apply', {
						selected_suggestion_ids: [itemId],
						operation_mode: this.recognitionOptions.operation_mode,
					});
				}
					await this.fetchRecognitionFindings();
					this.recognitionCurrentIndex = 0;
					if (this.recognitionOptions.operation_mode === 'immediate' && !this.recognitionReviewFindings.length) {
						await this.startCleanupRun({
							actionOverride: this.selectedRecognitionAction,
							resumeExisting: true,
						});
					}
			} catch (err) {
				this.cleanupStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.recognitionDecisionLoading = false;
			}
		},
		syncFaceFrameFindingsProgress() {
			const openCount = this.faceFrameReviewFindings.length;
			const totalCount = this.faceFrameFindings.length;
			const processedCount = Math.max(0, totalCount - openCount);
			const writtenCount = this.faceFrameFindings.filter((finding) => String(finding.write_state || '').toLowerCase() === 'written').length;
			const errorCount = this.faceFrameFindings.filter((finding) => String(finding.write_state || '').toLowerCase() === 'failed').length;
			const currentFinding = this.faceFrameCurrentFinding;
			const current = this.cleanupProgress && typeof this.cleanupProgress === 'object' ? this.cleanupProgress : {};
			const status = current.status && typeof current.status === 'object' ? current.status : {};
			const counters = Array.isArray(status.counters)
				? status.counters.map((counter) => {
					if (counter.key === 'findings') return { ...counter, value: openCount };
					if (counter.key === 'written') return { ...counter, value: writtenCount };
					if (counter.key === 'errors') return { ...counter, value: errorCount };
					return counter;
				})
				: status.counters;
			this.cleanupProgress = {
				...current,
				findings_count: openCount,
				written_count: writtenCount,
				errors_count: errorCount,
				current_path: currentFinding ? String(currentFinding.image_path || '') : '',
				message_key: openCount ? 'cleanup:face_frames_review_required' : current.message_key,
				message: openCount
					? this.$avt('cleanup:face_frames_review_required', 'Manual review required for the next face-frame finding.')
					: current.message,
				status: {
					...status,
					phase: openCount ? 'review_required' : status.phase,
					progress: openCount ? {
						kind: 'entries',
						current: processedCount,
						total: totalCount,
						title_key: 'checks:label_list_entries',
						fallback_title: 'Entries',
						primary_label_key: 'checks:label_index',
						fallback_primary_label: 'Entry',
						secondary_label_key: 'checks:label_entries_remaining',
						fallback_secondary_label: 'remaining',
					} : status.progress,
					counters,
				},
			};
			if (openCount) {
				this.cleanupStatusMessage = this.$avt(
					'cleanup:face_frames_review_required',
					'Manual review required for the next face-frame finding.'
				);
			}
		},
		getFaceFrameImageUrl(finding) {
			const path = String(finding && finding.image_path || '').trim();
			return path ? `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(path)}` : '';
		},
		getFaceFrameApplyIconUrl() {
			return this.resolveLocalIconUrl('face_to_left.png');
		},
		async decideFaceFrameCurrent(selected) {
			const finding = this.faceFrameCurrentFinding;
			if (!finding || this.faceFrameDecisionLoading) {
				return;
			}
			this.faceFrameDecisionLoading = true;
			try {
				await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_face_frames_select', {
					item_id: finding.item_id,
					selected: !!selected,
					operation_mode: this.faceFrameOptions.operation_mode,
				});
				if (selected) {
					await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_face_frames_apply', {
						selected_item_ids: [finding.item_id],
						operation_mode: this.faceFrameOptions.operation_mode,
					});
				}
				await this.fetchFaceFrameFindings();
				if (this.faceFrameReviewFindings.length) {
					this.faceFrameCurrentIndex = 0;
				} else if (this.faceFrameOptions.operation_mode === 'immediate') {
					await this.startCleanupRun({ skipFaceFrameOptionsDialog: true, resumeExisting: true });
				}
			} catch (err) {
				this.cleanupStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.faceFrameDecisionLoading = false;
			}
		},
		async applySelectedFaceFrames() {
			if (!this.faceFrameSelectedCount || this.faceFrameApplyLoading) {
				return;
			}
			this.faceFrameApplyLoading = true;
			try {
				const selectedItemIds = this.faceFrameFindings
					.filter((finding) => finding.selection_state === 'selected' && finding.write_state !== 'written')
					.map((finding) => finding.item_id);
				const response = await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_face_frames_apply', {
					selected_item_ids: selectedItemIds,
					operation_mode: this.faceFrameOptions.operation_mode,
				});
				const result = this.getResponseData(response);
				const findings = result.findings && Array.isArray(result.findings.entries) ? result.findings.entries : [];
				this.faceFrameFindings = findings;
				this.cleanupStatusMessage = this.$avt(
					'cleanup:face_frames_apply_finished',
					'Selected frames written: {written}; skipped: {skipped}; errors: {errors}',
					{ written: result.written_count || 0, skipped: result.skipped_count || 0, errors: result.errors_count || 0 }
				);
			} catch (err) {
				this.cleanupStatusMessage = `Error: ${this.getErrorMessage(err)}`;
			} finally {
				this.faceFrameApplyLoading = false;
			}
		},
			async stopCleanupRun(options = {}) {
				const action = String(options.actionOverride || this.cleanupRuntimeAction || this.selectedCleanupAction || 'normalize_names');
				this.cleanupRuntimeAction = action;
				try {
					await this.callDsmApi('/webman/3rdparty/AV_ImgData/index.cgi/api/cleanup_stop', {
						action,
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
		getFaceFrameDecisionLabel(decision) {
			const normalized = String(decision || '').trim().toLowerCase();
			const labels = {
				safe: this.$avt('cleanup:face_frames_decision_safe', 'Safe'),
				review: this.$avt('cleanup:face_frames_decision_review', 'Review'),
				conflict: this.$avt('cleanup:face_frames_decision_conflict', 'Conflict'),
			};
			return labels[normalized] || normalized;
		},
		getFaceFrameSelectionLabel(selectionState) {
			const normalized = String(selectionState || '').trim().toLowerCase();
			return normalized === 'selected'
				? this.$avt('cleanup:face_frames_selection_selected', 'Automatically selected')
				: this.$avt('cleanup:face_frames_selection_review', 'Manual decision required');
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
