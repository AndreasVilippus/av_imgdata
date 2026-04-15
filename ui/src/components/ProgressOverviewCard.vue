<template>
	<div class="sm-progress-overview-card">
		<div v-if="iconUrl" class="sm-progress-overview-icon-wrap">
			<img class="sm-progress-overview-icon" :src="iconUrl" alt="" />
		</div>
		<div class="sm-progress-overview-table">
			<div class="sm-progress-overview-desc">
				<div class="sm-progress-overview-title">{{ title }}</div>
				<div class="sm-progress-overview-count">{{ count }}</div>
			</div>
			<div class="sm-progress-overview-usage-container">
				<div class="sm-ratio-progress">
					<div class="sm-ratio-progress-bg">
						<div class="sm-ratio-progress-bar" :style="{ width: `${percent}%` }"></div>
					</div>
					<div class="sm-ratio-progress-text">
						<span class="sm-ratio-progress-primary">{{ current }} {{ primaryLabel }}</span>
						<span class="sm-ratio-progress-sep"> | </span>
						<span class="sm-ratio-progress-secondary">{{ remaining }} {{ secondaryLabel }}</span>
					</div>
					<div v-if="statusText" class="sm-progress-overview-status">{{ statusText }}</div>
				</div>
			</div>
		</div>
	</div>
</template>

<script>
export default {
	name: 'ProgressOverviewCard',
	props: {
		title: {
			type: String,
			default: '',
		},
		count: {
			type: [String, Number],
			default: '',
		},
		current: {
			type: Number,
			default: 0,
		},
		total: {
			type: Number,
			default: 0,
		},
		primaryLabel: {
			type: String,
			default: '',
		},
		secondaryLabel: {
			type: String,
			default: '',
		},
		statusText: {
			type: String,
			default: '',
		},
		iconUrl: {
			type: String,
			default: '',
		},
	},
	computed: {
		percent() {
			const current = Number(this.current) || 0;
			const total = Number(this.total) || 0;
			if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
				return 0;
			}
			return Math.max(0, Math.min(100, (current / total) * 100));
		},
		remaining() {
			const current = Number(this.current) || 0;
			const total = Number(this.total) || 0;
			if (!Number.isFinite(total) || total <= 0) {
				return 0;
			}
			return Math.max(total - current, 0);
		},
	},
};
</script>
