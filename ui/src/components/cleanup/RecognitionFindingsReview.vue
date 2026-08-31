<template>
		<section v-if="vm.recognitionManualReviewEnabled" class="panel face-match-split-panel panel-content-start">
		<div class="face-match-status-head">
			<div class="sm-section-title">{{ reviewTitle }}</div>
			<div v-if="vm.recognitionCurrentFinding" class="face-match-status-running">
				{{ vm.recognitionCurrentIndex + 1 }} / {{ vm.recognitionReviewFindings.length }}
			</div>
		</div>
		<div v-if="vm.recognitionFindingsLoading" class="face-match-loading"><span class="sm-loader"></span></div>
		<div v-else-if="vm.recognitionCurrentFinding">
			<div class="face-match-image-context">
				<div class="face-match-image-path">{{ vm.recognitionCurrentFinding.image_path }}</div>
				<div class="face-match-status-stats">
					<span>{{ vm.$avt('cleanup:recognition_person', 'Person') }}: {{ vm.getRecognitionPersonName(vm.recognitionCurrentFinding) }}</span>
					<span v-if="vm.recognitionCurrentFinding.current_person_name">{{ vm.$avt('cleanup:recognition_current_person', 'Current Photos person') }}: {{ vm.recognitionCurrentFinding.current_person_name }}</span>
					<span v-if="vm.recognitionCurrentFinding.best_person_name">{{ vm.$avt('cleanup:recognition_suggested_person', 'Suggested person') }}: {{ vm.recognitionCurrentFinding.best_person_name }}</span>
					<span v-if="vm.recognitionCurrentFinding.best_score !== undefined">{{ vm.$avt('cleanup:recognition_score', 'Score') }}: {{ Number(vm.recognitionCurrentFinding.best_score || 0).toFixed(3) }}</span>
					<span v-if="vm.recognitionCurrentFinding.decision">{{ vm.$avt('cleanup:recognition_decision', 'Decision') }}: {{ vm.recognitionCurrentFinding.decision }}</span>
				</div>
				<label v-if="!vm.isRecognitionOutlierAction" class="face-match-result-name-field recognition-person-field">
					<strong>{{ vm.$avt('face_match:label_photos_person', 'Photos person:') }}</strong>
					<input
						:value="vm.recognitionPersonName"
						type="text"
						class="face-match-result-name-input"
						:placeholder="vm.$avt('face_match:name_placeholder', 'Name of the match')"
						:disabled="vm.recognitionDecisionLoading"
						@input="vm.handleRecognitionPersonNameInput($event.target.value)"
						@focus="vm.handleRecognitionPersonNameFocus"
					/>
					<div v-if="vm.recognitionShowSuggestions && (vm.recognitionPersonSuggestLoading || vm.recognitionPersonSuggestions.length)" class="face-match-suggest-list">
						<div v-if="vm.recognitionPersonSuggestLoading" class="face-match-suggest-loading">
							<span class="sm-loader"></span>
							{{ vm.$avt('face_match:suggest_loading', 'Loading suggestions...') }}
						</div>
						<button
							v-for="person in vm.recognitionPersonSuggestions"
							:key="`recognition-person-suggest-${person.id}`"
							type="button"
							class="face-match-suggest-item"
							:disabled="vm.recognitionDecisionLoading"
							@click="vm.selectRecognitionPersonSuggestion(person)"
						>
							<img :src="vm.getFaceMatchPersonPreviewUrl(person)" alt="" class="face-match-suggest-thumb" />
							<span class="face-match-suggest-text">
								<span class="face-match-suggest-name">{{ person.name || vm.$avt('face_match:unknown_name', '(unnamed)') }}</span>
								<span class="face-match-suggest-meta">{{ vm.$avt('face_match:suggest_person_id', 'Photos Person-ID: {id}', { id: person.id }) }}</span>
							</span>
						</button>
					</div>
				</label>
			</div>
			<div class="face-match-split">
				<button
					type="button"
					class="face-match-icon-button face-match-icon-button-floating"
					:title="primaryTooltip"
					:aria-label="primaryTooltip"
					:disabled="vm.recognitionDecisionLoading"
					@click.prevent="vm.acceptRecognitionCurrent"
				>
					<span v-if="vm.isRecognitionOutlierAction" class="face-match-icon-stack">
						<img :src="vm.getRecognitionExcludeReferenceBaseIconUrl()" alt="" class="face-match-icon-image" />
						<img :src="vm.getRecognitionExcludeReferenceOverlayIconUrl()" alt="" class="face-match-icon-overlay" />
					</span>
					<img v-else :src="vm.getRecognitionApplyIconUrl()" alt="" class="face-match-icon-image" />
				</button>
				<div class="face-match-col">
					<h2>{{ leftTitle }}</h2>
					<div class="face-match-thumbnail-wrap">
						<div class="face-match-preview">
							<img :src="vm.getRecognitionImageUrl(vm.recognitionCurrentFinding.image_path)" alt="" class="face-match-thumbnail" />
							<div class="face-match-bbox" :style="vm.getFaceMatchBoxStyle(vm.getRecognitionDisplayFace(vm.recognitionCurrentFinding))"></div>
						</div>
					</div>
				</div>
				<div class="face-match-col">
					<h2>{{ rightTitle }}</h2>
					<div class="face-match-thumbnail-wrap">
						<div class="face-match-preview">
							<img :src="vm.getRecognitionImageUrl(vm.recognitionCurrentFinding.profile_image_path)" alt="" class="face-match-thumbnail" />
							<div class="face-match-bbox face-frame-insightface-box" :style="vm.getFaceMatchBoxStyle(vm.getRecognitionDisplayFace(vm.recognitionCurrentFinding, 'profile_bbox', 'profile_display_normalized'))"></div>
						</div>
					</div>
				</div>
			</div>
			<div class="face-match-action-buttons face-frame-review-actions">
				<v-button v-if="vm.isRecognitionOutlierAction" @click="vm.decideRecognitionCurrent('confirmed')" :disabled="vm.recognitionDecisionLoading" style="width: 160px;">
					{{ vm.$avt('cleanup:recognition_confirm_reference', 'Confirm reference') }}
				</v-button>
				<v-button v-if="vm.isRecognitionOutlierAction" @click="vm.decideRecognitionCurrent('needs_review')" :disabled="vm.recognitionDecisionLoading" style="width: 160px;">
					{{ vm.$avt('cleanup:recognition_review_later', 'Review later') }}
				</v-button>
				<v-button @click="vm.decideRecognitionCurrent('skipped')" :disabled="vm.recognitionDecisionLoading" style="width: 160px;">
					{{ vm.$avt('cleanup:button_skip', 'Skip') }}
				</v-button>
			</div>
		</div>
			<p v-else-if="!vm.cleanupLoading" class="config-card-desc">{{ vm.$avt('cleanup:recognition_no_review_findings', 'No recognition findings require manual review.') }}</p>
	</section>
