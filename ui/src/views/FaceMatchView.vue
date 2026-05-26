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
							<div v-if="vm.faceMatchLoading" class="face-match-status-running">
								<span class="sm-loader"></span>
								{{ vm.$avt('face_match:card_running', 'Running') }}
							</div>
						</div>
						<div v-if="!vm.faceMatchShowStoredFindingsProgress && !vm.faceMatchShowPersonsProgress && !vm.faceMatchShowFileProgress" class="face-match-status-message">{{ vm.faceMatchStatusMessage }}</div>
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
		<section class="panel face-match-split-panel">
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
					<span v-if="(vm.faceMatchActionMode === 'write_metadata' ? vm.personDataToRightIconUrl : vm.personDataToLeftIconUrl)" class="face-match-icon-stack">
						<img :src="vm.faceMatchActionMode === 'write_metadata' ? vm.personDataToRightIconUrl : vm.personDataToLeftIconUrl" alt="" class="face-match-icon-image" />
						<img v-if="vm.faceMatchShouldShowAddOverlay && vm.addIconUrl" :src="vm.addIconUrl" alt="" class="face-match-icon-overlay" />
					</span>
					<span v-else class="face-match-icon-fallback">{{ vm.faceMatchTransferTooltip }}</span>
				</button>
				<div class="face-match-col">
					<h2>{{ vm.faceMatchLeftTitle }}</h2>
					<div v-if="vm.getCurrentFaceMatchImageUrl()" class="face-match-thumbnail-wrap">
						<template v-if="vm.isFaceOnlyPreview">
							<div v-if="vm.getFaceMatchCropStyle(vm.getLeftFaceMatchFace())" class="face-match-crop-frame">
								<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:face_preview_alt', 'Face preview')" class="face-match-crop-image" :style="vm.getFaceMatchCropStyle(vm.getLeftFaceMatchFace())" />
							</div>
						</template>
						<div v-else class="face-match-preview">
							<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:thumbnail_alt', 'Thumbnail')" class="face-match-thumbnail" />
							<div v-for="(maskStyle, index) in vm.getFaceMatchMaskStyles(vm.getLeftFaceMatchFace())" :key="`photo-mask-${index}`" class="face-match-mask" :style="maskStyle"></div>
							<div v-if="vm.getFaceMatchBoxStyle(vm.getLeftFaceMatchFace())" class="face-match-bbox" :style="vm.getFaceMatchBoxStyle(vm.getLeftFaceMatchFace())"></div>
						</div>
					</div>
					<div v-else class="face-match-empty">{{ vm.$avt('face_match:empty_no_thumbnail', 'No thumbnail found yet.') }}</div>
				</div>
				<div class="face-match-col">
					<h2>{{ vm.faceMatchRightTitle }}</h2>
					<div v-if="vm.getCurrentFaceMatchImageUrl()" class="face-match-thumbnail-wrap">
						<template v-if="vm.isFaceOnlyPreview">
							<div v-if="vm.getFaceMatchCropStyle(vm.getRightFaceMatchFace())" class="face-match-crop-frame">
								<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:face_preview_alt', 'Face preview')" class="face-match-crop-image" :style="vm.getFaceMatchCropStyle(vm.getRightFaceMatchFace())" />
							</div>
						</template>
						<div v-else class="face-match-preview">
							<img :src="vm.getCurrentFaceMatchImageUrl()" :alt="vm.$avt('face_match:thumbnail_alt', 'Thumbnail')" class="face-match-thumbnail" />
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
	</div>
</template>

<script>
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';

export default {
	name: 'FaceMatchView',
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
