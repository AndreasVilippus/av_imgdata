<template>
	<section class="panel">
		<div class="sm-section-title sm-section-title-block">{{ title }}</div>
	</section>
</template>

<script>
export default {
	name: 'PlaceholderView',
	props: {
		title: {
			type: String,
			required: true,
		},
	},
};
</script>
