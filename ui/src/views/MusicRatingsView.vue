<template>
	<section class="panel">
		<div class="panel-head">
			<div class="sm-section-title">{{ vm.$avt('music_ratings:title', 'Ratings for music files') }}</div>
			<p>{{ vm.$avt('music_ratings:description', 'Read file ratings and prepare transfer to Audio Station / DS audio.') }}</p>
		</div>

		<div class="config-actions config-actions-right">
			<v-button @click="vm.loadMusicRatingsCapabilities" :disabled="vm.musicRatingsLoading">
				{{ vm.$avt('config:button_reload', 'Reload') }}
			</v-button>
		</div>
		<div v-if="vm.musicRatingsMessage" class="config-message">{{ vm.musicRatingsMessage }}</div>
		<div v-if="vm.musicRatingsLoading" class="config-loading">
			<span class="sm-loader"></span>
			{{ vm.$avt('music_ratings:loading', 'Loading music capabilities...') }}
		</div>

		<div v-else class="config-layout">
			<section class="config-card">
				<div class="sm-section-title">{{ vm.$avt('music_ratings:audio_station_status', 'Audio Station status') }}</div>
				<div class="sm-kv-list">
					<div class="sm-kv-row"><div class="sm-kv-key">{{ vm.$avt('music_ratings:installed', 'Installed') }}</div><div class="sm-kv-value">{{ vm.musicRatingsAudioStation.installed ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}</div></div>
					<div class="sm-kv-row"><div class="sm-kv-key">{{ vm.$avt('music_ratings:setrating_documented', 'setrating API documented') }}</div><div class="sm-kv-value">{{ vm.musicRatingsAudioStation.api_setrating_documented ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}</div></div>
					<div class="sm-kv-row"><div class="sm-kv-key">{{ vm.$avt('music_ratings:other_users_verified', 'Other-user writes verified') }}</div><div class="sm-kv-value">{{ vm.musicRatingsAudioStation.api_setrating_other_users_verified ? vm.$avt('status:yes', 'Yes') : vm.$avt('status:no', 'No') }}</div></div>
					<div class="sm-kv-row"><div class="sm-kv-key">{{ vm.$avt('music_ratings:required_write_scope', 'Required write scope') }}</div><div class="sm-kv-value">{{ vm.musicRatingsAudioStation.required_write_scope || '-' }}</div></div>
					<div class="sm-kv-row"><div class="sm-kv-key">{{ vm.$avt('music_ratings:recommended_write_strategy', 'Planned write strategy') }}</div><div class="sm-kv-value">{{ vm.musicRatingsAudioStation.recommended_write_strategy || '-' }}</div></div>
				</div>
				<div class="config-card-desc">{{ vm.$avt('music_ratings:write_blocked', 'The API does not currently prove multi-user writes from one system service. Database writes remain disabled until schema and runtime requirements are verified.') }}</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ vm.$avt('music_ratings:shared_folders', 'Shared music folders') }}</div>
				<div v-for="folder in vm.musicRatingsSharedFolders" :key="folder.path" class="sm-kv-row">
					<div class="sm-kv-key">{{ folder.name }}</div><div class="sm-kv-value">{{ folder.path }}</div>
				</div>
				<div v-if="!vm.musicRatingsSharedFolders.length" class="config-card-desc">{{ vm.$avt('music_ratings:no_shared_folders', 'No configured shared music folder was found.') }}</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ vm.$avt('music_ratings:users', 'Target users') }}</div>
				<label v-for="user in vm.musicRatingsUsers" :key="user.name" class="config-checkbox">
					<input type="checkbox" :checked="vm.musicRatingsSelectedUsers.includes(user.name)" @change="vm.toggleMusicRatingsUser(user.name)" />
					<span>{{ user.name }}<template v-if="user.description"> – {{ user.description }}</template></span>
				</label>
				<div v-if="!vm.musicRatingsUsers.length" class="config-card-desc">{{ vm.$avt('music_ratings:no_users', 'No selectable DSM users could be read with the current session.') }}</div>
			</section>

			<section class="config-card">
				<div class="sm-section-title">{{ vm.$avt('music_ratings:scan_options', 'Scan options') }}</div>
				<label class="config-field">
					<span class="config-field-label">{{ vm.$avt('music_ratings:changed_since_days', 'Only files changed in the last days (0 = all)') }}</span>
					<input v-model.number="vm.musicRatingsChangedSinceDays" type="number" min="0" class="config-text-input" />
				</label>
				<label class="config-checkbox">
					<input v-model="vm.musicRatingsLiveWatchEnabled" type="checkbox" disabled />
					<span>{{ vm.$avt('music_ratings:live_watch', 'React to file changes with an optional background service') }}</span>
				</label>
				<div class="config-card-desc">{{ vm.$avt('music_ratings:live_watch_planned', 'The live file-change service is planned but not implemented yet.') }}</div>
				<div class="config-actions config-actions-right">
					<v-button @click="vm.loadMusicRatingsPreview" :disabled="vm.musicRatingsPreviewLoading || !vm.musicRatingsSharedFolders.length">
						{{ vm.musicRatingsPreviewLoading ? vm.$avt('music_ratings:preview_loading', 'Scanning...') : vm.$avt('music_ratings:preview', 'Preview ratings') }}
					</v-button>
				</div>
			</section>

			<section v-if="vm.musicRatingsPreview && vm.musicRatingsPreview.entries" class="config-card">
				<div class="sm-section-title">{{ vm.$avt('music_ratings:preview_result', 'Preview result') }}</div>
				<div class="config-card-desc">{{ vm.$avt('music_ratings:preview_summary', '{found} ratings found in {scanned} scanned files.', { found: vm.musicRatingsPreview.ratings_found || 0, scanned: vm.musicRatingsPreview.files_scanned || 0 }) }}</div>
				<div class="database-list-table-wrap">
					<table class="database-list-table">
						<thead><tr><th>{{ vm.$avt('music_ratings:path', 'Path') }}</th><th>{{ vm.$avt('music_ratings:schema', 'Schema') }}</th><th>{{ vm.$avt('music_ratings:stars', 'Stars') }}</th></tr></thead>
						<tbody>
							<tr v-for="entry in vm.musicRatingsPreview.entries" :key="entry.path">
								<td>{{ entry.path }}</td><td>{{ entry.source_rating_schema }}</td><td>{{ entry.rating_stars }}</td>
							</tr>
						</tbody>
					</table>
				</div>
			</section>
		</div>
	</section>
</template>

<script>
export default {
	name: 'MusicRatingsView',
	props: { vm: { type: Object, required: true } },
};
</script>
