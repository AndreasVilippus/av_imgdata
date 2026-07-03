<template>
	<section class="config-card cleanup-options-card">
		<div class="sm-section-title">{{ vm.$avt('cleanup:recognition_options', 'Recognition options') }}</div>
		<div class="config-card-desc">
			{{ vm.$avt('cleanup:recognition_options_hint', 'Person profiles are built from existing Photos persons. InsightFace itself is not trained.') }}
		</div>

		<div v-if="!isProfileBuild" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:recognition_operation_title', 'Processing mode') }}</div>
			<div class="config-card-desc">{{ vm.$avt('cleanup:recognition_operation_hint', 'Review findings immediately, save them for later, or process the saved findings list.') }}</div>
			<label class="sm-form-field cleanup-wide-field">
				<span class="sm-form-label">{{ vm.$avt('cleanup:recognition_operation_mode', 'Action') }}</span>
				<select :value="vm.recognitionOptions.operation_mode" class="sm-form-select" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('operation_mode', $event.target.value)">
					<option value="immediate">{{ vm.$avt('cleanup:recognition_operation_immediate', 'Run scan and review immediately') }}</option>
					<option value="save_only">{{ vm.$avt('cleanup:recognition_operation_save_only', 'Run scan and save findings only') }}</option>
					<option value="findings">{{ vm.$avt('cleanup:recognition_operation_findings', 'Process saved findings list') }}</option>
				</select>
			</label>
		</div>

		<div v-if="vm.recognitionOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:recognition_scope_title', 'Photos persons') }}</div>
			<div class="cleanup-source-grid">
				<label class="face-match-switch">
					<input :checked="vm.recognitionOptions.include_hidden_persons" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('include_hidden_persons', $event.target.checked)" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_include_hidden', 'Include hidden persons') }}</span>
				</label>
				<label v-if="isProfileBuild" class="face-match-switch">
					<input :checked="vm.recognitionOptions.rebuild_all" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('rebuild_all', $event.target.checked)" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_rebuild_all', 'Rebuild all profiles') }}</span>
				</label>
				<label v-if="isProfileBuild" class="face-match-switch">
					<input :checked="vm.recognitionOptions.exclude_outliers" type="checkbox" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('exclude_outliers', $event.target.checked)" />
					<span class="face-match-switch-slider"></span>
					<span class="face-match-switch-label">{{ vm.$avt('cleanup:recognition_exclude_outliers', 'Exclude confirmed outliers') }}</span>
				</label>
			</div>
			<div class="sm-form-grid">
				<label class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:recognition_min_faces', 'Minimum reference faces per person') }}</span>
					<input :value="vm.recognitionOptions.min_faces_per_person" type="number" min="2" step="1" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateRecognitionOption('min_faces_per_person', Number($event.target.value))" />
				</label>
				<label v-if="isSuggestionScan" class="sm-form-field">
					<span class="sm-form-label">{{ vm.$avt('cleanup:recognition_changed_days', 'Changed within days') }}</span>
					<input :value="vm.recognitionOptions.changed_since_days" type="number" min="0" step="1" class="sm-form-input sm-form-number-input" :disabled="vm.cleanupLoading" @input="vm.updateRecognitionOption('changed_since_days', Number($event.target.value))" />
					<span class="sm-form-hint">{{ vm.$avt('cleanup:recognition_changed_days_hint', '0 checks all unknown Photos faces.') }}</span>
				</label>
			</div>
		</div>

		<div v-if="!isProfileBuild && vm.recognitionOptions.operation_mode !== 'findings'" class="cleanup-options-section">
			<div class="config-field-label">{{ vm.$avt('cleanup:recognition_decision_title', 'Decision mode') }}</div>
			<label class="sm-form-field cleanup-wide-field">
				<span class="sm-form-label">{{ vm.$avt('cleanup:recognition_selection_mode', 'Finding selection') }}</span>
				<select :value="vm.recognitionOptions.selection_mode" class="sm-form-select" :disabled="vm.cleanupLoading" @change="vm.updateRecognitionOption('selection_mode', $event.target.value)">
					<option value="review_all">{{ vm.$avt('cleanup:recognition_selection_review_all', 'Decide every finding manually') }}</option>
					<option :value="isSuggestionScan ? 'safe_only' : 'exclude_confirmed'">{{ automaticDecisionLabel }}</option>
				</select>
			</label>
		</div>

	</section>
</template>

<script>
export default {
	name: 'RecognitionOptions',
	props: { vm: { type: Object, required: true } },
	computed: {
			isProfileBuild() {
				return this.vm.selectedRecognitionAction === 'recognition_build_profiles';
			},
			isOutlierScan() {
				return this.vm.selectedRecognitionAction === 'recognition_check_reference_outliers';
			},
			isSuggestionScan() {
				return [
					'recognition_analyze_unknown_faces',
					'recognition_check_person_assignments',
				].includes(this.vm.selectedRecognitionAction);
			},
		automaticDecisionLabel() {
			return this.isSuggestionScan
				? this.vm.$avt('cleanup:recognition_selection_safe', 'Select safe suggestions automatically')
				: this.vm.$avt('cleanup:recognition_selection_exclude', 'Exclude confirmed outliers automatically');
		},
	},
};
</script>
