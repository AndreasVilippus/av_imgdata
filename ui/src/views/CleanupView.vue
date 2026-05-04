<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$avt('cleanup:title', 'Cleanup') }}</div>
			<p>{{ vm.$avt('cleanup:desc', 'Area for cleanup and normalization functions.') }}</p>
		</div>
		<div class="checks-actions panel-content-start">
			<div class="checks-actions-row checks-actions-row-selects">
				<select v-model="vm.selectedCleanupAction" class="face-match-select" :disabled="vm.cleanupLoading">
					<option value="normalize_names">{{ vm.$avt('cleanup:action_normalize_names', 'Adjust names by reference list') }}</option>
				</select>
			</div>
			<div class="checks-actions-row checks-actions-row-switches">
				<label v-for="target in ['ACD', 'MICROSOFT', 'MWG_REGIONS']" :key="`cleanup-target-${target}`" class="face-match-switch">
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
				<div class="sm-section-title">{{ vm.$avt('cleanup:status_title', 'Status') }}</div>
				<div v-if="vm.cleanupLoading" class="face-match-status-running">
					<span class="sm-loader"></span>
					{{ vm.$avt('cleanup:card_running', 'Running') }}
				</div>
			</div>
			<div class="face-match-status-message">{{ vm.getCleanupStatusHeadline() }}</div>
			<div v-if="Number(vm.cleanupProgress.persons_total) > 0" class="sm-status-progress">
				<ProgressOverviewCard
					:title="vm.$avt('cleanup:label_persons', 'Persons')"
					:count="Number(vm.cleanupProgress.persons_total) || 0"
					:current="Number(vm.cleanupProgress.persons_scanned) || 0"
					:total="Number(vm.cleanupProgress.persons_total) || 0"
					:primary-label="vm.$avt('cleanup:label_scanned', 'scanned')"
					:secondary-label="vm.$avt('cleanup:label_persons_remaining', 'remaining')"
					:status-text="vm.getCleanupProgressStatus('persons')"
				/>
			</div>
			<div v-if="Number(vm.cleanupProgress.total_files) > 0" class="sm-status-progress">
				<ProgressOverviewCard
					:title="vm.$avt('cleanup:label_images', 'Images')"
					:count="Number(vm.cleanupProgress.total_files) || 0"
					:current="Number(vm.cleanupProgress.files_scanned) || 0"
					:total="Number(vm.cleanupProgress.total_files) || 0"
					:primary-label="vm.$avt('cleanup:label_scanned', 'scanned')"
					:secondary-label="vm.$avt('cleanup:label_files_remaining', 'remaining')"
					:status-text="vm.getCleanupProgressStatus('files')"
				/>
			</div>
			<div class="face-match-status-stats">
				<span>{{ vm.$avt('cleanup:label_mappings', 'Mappings') }}: {{ vm.cleanupProgress.mappings_count || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_persons_scanned', 'Persons scanned') }}: {{ vm.cleanupProgress.persons_scanned || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_persons_updated', 'Persons updated') }}: {{ vm.cleanupProgress.persons_updated || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_faces_reassigned', 'Faces reassigned') }}: {{ vm.cleanupProgress.faces_reassigned || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_files_scanned', 'Files scanned') }}: {{ vm.cleanupProgress.files_scanned || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_files_updated', 'Files updated') }}: {{ vm.cleanupProgress.files_updated || 0 }}</span>
				<span>{{ vm.$avt('cleanup:label_metadata_faces_updated', 'Metadata faces updated') }}: {{ vm.cleanupProgress.metadata_faces_updated || 0 }}</span>
			</div>
			<div class="face-match-status-context">
				<span v-if="vm.cleanupProgress.current_name">{{ vm.$avt('cleanup:label_current_name', 'Current name') }}: {{ vm.cleanupProgress.current_name }}</span>
				<span v-if="vm.cleanupProgress.current_path">{{ vm.$avt('cleanup:label_current_path', 'Current file') }}: {{ vm.cleanupProgress.current_path }}</span>
				<span v-if="vm.cleanupProgress.warning">{{ vm.$avt(vm.cleanupProgress.warning, 'Warning') }}</span>
			</div>
		</div>
	</section>
</template>

<script>
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';

export default {
	name: 'CleanupView',
	components: {
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
