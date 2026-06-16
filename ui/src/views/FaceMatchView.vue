<template>
	<div class="face-match-view">
		<section class="panel">
			<div class="panel-head">
				<div class="sm-section-title">{{ vm.$avt('face_match:title', 'Face Matching') }}</div>
				<p>{{ vm.$avt('face_match:desc', 'Area for matching and file-processing actions.') }}</p>
			</div>
			<div class="face-match-top-layout panel-content-start">
				<div class="face-match-action-controls">
						<select v-model="vm.selectedFaceMatchingAction" class="face-match-select" :disabled="vm.faceMatchLoading">
							<option value="search_photo_face_in_file">{{ vm.$avt('face_match:action_search_photo_face_in_file', 'search unknown Photos face in file') }}</option>
							<option value="search_file_face_in_sources">{{ vm.$avt('face_match:action_search_file_face_in_sources', 'search face from file') }}</option>
							<option value="mark_missing_photos_faces">{{ vm.$avt('face_match:action_mark_missing_photos_faces', 'mark missing faces in Photos') }}</option>
							<option value="search_missing_faces_insightface" :disabled="!vm.hasInsightFaceForFaceMatch">{{ vm.$avt('face_match:action_search_missing_faces_insightface', 'search missing faces with InsightFace') }}</option>
							<option value="recognition_analyze_unknown_faces" :disabled="!vm.hasInsightFaceForFaceMatch">{{ vm.$avt('face_match:action_recognition_unknown_faces', 'recognize unknown faces with InsightFace') }}</option>
						</select>
					<div v-if="!vm.hasInsightFaceForFaceMatch" class="config-card-desc">
						{{ vm.$avt('face_match:hint_insightface_unavailable', 'InsightFace search becomes available after the optional InsightFace package is installed.') }}
					</div>
					<div class="face-match-action-buttons">
						<v-button @click="vm.handlePrimaryFaceMatchButton" :disabled="vm.faceMatchActionLocked" style="width: 160px;">
							{{ vm.faceMatchPrimaryButtonLabel }}
						</v-button>
						<v-button
							v-if="vm.hasNextFaceMatch || (vm.faceMatchReviewingStoredFindings && vm.faceMatchFindingEntries.length > 0)"
							@click="vm.loadNextFaceMatch"
							:disabled="vm.faceMatchInteractionDisabled || !vm.hasNextFaceMatch"
							style="width: 160px;"
						>
							{{ vm.$avt('face_match:button_next', 'Next') }}
						</v-button>
					</div>
					<label class="face-match-switch" :title="vm.$avt('face_match:hint_face_only', 'Only the face crop is shown in the preview windows.')">
						<input v-model="vm.faceMatchPreviewMode" type="checkbox" true-value="face" false-value="photo" />
						<span class="face-match-switch-slider"></span>
						<span class="face-match-switch-label">{{ vm.$avt('face_match:switch_face_only', 'Show face only') }}</span>
					</label>
					<label class="face-match-switch" :title="vm.$avt('face_match:hint_auto_assign', 'If a person with that name exists, the face is assigned automatically.')">
						<input v-model="vm.faceMatchAutoAssignKnown" type="checkbox" :disabled="vm.faceMatchLoading" />
						<span class="face-match-switch-slider"></span>
						<span class="face-match-switch-label">{{ vm.$avt('face_match:switch_auto_assign', 'Assign all known') }}</span>
					</label>
						<label
							v-if="vm.faceMatchSupportsSaveOnly"
							class="face-match-switch"
							:title="vm.$avt('face_match:hint_save_only', 'Known persons are still assigned depending on the setting; otherwise matches are only listed for later.')"
					>
						<input v-model="vm.faceMatchSaveOnly" type="checkbox" :disabled="vm.faceMatchLoading || vm.faceMatchUseStoredFindings" />
							<span class="face-match-switch-slider"></span>
							<span class="face-match-switch-label">{{ vm.$avt('face_match:switch_save_only', 'Save matches only') }}</span>
						</label>
						<label
							v-if="vm.selectedFaceMatchingAction === 'search_missing_faces_insightface'"
							class="face-match-switch"
							:title="vm.$avt('face_match:hint_recognize_missing_faces', 'Detected missing faces are compared with existing InsightFace recognition profiles and suggested for a Photos person when matched.')"
						>
							<input v-model="vm.faceMatchRecognizeMissingInsightFacePersons" type="checkbox" :disabled="vm.faceMatchLoading || !vm.hasInsightFaceForFaceMatch" />
							<span class="face-match-switch-slider"></span>
							<span class="face-match-switch-label">{{ vm.$avt('face_match:switch_recognize_missing_faces', 'Person recognition with InsightFace') }}</span>
						</label>
						<label
							class="face-match-switch"
							:title="vm.$avt('face_match:hint_use_findings', 'Load saved matches instead of starting a new search.')"
					>
						<input v-model="vm.faceMatchUseStoredFindings" type="checkbox" :disabled="vm.faceMatchLoading || !vm.hasFaceMatchStoredFindings" />
						<span class="face-match-switch-slider"></span>
						<span class="face-match-switch-label">{{ vm.$avt('face_match:switch_use_findings', 'Use match list') }}</span>
					</label>
				</div>
				<div class="face-match-status-column">
					<div class="face-match-status-card face-match-status-card-action">
						<div class="face-match-status-head">
							<div class="sm-section-title">{{ vm.$avt('face_match:card_action', 'Action') }}</div>
								<div v-if="vm.faceMatchLoading || (vm.faceMatchRecognitionActionSelected && vm.cleanupLoading)" class="face-match-status-running">
									<span class="sm-loader"></span>
									{{ vm.$avt('face_match:card_running', 'Running') }}
								</div>
							</div>
							<div v-if="vm.faceMatchRecognitionActionSelected" class="face-match-status-message">{{ vm.getCleanupStatusHeadline() }}</div>
							<div v-else-if="!vm.faceMatchShowStoredFindingsProgress && !vm.faceMatchShowPersonsProgress && !vm.faceMatchShowFileProgress" class="face-match-status-message">{{ vm.faceMatchStatusMessage }}</div>
							<div v-if="vm.faceMatchRecognitionActionSelected && Number(vm.getCleanupStatusProgress().total) > 0" class="sm-status-progress">
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
							<div v-if="vm.faceMatchRecognitionActionSelected && vm.getCleanupStatusCounters().length" class="face-match-status-stats">
								<span v-for="counter in vm.getCleanupStatusCounters()" :key="`face-match-recognition-counter-${counter.key}`">{{ vm.formatCleanupStatusCounter(counter) }}</span>
							</div>
						<div v-if="vm.faceMatchShowStoredFindingsProgress" class="sm-status-progress">
							<ProgressOverviewCard
								:title="vm.$avt('face_match:label_list_entries', 'List entries')"
								:count="vm.faceMatchStoredFindingsTotal"
								:current="vm.faceMatchStoredFindingsChecked"
								:total="vm.faceMatchStoredFindingsTotal"
								:primary-label="vm.$avt('face_match:label_checked', 'checked')"
								:secondary-label="vm.$avt('checks:label_remaining', 'remaining')"
								:status-text="vm.faceMatchStatusMessage"
							/>
						</div>
						<div v-if="vm.faceMatchShowPersonsProgress" class="sm-status-progress">
							<ProgressOverviewCard
								:title="vm.$avt('face_match:label_persons', 'Persons')"
								:count="vm.faceMatchPersonsTotal"
								:current="vm.faceMatchPersonsChecked"
								:total="vm.faceMatchPersonsTotal"
								:primary-label="vm.$avt('face_match:label_checked', 'checked')"
								:secondary-label="vm.$avt('face_match:label_unchecked', 'unchecked')"
								:status-text="vm.faceMatchStatusHeadline"
							/>
						</div>
						<div v-if="vm.faceMatchShowFileProgress" class="sm-status-progress">
							<ProgressOverviewCard
								:title="vm.$avt('face_match:label_images', 'Images')"
								:count="vm.faceMatchFileProgressTotal"
								:current="vm.faceMatchFileProgressCurrent"
								:total="vm.faceMatchFileProgressTotal"
								:primary-label="vm.$avt('cleanup:label_scanned', 'scanned')"
								:secondary-label="vm.$avt('checks:label_remaining', 'remaining')"
								:status-text="vm.faceMatchStatusHeadline"
								:icon-url="vm.faceMatchProgressIconUrl"
							/>
						</div>
					</div>
					<div class="face-match-status-card face-match-status-card-result">
						<div class="face-match-status-head">
							<div class="sm-section-title">{{ vm.$avt('face_match:card_result', 'Result') }}</div>
						</div>
						<div v-if="vm.faceMatchResultSummary.found" class="face-match-result-layout">
							<div class="face-match-result-details">
								<label class="face-match-result-name-field">
									<strong>{{ vm.$avt('face_match:label_name', 'Name:') }}</strong>
									<input
										v-model.trim="vm.faceMatchEditableName"
										type="text"
										class="face-match-result-name-input"
										:placeholder="vm.$avt('face_match:name_placeholder', 'Name of the match')"
										:disabled="vm.faceMatchInteractionDisabled"
										@input="vm.handleFaceMatchNameInput"
										@focus="vm.handleFaceMatchNameFocus"
									/>
									<div v-if="vm.faceMatchShowSuggestions && (vm.faceMatchPersonSuggestLoading || vm.faceMatchPersonSuggestions.length)" class="face-match-suggest-list">
										<div v-if="vm.faceMatchPersonSuggestLoading" class="face-match-suggest-loading">
											<span class="sm-loader"></span>
											{{ vm.$avt('face_match:suggest_loading', 'Loading suggestions...') }}
										</div>
										<button
											v-for="person in vm.faceMatchPersonSuggestions"
											:key="`face-person-suggest-${person.id}`"
											type="button"
											class="face-match-suggest-item"
											:disabled="vm.faceMatchInteractionDisabled"
											@click="vm.selectFaceMatchSuggestion(person)"
										>
											<img :src="vm.getFaceMatchPersonPreviewUrl(person)" alt="" class="face-match-suggest-thumb" />
											<span class="face-match-suggest-text">
												<span class="face-match-suggest-name">{{ person.name || vm.$avt('face_match:unknown_name', '(unnamed)') }}</span>
												<span class="face-match-suggest-meta">{{ vm.$avt('face_match:suggest_person_id', 'Photos Person-ID: {id}', { id: person.id }) }}</span>
											</span>
										</button>
									</div>
								</label>
								<div><strong>{{ vm.$avt('face_match:label_source', 'Source:') }}</strong> {{ vm.faceMatchResultSummary.source }}</div>
								<div><strong>{{ vm.$avt('face_match:label_format', 'Format:') }}</strong> {{ vm.faceMatchResultSummary.format }}</div>
								<div v-if="vm.faceMatchResultSummary.photosPersonId"><strong>{{ vm.$avt('face_match:label_photos_person_id', 'Photos Person ID:') }}</strong> {{ vm.faceMatchResultSummary.photosPersonId }}</div>
							</div>
							<div class="face-match-person-preview">
								<img :src="vm.getFaceMatchPersonPreviewUrl(vm.faceMatchEffectivePerson)" :alt="vm.$avt('face_match:person_preview_alt', 'Person preview')" class="face-match-person-preview-image" />
							</div>
						</div>
						<div v-else class="face-match-status-message">{{ vm.faceMatchResultSummary.message }}</div>
					</div>
				</div>
			</div>
			</section>
			<RecognitionOptions v-if="vm.faceMatchRecognitionActionSelected" :vm="vm" />
			<RecognitionFindingsReview v-if="vm.faceMatchRecognitionActionSelected" :vm="vm" />
			<section v-if="!vm.faceMatchRecognitionActionSelected" class="panel face-match-split-panel">
			<div class="face-match-image-context">
				<div class="sm-section-title sm-section-title-block">{{ vm.faceMatchImageContextTitle }}</div>
				<div v-if="vm.faceMatchImageContextPath" class="face-match-image-path" :title="vm.faceMatchImageContextPath">{{ vm.faceMatchImageContextPath }}</div>
			</div>
			<div v-if="vm.faceMatchLoading" class="face-match-loading">
				<span class="sm-loader"></span>
				{{ vm.$avt('face_match:loading', 'Loading data...') }}
			</div>
			<div v-else class="face-match-split">
				<button
					v-if="vm.faceMatchActionMode"
					type="button"
					class="face-match-icon-button face-match-icon-button-floating"
					:title="vm.faceMatchTransferTooltip"
					:aria-label="vm.faceMatchTransferTooltip"
					:disabled="vm.faceMatchInteractionDisabled"
					@click.prevent="vm.handleFaceMatchAction"
				>
					<span v-if="vm.faceMatchTransferIconUrl" class="face-match-icon-stack">
						<img :src="vm.faceMatchTransferIconUrl" alt="" class="face-match-icon-image" />
						<img v-if="vm.faceMatchShouldShowAddOverlay && vm.addIconUrl" :src="vm.addIconUrl" alt="" class="face-match-icon-overlay" />
					</span>
					<span v-else class="face-match-icon-fallback">{{ vm.faceMatchTransferTooltip }}</span>
				</button>
				<div class="face-match-col">
					<h2>{{ vm.faceMatchLeftTitle }}</h2>
					<div v-if="vm.getCurrentFaceMatchImageUrl()" class="face-match-thumbnail-wrap">
						<button
							v-if="vm.faceMatchCanDeleteMetadataFace"
							type="button"
							class="face-match-icon-button checks-delete-button checks-delete-button-right"
							:title="vm.$avt('face_match:button_delete_file_face', 'Delete face from file')"
							:aria-label="vm.$avt('face_match:button_delete_file_face', 'Delete face from file')"
							:disabled="vm.faceMatchInteractionDisabled"
							@click.prevent="vm.deleteFaceMatchMetadataFace"
						>
							<span class="face-match-icon-stack">
								<img :src="vm.faceIconUrl" alt="" class="face-match-icon-image" />
								<img :src="vm.deleteIconUrl" alt="" class="face-match-icon-overlay" />
							</span>
						</button>
						<template v-if="vm.isFaceOnlyPreview">
							<div v-if="vm.getFaceMatchCropStyle(vm.getLeftFaceMatchFace())" class="face-match-crop-frame">
								<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:face_preview_alt', 'Face preview')" class="face-match-crop-image" :style="vm.getFaceMatchCropStyle(vm.getLeftFaceMatchFace())" @error="vm.handleFaceMatchImagePreviewError" />
							</div>
						</template>
						<div v-else class="face-match-preview">
							<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:thumbnail_alt', 'Thumbnail')" class="face-match-thumbnail" @error="vm.handleFaceMatchImagePreviewError" />
							<div v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.getLeftFaceMatchFace())" :key="`photo-mask-${index}`" class="face-match-mask" :style="maskStyle"></div>
							<div v-if="vm.getFaceMatchBoxStyle(vm.getLeftFaceMatchFace())" class="face-match-bbox" :style="vm.getFaceMatchBoxStyle(vm.getLeftFaceMatchFace())"></div>
						</div>
					</div>
					<div v-else class="face-match-empty">{{ vm.$avt('face_match:empty_no_thumbnail', 'No thumbnail found yet.') }}</div>
				</div>
				<div class="face-match-col">
					<h2>{{ vm.faceMatchRightTitle }}</h2>
					<div v-if="vm.getCurrentFaceMatchImageUrl()" class="face-match-thumbnail-wrap">
						<template v-if="vm.isFaceOnlyPreview && vm.getRightFaceMatchFace()">
							<div v-if="vm.getFaceMatchCropStyle(vm.getRightFaceMatchFace())" class="face-match-crop-frame">
								<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:face_preview_alt', 'Face preview')" class="face-match-crop-image" :style="vm.getFaceMatchCropStyle(vm.getRightFaceMatchFace())" @error="vm.handleFaceMatchImagePreviewError" />
							</div>
						</template>
						<div v-else class="face-match-preview">
							<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:thumbnail_alt', 'Thumbnail')" class="face-match-thumbnail" @error="vm.handleFaceMatchImagePreviewError" />
							<div v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.getRightFaceMatchFace())" :key="`metadata-mask-${index}`" class="face-match-mask" :style="maskStyle"></div>
							<div v-if="vm.getFaceMatchBoxStyle(vm.getRightFaceMatchFace())" class="face-match-bbox" :style="vm.getFaceMatchBoxStyle(vm.getRightFaceMatchFace())"></div>
						</div>
					</div>
					<div v-else class="face-match-empty">{{ vm.$avt('face_match:empty_no_preview', 'No preview found yet.') }}</div>
				</div>
			</div>
		</section>
		<div v-if="vm.nameMappingConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal sm-modal-centered" role="dialog" aria-modal="true" aria-labelledby="name-mapping-confirm-title">
				<div id="name-mapping-confirm-title" class="sm-modal-title">{{ vm.$avt('face_match:modal_mapping_title', 'Save name mapping') }}</div>
				<div class="sm-modal-text">{{ vm.nameMappingConfirm.message }}</div>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveNameMappingConfirm(false)" style="width: 120px;">{{ vm.$avt('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveNameMappingConfirm(true)" style="width: 120px;">{{ vm.$avt('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
		</div>
		<div v-if="vm.metadataNameConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal sm-modal-centered" role="dialog" aria-modal="true" aria-labelledby="metadata-name-confirm-title">
				<div id="metadata-name-confirm-title" class="sm-modal-title">{{ vm.$avt('face_match:modal_metadata_name_title', 'Change name in file') }}</div>
				<div class="sm-modal-text">{{ vm.metadataNameConfirm.message }}</div>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveMetadataNameConfirm(false)" style="width: 120px;">{{ vm.$avt('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveMetadataNameConfirm(true)" style="width: 120px;">{{ vm.$avt('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
		</div>
		<div v-if="vm.metadataFaceDeleteConfirm.visible" class="sm-modal-backdrop">
			<div class="sm-modal sm-modal-centered" role="dialog" aria-modal="true" aria-labelledby="metadata-face-delete-confirm-title">
				<div id="metadata-face-delete-confirm-title" class="sm-modal-title">{{ vm.$avt('face_match:modal_delete_file_face_title', 'Delete face from file') }}</div>
				<div class="sm-modal-text">{{ vm.metadataFaceDeleteConfirm.message }}</div>
				<div class="sm-modal-actions">
					<v-button @click="vm.resolveMetadataFaceDeleteConfirm(false)" style="width: 120px;">{{ vm.$avt('face_match:button_no', 'No') }}</v-button>
					<v-button @click="vm.resolveMetadataFaceDeleteConfirm(true)" style="width: 120px;">{{ vm.$avt('face_match:button_yes', 'Yes') }}</v-button>
				</div>
			</div>
		</div>
	</div>
</template>

<script>
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';
import RecognitionOptions from '../components/cleanup/RecognitionOptions.vue';
import RecognitionFindingsReview from '../components/cleanup/RecognitionFindingsReview.vue';

export default {
	name: 'FaceMatchView',
	components: {
		ProgressOverviewCard,
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
