<template>
	<div>
		<section class="panel">
			<div class="sm-section-title sm-section-title-block">{{ vm.$avt('status:overview_title', 'Person detection in Photos') }}</div>
			<div v-if="vm.statusLoading" class="sm-overview-person-loading">
				<span class="sm-loader"></span>
				{{ vm.$avt('status:loading', 'Loading data...') }}
			</div>
			<div v-else class="sm-overview-person-card">
				<div class="sm-overview-person-icon-wrap">
					<img class="sm-overview-person-icon" :src="vm.personsIconUrl" alt="" />
				</div>
				<div class="sm-overview-person-table">
					<div class="sm-overview-person-desc">
						<div class="sm-overview-person-mini-text">{{ vm.$avt('status:photos_persons', 'Photos persons') }}</div>
						<div class="sm-overview-person-mini-usedby">{{ vm.persons.total }}</div>
					</div>
					<div class="sm-overview-person-usage-container">
						<div class="sm-person-usage-wrapper">
							<RatioProgress
								:current="vm.persons.known"
								:total="vm.persons.total"
								:primary-text="`${vm.persons.known} ${vm.$avt('status:known_suffix', 'Persons')}`"
								:secondary-text="`${vm.persons.unknown} ${vm.$avt('status:unknown_suffix', 'unknown persons')}`"
							/>
							<div class="sm-overview-person-mappings" :title="vm.$avt('status:name_mappings_hint', 'Names that are replaced by others')">{{ vm.$avt('status:name_mappings', 'Name mappings') }}: {{ vm.persons.mappings }}</div>
						</div>
					</div>
				</div>
			</div>
		</section>
		<section class="panel">
			<div class="sm-section-title sm-section-title-block">{{ vm.$avt('status:files_title', 'Files') }}</div>
			<div class="panel-head panel-content-start">
				<p>{{ vm.$avt('status:files_desc', 'Analyze image files and sidecars for face metadata formats.') }}</p>
			</div>
			<div v-if="Number(vm.getFileAnalysisStatusProgress().total) > 0" class="sm-status-progress">
				<ProgressOverviewCard
					:title="vm.getFileAnalysisStatusProgressTitle()"
					:count="Number(vm.getFileAnalysisStatusProgress().total) || 0"
					:current="Number(vm.getFileAnalysisStatusProgress().current) || 0"
					:total="Number(vm.getFileAnalysisStatusProgress().total) || 0"
					:primary-label="vm.getFileAnalysisStatusProgressPrimaryLabel()"
					:secondary-label="vm.getFileAnalysisStatusProgressSecondaryLabel()"
					:status-text="vm.getFileAnalysisStatusMessage(vm.fileAnalysisProgress)"
				/>
			</div>
			<div class="sm-files-result-details">
				<div v-for="counter in vm.getFileAnalysisStatusCounters()" :key="`file-analysis-counter-${counter.key}`"><strong>{{ counter.label }}:</strong> {{ counter.value }}</div>
				<div><strong>{{ vm.$avt('status:last_run', 'Last run') }}:</strong> {{ vm.formatAnalysisTimestamp(vm.fileAnalysisProgress.finished_at || vm.fileAnalysisProgress.started_at) }}</div>
				<div><strong>{{ vm.$avt('status:files_seen', 'Files seen') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_seen_total) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:files_matched', 'Matching files') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_matched_total) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:files_analyzed', 'Analyzed') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_analyzed) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:files_with_sidecar', 'With sidecar') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_sidecar) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:files_with_embedded_xmp', 'With embedded XMP') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_embedded_xmp) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:files_with_face_metadata', 'With face metadata') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_face_metadata) || 0 }}</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_dimension_issues)"><strong>{{ vm.$avt('status:files_with_mwg_applied_to_dimensions', 'With MWG AppliedToDimensions') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_mwg_applied_to_dimensions) || 0 }}</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_dimension_issues)"><strong>{{ vm.$avt('status:files_with_mwg_dimension_mismatch', 'With MWG dimension mismatch') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_mwg_dimension_mismatch) || 0 }}</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_dimension_issues)"><strong>{{ vm.$avt('status:files_with_mwg_orientation_transform_risk', 'With MWG orientation transform risk') }}:</strong> {{ Number(vm.fileAnalysisProgress.files_with_mwg_orientation_transform_risk) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:faces_total', 'Faces') }}:</strong> {{ Number(vm.fileAnalysisProgress.faces_total) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:faces_named', 'Named') }}:</strong> {{ Number(vm.fileAnalysisProgress.faces_named) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:faces_unnamed', 'Unnamed') }}:</strong> {{ Number(vm.fileAnalysisProgress.faces_unnamed) || 0 }}</div>
				<div><strong>{{ vm.$avt('status:persons_distinct', 'Distinct persons') }}:</strong> {{ Number(vm.fileAnalysisProgress.persons_distinct_by_name) || 0 }}</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_duplicate_faces)">
					<strong>{{ vm.$avt('status:files_with_duplicate_faces', 'With duplicate face markings') }}:</strong>
					{{ Number(vm.fileAnalysisProgress.files_with_duplicate_faces) }}
				</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_face_position_deviations)">
					<strong>{{ vm.$avt('status:files_with_face_position_deviations', 'With deviating face positions') }}:</strong>
					{{ Number(vm.fileAnalysisProgress.files_with_face_position_deviations) }}
				</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_dimension_issues)">
					<strong>{{ vm.$avt('status:files_with_dimension_issues', 'With dimension issues') }}:</strong>
					{{ Number(vm.fileAnalysisProgress.files_with_dimension_issues) }}
				</div>
				<div v-if="vm.hasAnalysisCheckValue(vm.fileAnalysisProgress.files_with_name_conflicts)">
					<strong>{{ vm.$avt('status:files_with_name_conflicts', 'With name conflicts') }}:</strong>
					{{ Number(vm.fileAnalysisProgress.files_with_name_conflicts) }}
				</div>
				<div v-if="vm.formatAnalysisCountSummary(vm.fileAnalysisProgress.focus_usages, 'raw') !== '-'">
					<strong>{{ vm.$avt('status:focus_usages', 'Focus usage') }}:</strong>
					{{ vm.formatAnalysisCountSummary(vm.fileAnalysisProgress.focus_usages, 'raw') }}
				</div>
				<div><strong>{{ vm.$avt('status:formats', 'Formats') }}:</strong> {{ vm.formatAnalysisCountSummary(vm.fileAnalysisProgress.formats, 'format') }}</div>
				<div><strong>{{ vm.$avt('status:sources', 'Sources') }}:</strong> {{ vm.formatAnalysisCountSummary(vm.fileAnalysisProgress.sources, 'source') }}</div>
			</div>
			<div v-if="vm.getFileAnalysisWarningMessage(vm.fileAnalysisProgress)" class="sm-files-warning">
				{{ vm.getFileAnalysisWarningMessage(vm.fileAnalysisProgress) }}
			</div>
			<div class="sm-files-action-row">
				<v-button @click="vm.handleFilesAnalyze" style="width: 160px;">{{ vm.isFileAnalysisRunning ? vm.$avt('status:button_stop_analysis', 'Stop') : vm.$avt('status:button_analyze', 'Analyze') }}</v-button>
			</div>
		</section>
		<section class="panel">
			<div class="sm-section-title sm-section-title-block">{{ vm.$avt('status:system_title', 'System') }}</div>
			<div v-if="vm.statusLoading" class="sm-overview-person-loading">
				<span class="sm-loader"></span>
				{{ vm.$avt('status:loading', 'Loading data...') }}
			</div>
			<div v-else class="sm-system-grid">
				<div class="sm-status-card">
					<div class="sm-status-head">
						<div class="sm-section-title">{{ vm.$avt('status:settings_components', 'Settings and components') }}</div>
					</div>
					<div class="sm-kv-list sm-kv-list-compact">
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:shared_folder', 'Photos shared folder') }}</div>
							<div class="sm-kv-value">{{ vm.system.sharedFolder || vm.$avt('status:not_available', 'Not available') }}</div>
						</div>
						<div class="sm-kv-row">
							<div class="sm-kv-key">{{ vm.$avt('status:perl_component_version', 'Perl version') }}</div>
							<div class="sm-kv-value">{{ vm.getPerlStatusValue() }}</div>
						</div>
					</div>
				</div>
			</div>
		</section>
	</div>
</template>

<script>
import ProgressOverviewCard from '../components/ProgressOverviewCard.vue';
import RatioProgress from '../components/RatioProgress.vue';

export default {
	name: 'StatusView',
	components: {
		ProgressOverviewCard,
		RatioProgress,
	},
	props: {
		vm: {
			type: Object,
			required: true,
		},
	},
};
</script>
