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
			<input :checked="vm.checksInsightFaceAutoSelectSafe" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.checksInsightFaceAutoSelectSafe = $event.target.checked" />
			<span class="face-match-switch-slider"></span>
			<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_selection_safe', 'Select safe suggestions automatically') }}</span>
		</label>
		<label
			v-if="vm.selectedChecksAction === 'scan'"
			class="checks-number-field"
			:title="vm.$avt('checks:hint_changed_since_days', 'Only images whose file or sidecar changed within the selected number of days are checked. 0 checks all images.')"
		>
			<span class="face-match-switch-label">{{ vm.$avt('checks:label_changed_since_days', 'Changed in days') }}</span>
			<input v-model.number="vm.checksChangedSinceDays" type="number" min="0" step="1" class="checks-number-input" :disabled="vm.cleanupLoading" />
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
</style>
