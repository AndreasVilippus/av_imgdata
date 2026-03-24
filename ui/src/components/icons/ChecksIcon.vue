<template>
	<img
		class="sm-nav-svg"
		:src="iconUrl"
		alt=""
		aria-hidden="true"
	/>
</template>

<script>
import iconUrl from './check.svg';

export default {
	name: 'ChecksIcon',
	data() {
		return {
			iconUrl,
		};
	},
};
</script>
