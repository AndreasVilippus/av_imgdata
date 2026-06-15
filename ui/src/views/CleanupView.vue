<template>
	<div class="cleanup-view">
		<section class="panel">
			<div class="panel-head">
				<div class="sm-section-title">{{ vm.$avt('cleanup:title', 'Cleanup') }}</div>
				<p>{{ vm.$avt('cleanup:desc', 'Area for cleanup and normalization functions.') }}</p>
			</div>
			<div class="checks-actions panel-content-start">
				<div class="checks-actions-row checks-actions-row-selects">
					<select v-model="vm.selectedCleanupAction" class="face-match-select" :disabled="vm.cleanupLoading">
						<option value="normalize_names">{{ vm.$avt('cleanup:action_normalize_names', 'Adjust names by reference list') }}</option>
						<option value="standardize_face_frames">{{ vm.$avt('cleanup:action_standardize_face_frames', 'Standardize face frames') }}</option>
						<option value="recognition_build_profiles">{{ vm.$avt('cleanup:action_recognition_build_profiles', 'Build recognition profiles') }}</option>
						<option value="recognition_check_reference_outliers">{{ vm.$avt('cleanup:action_recognition_check_outliers', 'Review recognition reference faces') }}</option>
						<option value="recognition_analyze_unknown_faces">{{ vm.$avt('cleanup:action_recognition_unknown_faces', 'Find persons for unknown faces') }}</option>
					</select>
				</div>
				<div v-if="vm.selectedCleanupAction === 'normalize_names'" class="checks-actions-row checks-actions-row-switches">
					<label v-for="target in ['ACD', 'MICROSOFT', 'MWG_REGIONS']" :key="`cleanup-target-${target}`" class="face-match-switch">
						<input v-model="vm.cleanupTargets[target]" type="checkbox" :disabled="vm.cleanupLoading" />
						<span class="face-match-switch-slider"></span>
						<span class="face-match-switch-label">{{ vm.getCleanupTargetLabel(target) }}</span>
					</label>
				</div>
				<div class="checks-actions-row checks-actions-row-buttons">
					<div class="face-match-action-buttons">
						<v-button @click="vm.handleCleanupAction" :disabled="!vm.cleanupCanStart" style="width: 160px;">
							{{ vm.cleanupPrimaryButtonLabel }}
						</v-button>
						<v-button
							v-if="vm.selectedCleanupAction === 'standardize_face_frames' && vm.faceFrameSelectedCount > 0"
							@click="vm.applySelectedFaceFrames"
							:disabled="vm.cleanupLoading || vm.faceFrameApplyLoading"
							style="width: 160px;"
						>
							{{ vm.$avt('cleanup:button_apply_selected', 'Apply selected') }}
						</v-button>
					</div>
				</div>
			</div>
			<FaceFrameStandardizationOptions v-if="vm.selectedCleanupAction === 'standardize_face_frames'" :vm="vm" />
			<RecognitionOptions v-if="vm.isRecognitionCleanupAction" :vm="vm" />
			<div class="face-match-status-card face-match-status-card-action">
				<div class="face-match-status-head">
					<div class="sm-section-title">{{ vm.$avt('cleanup:status_title', 'Status') }}</div>
					<div v-if="vm.cleanupLoading" class="face-match-status-running">
						<span class="sm-loader"></span>
						{{ vm.$avt('cleanup:card_running', 'Running') }}
					</div>
				</div>
				<div class="face-match-status-message">{{ vm.getCleanupStatusHeadline() }}</div>
				<div v-if="Number(vm.getCleanupStatusProgress().total) > 0" class="sm-status-progress">
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
				<div v-if="vm.selectedCleanupAction === 'normalize_names'" class="face-match-status-stats">
					<span v-for="counter in vm.getCleanupStatusCounters()" :key="`cleanup-counter-${counter.key}`">{{ vm.formatCleanupStatusCounter(counter) }}</span>
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
		<FaceFrameFindingsTable v-if="vm.selectedCleanupAction === 'standardize_face_frames'" :vm="vm" />
		<RecognitionFindingsReview v-if="vm.isRecognitionReviewAction" :vm="vm" />
	</div>
</template>

<script>
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';
import FaceFrameStandardizationOptions from '../components/cleanup/FaceFrameStandardizationOptions.vue';
import FaceFrameFindingsTable from '../components/cleanup/FaceFrameFindingsTable.vue';
import RecognitionOptions from '../components/cleanup/RecognitionOptions.vue';
import RecognitionFindingsReview from '../components/cleanup/RecognitionFindingsReview.vue';

export default {
	name: 'CleanupView',
	components: {
		ProgressOverviewCard,
		FaceFrameStandardizationOptions,
		FaceFrameFindingsTable,
		RecognitionOptions,
		RecognitionFindingsReview,
	},
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
