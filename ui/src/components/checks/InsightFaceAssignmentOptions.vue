<template>
	<div class="checks-insightface-options">
		<label
			v-if="vm.selectedChecksAction === 'scan'"
			class="face-match-switch"
			:title="vm.$avt('checks:hint_insightface_include_hidden_persons', 'Hidden Photos persons are included when building assignment candidates.')"
		>
			<input :checked="vm.recognitionOptions.include_hidden_persons" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('include_hidden_persons', $event.target.checked)" />
			<span class="face-match-switch-slider"></span>
			<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_include_hidden', 'Include hidden persons') }}</span>
		</label>
		<label
			v-if="vm.selectedChecksAction === 'scan'"
			class="face-match-switch"
			:title="vm.$avt('checks:hint_insightface_safe_assignment', 'Safe assignment suggestions are preselected automatically; uncertain findings remain for manual review.')"
		>
			<input :checked="vm.checksInsightFaceAutoSelectSafe" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateChecksInsightFaceAutoSelectSafe($event.target.checked)" />
			<span class="face-match-switch-slider"></span>
			<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_selection_safe', 'Select safe suggestions automatically') }}</span>
		</label>
		<label
			v-if="vm.selectedChecksAction === 'scan'"
			class="checks-number-field"
			:title="vm.$avt('checks:hint_changed_since_days', 'Only images whose file or sidecar changed within the selected number of days are checked. 0 checks all images.')"
		>
			<span class="face-match-switch-label">{{ vm.$avt('checks:label_changed_since_days', 'Changed in days') }}</span>
			<input :value="vm.checksChangedSinceDays" type="number" min="0" step="1" class="checks-number-input" :disabled="vm.cleanupLoading" @input="vm.updateChecksChangedSinceDays($event.target.value)" />
		</label>
		<label
			v-if="vm.selectedChecksAction === 'scan'"
			class="checks-number-field checks-number-field-wide"
			:title="vm.$avt('cleanup:recognition_min_faces', 'Minimum reference faces per person')"
		>
			<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_min_faces', 'Minimum reference faces per person') }}</span>
			<input :value="vm.recognitionOptions.min_faces_per_person" type="number" min="2" step="1" class="checks-number-input" :disabled="vm.cleanupLoading" @input="vm.updateRecognitionOption('min_faces_per_person', Number($event.target.value))" />
		</label>
	</div>
</template>

<script>
export default {
	name: 'InsightFaceAssignmentOptions',
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>

<style>
.checks-insightface-options {
	display: contents;
}

.checks-insightface-options .checks-number-field-wide {
	margin-left: 0;
}
</style>
