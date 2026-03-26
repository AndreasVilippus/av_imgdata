export default {
	data() {
		return {
			selectedChecksType: 'dimension_issues',
			selectedChecksAction: 'findings',
			checksLoading: false,
			checksEntries: [],
			checksCurrentIndex: 0,
			checksStatusMessage: '',
			checksCurrentItem: null,
		};
	},
	computed: {
		hasNextChecksItem() {
			return this.checksCurrentIndex + 1 < this.checksEntries.length;
		},
	},
	methods: {
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
		async startChecksReview() {
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
			const entry = this.checksEntries[index];
			if (!entry) {
				this.checksCurrentItem = null;
				return;
			}
			const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_item', {
				entry,
			});
			const item = this.getResponseDataObject(data, 'item');
			this.checksCurrentItem = Object.keys(item).length ? item : null;
			this.checksCurrentIndex = index;
			this.checksStatusMessage = this.checksCurrentItem
				? this.$t('checks:status_entry', 'Entry {current} of {total}.', {
					current: this.checksCurrentIndex + 1,
					total: this.checksEntries.length,
				})
				: this.$t('checks:status_empty', 'No matching entries found.');
		},
		async nextChecksReview() {
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
	},
};
