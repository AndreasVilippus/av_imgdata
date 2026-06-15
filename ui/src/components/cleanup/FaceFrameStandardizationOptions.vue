<template>
	<section class="config-card cleanup-options-card">
		<div class="sm-section-title">{{ vm.$avt('cleanup:face_frames_options', 'Preview options') }}</div>
		<div class="config-card-desc">
			{{ vm.$avt('cleanup:face_frames_preview_only', 'The scan only creates a preview. Selected metadata frames can then be applied; Photos frames remain locked.') }}
		</div>

		<div class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:face_frames_operation_title', 'Processing mode') }}</div>
			<div class="config-card-desc">{{ vm.$avt('cleanup:face_frames_operation_hint', 'Review findings immediately, save them for later, or process the saved findings list.') }}</div>
			<label class="sm-form-field cleanup-wide-field">
				<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_operation_mode', 'Action') }}</span>
				<select
					:value="vm.faceFrameOptions.operation_mode"
					class="sm-form-select"
					:disabled="vm.cleanupLoading"
					@change="vm.updateFaceFrameOption('operation_mode', $event.target.value)"
				>
					<option value="immediate">{{ vm.$avt('cleanup:face_frames_operation_immediate', 'Run scan and review immediately') }}</option>
					<option value="save_only">{{ vm.$avt('cleanup:face_frames_operation_save_only', 'Run scan and save findings only') }}</option>
					<option value="findings">{{ vm.$avt('cleanup:face_frames_operation_findings', 'Process saved findings list') }}</option>
				</select>
			</label>
		</div>

		<div v-if="vm.faceFrameOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:face_frames_selection_title', 'Decision mode') }}</div>
			<div class="config-card-desc">{{ vm.$avt('cleanup:face_frames_selection_hint', 'Choose whether every finding requires review or safe findings are selected automatically.') }}</div>
			<label class="sm-form-field cleanup-wide-field">
				<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_selection_mode', 'Finding selection') }}</span>
				<select
					:value="vm.faceFrameOptions.selection_mode"
					class="sm-form-select"
					:disabled="vm.cleanupLoading"
					@change="vm.updateFaceFrameOption('selection_mode', $event.target.value)"
				>
					<option value="review_all">{{ vm.$avt('cleanup:face_frames_selection_review_all', 'Decide every finding manually') }}</option>
					<option value="safe_matches">{{ vm.$avt('cleanup:face_frames_selection_safe', 'Apply safe metadata findings automatically') }}</option>
				</select>
			</label>
		</div>

		<div v-if="vm.faceFrameOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:face_frames_sources_title', 'Frame sources') }}</div>
			<div class="config-card-desc">{{ vm.$avt('cleanup:face_frames_sources_hint', 'Only selected source formats are compared with InsightFace detections.') }}</div>
			<div class="cleanup-source-grid">
				<label v-for="source in sourceOptions" :key="source.key" class="face-match-switch">
					<input
						:checked="vm.faceFrameOptions.sources[source.key]"
						type="checkbox"
						:disabled="vm.cleanupLoading"
						@change="vm.updateFaceFrameSource(source.key, $event.target.checked)"
					/>
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ source.label }}</span>
				</label>
			</div>
		</div>

		<div v-if="vm.faceFrameOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:face_frames_standardization_title', 'Standardization') }}</div>
			<div class="sm-form-grid">
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_strategy', 'Standardization strategy') }}</span>
					<select :value="vm.faceFrameOptions.strategy" class="sm-form-select" :disabled="vm.cleanupLoading" @change="vm.updateFaceFrameOption('strategy', $event.target.value)">
						<option value="insightface_exact">{{ vm.$avt('cleanup:strategy_insightface_exact', 'Use exact InsightFace frame') }}</option>
						<option value="insightface_scaled">{{ vm.$avt('cleanup:strategy_insightface_scaled', 'Scale InsightFace frame by profile') }}</option>
						<option value="keep_existing_center_scale_size">{{ vm.$avt('cleanup:strategy_keep_center', 'Keep current center, use detected size') }}</option>
						<option value="correct_only_if_deviation">{{ vm.$avt('cleanup:strategy_only_deviation', 'Correct only clear deviations') }}</option>
						<option value="average_sources">{{ vm.$avt('cleanup:strategy_average', 'Average current and detected frame') }}</option>
						<option value="largest_plausible">{{ vm.$avt('cleanup:strategy_largest', 'Use largest plausible frame') }}</option>
					</select>
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_profile', 'Target-frame profile') }}</span>
					<select :value="vm.faceFrameOptions.profile" class="sm-form-select" :disabled="vm.cleanupLoading" @change="vm.updateFaceFrameOption('profile', $event.target.value)">
						<option value="tight">{{ vm.$avt('cleanup:face_frames_profile_tight', 'Tight') }}</option>
						<option value="normal">{{ vm.$avt('cleanup:face_frames_profile_normal', 'Normal') }}</option>
						<option value="photos_compatible">{{ vm.$avt('cleanup:face_frames_profile_photos', 'Photos compatible') }}</option>
						<option value="acdsee_compatible">{{ vm.$avt('cleanup:face_frames_profile_acdsee', 'ACDSee compatible') }}</option>
					</select>
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_changed_days', 'Changed within days') }}</span>
					<input :value="vm.faceFrameOptions.changed_since_days" type="number" min="0" step="1" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('changed_since_days', Number($event.target.value))" />
					<span class="sm-form-hint">{{ vm.$avt('cleanup:face_frames_changed_days_hint', '0 checks all images.') }}</span>
				</label>
			</div>
		</div>

		<div v-if="vm.faceFrameOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:face_frames_detection_title', 'InsightFace detection') }}</div>
			<div class="config-card-desc">{{ vm.$avt('cleanup:face_frames_detection_hint', 'Detection parameters affect comparison candidates, not existing source frames.') }}</div>
			<div class="sm-form-grid">
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_det_threshold', 'Minimum detection confidence') }}</span>
					<input :value="vm.faceFrameOptions.det_thresh" type="number" min="0" max="1" step="0.05" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('det_thresh', Number($event.target.value))" />
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_det_width', 'Detection width') }}</span>
					<input :value="vm.faceFrameOptions.det_size[0]" type="number" min="64" step="32" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameDetSize(0, Number($event.target.value))" />
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_det_height', 'Detection height') }}</span>
					<input :value="vm.faceFrameOptions.det_size[1]" type="number" min="64" step="32" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameDetSize(1, Number($event.target.value))" />
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_max_faces', 'Maximum faces per image') }}</span>
					<input :value="vm.faceFrameOptions.max_num" type="number" min="0" step="1" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('max_num', Number($event.target.value))" />
					<span class="sm-form-hint">{{ vm.$avt('cleanup:face_frames_max_faces_hint', '0 means unlimited.') }}</span>
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_min_width', 'Minimum face-width ratio') }}</span>
					<input :value="vm.faceFrameOptions.min_width_ratio" type="number" min="0" max="1" step="0.001" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('min_width_ratio', Number($event.target.value))" />
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_min_height', 'Minimum face-height ratio') }}</span>
					<input :value="vm.faceFrameOptions.min_height_ratio" type="number" min="0" max="1" step="0.001" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('min_height_ratio', Number($event.target.value))" />
				</label>
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:face_frames_min_area', 'Minimum face-area ratio') }}</span>
					<input :value="vm.faceFrameOptions.min_area_ratio" type="number" min="0" max="1" step="0.001" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateFaceFrameOption('min_area_ratio', Number($event.target.value))" />
				</label>
			</div>
		</div>
	</section>
</template>

<script>
export default {
	name: 'FaceFrameStandardizationOptions',
	props: { vm: { type: Object, required: true } },
	computed: {
		sourceOptions() {
			return [
				{ key: 'photos', label: this.vm.$avt('cleanup:face_frames_source_photos', 'Photos frames') },
				{ key: 'acd', label: this.vm.$avt('cleanup:face_frames_source_acd', 'ACDSee tags') },
				{ key: 'microsoft', label: this.vm.$avt('cleanup:face_frames_source_microsoft', 'Microsoft people tags') },
				{ key: 'mwg_regions', label: this.vm.$avt('cleanup:face_frames_source_mwg', 'MWG regions') },
			];
		},
	},
};
</script>
