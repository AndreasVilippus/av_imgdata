<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$avt('database_lists:title', 'Database lists') }}</div>
			<p>{{ vm.$avt('database_lists:description', 'Inspect and manage persistent application lists.') }}</p>
		</div>

		<div class="database-list-toolbar">
			<label class="config-field database-list-selector">
				<span class="config-field-label">{{ vm.$avt('database_lists:list', 'List') }}</span>
				<select v-model="vm.databaseListType" class="config-select" :disabled="vm.databaseListLoading">
					<option value="name_mappings">{{ vm.$avt('database_lists:name_mappings', 'Name mappings') }}</option>
				</select>
			</label>
			<label class="config-field database-list-search">
				<span class="config-field-label">{{ vm.$avt('database_lists:search', 'Search / filter') }}</span>
				<input
					v-model="vm.databaseListSearch"
					type="search"
					class="config-text-input"
					:disabled="vm.databaseListLoading"
					:placeholder="vm.$avt('database_lists:search_placeholder', 'Source, target or type')"
					@keyup.enter="vm.applyDatabaseListSearch"
				/>
			</label>
			<div class="database-list-toolbar-actions">
				<v-button @click="vm.applyDatabaseListSearch" :disabled="vm.databaseListLoading">
					{{ vm.$avt('database_lists:button_search', 'Search') }}
				</v-button>
				<v-button @click="vm.clearDatabaseListSearch" :disabled="vm.databaseListLoading || (!vm.databaseListSearch && !vm.databaseListAppliedSearch)">
					{{ vm.$avt('database_lists:button_clear', 'Clear') }}
				</v-button>
				<v-button @click="vm.loadDatabaseList" :disabled="vm.databaseListLoading">
					{{ vm.$avt('config:button_reload', 'Reload') }}
				</v-button>
			</div>
		</div>

		<div v-if="vm.databaseListMessage" class="config-message">{{ vm.databaseListMessage }}</div>
		<div class="config-card database-list-editor">
			<div class="config-card-title">
				{{ vm.databaseListEditorId ? vm.$avt('database_lists:edit_title', 'Edit name mapping') : vm.$avt('database_lists:add_title', 'Add name mapping') }}
			</div>
			<div class="database-list-editor-fields">
				<label class="config-field">
					<span class="config-field-label">{{ vm.$avt('database_lists:source_name', 'Source name') }}</span>
					<input :value="vm.databaseListEditorSourceName" class="config-text-input" :disabled="vm.databaseListSaving || !!vm.databaseListEditorId" @input="vm.setDatabaseListEditorSourceName($event.target.value)" />
				</label>
				<label class="config-field">
					<span class="config-field-label">{{ vm.$avt('database_lists:target_name', 'Target name') }}</span>
					<input :value="vm.databaseListEditorTargetName" class="config-text-input" :disabled="vm.databaseListSaving" @input="vm.setDatabaseListEditorTargetName($event.target.value)" @keyup.enter="vm.saveDatabaseNameMapping" />
				</label>
				<div class="database-list-toolbar-actions">
					<v-button @click="vm.saveDatabaseNameMapping" :disabled="vm.databaseListSaving || !vm.databaseListEditorSourceName || !vm.databaseListEditorTargetName">
						{{ vm.databaseListSaving ? vm.$avt('database_lists:saving', 'Saving...') : vm.$avt('database_lists:save', 'Save') }}
					</v-button>
					<v-button @click="vm.cancelDatabaseNameMappingEdit" :disabled="vm.databaseListSaving">
						{{ vm.$avt('database_lists:cancel', 'Cancel') }}
					</v-button>
				</div>
			</div>
		</div>

		<div v-if="vm.databaseListLoading" class="config-loading">
			<span class="sm-loader"></span>
			{{ vm.$avt('database_lists:loading', 'Loading list...') }}
		</div>

		<div v-else class="database-list-table-wrap">
			<table class="database-list-table">
				<thead>
					<tr>
						<th>{{ vm.$avt('database_lists:source_name', 'Source name') }}</th>
						<th>{{ vm.$avt('database_lists:target_name', 'Target name') }}</th>
						<th>{{ vm.$avt('database_lists:source_kind', 'Source type') }}</th>
						<th>{{ vm.$avt('database_lists:mapping_kind', 'Mapping type') }}</th>
						<th>{{ vm.$avt('database_lists:updated_at', 'Updated') }}</th>
						<th class="database-list-actions-column">{{ vm.$avt('database_lists:actions', 'Actions') }}</th>
					</tr>
				</thead>
				<tbody>
					<tr v-for="entry in vm.databaseListEntries" :key="entry.id">
						<td>{{ entry.source_name }}</td>
						<td>{{ entry.target_name }}</td>
						<td>{{ entry.source_kind }}</td>
						<td>{{ entry.mapping_kind }}</td>
						<td>{{ entry.updated_at }}</td>
						<td class="database-list-actions-column">
							<v-button @click="vm.startDatabaseNameMappingEdit(entry)" :disabled="vm.databaseListSaving || !!vm.databaseListDeletingId">
								{{ vm.$avt('database_lists:edit', 'Edit') }}
							</v-button>
							<v-button @click="vm.deleteDatabaseNameMapping(entry)" :disabled="!!vm.databaseListDeletingId">
								{{ vm.databaseListDeletingId === entry.id ? vm.$avt('database_lists:deleting', 'Deleting...') : vm.$avt('database_lists:delete', 'Delete') }}
							</v-button>
						</td>
					</tr>
					<tr v-if="!vm.databaseListEntries.length">
						<td colspan="6" class="database-list-empty">{{ vm.$avt('database_lists:empty', 'No entries found.') }}</td>
					</tr>
				</tbody>
			</table>
		</div>

		<div class="database-list-pagination">
			<div>
				{{ vm.$avt('database_lists:range', '{first}-{last} of {total}', {
					first: vm.databaseListFirstEntry,
					last: vm.databaseListLastEntry,
					total: vm.databaseListTotal,
				}) }}
			</div>
			<label class="database-list-page-size">
				<span>{{ vm.$avt('database_lists:page_size', 'Rows per page') }}</span>
				<select v-model.number="vm.databaseListPageSize" class="config-select" :disabled="vm.databaseListLoading" @change="vm.changeDatabaseListPageSize">
					<option :value="10">10</option>
					<option :value="25">25</option>
					<option :value="50">50</option>
					<option :value="100">100</option>
				</select>
			</label>
			<v-button @click="vm.changeDatabaseListPage(-1)" :disabled="vm.databaseListLoading || vm.databaseListPage <= 1">
				{{ vm.$avt('database_lists:previous', 'Previous') }}
			</v-button>
			<span>{{ vm.databaseListPage }} / {{ vm.databaseListTotalPages }}</span>
			<v-button @click="vm.changeDatabaseListPage(1)" :disabled="vm.databaseListLoading || vm.databaseListPage >= vm.databaseListTotalPages">
				{{ vm.$avt('database_lists:next', 'Next') }}
			</v-button>
		</div>
	</section>
</template>

<script>
export default {
	name: 'DatabaseListsView',
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
