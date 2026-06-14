<template>
	<aside class="sm-nav">
		<div class="sm-nav-group">{{ $avt('nav:group_photos', 'Photos') }}</div>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'status' }"
			@click="$emit('select', 'status')"
		>
			<StatusIcon class="sm-nav-icon" />
			{{ $avt('nav:status', 'Status') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'face_match' }"
			@click="$emit('select', 'face_match')"
		>
			<FaceMatchIcon class="sm-nav-icon" />
			{{ $avt('nav:face_match', 'Face Matching') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'checks' }"
			@click="$emit('select', 'checks')"
		>
			<ChecksIcon class="sm-nav-icon" />
			{{ $avt('nav:checks', 'Checks') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'cleanup' }"
			@click="$emit('select', 'cleanup')"
		>
			<CleanupIcon class="sm-nav-icon" />
			{{ $avt('nav:cleanup', 'Cleanup') }}
		</button>
		<div class="sm-nav-separator"></div>
		<div class="sm-nav-group">{{ $avt('nav:group_settings', 'Settings / extensions') }}</div>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'configuration' }"
			@click="$emit('select', 'configuration')"
		>
			<ConfigIcon class="sm-nav-icon" />
			{{ $avt('nav:configuration', 'Configuration') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'external_libraries' }"
			@click="$emit('select', 'external_libraries')"
		>
			<ExternalLibrariesIcon class="sm-nav-icon" />
			{{ $avt('nav:external_libraries', 'External libraries') }}
		</button>
		<button
			class="sm-nav-item sm-nav-sub-item"
			:class="{ active: selectedOption === 'database_lists' }"
			@click="$emit('select', 'database_lists')"
		>
			{{ $avt('nav:database_lists', 'Database lists') }}
		</button>
		<button
			class="sm-nav-item sm-nav-sub-item"
			:class="{ active: selectedOption === 'external_libraries_exiftool' }"
			@click="$emit('select', 'external_libraries_exiftool')"
		>
			{{ $avt('nav:exiftool', 'ExifTool') }}
		</button>
		<button
			class="sm-nav-item"
			:class="{ active: selectedOption === 'external_libraries_pip_packages' }"
			@click="$emit('select', 'external_libraries_pip_packages')"
		>
			<ModulesIcon class="sm-nav-icon" />
			{{ $avt('nav:pip_packages', 'pip packages') }}
		</button>
	</aside>
</template>

<script>
import ChecksIcon from './icons/ChecksIcon.vue';
import CleanupIcon from './icons/CleanupIcon.vue';
import ConfigIcon from './icons/ConfigIcon.vue';
import ExternalLibrariesIcon from './icons/ExternalLibrariesIcon.vue';
import FaceMatchIcon from './icons/FaceMatchIcon.vue';
import ModulesIcon from './icons/ModulesIcon.vue';
import StatusIcon from './icons/StatusIcon.vue';

export default {
	name: 'AppSidebarNav',
	components: {
		ChecksIcon,
		CleanupIcon,
		ConfigIcon,
		ExternalLibrariesIcon,
		FaceMatchIcon,
		ModulesIcon,
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
