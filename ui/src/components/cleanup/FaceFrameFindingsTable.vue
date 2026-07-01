<template>
	<section v-if="vm.faceFrameManualReviewEnabled" class="panel face-match-split-panel">
		<div class="face-match-status-head">
			<div class="sm-section-title">{{ vm.$avt('cleanup:face_frames_review_title', 'Review face frame') }}</div>
			<div v-if="vm.faceFrameCurrentFinding" class="face-match-status-running">
				{{ vm.faceFrameCurrentIndex + 1 }} / {{ vm.faceFrameReviewFindings.length }}
			</div>
		</div>
		<div v-if="vm.faceFrameFindingsLoading" class="face-match-loading"><span class="sm-loader"></span></div>
		<div v-else-if="vm.faceFrameCurrentFinding">
			<div class="face-match-image-context">
				<div class="face-match-image-path">{{ vm.faceFrameCurrentFinding.image_path }}</div>
				<div class="face-match-status-stats">
					<span>{{ vm.$avt('cleanup:face_frames_source', 'Source') }}: {{ vm.faceFrameCurrentFinding.source_frame.source_format }}</span>
					<span>IoU: {{ Number(vm.faceFrameCurrentFinding.match.iou || 0).toFixed(3) }}</span>
					<span>{{ vm.$avt('cleanup:face_frames_decision', 'Decision') }}: {{ vm.getFaceFrameDecisionLabel(vm.faceFrameCurrentFinding.match.decision) }}</span>
				</div>
			</div>
			<div class="face-match-split">
				<button
					type="button"
					class="face-match-icon-button face-match-icon-button-floating"
					:title="vm.$avt('cleanup:button_select', 'Apply')"
					:aria-label="vm.$avt('cleanup:button_select', 'Apply')"
					:disabled="vm.faceFrameDecisionLoading"
					@click.prevent="vm.decideFaceFrameCurrent(true)"
				>
					<img :src="vm.getFaceFrameApplyIconUrl()" alt="" class="face-match-icon-image" />
				</button>
				<div class="face-match-col">
					<h2>{{ vm.$avt('cleanup:face_frames_now', 'Current frame') }}</h2>
					<div class="face-match-thumbnail-wrap">
						<div class="face-match-preview">
							<img :src="vm.getFaceFrameImageUrl(vm.faceFrameCurrentFinding)" alt="" class="face-match-thumbnail" />
							<div class="face-match-bbox" :style="vm.getFaceMatchBoxStyle(vm.faceFrameCurrentFinding.source_frame)"></div>
						</div>
					</div>
				</div>
				<div class="face-match-col">
					<h2>{{ vm.$avt('cleanup:face_frames_insightface', 'InsightFace frame') }}</h2>
					<div class="face-match-thumbnail-wrap">
						<div class="face-match-preview">
							<img :src="vm.getFaceFrameImageUrl(vm.faceFrameCurrentFinding)" alt="" class="face-match-thumbnail" />
							<div class="face-match-bbox face-frame-insightface-box" :style="vm.getFaceMatchBoxStyle(vm.faceFrameCurrentFinding.insightface_frame)"></div>
						</div>
					</div>
				</div>
			</div>
			<div class="face-match-action-buttons face-frame-review-actions">
				<v-button @click="vm.applyAllFaceFrameFindings()" :disabled="vm.faceFrameDecisionLoading || vm.faceFrameApplyLoading" style="width: 160px;">
					{{ vm.$avt('cleanup:button_apply_all', 'Apply all') }}
				</v-button>
				<v-button @click="vm.decideFaceFrameCurrent(false)" :disabled="vm.faceFrameDecisionLoading" style="width: 160px;">
					{{ vm.$avt('cleanup:button_skip', 'Skip') }}
				</v-button>
			</div>
		</div>
		<p v-else-if="!vm.cleanupLoading">{{ vm.$avt('cleanup:face_frames_no_review_findings', 'No findings require manual review.') }}</p>
	</section>
</template>

<script>
export default {
	name: 'FaceFrameFindingsTable',
	props: { vm: { type: Object, required: true } },
};
</script>
