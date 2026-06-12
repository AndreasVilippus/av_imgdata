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
			databaseListSaving: false,
			databaseListMessage: '',
			databaseListEditorId: null,
			databaseListEditorSourceName: '',
			databaseListEditorTargetName: '',
		};
	},
	computed: {
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
	methods: {
		async loadDatabaseList({ resetPage = false } = {}) {
			if (resetPage) {
				this.databaseListPage = 1;
			}
			this.databaseListLoading = true;
			this.databaseListMessage = '';
			try {
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
	},
};
