<template>
	<div class="face-match-status-card">
		<div class="sm-section-title">{{ vm.$avt('cleanup:face_frames_options', 'Preview options') }}</div>
		<div class="checks-actions-row checks-actions-row-switches">
			<label class="face-match-switch">
				<input :checked="vm.faceFrameOptions.include_metadata" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateFaceFrameOption('include_metadata', $event.target.checked)" />
				<span class="face-match-switch-slider"></span>
				<span class="face-match-switch-label">{{ vm.$avt('cleanup:face_frames_source_metadata', 'Metadata frames') }}</span>
			</label>
			<label class="face-match-switch">
				<input :checked="vm.faceFrameOptions.include_photos" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateFaceFrameOption('include_photos', $event.target.checked)" />
				<span class="face-match-switch-slider"></span>
				<span class="face-match-switch-label">{{ vm.$avt('cleanup:face_frames_source_photos', 'Photos frames') }}</span>
			</label>
		</div>
		<div class="checks-actions-row checks-actions-row-selects">
			<select :value="vm.faceFrameOptions.profile" class="face-match-select" :disabled="vm.cleanupLoading" @change="vm.updateFaceFrameOption('profile', $event.target.value)">
				<option value="tight">tight</option>
				<option value="normal">normal</option>
				<option value="photos_compatible">photos_compatible</option>
				<option value="acdsee_compatible">acdsee_compatible</option>
			</select>
			<input :value="vm.faceFrameOptions.changed_since_days" type="number" min="0" :disabled="vm.cleanupLoading" placeholder="Days" @input="vm.updateFaceFrameOption('changed_since_days', Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.det_thresh" type="number" min="0" max="1" step="0.05" :disabled="vm.cleanupLoading" placeholder="det_thresh" @input="vm.updateFaceFrameOption('det_thresh', Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.det_size[0]" type="number" min="64" step="32" :disabled="vm.cleanupLoading" placeholder="det width" @input="vm.updateFaceFrameDetSize(0, Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.det_size[1]" type="number" min="64" step="32" :disabled="vm.cleanupLoading" placeholder="det height" @input="vm.updateFaceFrameDetSize(1, Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.max_num" type="number" min="0" :disabled="vm.cleanupLoading" placeholder="max faces" @input="vm.updateFaceFrameOption('max_num', Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.min_width_ratio" type="number" min="0" max="1" step="0.001" :disabled="vm.cleanupLoading" placeholder="min width ratio" @input="vm.updateFaceFrameOption('min_width_ratio', Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.min_height_ratio" type="number" min="0" max="1" step="0.001" :disabled="vm.cleanupLoading" placeholder="min height ratio" @input="vm.updateFaceFrameOption('min_height_ratio', Number($event.target.value))" />
			<input :value="vm.faceFrameOptions.min_area_ratio" type="number" min="0" max="1" step="0.001" :disabled="vm.cleanupLoading" placeholder="min area ratio" @input="vm.updateFaceFrameOption('min_area_ratio', Number($event.target.value))" />
		</div>
		<p>{{ vm.$avt('cleanup:face_frames_preview_only', 'Preview only. No metadata or Photos frames are written.') }}</p>
	</div>
</template>

<script>
export default {
	name: 'FaceFrameStandardizationOptions',
	props: { vm: { type: Object, required: true } },
};
</script>
