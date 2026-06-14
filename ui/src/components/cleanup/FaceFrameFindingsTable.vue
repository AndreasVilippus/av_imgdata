<template>
	<div class="face-match-status-card">
		<div class="sm-section-title">{{ vm.$avt('cleanup:face_frames_findings', 'Face-frame findings') }}</div>
		<div v-if="vm.faceFrameFindingsLoading" class="face-match-status-running"><span class="sm-loader"></span></div>
		<table v-else-if="vm.faceFrameFindings.length" class="sm-table">
			<thead><tr>
				<th>{{ vm.$avt('cleanup:label_current_path', 'Current file') }}</th>
				<th>{{ vm.$avt('cleanup:face_frames_source', 'Source') }}</th>
				<th>IoU</th>
				<th>{{ vm.$avt('cleanup:face_frames_decision', 'Decision') }}</th>
			</tr></thead>
			<tbody><tr v-for="finding in vm.faceFrameFindings" :key="finding.item_id">
				<td>{{ finding.image_path }}</td>
				<td>{{ finding.source_frame && finding.source_frame.source_format }}</td>
				<td>{{ Number(finding.match && finding.match.iou || 0).toFixed(3) }}</td>
				<td>{{ finding.match && finding.match.decision }}</td>
			</tr></tbody>
		</table>
		<p v-else>{{ vm.$avt('cleanup:face_frames_no_findings', 'No persisted findings.') }}</p>
	</div>
</template>

<script>
export default {
	name: 'FaceFrameFindingsTable',
	props: { vm: { type: Object, required: true } },
};
</script>
