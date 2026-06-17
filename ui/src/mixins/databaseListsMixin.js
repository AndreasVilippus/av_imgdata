export default {
	data() {
		return {
			databaseListType: 'name_mappings',
			databaseListEntries: [],
			databaseListSearch: '',
			databaseListAppliedSearch: '',
			databaseListPage: 1,
			databaseListPageSize: 25,
			databaseListTotal: 0,
			databaseListLoading: false,
			databaseListDeletingId: null,
			databaseListClearing: false,
			databaseListSaving: false,
			databaseListMessage: '',
			databaseChecksIgnoreListsStatus: {},
			databaseListEditorId: null,
			databaseListEditorSourceName: '',
			databaseListEditorTargetName: '',
		};
	},
	computed: {
		databaseListIsNameMappings() {
			return this.databaseListType === 'name_mappings';
		},
		databaseListIsIgnoreList() {
			return String(this.databaseListType || '').startsWith('ignore_');
		},
		databaseIgnoreReviewType() {
			const type = String(this.databaseListType || '');
			if (type === 'ignore_duplicate_faces') {
				return 'duplicate_faces';
			}
			if (type === 'ignore_position_deviations') {
				return 'position_deviations';
			}
			if (type === 'ignore_name_conflicts') {
				return 'name_conflicts';
			}
			return '';
		},
		currentDatabaseListLabel() {
			const labels = {
				name_mappings: this.$avt('database_lists:name_mappings', 'Name mappings'),
				ignore_duplicate_faces: this.$avt('database_lists:ignore_duplicate_faces', 'Ignore list for duplicate face markings'),
				ignore_position_deviations: this.$avt('database_lists:ignore_position_deviations', 'Ignore list for deviating face positions'),
				ignore_name_conflicts: this.$avt('database_lists:ignore_name_conflicts', 'Ignore list for name conflicts'),
			};
			return labels[this.databaseListType] || this.databaseListType;
		},
		currentDatabaseIgnoreListStatus() {
			const reviewType = this.databaseIgnoreReviewType;
			const status = this.databaseChecksIgnoreListsStatus && typeof this.databaseChecksIgnoreListsStatus === 'object'
				? this.databaseChecksIgnoreListsStatus[reviewType]
				: null;
			return status && typeof status === 'object'
				? status
				: { count: 0, path: '', storage: '', enabled: true };
		},
		databaseListTotalPages() {
			return Math.max(1, Math.ceil(this.databaseListTotal / this.databaseListPageSize));
		},
		databaseListFirstEntry() {
			return this.databaseListTotal ? ((this.databaseListPage - 1) * this.databaseListPageSize) + 1 : 0;
		},
		databaseListLastEntry() {
			return Math.min(this.databaseListTotal, this.databaseListPage * this.databaseListPageSize);
		},
	},
	watch: {
		databaseListType() {
			this.databaseListSearch = '';
			this.databaseListAppliedSearch = '';
			this.cancelDatabaseNameMappingEdit();
			this.loadDatabaseList({ resetPage: true });
		},
	},
	methods: {
		async loadDatabaseList({ resetPage = false } = {}) {
			if (resetPage) {
				this.databaseListPage = 1;
			}
			this.databaseListLoading = true;
			this.databaseListMessage = '';
			try {
				if (this.databaseListIsIgnoreList) {
					await this.loadDatabaseIgnoreListStatus();
					this.databaseListEntries = [];
					this.databaseListTotal = 0;
					this.databaseListPage = 1;
					return;
				}
				const response = await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/database_name_mappings',
					{
						search: this.databaseListAppliedSearch,
						page: this.databaseListPage,
						page_size: this.databaseListPageSize,
					}
				);
				const data = this.getResponseData(response);
				this.databaseListEntries = Array.isArray(data.entries) ? data.entries : [];
				this.databaseListTotal = Number(data.total) || 0;
				this.databaseListPage = Math.max(1, Number(data.page) || 1);
				this.databaseListPageSize = Math.max(1, Number(data.page_size) || this.databaseListPageSize);
				if (this.databaseListPage > this.databaseListTotalPages) {
					this.databaseListPage = this.databaseListTotalPages;
					await this.loadDatabaseList();
				}
			} catch (err) {
				this.databaseListMessage = `Error: ${err.message}`;
			} finally {
				this.databaseListLoading = false;
			}
		},
		normalizeDatabaseIgnoreListsStatus(value) {
			const source = value && typeof value === 'object' && !Array.isArray(value) ? value : {};
			const normalized = {};
			for (const reviewType of ['duplicate_faces', 'position_deviations', 'name_conflicts']) {
				const entry = source[reviewType] && typeof source[reviewType] === 'object' && !Array.isArray(source[reviewType])
					? source[reviewType]
					: {};
				normalized[reviewType] = {
					count: Math.max(0, Number(entry.count) || 0),
					path: String(entry.path || ''),
					storage: String(entry.storage || ''),
					enabled: Boolean(entry.enabled ?? true),
				};
			}
			return normalized;
		},
		async loadDatabaseIgnoreListStatus() {
			const response = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/database_checks_ignore_lists', {});
			const data = this.getResponseData(response);
			this.databaseChecksIgnoreListsStatus = this.normalizeDatabaseIgnoreListsStatus(data.checks_ignore_lists);
		},
		applyDatabaseListSearch() {
			this.databaseListAppliedSearch = String(this.databaseListSearch || '').trim();
			return this.loadDatabaseList({ resetPage: true });
		},
		clearDatabaseListSearch() {
			this.databaseListSearch = '';
			this.databaseListAppliedSearch = '';
			return this.loadDatabaseList({ resetPage: true });
		},
		changeDatabaseListPageSize() {
			return this.loadDatabaseList({ resetPage: true });
		},
		changeDatabaseListPage(direction) {
			const nextPage = Math.min(
				this.databaseListTotalPages,
				Math.max(1, this.databaseListPage + Number(direction || 0))
			);
			if (nextPage === this.databaseListPage) {
				return;
			}
			this.databaseListPage = nextPage;
			this.loadDatabaseList();
		},
		startDatabaseNameMappingEdit(entry = null) {
			this.databaseListEditorId = entry ? Number(entry.id) || null : null;
			this.databaseListEditorSourceName = entry ? String(entry.source_name || '') : '';
			this.databaseListEditorTargetName = entry ? String(entry.target_name || '') : '';
			this.databaseListMessage = '';
		},
		cancelDatabaseNameMappingEdit() {
			this.startDatabaseNameMappingEdit();
		},
		setDatabaseListEditorSourceName(value) {
			this.databaseListEditorSourceName = String(value || '');
		},
		setDatabaseListEditorTargetName(value) {
			this.databaseListEditorTargetName = String(value || '');
		},
		async saveDatabaseNameMapping() {
			const sourceName = String(this.databaseListEditorSourceName || '').trim();
			const targetName = String(this.databaseListEditorTargetName || '').trim();
			if (!sourceName || !targetName || this.databaseListSaving) {
				return;
			}
			this.databaseListSaving = true;
			this.databaseListMessage = '';
			try {
				await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/database_name_mapping_save',
					{ id: this.databaseListEditorId, source_name: sourceName, target_name: targetName }
				);
				this.cancelDatabaseNameMappingEdit();
				this.databaseListMessage = this.$avt('database_lists:message_saved', 'Entry saved.');
				await this.loadDatabaseList();
			} catch (err) {
				this.databaseListMessage = `Error: ${err.message}`;
			} finally {
				this.databaseListSaving = false;
			}
		},
		async deleteDatabaseNameMapping(entry) {
			const mappingId = Number(entry && entry.id);
			if (!mappingId || this.databaseListDeletingId) {
				return;
			}
			const sourceName = String(entry.source_name || '');
			const targetName = String(entry.target_name || '');
			const confirmation = this.$avt(
				'database_lists:confirm_delete_name_mapping',
				'Delete mapping "{source}" → "{target}"?',
				{ source: sourceName, target: targetName }
			);
			if (!window.confirm(confirmation)) {
				return;
			}
			this.databaseListDeletingId = mappingId;
			this.databaseListMessage = '';
			try {
				await this.callFileAnalysisApi(
					'/webman/3rdparty/AV_ImgData/index.cgi/api/database_name_mapping_delete',
					{ id: mappingId }
				);
				this.databaseListMessage = this.$avt('database_lists:message_deleted', 'Entry deleted.');
				await this.loadDatabaseList();
			} catch (err) {
				this.databaseListMessage = `Error: ${err.message}`;
			} finally {
				this.databaseListDeletingId = null;
			}
		},
		async clearCurrentDatabaseList() {
			if (this.databaseListClearing) {
				return;
			}
			const confirmation = this.$avt(
				'database_lists:confirm_clear_list',
				'Clear "{list}" completely?',
				{ list: this.currentDatabaseListLabel }
			);
			if (!window.confirm(confirmation)) {
				return;
			}
			this.databaseListClearing = true;
			this.databaseListMessage = '';
			try {
				if (this.databaseListIsIgnoreList) {
					const response = await this.callFileAnalysisApi(
						'/webman/3rdparty/AV_ImgData/index.cgi/api/checks_ignore_list_clear',
						{ review_type: this.databaseIgnoreReviewType }
					);
					const data = this.getResponseData(response);
					this.databaseChecksIgnoreListsStatus = this.normalizeDatabaseIgnoreListsStatus(data.checks_ignore_lists);
				} else {
					await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/database_name_mappings_clear', {});
				}
				this.cancelDatabaseNameMappingEdit();
				this.databaseListMessage = this.$avt('database_lists:message_cleared', 'List cleared.');
				await this.loadDatabaseList({ resetPage: true });
			} catch (err) {
				this.databaseListMessage = `Error: ${err.message}`;
			} finally {
				this.databaseListClearing = false;
			}
		},
	},
};