</template>

<script>
export default {
	name: 'RecognitionFindingsReview',
	props: { vm: { type: Object, required: true } },
	computed: {
		reviewTitle() {
			return this.vm.isRecognitionOutlierAction
				? this.vm.$avt('cleanup:recognition_outlier_review_title', 'Review reference face')
				: this.vm.isRecognitionAssignmentAction
					? this.vm.$avt('cleanup:recognition_assignment_review_title', 'Review person assignment')
				: this.vm.$avt('cleanup:recognition_suggestion_review_title', 'Review recognition suggestion');
		},
		leftTitle() {
			return this.vm.isRecognitionOutlierAction
				? this.vm.$avt('cleanup:recognition_suspected_reference', 'Suspected reference face')
				: this.vm.isRecognitionAssignmentAction
					? this.vm.$avt('cleanup:recognition_assigned_face', 'Currently assigned Photos face')
				: this.vm.$avt('cleanup:recognition_unknown_face', 'Unknown Photos face');
		},
		rightTitle() {
			return this.vm.$avt('cleanup:recognition_profile_reference', 'Person profile reference');
		},
		primaryTooltip() {
			return this.vm.isRecognitionOutlierAction
				? this.vm.$avt('cleanup:recognition_exclude_reference', 'Exclude from person profile')
				: this.vm.isRecognitionAssignmentAction
					? this.vm.$avt('cleanup:recognition_reassign_person', 'Assign suggested person')
				: this.vm.$avt('cleanup:recognition_assign_person', 'Assign suggested person');
		},
	},
};
</script>
