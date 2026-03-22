<template>
	<aside class="sm-nav">
		<div class="sm-nav-group">{{ $t('nav:group_photos', 'Photos') }}</div>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'status' }"
			@click="$emit('select', 'status')"
		>
			<StatusIcon class="sm-nav-icon" />
			{{ $t('nav:status', 'Status') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'face_match' }"
			@click="$emit('select', 'face_match')"
		>
			<FaceMatchIcon class="sm-nav-icon" />
			{{ $t('nav:face_match', 'Face Matching') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'configuration' }"
			@click="$emit('select', 'configuration')"
		>
			<ConfigIcon class="sm-nav-icon" />
			{{ $t('nav:configuration', 'Configuration') }}
		</button>
	</aside>
</template>

<script>
import ConfigIcon from './icons/ConfigIcon.vue';
import FaceMatchIcon from './icons/FaceMatchIcon.vue';
import StatusIcon from './icons/StatusIcon.vue';

export default {
	name: 'AppSidebarNav',
	components: {
		ConfigIcon,
		FaceMatchIcon,
		StatusIcon,
	},
	props: {
		selectedOption: {
			type: String,
			required: true,
		},
	},
};
</script>
