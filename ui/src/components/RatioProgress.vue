<template>
	<div class="sm-ratio-progress" :title="tooltip">
		<div v-if="iconUrl" class="sm-ratio-progress-icon-wrap">
			<img class="sm-ratio-progress-icon" :src="iconUrl" alt="" />
		</div>
		<div class="sm-ratio-progress-body">
			<div class="sm-ratio-progress-bg">
				<div class="sm-ratio-progress-bar" :style="{ width: `${percent}%` }"></div>
			</div>
			<div class="sm-ratio-progress-text">
				<span class="sm-ratio-progress-primary">{{ primaryText }}</span>
				<template v-if="secondaryText">
					<span class="sm-ratio-progress-sep"> | </span>
					<span class="sm-ratio-progress-secondary">{{ secondaryText }}</span>
				</template>
			</div>
		</div>
	</div>
</template>

<script>
export default {
	name: 'RatioProgress',
	props: {
		current: {
			type: Number,
			default: 0,
		},
		total: {
			type: Number,
			default: 0,
		},
		primaryText: {
			type: String,
			default: '',
		},
		secondaryText: {
			type: String,
			default: '',
		},
		tooltip: {
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
	},
};
</script>
