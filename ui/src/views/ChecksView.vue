<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$avt('checks:title', 'Checks') }}</div>
			<p>{{ vm.$avt('checks:desc', 'Area for validation and review functions.') }}</p>
		</div>
		<div class="checks-actions panel-content-start">
			<div class="checks-actions-row checks-actions-row-selects">
				<select v-model="vm.selectedChecksType" class="face-match-select" :disabled="vm.checksLoading || (vm.isInsightFaceAssignmentCheck && vm.cleanupLoading)">
					<option value="dimension_issues">{{ vm.$avt('checks:type_dimension_issues', 'Dimension issues') }}</option>
					<option value="duplicate_faces">{{ vm.$avt('checks:type_duplicate_faces', 'Duplicate face markings') }}</option>
					<option value="position_deviations">{{ vm.$avt('checks:type_position_deviations', 'Deviating face positions') }}</option>
					<option value="name_conflicts">{{ vm.$avt('checks:type_name_conflicts', 'Name conflicts') }}</option>
					<option value="recognition_check_person_assignments" :disabled="!vm.hasInsightFaceForFaceMatch">{{ vm.$avt('checks:type_recognition_check_person_assignments', 'Person assignments with InsightFace') }}</option>
				</select>
				<select v-model="vm.selectedChecksAction" class="face-match-select" :disabled="vm.checksLoading || (vm.isInsightFaceAssignmentCheck && vm.cleanupLoading)">
					<option value="findings">{{ vm.$avt('checks:action_findings', 'Process saved findings list') }}</option>
					<option value="scan">{{ vm.$avt('checks:action_scan', 'Run check scan') }}</option>
				</select>
			</div>
			<div class="checks-actions-row checks-actions-row-switches">
				<label
					v-if="vm.selectedChecksAction === 'scan'"
					class="face-match-switch"
					:title="vm.$avt('checks:hint_save_only', 'Findings are only stored in the findings list and not shown directly during the scan. Automatic recommended solutions are still applied.')"
				>
					<input v-model="vm.checksSaveOnly" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('checks:switch_save_only', 'Save findings only') }}</span>
				</label>
				<label
					v-if="vm.selectedChecksType === 'name_conflicts'"
					class="face-match-switch"
					:title="vm.$avt('checks:hint_auto_apply_suggested_names', 'Suggested target names from stored name mappings are applied automatically.')"
				>
					<input v-model="vm.checksAutoApplySuggestedNames" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('checks:switch_auto_apply_suggested_names', 'Apply suggested names automatically') }}</span>
				</label>
				<label
					v-if="vm.selectedChecksType === 'duplicate_faces'"
					class="face-match-switch"
					:title="vm.$avt('checks:hint_auto_apply_suggested_duplicates', 'If a clear recommendation exists, the alternative face marking is removed automatically.')"
				>
					<input v-model="vm.checksAutoApplySuggestedDuplicates" type="checkbox" :disabled="vm.checksLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('checks:switch_auto_apply_suggested_duplicates', 'Keep suggested face automatically') }}</span>
				</label>
				<label
					v-if="vm.selectedChecksAction === 'scan' && !vm.isInsightFaceAssignmentCheck"
					class="checks-number-field"
					:title="vm.$avt('checks:hint_changed_since_days', 'Only images whose file or sidecar changed within the selected number of days are checked. 0 checks all images.')"
				>
					<span class="face-match-switch-label">{{ vm.$avt('checks:label_changed_since_days', 'Changed in days') }}</span>
					<input v-model.number="vm.checksChangedSinceDays" type="number" min="0" step="1" class="checks-number-input" :disabled="vm.checksLoading" />
				</label>
				<div v-if="vm.isInsightFaceAssignmentCheck && !vm.hasInsightFaceForFaceMatch" class="config-card-desc">
					{{ vm.faceMatchInsightFaceUnavailableMessage }}
				</div>
				<InsightFaceAssignmentOptions v-if="vm.isInsightFaceAssignmentCheck && vm.hasInsightFaceForFaceMatch" :vm="vm" />
			</div>
			<div class="checks-actions-row checks-actions-row-buttons">
				<div class="face-match-action-buttons">
					<v-button @click="vm.startChecksReview" :disabled="vm.isInsightFaceAssignmentCheck && !vm.hasInsightFaceForFaceMatch" style="width: 160px;">
						{{ vm.checksPrimaryButtonLabel }}
					</v-button>
					<v-button
						v-if="vm.checksCurrentItem && vm.canIgnoreChecksItem()"
						@click="vm.ignoreChecksCurrentItem"
						:disabled="vm.checksLoading"
						style="width: 160px;"
					>
						{{ vm.$avt('checks:button_ignore', 'Ignore') }}
					<!-- status-source-contract: vm.isChecksScanRunning || -->
					</v-button>
					<v-button v-if="vm.hasNextChecksItem" @click="vm.nextChecksReview" :disabled="vm.checksLoading" style="width: 160px;">
						{{ vm.$avt('checks:button_next', 'Next') }}
					</v-button>
				</div>
			</div>
		</div>
		<div class="face-match-status-card face-match-status-card-action">
			<div class="face-match-status-head">
				<div class="sm-section-title">{{ vm.$avt('checks:status_title', 'Status') }}</div>
			</div>
			<div
				v-if="vm.isInsightFaceAssignmentCheck && Number(vm.getCleanupStatusProgress().total) > 0"
				class="sm-status-progress"
			>
				<ProgressOverviewCard
					:title="vm.getCleanupStatusProgressTitle()"
					:count="Number(vm.getCleanupStatusProgress().total) || 0"
					:current="Number(vm.getCleanupStatusProgress().current) || 0"
					:total="Number(vm.getCleanupStatusProgress().total) || 0"
					:primary-label="vm.getCleanupStatusProgressPrimaryLabel()"
					:secondary-label="vm.getCleanupStatusProgressSecondaryLabel()"
					:status-text="vm.getCleanupStatusHeadline()"
				/>
			</div>
			<div
				v-if="!vm.isInsightFaceAssignmentCheck && vm.shouldShowChecksScanProgressCard"
				class="sm-status-progress"
			>
				<ProgressOverviewCard
					:title="vm.getChecksStatusProgressTitle()"
					:count="vm.getChecksStatusProgress().total"
					:current="vm.getChecksStatusProgress().current"
					:total="vm.getChecksStatusProgress().total"
					:primary-label="vm.getChecksStatusProgressPrimaryLabel()"
					:secondary-label="vm.getChecksStatusProgressSecondaryLabel()"
					:status-text="vm.getChecksProgressStatusText()"
					:icon-url="vm.getChecksProgressIconUrl()"
				/>
			</div>
			<div v-if="!vm.isInsightFaceAssignmentCheck && vm.shouldShowChecksListProgressCard" class="sm-status-progress">
				<ProgressOverviewCard
					:title="vm.$avt('checks:label_list_entries', 'Entries')"
					:count="vm.getChecksListTotalCount()"
					:current="vm.getChecksListCurrentCount()"
					:total="vm.getChecksListTotalCount()"
					:primary-label="vm.$avt('checks:label_index', 'Entry:').replace(':', '')"
					:secondary-label="vm.$avt('checks:label_entries_remaining', 'remaining')"
					:status-text="vm.getChecksProgressStatusText()"
				/>
			</div>
			<div v-if="vm.isInsightFaceAssignmentCheck" class="face-match-status-message">{{ vm.getCleanupStatusHeadline() }}</div>
			<div v-else-if="vm.shouldShowChecksStandaloneStatusMessage && vm.getChecksProgressStatusText()" class="face-match-status-message">{{ vm.getChecksProgressStatusText() }}</div>
			<div v-if="vm.isInsightFaceAssignmentCheck && vm.getCleanupStatusCounters().length" class="face-match-status-stats">
				<span v-for="counter in vm.getCleanupStatusCounters()" :key="`checks-recognition-counter-${counter.key}`">{{ vm.formatCleanupStatusCounter(counter) }}</span>
			</div>
			<div v-if="vm.isInsightFaceAssignmentCheck && vm.cleanupProgress.current_path" class="face-match-status-stats">
				<div><strong>{{ vm.$avt('checks:label_file', 'File:') }}</strong> {{ vm.cleanupProgress.current_path }}</div>
				<div v-if="vm.cleanupProgress.current_name"><strong>{{ vm.$avt('cleanup:label_current_name', 'Current name') }}:</strong> {{ vm.cleanupProgress.current_name }}</div>
			</div>
			<div v-if="!vm.isInsightFaceAssignmentCheck && vm.checksCurrentItem" class="face-match-status-stats">
				<div><strong>{{ vm.$avt('checks:label_file', 'File:') }}</strong> {{ vm.checksCurrentItem.image_name }}</div>
				<div><strong>{{ vm.$avt('checks:label_face_name', 'Face:') }}</strong> {{ vm.checksCurrentItem.face_name || vm.$avt('face_match:unknown_name', '(unnamed)') }}</div>
				<div><strong>{{ vm.$avt('checks:label_pair', 'Pair:') }}</strong> {{ vm.getChecksPairLabel(vm.checksCurrentItem) }}</div>
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
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.right_face_target, vm.checksCurrentItem.left_name, { createMissingPerson: vm.isChecksPhotosFace(vm.checksCurrentItem.right_face_target) })"
				>
					<img v-if="vm.getChecksReplaceRightIconUrl()" :src="vm.getChecksReplaceRightIconUrl()" alt="" class="face-match-icon-image" />
					<span v-else class="face-match-icon-fallback">{{ vm.$avt('checks:button_replace_name_right', 'Name ->') }}</span>
				</button>
				<button
					v-if="vm.isChecksNameConflict(vm.checksCurrentItem) && vm.canReplaceChecksFaceName(vm.checksCurrentItem, vm.checksCurrentItem.left_face_target, vm.checksCurrentItem.right_name)"
					type="button"
					class="face-match-icon-button checks-replace-button"
					:title="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:aria-label="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:disabled="vm.checksLoading"
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.left_face_target, vm.checksCurrentItem.right_name, { createMissingPerson: vm.isChecksPhotosFace(vm.checksCurrentItem.left_face_target) })"
				>
					<img v-if="vm.getChecksReplaceLeftIconUrl()" :src="vm.getChecksReplaceLeftIconUrl()" alt="" class="face-match-icon-image" />
					<span v-else class="face-match-icon-fallback">{{ vm.$avt('checks:button_replace_name_left', 'Name left') }}</span>
				</button>
			</div>
			<ChecksFacePane :vm="vm" :item="vm.checksCurrentItem" side="left" />
			<ChecksFacePane :vm="vm" :item="vm.checksCurrentItem" side="right" />
		</div>
		<div v-if="vm.nameMappingConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal sm-modal-centered" role="dialog" aria-modal="true" aria-labelledby="checks-name-mapping-confirm-title">
				<div id="checks-name-mapping-confirm-title" class="sm-modal-title">{{ vm.$avt('face_match:modal_mapping_title', 'Save name mapping') }}</div>
				<div class="sm-modal-text">{{ vm.nameMappingConfirm.message }}</div>
				<label v-if="vm.nameMappingConfirm.context === 'checks'" class="face-match-switch sm-modal-switch-option">
					<input v-model="vm.nameMappingConfirm.skipFuturePrompts" type="checkbox" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('checks:switch_skip_name_mapping_confirm', 'Do not ask again for this check') }}</span>
				</label>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveNameMappingConfirm(false)" style="width: 120px;">{{ vm.$avt('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveNameMappingConfirm(true)" style="width: 120px;">{{ vm.$avt('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
		</div>
		<InsightFaceAssignmentReview v-if="vm.isInsightFaceAssignmentCheck && vm.hasInsightFaceForFaceMatch" :vm="vm" />
	</section>
</template>

<script>
import ChecksFacePane from '../components/ChecksFacePane.vue';
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';

export default {
	name: 'ChecksView',
	components: {
		ChecksFacePane,
		InsightFaceAssignmentOptions: () => import('../components/checks/InsightFaceAssignmentOptions.vue'),
		InsightFaceAssignmentReview: () => import('../components/cleanup/RecognitionFindingsReview.vue'),
		ProgressOverviewCard,
	},
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
