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
			<label
				v-if="vm.selectedChecksAction === 'scan'"
				class="face-match-switch"
				:title="vm.$t('checks:hint_save_only', 'Findings are only stored in the findings list and not shown directly during the scan.')"
			>
				<input v-model="vm.checksSaveOnly" type="checkbox" :disabled="vm.checksLoading" />
				<span class="face-match-switch-slider"></span>
				<span class="face-match-switch-label">{{ vm.$t('checks:switch_save_only', 'Save findings only') }}</span>
			</label>
			<label
				v-if="vm.selectedChecksType === 'name_conflicts'"
				class="face-match-switch"
				:title="vm.$t('checks:hint_auto_apply_suggested_names', 'Suggested target names from stored name mappings are applied automatically.')"
			>
				<input v-model="vm.checksAutoApplySuggestedNames" type="checkbox" :disabled="vm.checksLoading" />
				<span class="face-match-switch-slider"></span>
				<span class="face-match-switch-label">{{ vm.$t('checks:switch_auto_apply_suggested_names', 'Apply suggested names automatically') }}</span>
			</label>
			<div class="face-match-action-buttons">
				<v-button @click="vm.startChecksReview" style="width: 160px;">
					{{ vm.checksPrimaryButtonLabel }}
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
			<div v-if="vm.selectedChecksAction === 'scan'" class="face-match-status-stats">
				<div><strong>{{ vm.$t('checks:label_source_mode', 'Mode:') }}</strong> {{ vm.getChecksSourceModeLabel() }}</div>
				<div><strong>{{ vm.$t('checks:label_scanned', 'Scanned:') }}</strong> {{ vm.checksProgress.files_scanned || 0 }} / {{ vm.checksProgress.total_files || 0 }}</div>
				<div><strong>{{ vm.$t('checks:label_findings_count', 'Findings:') }}</strong> {{ vm.checksProgress.findings_count || 0 }}</div>
			</div>
			<div v-if="vm.checksCurrentItem" class="face-match-status-stats">
				<div><strong>{{ vm.$t('checks:label_type', 'Check:') }}</strong> {{ vm.getChecksTypeLabel(vm.selectedChecksType) }}</div>
				<div><strong>{{ vm.$t('checks:label_file', 'File:') }}</strong> {{ vm.checksCurrentItem.image_name }}</div>
				<div><strong>{{ vm.$t('checks:label_face_name', 'Face:') }}</strong> {{ vm.checksCurrentItem.face_name || vm.$t('face_match:unknown_name', '(unnamed)') }}</div>
				<div><strong>{{ vm.$t('checks:label_pair', 'Pair:') }}</strong> {{ vm.getChecksPairLabel(vm.checksCurrentItem) }}</div>
				<div v-if="vm.selectedChecksAction !== 'scan'"><strong>{{ vm.$t('checks:label_index', 'Entry:') }}</strong> {{ vm.checksCurrentIndex + 1 }} / {{ vm.checksEntries.length }}</div>
				<div v-else><strong>{{ vm.$t('checks:label_findings_count', 'Findings:') }}</strong> {{ vm.checksProgress.findings_count || 0 }}</div>
			</div>
		</div>
		<div v-if="vm.checksCurrentItem" class="face-match-split checks-split">
			<div v-if="vm.isChecksNameConflict(vm.checksCurrentItem)" class="checks-replace-actions">
				<button
					v-if="vm.canReplaceChecksFaceName(vm.checksCurrentItem, vm.checksCurrentItem.right_face, vm.checksCurrentItem.left_name)"
					type="button"
					class="face-match-icon-button checks-replace-button"
					:title="vm.getChecksReplaceRightTooltip(vm.checksCurrentItem)"
					:aria-label="vm.getChecksReplaceRightTooltip(vm.checksCurrentItem)"
					:disabled="vm.checksLoading"
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.right_face, vm.checksCurrentItem.left_name)"
				>
					<img :src="vm.getChecksReplaceRightIconUrl()" alt="" class="face-match-icon-image" />
				</button>
				<button
					v-if="vm.canReplaceChecksFaceName(vm.checksCurrentItem, vm.checksCurrentItem.left_face, vm.checksCurrentItem.right_name)"
					type="button"
					class="face-match-icon-button checks-replace-button"
					:title="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:aria-label="vm.getChecksReplaceLeftTooltip(vm.checksCurrentItem)"
					:disabled="vm.checksLoading"
					@click.prevent="vm.replaceChecksMetadataFaceName(vm.checksCurrentItem.left_face, vm.checksCurrentItem.right_name)"
				>
					<img :src="vm.getChecksReplaceLeftIconUrl()" alt="" class="face-match-icon-image" />
				</button>
			</div>
			<div class="face-match-col">
				<h2>{{ vm.getChecksLeftTitle(vm.checksCurrentItem) }}</h2>
				<div v-if="vm.showChecksFaceName(vm.checksCurrentItem)" class="checks-face-name">
					{{ vm.getChecksDisplayName(vm.checksCurrentItem.left_name) }}
				</div>
				<div v-if="vm.getChecksImageUrl(vm.checksCurrentItem)" class="face-match-thumbnail-wrap">
					<div class="face-match-preview">
						<button
							v-if="!vm.isChecksNameConflict(vm.checksCurrentItem) && vm.canDeleteChecksFace(vm.checksCurrentItem, vm.checksCurrentItem.left_face)"
							type="button"
							class="face-match-icon-button checks-delete-button checks-delete-button-right"
							:title="vm.$t('checks:tooltip_delete_face', 'Delete face from metadata')"
							:aria-label="vm.$t('checks:tooltip_delete_face', 'Delete face from metadata')"
							@click.prevent="vm.deleteChecksMetadataFace(vm.checksCurrentItem.left_face)"
						>
							<span class="face-match-icon-stack">
								<img :src="vm.getChecksDeleteFaceBaseIconUrl()" alt="" class="face-match-icon-image" />
								<img :src="vm.getChecksDeleteFaceOverlayIconUrl()" alt="" class="face-match-icon-overlay" />
							</span>
						</button>
						<img
							:src="vm.getChecksImageUrl(vm.checksCurrentItem)"
							:alt="vm.$t('checks:image_alt', 'Check preview')"
							class="face-match-thumbnail"
						/>
						<div
							v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.checksCurrentItem.left_face)"
							:key="`checks-left-mask-${index}`"
							class="face-match-mask"
							:style="maskStyle"
						></div>
						<div
							v-for="(face, index) in vm.checksCurrentItem.left_reference_faces || []"
							:key="`checks-left-reference-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksReferenceBoxStyle(face)"
						></div>
						<div
							v-for="(face, index) in vm.checksCurrentItem.left_alert_faces || []"
							:key="`checks-left-alert-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(face, vm.checksCurrentItem.left_face)"
						></div>
						<div
							v-if="vm.getFaceMatchBoxStyle(vm.checksCurrentItem.left_face)"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(vm.checksCurrentItem.left_face, vm.checksCurrentItem.left_face, vm.checksCurrentItem.left_state || 'alert')"
						></div>
					</div>
				</div>
				<div v-else class="face-match-empty">{{ vm.$t('checks:empty_image', 'No preview available.') }}</div>
			</div>
			<div class="face-match-col">
				<h2>{{ vm.getChecksRightTitle(vm.checksCurrentItem) }}</h2>
				<div v-if="vm.showChecksFaceName(vm.checksCurrentItem)" class="checks-face-name">
					{{ vm.getChecksDisplayName(vm.checksCurrentItem.right_name) }}
				</div>
				<div v-if="vm.getChecksImageUrl(vm.checksCurrentItem)" class="face-match-thumbnail-wrap">
					<div class="face-match-preview">
						<button
							v-if="!vm.isChecksNameConflict(vm.checksCurrentItem) && vm.canDeleteChecksFace(vm.checksCurrentItem, vm.checksCurrentItem.right_face)"
							type="button"
							class="face-match-icon-button checks-delete-button checks-delete-button-left"
							:title="vm.$t('checks:tooltip_delete_face', 'Delete face from metadata')"
							:aria-label="vm.$t('checks:tooltip_delete_face', 'Delete face from metadata')"
							@click.prevent="vm.deleteChecksMetadataFace(vm.checksCurrentItem.right_face)"
						>
							<span class="face-match-icon-stack">
								<img :src="vm.getChecksDeleteFaceBaseIconUrl()" alt="" class="face-match-icon-image" />
								<img :src="vm.getChecksDeleteFaceOverlayIconUrl()" alt="" class="face-match-icon-overlay" />
							</span>
						</button>
						<img
							:src="vm.getChecksImageUrl(vm.checksCurrentItem)"
							:alt="vm.$t('checks:image_alt', 'Check preview')"
							class="face-match-thumbnail"
						/>
						<div
							v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.checksCurrentItem.right_face)"
							:key="`checks-right-mask-${index}`"
							class="face-match-mask"
							:style="maskStyle"
						></div>
						<div
							v-for="(face, index) in vm.checksCurrentItem.right_reference_faces || []"
							:key="`checks-right-reference-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksReferenceBoxStyle(face)"
						></div>
						<div
							v-for="(face, index) in vm.checksCurrentItem.right_alert_faces || []"
							:key="`checks-right-alert-${index}`"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(face, vm.checksCurrentItem.right_face)"
						></div>
						<div
							v-if="vm.getFaceMatchBoxStyle(vm.checksCurrentItem.right_face)"
							class="face-match-bbox"
							:style="vm.getChecksAlertBoxStyle(vm.checksCurrentItem.right_face, vm.checksCurrentItem.right_face, vm.checksCurrentItem.right_state || 'alert')"
						></div>
					</div>
				</div>
				<div v-else class="face-match-empty">{{ vm.$t('checks:empty_image', 'No preview available.') }}</div>
			</div>
		</div>
		<div v-if="vm.nameMappingConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal" role="dialog" aria-modal="true" aria-labelledby="checks-name-mapping-confirm-title">
				<div id="checks-name-mapping-confirm-title" class="sm-modal-title">{{ vm.$t('face_match:modal_mapping_title', 'Save name mapping') }}</div>
				<div class="sm-modal-text">{{ vm.nameMappingConfirm.message }}</div>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveNameMappingConfirm(false)" style="width: 120px;">{{ vm.$t('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveNameMappingConfirm(true)" style="width: 120px;">{{ vm.$t('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
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
