<template>
	<section class="panel">
		<div class="panel-head">
			<h1>{{ vm.$t('checks:title', 'Checks') }}</h1>
			<p>{{ vm.$t('checks:desc', 'Area for validation and review functions.') }}</p>
		</div>
		<div class="checks-actions">
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
			<div class="face-match-action-buttons">
				<v-button @click="vm.startChecksReview" :disabled="vm.checksLoading" style="width: 160px;">
					{{ vm.checksLoading ? vm.$t('checks:button_loading', 'Loading...') : vm.$t('checks:button_start', 'Start') }}
				</v-button>
				<v-button v-if="vm.hasNextChecksItem" @click="vm.nextChecksReview" :disabled="vm.checksLoading" style="width: 160px;">
					{{ vm.$t('checks:button_next', 'Next') }}
				</v-button>
			</div>
		</div>
		<div class="face-match-status-card face-match-status-card-action">
			<div class="face-match-status-head">
				<div class="face-match-status-title">{{ vm.$t('checks:status_title', 'Status') }}</div>
			</div>
			<div class="face-match-status-message">{{ vm.checksStatusMessage }}</div>
			<div v-if="vm.currentChecksItem" class="face-match-status-stats">
				<div><strong>{{ vm.$t('checks:label_type', 'Check:') }}</strong> {{ vm.getChecksTypeLabel(vm.selectedChecksType) }}</div>
				<div><strong>{{ vm.$t('checks:label_file', 'File:') }}</strong> {{ vm.currentChecksItem.image_name }}</div>
				<div><strong>{{ vm.$t('checks:label_face_name', 'Face:') }}</strong> {{ vm.currentChecksItem.face_name || vm.$t('face_match:unknown_name', '(unnamed)') }}</div>
				<div><strong>{{ vm.$t('checks:label_pair', 'Pair:') }}</strong> {{ vm.getChecksPairLabel(vm.currentChecksItem) }}</div>
				<div><strong>{{ vm.$t('checks:label_index', 'Entry:') }}</strong> {{ vm.checksCurrentIndex + 1 }} / {{ vm.checksEntries.length }}</div>
			</div>
		</div>
		<div v-if="vm.currentChecksItem" class="face-match-split checks-split">
			<div class="face-match-col">
				<h2>{{ vm.getChecksLeftTitle(vm.currentChecksItem) }}</h2>
				<div v-if="vm.showChecksFaceName(vm.currentChecksItem)" class="checks-face-name">
					{{ vm.getChecksDisplayName(vm.currentChecksItem.left_name) }}
				</div>
				<div v-if="vm.getChecksImageUrl(vm.currentChecksItem)" class="face-match-thumbnail-wrap">
					<div class="face-match-preview">
						<img
							:src="vm.getChecksImageUrl(vm.currentChecksItem)"
							:alt="vm.$t('checks:image_alt', 'Check preview')"
							class="face-match-thumbnail"
						/>
						<div
							v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.currentChecksItem.left_face)"
							:key="`checks-left-mask-${index}`"
							class="face-match-mask"
							:style="maskStyle"
						></div>
						<div
							v-for="(face, index) in vm.currentChecksItem.left_reference_faces || []"
							:key="`checks-left-reference-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksReferenceBoxStyle(face)"
						></div>
						<div
							v-for="(face, index) in vm.currentChecksItem.left_alert_faces || []"
							:key="`checks-left-alert-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(face, vm.currentChecksItem.left_face)"
						></div>
						<div
							v-if="vm.getFaceMatchBoxStyle(vm.currentChecksItem.left_face)"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(vm.currentChecksItem.left_face, vm.currentChecksItem.left_face, vm.currentChecksItem.left_state || 'alert')"
						></div>
					</div>
				</div>
				<div v-else class="face-match-empty">{{ vm.$t('checks:empty_image', 'No preview available.') }}</div>
			</div>
			<div class="face-match-col">
				<h2>{{ vm.getChecksRightTitle(vm.currentChecksItem) }}</h2>
				<div v-if="vm.showChecksFaceName(vm.currentChecksItem)" class="checks-face-name">
					{{ vm.getChecksDisplayName(vm.currentChecksItem.right_name) }}
				</div>
				<div v-if="vm.getChecksImageUrl(vm.currentChecksItem)" class="face-match-thumbnail-wrap">
					<div class="face-match-preview">
						<img
							:src="vm.getChecksImageUrl(vm.currentChecksItem)"
							:alt="vm.$t('checks:image_alt', 'Check preview')"
							class="face-match-thumbnail"
						/>
						<div
							v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.currentChecksItem.right_face)"
							:key="`checks-right-mask-${index}`"
							class="face-match-mask"
							:style="maskStyle"
						></div>
						<div
							v-for="(face, index) in vm.currentChecksItem.right_reference_faces || []"
							:key="`checks-right-reference-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksReferenceBoxStyle(face)"
						></div>
						<div
							v-for="(face, index) in vm.currentChecksItem.right_alert_faces || []"
							:key="`checks-right-alert-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(face, vm.currentChecksItem.right_face)"
						></div>
						<div
							v-if="vm.getFaceMatchBoxStyle(vm.currentChecksItem.right_face)"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(vm.currentChecksItem.right_face, vm.currentChecksItem.right_face, vm.currentChecksItem.right_state || 'alert')"
						></div>
					</div>
				</div>
				<div v-else class="face-match-empty">{{ vm.$t('checks:empty_image', 'No preview available.') }}</div>
			</div>
		</div>
		<div v-else class="config-placeholder">
			<div class="config-placeholder-title">{{ vm.$t('checks:placeholder_title', 'Checks will be added here.') }}</div>
		</div>
	</section>
</template>

<script>
export default {
	name: 'ChecksView',
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
