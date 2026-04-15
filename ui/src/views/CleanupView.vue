<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$t('cleanup:title', 'Cleanup') }}</div>
			<p>{{ vm.$t('cleanup:desc', 'Area for cleanup and normalization functions.') }}</p>
		</div>
		<div class="checks-actions panel-content-start">
			<div class="checks-actions-row checks-actions-row-selects">
				<select v-model="vm.selectedCleanupAction" class="face-match-select" :disabled="vm.cleanupLoading">
					<option value="normalize_names">{{ vm.$t('cleanup:action_normalize_names', 'Adjust names by reference list') }}</option>
				</select>
			</div>
			<div class="checks-actions-row checks-actions-row-switches">
				<label v-for="target in ['PHOTOS', 'ACD', 'MICROSOFT', 'MWG_REGIONS']" :key="`cleanup-target-${target}`" class="face-match-switch">
					<input v-model="vm.cleanupTargets[target]" type="checkbox" :disabled="vm.cleanupLoading" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.getCleanupTargetLabel(target) }}</span>
				</label>
			</div>
			<div class="checks-actions-row checks-actions-row-buttons">
				<div class="face-match-action-buttons">
					<v-button @click="vm.handleCleanupAction" style="width: 160px;">
						{{ vm.cleanupPrimaryButtonLabel }}
					</v-button>
				</div>
			</div>
		</div>
		<div class="face-match-status-card face-match-status-card-action">
			<div class="face-match-status-head">
				<div class="sm-section-title">{{ vm.$t('cleanup:status_title', 'Status') }}</div>
				<div v-if="vm.cleanupLoading" class="face-match-status-running">
					<span class="sm-loader"></span>
					{{ vm.$t('cleanup:card_running', 'Running') }}
				</div>
			</div>
			<div class="face-match-status-message">{{ vm.cleanupStatusMessage }}</div>
			<div v-if="Number(vm.cleanupProgress.persons_total) > 0" class="sm-status-progress">
				<RatioProgress
					:current="Number(vm.cleanupProgress.persons_scanned) || 0"
					:total="Number(vm.cleanupProgress.persons_total) || 0"
					:primary-text="`${Number(vm.cleanupProgress.persons_scanned) || 0} ${vm.$t('cleanup:label_persons_scanned', 'Persons scanned')}`"
					:secondary-text="`${Number(vm.cleanupProgress.persons_total) || 0} ${vm.$t('face_match:label_persons', 'Persons')}`"
					:tooltip="`${Number(vm.cleanupProgress.persons_scanned) || 0} / ${Number(vm.cleanupProgress.persons_total) || 0}`"
				/>
			</div>
			<div v-if="Number(vm.cleanupProgress.total_files) > 0" class="sm-status-progress">
				<RatioProgress
					:current="Number(vm.cleanupProgress.files_scanned) || 0"
					:total="Number(vm.cleanupProgress.total_files) || 0"
					:primary-text="`${Number(vm.cleanupProgress.files_scanned) || 0} ${vm.$t('cleanup:label_files_scanned', 'Files scanned')}`"
					:secondary-text="`${Number(vm.cleanupProgress.total_files) || 0} ${vm.$t('status:files_matched', 'Matching files')}`"
					:tooltip="`${Number(vm.cleanupProgress.files_scanned) || 0} / ${Number(vm.cleanupProgress.total_files) || 0}`"
				/>
			</div>
			<div class="face-match-status-stats">
				<span>{{ vm.$t('cleanup:label_mappings', 'Mappings') }}: {{ vm.cleanupProgress.mappings_count || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_persons_scanned', 'Persons scanned') }}: {{ vm.cleanupProgress.persons_scanned || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_persons_updated', 'Persons updated') }}: {{ vm.cleanupProgress.persons_updated || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_faces_reassigned', 'Faces reassigned') }}: {{ vm.cleanupProgress.faces_reassigned || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_files_scanned', 'Files scanned') }}: {{ vm.cleanupProgress.files_scanned || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_files_updated', 'Files updated') }}: {{ vm.cleanupProgress.files_updated || 0 }}</span>
				<span>{{ vm.$t('cleanup:label_metadata_faces_updated', 'Metadata faces updated') }}: {{ vm.cleanupProgress.metadata_faces_updated || 0 }}</span>
			</div>
			<div class="face-match-status-context">
				<span v-if="vm.cleanupProgress.current_name">{{ vm.$t('cleanup:label_current_name', 'Current name') }}: {{ vm.cleanupProgress.current_name }}</span>
				<span v-if="vm.cleanupProgress.current_path">{{ vm.$t('cleanup:label_current_path', 'Current file') }}: {{ vm.cleanupProgress.current_path }}</span>
				<span v-if="vm.cleanupProgress.warning">{{ vm.$t(vm.cleanupProgress.warning, 'Warning') }}</span>
			</div>
		</div>
	</section>
</template>

<script>
import RatioProgress from '../components/RatioProgress.vue';

export default {
	name: 'CleanupView',
	components: {
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
