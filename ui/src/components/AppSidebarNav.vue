<template>
	<aside class="sm-nav">
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
			:class="{ active: selectedOption === 'checks' }"
			@click="$emit('select', 'checks')"
		>
			<ChecksIcon class="sm-nav-icon" />
			{{ $t('nav:checks', 'Checks') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'cleanup' }"
			@click="$emit('select', 'cleanup')"
		>
			<CleanupIcon class="sm-nav-icon" />
			{{ $t('nav:cleanup', 'Cleanup') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'configuration' }"
			@click="$emit('select', 'configuration')"
		>
			<ConfigIcon class="sm-nav-icon" />
			{{ $t('nav:configuration', 'Configuration') }}
		</button>
		<div class="sm-nav-separator"></div>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'external_libraries' }"
			@click="$emit('select', 'external_libraries')"
		>
			<ExternalLibrariesIcon class="sm-nav-icon" />
			{{ $t('nav:external_libraries', 'External libraries') }}
		</button>
		<button
			class="sm-nav-item sm-nav-sub-item"
			:class="{ active: selectedOption === 'external_libraries_exiftool' }"
			@click="$emit('select', 'external_libraries_exiftool')"
		>
			{{ $t('nav:exiftool', 'ExifTool') }}
		</button>
	</aside>
</template>

<script>
import ChecksIcon from './icons/ChecksIcon.vue';
import CleanupIcon from './icons/CleanupIcon.vue';
import ConfigIcon from './icons/ConfigIcon.vue';
import ExternalLibrariesIcon from './icons/ExternalLibrariesIcon.vue';
import FaceMatchIcon from './icons/FaceMatchIcon.vue';
import StatusIcon from './icons/StatusIcon.vue';

export default {
	name: 'AppSidebarNav',
	components: {
		ChecksIcon,
		CleanupIcon,
		ConfigIcon,
		ExternalLibrariesIcon,
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
