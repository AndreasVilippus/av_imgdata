<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$t('checks:title', 'Checks') }}</div>
			<p>{{ vm.$t('checks:desc', 'Area for validation and review functions.') }}</p>
		</div>
		<div class="checks-actions panel-content-start">
			<div class="checks-actions-row checks-actions-row-selects">
				<select v-model="vm.selectedChecksType" class="face-match-select" :disabled="vm.checksLoading">
					<option value="dimension_issues">{{ vm.$t('checks:type_dimension_issues', 'Dimension issues') }}</option>
					<option value="duplicate_faces">{{ vm.$t('checks:type_duplicate_faces', 'Duplicate face markings') }}</option>
					<option value="position_deviations">{{ vm.$t('checks:type_position_deviations', 'Deviating face positions') }}</option>
					<option value="name_conflicts">{{ vm.$t('checks:type_name_conflicts', 'Name conflicts') }}</option>
				</select>
				<select v-model="vm.selectedChecksAction" class="face-match-select" :disabled="vm.checksLoading">
					<option value="findings">{{ vm.$t('checks:action_findings', 'Use analysis findings') }}</option>
					<option value="scan">{{ vm.$t('checks:action_scan', 'Run check scan') }}</option>
				</select>
			</div>
			<div class="checks-actions-row checks-actions-row-switches">
				<label
					v-if="vm.selectedChecksAction === 'scan'"
					class="face-match-switch"
					:title="vm.$t('checks:hint_save_only', 'Findings are only stored in the findings list and not shown directly during the scan. Automatic recommended solutions are still applied.')"
				>
					<input v-model="vm.checksSaveOnly" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$t('checks:switch_save_only', 'Save findings only') }}</span>
				</label>
				<label
					v-if="vm.selectedChecksType === 'name_conflicts'"
					class="face-match-switch"
					:title="vm.$t('checks:hint_auto_apply_suggested_names', 'Suggested target names from stored name mappings are applied automatically.')"
				>
					<input v-model="vm.checksAutoApplySuggestedNames" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$t('checks:switch_auto_apply_suggested_names', 'Apply suggested names automatically') }}</span>
				</label>
				<label
					v-if="vm.selectedChecksType === 'duplicate_faces'"
					class="face-match-switch"
					:title="vm.$t('checks:hint_auto_apply_suggested_duplicates', 'If a clear recommendation exists, the alternative face marking is removed automatically.')"
				>
					<input v-model="vm.checksAutoApplySuggestedDuplicates" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$t('checks:switch_auto_apply_suggested_duplicates', 'Keep suggested face automatically') }}</span>
				</label>
			</div>
			<div class="checks-actions-row checks-actions-row-buttons">
				<div class="face-match-action-buttons">
					<v-button @click="vm.startChecksReview" style="width: 160px;">
						{{ vm.checksPrimaryButtonLabel }}
					</v-button>
					<v-button v-if="vm.hasNextChecksItem" @click="vm.nextChecksReview" :disabled="vm.checksLoading" style="width: 160px;">
						{{ vm.$t('checks:button_next', 'Next') }}
					</v-button>
				</div>
			</div>
		</div>
		<div class="face-match-status-card face-match-status-card-action">
			<div class="face-match-status-head">
				<div class="sm-section-title">{{ vm.$t('checks:status_title', 'Status') }}</div>
			</div>
			<div class="face-match-status-message">{{ vm.checksStatusMessage }}</div>
			<div v-if="Number(vm.checksProgress.total_files) > 0" class="sm-status-progress">
				<RatioProgress
					:current="Number(vm.checksProgress.files_scanned) || 0"
					:total="Number(vm.checksProgress.total_files) || 0"
					:primary-text="`${Number(vm.checksProgress.files_scanned) || 0} ${vm.$t('checks:label_scanned', 'Scanned:').replace(':', '')}`"
					:secondary-text="`${Number(vm.checksProgress.total_files) || 0} ${vm.$t('status:files_matched', 'Matching files')}`"
					:tooltip="`${Number(vm.checksProgress.files_scanned) || 0} / ${Number(vm.checksProgress.total_files) || 0}`"
				/>
			</div>
			<div v-if="vm.selectedChecksAction !== 'scan' && vm.checksEntries.length > 0" class="sm-status-progress">
				<RatioProgress
					:current="vm.checksCurrentIndex + 1"
					:total="vm.checksEntries.length"
					:primary-text="`${vm.checksCurrentIndex + 1} ${vm.$t('checks:label_index', 'Entry:').replace(':', '')}`"
					:secondary-text="`${vm.checksEntries.length} ${vm.$t('checks:label_list_entries', 'Entries')}`"
					:tooltip="`${vm.checksCurrentIndex + 1} / ${vm.checksEntries.length}`"
				/>
			</div>
			<div v-if="vm.selectedChecksAction === 'scan' && !vm.checksCurrentItem" class="face-match-status-stats">
				<div><strong>{{ vm.$t('checks:label_findings_count', 'Findings:') }}</strong> {{ vm.checksProgress.findings_count || 0 }}</div>
			</div>
			<div v-if="vm.checksCurrentItem" class="face-match-status-stats">
				<div><strong>{{ vm.$t('checks:label_type', 'Check:') }}</strong> {{ vm.getChecksTypeLabel(vm.selectedChecksType) }}</div>
				<div><strong>{{ vm.$t('checks:label_file', 'File:') }}</strong> {{ vm.checksCurrentItem.image_name }}</div>
				<div><strong>{{ vm.$t('checks:label_face_name', 'Face:') }}</strong> {{ vm.checksCurrentItem.face_name || vm.$t('face_match:unknown_name', '(unnamed)') }}</div>
				<div><strong>{{ vm.$t('checks:label_pair', 'Pair:') }}</strong> {{ vm.getChecksPairLabel(vm.checksCurrentItem) }}</div>
			</div>
		</div>
			<div v-if="vm.checksCurrentItem" class="face-match-split checks-split">
			<div v-if="vm.isChecksNameConflict(vm.checksCurrentItem)" class="checks-replace-actions">
				<button
					v-if="vm.isChecksNameConflict(vm.checksCurrentItem) && vm.canReplaceChecksFaceName(vm.checksCurrentItem, vm.checksCurrentItem.right_face_target, vm.checksCurrentItem.left_name)"
					type="button"
					class="face-match-icon-button checks-replace-button"
					:title="vm.getChecksReplaceRightTooltip(vm.checksCurrentItem)"
					:aria-label="vm.getChecksReplaceRightTooltip(vm.checksCurrentItem)"
					:disabled="vm.checksLoading"
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.right_face_target, vm.checksCurrentItem.left_name)"
				>
					<img v-if="vm.getChecksReplaceRightIconUrl()" :src="vm.getChecksReplaceRightIconUrl()" alt="" class="face-match-icon-image" />
					<span v-else class="face-match-icon-fallback">{{ vm.$t('checks:button_replace_name_right', 'Name ->') }}</span>
				</button>
				<button
					v-if="vm.isChecksNameConflict(vm.checksCurrentItem) && vm.canReplaceChecksFaceName(vm.checksCurrentItem, vm.checksCurrentItem.left_face_target, vm.checksCurrentItem.right_name)"
					type="button"
					class="face-match-icon-button checks-replace-button"
					:title="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:aria-label="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:disabled="vm.checksLoading"
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.left_face_target, vm.checksCurrentItem.right_name)"
				>
					<img v-if="vm.getChecksReplaceLeftIconUrl()" :src="vm.getChecksReplaceLeftIconUrl()" alt="" class="face-match-icon-image" />
					<span v-else class="face-match-icon-fallback">{{ vm.$t('checks:button_replace_name_left', '<- Name') }}</span>
				</button>
			</div>
			<ChecksFacePane :vm="vm" :item="vm.checksCurrentItem" side="left" />
			<ChecksFacePane :vm="vm" :item="vm.checksCurrentItem" side="right" />
		</div>
		<div v-if="vm.nameMappingConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal sm-modal-centered" role="dialog" aria-modal="true" aria-labelledby="checks-name-mapping-confirm-title">
				<div id="checks-name-mapping-confirm-title" class="sm-modal-title">{{ vm.$t('face_match:modal_mapping_title', 'Save name mapping') }}</div>
				<div class="sm-modal-text">{{ vm.nameMappingConfirm.message }}</div>
				<label v-if="vm.nameMappingConfirm.context === 'checks'" class="face-match-switch sm-modal-switch-option">
					<input v-model="vm.nameMappingConfirm.skipFuturePrompts" type="checkbox" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$t('checks:switch_skip_name_mapping_confirm', 'Do not ask again for this check') }}</span>
				</label>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveNameMappingConfirm(false)" style="width: 120px;">{{ vm.$t('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveNameMappingConfirm(true)" style="width: 120px;">{{ vm.$t('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
		</div>
	</section>
</template>

<script>
import ChecksFacePane from '../components/ChecksFacePane.vue';
import RatioProgress from '../components/RatioProgress.vue';

export default {
	name: 'ChecksView',
	components: {
		ChecksFacePane,
		RatioProgress,
	},
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
