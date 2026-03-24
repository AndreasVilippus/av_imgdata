<template>
	<v-app-instance class-name="SYNO.SDS.App.AV_ImgData.Instance">
		<v-app-window width="850" min-width="600" height="574" ref="appWindow" :resizable="true" syno-id="SYNO.SDS.App.AV_ImgData.Window">
			<div class="sm-shell">
				<div class="sm-body">
					<app-sidebar-nav :selected-option="selectedOption" @select="selectContent" />

					<main class="sm-content">
						<template v-if="selectedOption === 'status'">
							<section class="panel">
								<div class="sm-overview-person-title">{{ $t('status:overview_title', 'Person detection in Photos') }}</div>
								<div v-if="statusLoading" class="sm-overview-person-loading">
									<span class="sm-loader"></span>
									{{ $t('status:loading', 'Loading data...') }}
								</div>
								<div v-else class="sm-overview-person-card">
									<div class="sm-overview-person-icon-wrap">
										<img class="sm-overview-person-icon" :src="personsIconUrl" alt="" />
									</div>
									<div class="sm-overview-person-table">
										<div class="sm-overview-person-desc">
											<div class="sm-overview-person-mini-text">{{ $t('status:photos_persons', 'Photos persons') }}</div>
											<div class="sm-overview-person-mini-usedby">{{ persons.total }}</div>
										</div>
										<div class="sm-overview-person-usage-container">
											<div class="sm-person-usage-wrapper">
												<div class="sm-person-usage-bg">
													<div class="sm-person-usage-bar" :style="{ width: knownRatioPercent + '%' }"></div>
												</div>
												<div class="sm-person-usage-text">
													<span class="sm-person-usage-known">{{ persons.known }} {{ $t('status:known_suffix', 'Persons') }}</span>
													<span class="sm-person-usage-sep"> | </span>
													<span class="sm-person-usage-unknown">{{ persons.unknown }} {{ $t('status:unknown_suffix', 'unknown persons') }}</span>
												</div>
												<div class="sm-overview-person-mappings" :title="$t('status:name_mappings_hint', 'Names that are replaced by others')">{{ $t('status:name_mappings', 'Name mappings') }}: {{ persons.mappings }}</div>
											</div>
										</div>
									</div>
								</div>
							</section>
							<section class="panel">
								<div class="sm-system-title">{{ $t('status:files_title', 'Files') }}</div>
								<div class="sm-system-card">
									<div class="sm-system-row">
										<div class="sm-system-label">{{ $t('status:files_desc', 'Analyze image files and sidecars for face metadata formats.') }}</div>
										<div class="sm-system-value">{{ getFileAnalysisStatusMessage(fileAnalysisProgress) }}</div>
									</div>
								</div>
								<div class="sm-files-result-details">
									<div><strong>{{ $t('status:last_run', 'Last run') }}:</strong> {{ formatAnalysisTimestamp(fileAnalysisProgress.finished_at || fileAnalysisProgress.started_at) }}</div>
									<div><strong>{{ $t('status:files_seen', 'Files seen') }}:</strong> {{ Number(fileAnalysisProgress.files_seen_total) || 0 }}</div>
									<div><strong>{{ $t('status:files_matched', 'Matching files') }}:</strong> {{ Number(fileAnalysisProgress.files_matched_total) || 0 }}</div>
									<div><strong>{{ $t('status:files_analyzed', 'Analyzed') }}:</strong> {{ Number(fileAnalysisProgress.files_analyzed) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_sidecar', 'With sidecar') }}:</strong> {{ Number(fileAnalysisProgress.files_with_sidecar) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_embedded_xmp', 'With embedded XMP') }}:</strong> {{ Number(fileAnalysisProgress.files_with_embedded_xmp) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_face_metadata', 'With face metadata') }}:</strong> {{ Number(fileAnalysisProgress.files_with_face_metadata) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_mwg_applied_to_dimensions', 'With MWG AppliedToDimensions') }}:</strong> {{ Number(fileAnalysisProgress.files_with_mwg_applied_to_dimensions) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_mwg_dimension_mismatch', 'With MWG dimension mismatch') }}:</strong> {{ Number(fileAnalysisProgress.files_with_mwg_dimension_mismatch) || 0 }}</div>
									<div><strong>{{ $t('status:files_with_mwg_orientation_transform_risk', 'With MWG orientation transform risk') }}:</strong> {{ Number(fileAnalysisProgress.files_with_mwg_orientation_transform_risk) || 0 }}</div>
									<div><strong>{{ $t('status:faces_total', 'Faces') }}:</strong> {{ Number(fileAnalysisProgress.faces_total) || 0 }}</div>
									<div><strong>{{ $t('status:faces_named', 'Named') }}:</strong> {{ Number(fileAnalysisProgress.faces_named) || 0 }}</div>
									<div><strong>{{ $t('status:faces_unnamed', 'Unnamed') }}:</strong> {{ Number(fileAnalysisProgress.faces_unnamed) || 0 }}</div>
									<div><strong>{{ $t('status:persons_distinct', 'Distinct persons') }}:</strong> {{ Number(fileAnalysisProgress.persons_distinct_by_name) || 0 }}</div>
									<div><strong>{{ $t('status:focus_usages', 'Focus usage') }}:</strong> {{ formatAnalysisCountSummary(fileAnalysisProgress.focus_usages, 'raw') }}</div>
									<div><strong>{{ $t('status:formats', 'Formats') }}:</strong> {{ formatAnalysisCountSummary(fileAnalysisProgress.formats, 'format') }}</div>
									<div><strong>{{ $t('status:sources', 'Sources') }}:</strong> {{ formatAnalysisCountSummary(fileAnalysisProgress.sources, 'source') }}</div>
								</div>
								<div v-if="getFileAnalysisWarningMessage(fileAnalysisProgress)" class="sm-files-warning">
									{{ getFileAnalysisWarningMessage(fileAnalysisProgress) }}
								</div>
								<div class="sm-files-action-row">
									<v-button @click="handleFilesAnalyze" style="width: 160px;">{{ isFileAnalysisRunning ? $t('status:button_stop_analysis', 'Stop') : $t('status:button_analyze', 'Analyze') }}</v-button>
								</div>
							</section>
							<section class="panel">
								<div class="sm-system-title">{{ $t('status:system_title', 'System') }}</div>
								<div v-if="statusLoading" class="sm-overview-person-loading">
									<span class="sm-loader"></span>
									{{ $t('status:loading', 'Loading data...') }}
								</div>
								<div v-else class="sm-system-card">
									<div class="sm-system-row">
										<div class="sm-system-label">{{ $t('status:shared_folder', 'Photos shared folder') }}</div>
										<div class="sm-system-value">{{ system.sharedFolder || $t('status:not_available', 'Not available') }}</div>
									</div>
								</div>
							</section>
						</template>

						<template v-if="selectedOption === 'face_match'">
							<section class="panel">
								<div class="panel-head">
									<h1>{{ $t('face_match:title', 'Face Matching') }}</h1>
									<p>{{ $t('face_match:desc', 'Area for matching and file-processing actions.') }}</p>
								</div>
								<div class="face-match-top-layout">
									<div class="face-match-action-controls">
										<select v-model="selectedFaceMatchingAction" class="face-match-select" :disabled="faceMatchLoading">
											<option value="search_photo_face_in_file">{{ $t('face_match:action_search_photo_face_in_file', 'search unknown Photos face in file') }}</option>
										</select>
										<div class="face-match-action-buttons">
											<v-button @click="handlePrimaryFaceMatchButton" style="width: 160px;">
												{{ faceMatchPrimaryButtonLabel }}
											</v-button>
											<v-button
												v-if="faceMatchResultSummary.found"
												@click="loadNextFaceMatch"
												:disabled="faceMatchLoading"
												style="width: 160px;"
											>
												{{ $t('face_match:button_next', 'Next') }}
											</v-button>
										</div>
										<label class="face-match-switch">
											<input v-model="faceMatchPreviewMode" type="checkbox" true-value="face" false-value="photo" />
											<span class="face-match-switch-slider"></span>
											<span class="face-match-switch-label">{{ $t('face_match:switch_face_only', 'Show face only') }}</span>
										</label>
										<label class="face-match-switch">
											<input v-model="faceMatchAutoAssignKnown" type="checkbox" />
											<span class="face-match-switch-slider"></span>
											<span class="face-match-switch-label">{{ $t('face_match:switch_auto_assign', 'Assign all known') }}</span>
										</label>
									</div>
									<div class="face-match-status-column">
										<div class="face-match-status-card face-match-status-card-action">
											<div class="face-match-status-head">
												<div class="face-match-status-title">{{ $t('face_match:card_action', 'Action') }}</div>
												<div v-if="faceMatchLoading" class="face-match-status-running">
													<span class="sm-loader"></span>
													{{ $t('face_match:card_running', 'Running') }}
												</div>
											</div>
											<div class="face-match-status-message">{{ faceMatchStatusMessage }}</div>
											<div class="face-match-status-stats">
												<span>{{ $t('face_match:label_persons', 'Persons') }}: {{ faceMatchDisplayedProgress.persons_read }}</span>
												<span>{{ $t('face_match:label_images', 'Images') }}: {{ faceMatchDisplayedProgress.images_read }}</span>
												<span>{{ $t('face_match:label_faces', 'Faces') }}: {{ faceMatchDisplayedProgress.faces_read }}</span>
												<span :title="$t('face_match:label_metadata_hint', 'Read metadata')">{{ $t('face_match:label_metadata', 'Metadata') }}: {{ faceMatchDisplayedProgress.metadata_faces_read }}</span>
												<span>{{ $t('face_match:label_transferred', 'Transferred') }}: {{ faceMatchDisplayedTransferredCount }}</span>
											</div>
											<div class="face-match-status-context">
												<span v-if="faceMatchProgress.current_person_id">{{ $t('face_match:label_person_id', 'Person ID') }}: {{ faceMatchProgress.current_person_id }}</span>
												<span v-if="faceMatchProgress.current_image_id">{{ $t('face_match:label_image_id', 'Image ID') }}: {{ faceMatchProgress.current_image_id }}</span>
												<span v-if="faceMatchProgress.current_face_id">{{ $t('face_match:label_face_id', 'Face ID') }}: {{ faceMatchProgress.current_face_id }}</span>
											</div>
										</div>
										<div class="face-match-status-card face-match-status-card-result">
											<div class="face-match-status-head">
												<div class="face-match-status-title">{{ $t('face_match:card_result', 'Result') }}</div>
											</div>
											<div v-if="faceMatchResultSummary.found" class="face-match-result-layout">
												<div class="face-match-result-details">
													<label class="face-match-result-name-field">
														<strong>{{ $t('face_match:label_name', 'Name:') }}</strong>
														<input
															v-model.trim="faceMatchEditableName"
															type="text"
															class="face-match-result-name-input"
															:placeholder="$t('face_match:name_placeholder', 'Name of the match')"
															@input="handleFaceMatchNameInput"
															@focus="handleFaceMatchNameFocus"
														/>
														<div
															v-if="faceMatchShowSuggestions && (faceMatchPersonSuggestLoading || faceMatchPersonSuggestions.length)"
															class="face-match-suggest-list"
														>
															<div v-if="faceMatchPersonSuggestLoading" class="face-match-suggest-loading">
																<span class="sm-loader"></span>
																{{ $t('face_match:suggest_loading', 'Loading suggestions...') }}
															</div>
															<button
																v-for="person in faceMatchPersonSuggestions"
																:key="`face-person-suggest-${person.id}`"
																type="button"
																class="face-match-suggest-item"
																@click="selectFaceMatchSuggestion(person)"
															>
																<img
																:src="getFaceMatchPersonPreviewUrl(person)"
																alt=""
																class="face-match-suggest-thumb"
															/>
															<span class="face-match-suggest-text">
																<span class="face-match-suggest-name">{{ person.name || $t('face_match:unknown_name', '(unnamed)') }}</span>
																<span class="face-match-suggest-meta">{{ $t('face_match:suggest_person_id', 'Photos Person-ID: {id}', { id: person.id }) }}</span>
															</span>
														</button>
													</div>
												</label>
												<div><strong>{{ $t('face_match:label_source', 'Source:') }}</strong> {{ faceMatchResultSummary.source }}</div>
												<div><strong>{{ $t('face_match:label_format', 'Format:') }}</strong> {{ faceMatchResultSummary.format }}</div>
												<div v-if="faceMatchResultSummary.photosPersonId"><strong>{{ $t('face_match:label_photos_person_id', 'Photos Person ID:') }}</strong> {{ faceMatchResultSummary.photosPersonId }}</div>
											</div>
											<div class="face-match-person-preview">
												<img
													:src="getFaceMatchPersonPreviewUrl(faceMatchEffectivePerson)"
													:alt="$t('face_match:person_preview_alt', 'Person preview')"
													class="face-match-person-preview-image"
												/>
												</div>
											</div>
											<div v-else class="face-match-status-message">
												{{ faceMatchResultSummary.message }}
											</div>
										</div>
									</div>
								</div>
							</section>
							<section class="panel face-match-split-panel">
								<div v-if="faceMatchLoading" class="face-match-loading">
									<span class="sm-loader"></span>
									{{ $t('face_match:loading', 'Loading data...') }}
								</div>
								<div v-else class="face-match-split">
									<button
										v-if="faceMatchActionMode"
										type="button"
										class="face-match-icon-button face-match-icon-button-floating"
										:title="faceMatchTransferTooltip"
										:aria-label="faceMatchTransferTooltip"
										@click.prevent="handleFaceMatchAction"
									>
										<span v-if="personDataToLeftIconUrl" class="face-match-icon-stack">
											<img
												:src="personDataToLeftIconUrl"
												alt=""
												class="face-match-icon-image"
											/>
											<img
												v-if="faceMatchActionMode === 'create' && addIconUrl"
												:src="addIconUrl"
												alt=""
												class="face-match-icon-overlay"
											/>
										</span>
										<span v-else class="face-match-icon-fallback">{{ faceMatchTransferTooltip }}</span>
									</button>
									<div class="face-match-col">
										<h2>{{ $t('face_match:photos_title', 'Photos') }}</h2>
										<div v-if="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)" class="face-match-thumbnail-wrap">
											<template v-if="isFaceOnlyPreview">
												<div v-if="getFaceMatchCropStyle(faceMatchResult && faceMatchResult.face)" class="face-match-crop-frame">
													<img
														:src="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)"
														:alt="$t('face_match:face_preview_alt', 'Face preview')"
														class="face-match-crop-image"
														:style="getFaceMatchCropStyle(faceMatchResult && faceMatchResult.face)"
													/>
												</div>
											</template>
												<div v-else class="face-match-preview">
													<img
														:src="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)"
														:alt="$t('face_match:thumbnail_alt', 'Thumbnail')"
														class="face-match-thumbnail"
													/>
													<div
														v-for="(maskStyle, index) in getFaceMatchMaskStyles(faceMatchResult && faceMatchResult.face)"
														:key="`photo-mask-${index}`"
														class="face-match-mask"
														:style="maskStyle"
													></div>
													<div
														v-if="getFaceMatchBoxStyle(faceMatchResult && faceMatchResult.face)"
														class="face-match-bbox"
														:style="getFaceMatchBoxStyle(faceMatchResult && faceMatchResult.face)"
													></div>
											</div>
										</div>
										<div v-else class="face-match-empty">{{ $t('face_match:empty_no_thumbnail', 'No thumbnail found yet.') }}</div>
									</div>
									<div class="face-match-col">
										<h2>{{ faceMatchFileTitle }}</h2>
										<div v-if="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)" class="face-match-thumbnail-wrap">
											<template v-if="isFaceOnlyPreview">
												<div v-if="getFaceMatchCropStyle(getRightFaceMatchFace())" class="face-match-crop-frame">
													<img
														:src="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)"
														:alt="$t('face_match:face_preview_alt', 'Face preview')"
														class="face-match-crop-image"
														:style="getFaceMatchCropStyle(getRightFaceMatchFace())"
													/>
												</div>
											</template>
												<div v-else class="face-match-preview">
													<img
														:src="getFaceMatchThumbnailUrl(faceMatchResult && faceMatchResult.image)"
														:alt="$t('face_match:thumbnail_alt', 'Thumbnail')"
														class="face-match-thumbnail"
													/>
													<div
														v-for="(maskStyle, index) in getFaceMatchMaskStyles(getRightFaceMatchFace())"
														:key="`metadata-mask-${index}`"
														class="face-match-mask"
														:style="maskStyle"
													></div>
													<div
														v-if="getFaceMatchBoxStyle(getRightFaceMatchFace())"
														class="face-match-bbox"
														:style="getFaceMatchBoxStyle(getRightFaceMatchFace())"
													></div>
											</div>
										</div>
										<div v-else class="face-match-empty">{{ $t('face_match:empty_no_preview', 'No preview found yet.') }}</div>
									</div>
								</div>
							</section>
						</template>
						<section v-if="selectedOption === 'checks'" class="panel">
							<div class="panel-head">
								<h1>{{ $t('checks:title', 'Checks') }}</h1>
								<p>{{ $t('checks:desc', 'Area for validation and review functions.') }}</p>
							</div>
							<div class="checks-actions">
								<select v-model="selectedChecksAction" class="face-match-select" :disabled="checksLoading">
									<option value="findings">{{ $t('checks:action_findings', 'Use mismatch findings') }}</option>
									<option value="scan">{{ $t('checks:action_scan', 'Run mismatch scan') }}</option>
								</select>
								<div class="face-match-action-buttons">
									<v-button @click="startChecksReview" :disabled="checksLoading" style="width: 160px;">
										{{ checksLoading ? $t('checks:button_loading', 'Loading...') : $t('checks:button_start', 'Start') }}
									</v-button>
									<v-button @click="nextChecksReview" :disabled="checksLoading || !hasNextChecksItem" style="width: 160px;">
										{{ $t('checks:button_next', 'Next') }}
									</v-button>
								</div>
							</div>
							<div class="face-match-status-card face-match-status-card-action">
								<div class="face-match-status-head">
									<div class="face-match-status-title">{{ $t('checks:status_title', 'Status') }}</div>
								</div>
								<div class="face-match-status-message">{{ checksStatusMessage }}</div>
								<div v-if="currentChecksItem" class="face-match-status-stats">
									<div><strong>{{ $t('checks:label_file', 'File:') }}</strong> {{ currentChecksItem.image_name }}</div>
									<div><strong>{{ $t('checks:label_face_name', 'Face:') }}</strong> {{ currentChecksItem.face_name || $t('face_match:unknown_name', '(unnamed)') }}</div>
									<div><strong>{{ $t('checks:label_index', 'Entry:') }}</strong> {{ checksCurrentIndex + 1 }} / {{ checksItems.length }}</div>
								</div>
							</div>
							<div v-if="currentChecksItem" class="face-match-split checks-split">
								<div class="face-match-col">
									<h2>{{ $t('checks:preview_applied', 'With handling') }}</h2>
									<div v-if="getChecksImageUrl(currentChecksItem)" class="face-match-thumbnail-wrap">
										<div class="face-match-preview">
											<img
												:src="getChecksImageUrl(currentChecksItem)"
												:alt="$t('checks:image_alt', 'Check preview')"
												class="face-match-thumbnail"
											/>
											<div
												v-for="(maskStyle, index) in getFaceMatchMaskStyles(currentChecksItem.applied_face)"
												:key="`checks-applied-mask-${index}`"
												class="face-match-mask"
												:style="maskStyle"
											></div>
											<div
												v-if="getFaceMatchBoxStyle(currentChecksItem.applied_face)"
												class="face-match-bbox"
												:style="getFaceMatchBoxStyle(currentChecksItem.applied_face)"
											></div>
										</div>
									</div>
									<div v-else class="face-match-empty">{{ $t('checks:empty_image', 'No preview available.') }}</div>
								</div>
								<div class="face-match-col">
									<h2>{{ $t('checks:preview_ignored', 'Ignoring handling') }}</h2>
									<div v-if="getChecksImageUrl(currentChecksItem)" class="face-match-thumbnail-wrap">
										<div class="face-match-preview">
											<img
												:src="getChecksImageUrl(currentChecksItem)"
												:alt="$t('checks:image_alt', 'Check preview')"
												class="face-match-thumbnail"
											/>
											<div
												v-for="(maskStyle, index) in getFaceMatchMaskStyles(currentChecksItem.raw_face)"
												:key="`checks-raw-mask-${index}`"
												class="face-match-mask"
												:style="maskStyle"
											></div>
											<div
												v-if="getFaceMatchBoxStyle(currentChecksItem.raw_face)"
												class="face-match-bbox"
												:style="getFaceMatchBoxStyle(currentChecksItem.raw_face)"
											></div>
										</div>
									</div>
									<div v-else class="face-match-empty">{{ $t('checks:empty_image', 'No preview available.') }}</div>
								</div>
							</div>
							<div v-else class="config-placeholder">
								<div class="config-placeholder-title">{{ $t('checks:placeholder_title', 'Checks will be added here.') }}</div>
							</div>
						</section>
						<configuration-view v-if="selectedOption === 'configuration'" />
					</main>
				</div>
				<div v-if="nameMappingConfirm.visible" class="sm-modal-backdrop">
					<div class="sm-modal" role="dialog" aria-modal="true" aria-labelledby="name-mapping-confirm-title">
						<div id="name-mapping-confirm-title" class="sm-modal-title">{{ $t('face_match:modal_mapping_title', 'Save name mapping') }}</div>
						<div class="sm-modal-text">{{ nameMappingConfirm.message }}</div>
						<div class="sm-modal-actions">
							<v-button @click="resolveNameMappingConfirm(false)" style="width: 120px;">{{ $t('face_match:button_no', 'No') }}</v-button>
							<v-button @click="resolveNameMappingConfirm(true)" style="width: 120px;">{{ $t('face_match:button_yes', 'Yes') }}</v-button>
						</div>
					</div>
				</div>
			</div>
		</v-app-window>
	</v-app-instance>
</template>

<script>
import AppSidebarNav from './components/AppSidebarNav.vue';
import ConfigurationView from './views/ConfigurationView.vue';

export default {
	components: {
		AppSidebarNav,
		ConfigurationView,
	},
	data() {
		return {
			selectedOption: 'status',
			output: '',
			statusLoading: false,
			statusLoaded: false,
			fileAnalysisProgress: {},
			fileAnalysisProgressTimer: null,
			faceMatchLoading: false,
			faceMatchProgress: {},
			faceMatchProgressBase: {},
			faceMatchProgressTimer: null,
			faceMatchAbortController: null,
			faceMatchResult: null,
			faceMatchSkippedFaceIds: [],
			faceMatchPreviewMode: 'photo',
			faceMatchAutoAssignKnown: false,
			faceMatchTransferredCount: 0,
			faceMatchEditableName: '',
			faceMatchInitialEditableName: '',
			faceMatchSelectedPerson: null,
			faceMatchPersonSuggestions: [],
			faceMatchPersonSuggestLoading: false,
			faceMatchShowSuggestions: false,
			faceMatchSuggestTimer: null,
			faceMatchSuggestRequestId: 0,
			selectedFaceMatchingAction: 'search_photo_face_in_file',
			selectedChecksAction: 'findings',
			checksLoading: false,
			checksItems: [],
			checksCurrentIndex: 0,
			checksStatusMessage: '',
			persons: {
				total: 0,
				known: 0,
				unknown: 0,
				mappings: 0,
			},
			system: {
				sharedFolder: "",
			},
			personsIconUrl: '/webman/3rdparty/AV_ImgData/images/persons_known_unknown.png',
			addIconUrl: '',
			personDataToLeftIconUrl: '',
			nameMappingConfirm: {
				visible: false,
				message: '',
				resolver: null,
			},
		};
	},
	computed: {
		isFileAnalysisRunning() {
			const progress = this.fileAnalysisProgress && typeof this.fileAnalysisProgress === 'object' ? this.fileAnalysisProgress : {};
			return Boolean(progress.running) && !Boolean(progress.finished);
		},
		knownRatioPercent() {
			if (!this.persons.total) {
				return 0;
			}
			return Math.max(0, Math.min(100, (this.persons.known / this.persons.total) * 100));
		},
		isFaceOnlyPreview() {
			return this.faceMatchPreviewMode === 'face';
		},
		faceMatchDisplayedTransferredCount() {
			const progressCount = Number(this.faceMatchProgress && this.faceMatchProgress.transferred_count);
			if (Number.isFinite(progressCount) && progressCount > 0) {
				return progressCount;
			}
			return this.faceMatchTransferredCount;
		},
		faceMatchDisplayedProgress() {
			const fields = ['persons_read', 'images_read', 'faces_read', 'metadata_faces_read'];
			return fields.reduce((acc, field) => {
				const baseValue = Number(this.faceMatchProgressBase && this.faceMatchProgressBase[field]) || 0;
				const currentValue = Number(this.faceMatchProgress && this.faceMatchProgress[field]) || 0;
				acc[field] = baseValue + currentValue;
				return acc;
			}, {});
		},
		faceMatchStatusMessage() {
			const progress = this.faceMatchProgress && typeof this.faceMatchProgress === 'object'
				? this.faceMatchProgress
				: null;
			if (progress && progress.message_key) {
				return this.$t(
					progress.message_key,
					progress.message || progress.message_key,
					progress.message_params && typeof progress.message_params === 'object'
						? progress.message_params
						: null
				);
			}
			if (progress && progress.message) {
				return progress.message;
			}
			return this.faceMatchLoading
				? this.$t('face_match:status_search_running', 'Search running...')
				: this.$t('face_match:status_idle', 'No action running.');
		},
		faceMatchIsPaused() {
			return !this.faceMatchLoading && !!(this.faceMatchResult && this.faceMatchResult.searched);
		},
		faceMatchPrimaryButtonLabel() {
			if (this.faceMatchLoading) {
				return this.$t('face_match:button_stop', 'Stop');
			}
			if (this.faceMatchIsPaused) {
				return this.$t('face_match:button_restart', 'Restart');
			}
			return this.$t('face_match:button_start', 'Start');
		},
		faceMatchResultSummary() {
			if (this.faceMatchLoading) {
				return { found: false, message: this.$t('face_match:result_none', 'No result yet.') };
			}
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const match = this.faceMatchResult && this.faceMatchResult.match;
			const matchedPerson = this.faceMatchEffectivePerson;
			if (match && metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$t('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (metadataFace) {
				return {
					found: true,
					name: metadataFace.name || this.$t('face_match:unknown_name', '(unnamed)'),
					source: this.getFaceMatchSourceLabel(metadataFace.source),
					format: this.getFaceMatchFormatLabel(metadataFace.source_format || metadataFace.format),
					photosPersonId: matchedPerson && matchedPerson.id ? matchedPerson.id : null,
				};
			}
			if (this.faceMatchResult && this.faceMatchResult.searched) {
				return { found: false, message: this.$t('face_match:result_no_match', 'No match found yet.') };
			}
			return { found: false, message: this.$t('face_match:result_none', 'No result yet.') };
		},
		faceMatchTransferTooltip() {
			if (this.faceMatchActionMode === 'create') {
				return this.$t('face_match:transfer_tooltip_create', 'Create person and apply name from file');
			}
			return this.$t('face_match:transfer_tooltip_assign', 'Apply name from file');
		},
		faceMatchActionMode() {
			if (!this.faceMatchResultSummary.found) {
				return '';
			}
			return this.faceMatchResultSummary.photosPersonId ? 'assign' : 'create';
		},
		faceMatchEffectivePerson() {
			if (this.faceMatchSelectedPerson && this.faceMatchEditableNameMatchesPerson(this.faceMatchSelectedPerson)) {
				return this.faceMatchSelectedPerson;
			}
			const matchedPerson = this.faceMatchResult && this.faceMatchResult.matched_person;
			if (matchedPerson && this.faceMatchEditableNameMatchesPerson(matchedPerson)) {
				return matchedPerson;
			}
			return null;
		},
		faceMatchFileTitle() {
			const matchedPerson = this.faceMatchEffectivePerson;
			if (matchedPerson && matchedPerson.id && matchedPerson.name) {
				return `${this.$t('face_match:file_title', 'File')} - ${matchedPerson.name}`;
			}
			return this.$t('face_match:file_title', 'File');
		},
		faceMatchHasStoredNameMapping() {
			const mapping = this.faceMatchResult && this.faceMatchResult.name_mapping;
			return !!(mapping && mapping.source_name && mapping.target_name);
		},
		currentChecksItem() {
			return this.checksItems[this.checksCurrentIndex] || null;
		},
		hasNextChecksItem() {
			return this.checksCurrentIndex + 1 < this.checksItems.length;
		},
	},
	mounted() {
		this.addIconUrl = this.resolveLocalIconUrl('add_icon.png');
		this.personDataToLeftIconUrl = this.resolveLocalIconUrl('person_data_to_left.png');
		this.getStatus({ auto: true });
		this.fetchFileAnalysisProgress();
	},
	beforeDestroy() {
		if (this.faceMatchSuggestTimer) {
			window.clearTimeout(this.faceMatchSuggestTimer);
			this.faceMatchSuggestTimer = null;
		}
		if (this.faceMatchAbortController) {
			this.faceMatchAbortController.abort();
			this.faceMatchAbortController = null;
		}
		this.resolveNameMappingConfirm(false);
		this.stopFaceMatchProgressPolling();
		this.stopFileAnalysisProgressPolling();
	},
	methods: {
		close() {
			this.$refs.appWindow.close();
		},
		resolveLocalIconUrl(filename) {
			if (!filename) {
				return '';
			}
			return `/webman/3rdparty/AV_ImgData/images/${filename}`;
		},
		selectContent(option) {
			this.selectedOption = option;
			if (option === 'status' && !this.statusLoaded && !this.statusLoading) {
				this.getStatus({ auto: true });
			}
			if (option === 'status') {
				this.fetchFileAnalysisProgress();
			}
		},
		readCookie(name) {
			const match = document.cookie.match(new RegExp('(?:^|; )' + name.replace(/[.$?*|{}()\[\]\\/+^]/g, '\\$&') + '=([^;]*)'));
			return match ? decodeURIComponent(match[1]) : '';
		},
		collectDsmCookies() {
			return {
				_SSID: this.readCookie('_SSID'),
				id: this.readCookie('id'),
				did: this.readCookie('did'),
			};
		},
		async callFileAnalysisApi(apiPath) {
			await synocredential._instance.Resume();

			const remote = synocredential._instance.GetRemoteKey();
			const params = synocredential._instance.GetResumeParams({}, remote) || {};
			const kk_message = params.kk_message || '';
			const synoToken = this.getSynoToken();
			const cookies = this.collectDsmCookies();

			const resp = await fetch(apiPath, {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					'X-SYNO-TOKEN': synoToken,
				},
				body: JSON.stringify({
					kk_message,
					synoToken,
					cookies,
				}),
			});
			const data = await resp.json().catch(() => ({}));
			if (!resp.ok || data.success === false) {
				const backendError = data.error || `HTTP ${resp.status}`;
				throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
			}
			return data;
		},
		async callChecksApi(apiPath, body = {}) {
			await synocredential._instance.Resume();

			const remote = synocredential._instance.GetRemoteKey();
			const params = synocredential._instance.GetResumeParams({}, remote) || {};
			const kk_message = params.kk_message || '';
			const synoToken = this.getSynoToken();
			const cookies = this.collectDsmCookies();

			const resp = await fetch(apiPath, {
				method: 'POST',
				credentials: 'include',
				headers: {
					'Content-Type': 'application/json',
					'X-SYNO-TOKEN': synoToken,
				},
				body: JSON.stringify({
					...body,
					kk_message,
					synoToken,
					cookies,
				}),
			});
			const data = await resp.json().catch(() => ({}));
			if (!resp.ok || data.success === false) {
				const backendError = data.error || `HTTP ${resp.status}`;
				throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
			}
			return data;
		},
		async fetchFileAnalysisProgress() {
			try {
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_progress');
				this.fileAnalysisProgress = (data && data.data && typeof data.data === 'object') ? data.data : {};
				if (!this.isFileAnalysisRunning) {
					this.stopFileAnalysisProgressPolling();
				}
			} catch (err) {
				return;
			}
		},
		startFileAnalysisProgressPolling() {
			this.stopFileAnalysisProgressPolling();
			this.fetchFileAnalysisProgress();
			this.fileAnalysisProgressTimer = window.setInterval(() => {
				this.fetchFileAnalysisProgress();
			}, 1000);
		},
		stopFileAnalysisProgressPolling() {
			if (this.fileAnalysisProgressTimer) {
				window.clearInterval(this.fileAnalysisProgressTimer);
				this.fileAnalysisProgressTimer = null;
			}
		},
		formatCountSummary(counterMap) {
			if (!counterMap || typeof counterMap !== 'object') {
				return '-';
			}
			const entries = Object.entries(counterMap)
				.filter(([, value]) => Number(value) > 0)
				.sort((left, right) => String(left[0]).localeCompare(String(right[0])));
			if (!entries.length) {
				return '-';
			}
			return entries.map(([key, value]) => `${key}: ${value}`).join(', ');
		},
		formatAnalysisCountSummary(counterMap, kind) {
			if (!counterMap || typeof counterMap !== 'object') {
				return '-';
			}
			const entries = Object.entries(counterMap)
				.filter(([, value]) => Number(value) > 0)
				.sort((left, right) => String(left[0]).localeCompare(String(right[0])));
			if (!entries.length) {
				return '-';
			}
			return entries.map(([key, value]) => {
				const label = kind === 'source'
					? this.getFaceMatchSourceLabel(key)
					: (kind === 'format' ? this.getFaceMatchFormatLabel(key) : String(key));
				return `${label}: ${value}`;
			}).join(', ');
		},
		formatAnalysisTimestamp(value) {
			if (!value) {
				return '-';
			}
			const parsed = new Date(value);
			if (Number.isNaN(parsed.getTime())) {
				return String(value);
			}
			return parsed.toLocaleString();
		},
		getFileAnalysisStatusMessage(progress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			const analyzed = Number(current.files_analyzed) || 0;
			const total = Number(current.files_matched_total) || 0;

			if (current.stop_requested) {
				return this.$t('status:analyze_stopping', 'Stopping file analysis...');
			}
			if (current.running && current.phase === 'discovery') {
				return this.$t('status:progress_discovery_running', 'Scanning files...');
			}
			if (current.running && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_running',
					'Analyzing face metadata... {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'stopped' && current.phase === 'discovery') {
				return this.$t(
					'status:progress_discovery_stopped',
					'Discovery stopped. 0 of {total} files analyzed.',
					{ total }
				);
			}
			if (current.status === 'stopped' && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_stopped',
					'Analysis stopped. {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'finished' && current.phase === 'analysis') {
				return this.$t(
					'status:progress_analysis_finished',
					'Analysis finished. {current} of {total} files analyzed.',
					{ current: analyzed, total }
				);
			}
			if (current.status === 'failed' && !current.shared_folder) {
				return this.$t('status:progress_shared_folder_missing', 'Shared folder not found.');
			}
			if (current.status === 'failed') {
				return this.$t('status:progress_analysis_failed', 'File analysis failed.');
			}
			return current.message || this.$t('status:analyze_idle', 'No file analysis has been started yet.');
		},
		getFileAnalysisWarningMessage(progress) {
			const current = progress && typeof progress === 'object' ? progress : {};
			const mismatchCount = Number(current.files_with_mwg_dimension_mismatch) || 0;
			const orientationRiskCount = Number(current.files_with_mwg_orientation_transform_risk) || 0;
			if (mismatchCount > 0 && orientationRiskCount > 0) {
				return this.$t(
					'status:warning_mwg_mismatch_and_orientation',
					'Warning: {mismatch} files with MWG dimension mismatches and {risk} files with MWG orientation transform risk were found.',
					{ mismatch: mismatchCount, risk: orientationRiskCount }
				);
			}
			if (mismatchCount > 0) {
				return this.$t(
					'status:warning_mwg_mismatch',
					'Warning: {count} files with MWG dimension mismatches were found.',
					{ count: mismatchCount }
				);
			}
			if (orientationRiskCount > 0) {
				return this.$t(
					'status:warning_mwg_orientation_risk',
					'Warning: {count} files with MWG orientation transform risk were found.',
					{ count: orientationRiskCount }
				);
			}
			return '';
		},
		getChecksImageUrl(item) {
			const imagePath = item && item.image_path ? String(item.image_path).trim() : '';
			if (!imagePath) {
				return '';
			}
			return `/webman/3rdparty/AV_ImgData/index.cgi/api/file_image?path=${encodeURIComponent(imagePath)}`;
		},
		getFaceMatchSourceLabel(source) {
			const normalized = String(source || '').trim().toLowerCase();
			if (!normalized) {
				return this.$t('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'xmp_file') {
				return this.$t('face_match:source_xmp_file', 'XMP sidecar file');
			}
			if (normalized === 'embedded_xmp_parsed') {
				return this.$t('face_match:source_embedded_xmp', 'Embedded XMP');
			}
			if (normalized === 'embedded_xmp_exiftool') {
				return this.$t('face_match:source_embedded_xmp_exiftool', 'Embedded XMP via ExifTool');
			}
			if (normalized === 'metadata') {
				return this.$t('face_match:source_metadata', 'Metadata');
			}
			return String(source || '')
				.replace(/[_-]+/g, ' ')
				.replace(/\s+/g, ' ')
				trim()
				.replace(/\b\w/g, (char) => char.toUpperCase());
		},
		getFaceMatchFormatLabel(format) {
			const normalized = String(format || '').trim().toUpperCase();
			if (!normalized) {
				return this.$t('face_match:result_unknown', 'unknown');
			}
			if (normalized === 'ACD' || normalized === 'ACDSEE') {
				return this.$t('face_match:format_acdsee', 'ACDSee');
			}
			if (normalized === 'MICROSOFT') {
				return this.$t('face_match:format_microsoft', 'Microsoft People Tagging');
			}
			if (normalized === 'MWG_REGIONS') {
				return this.$t('face_match:format_mwg_regions', 'MWG face regions');
			}
			return String(format);
		},
		async startChecksReview() {
			this.checksLoading = true;
			this.checksStatusMessage = this.$t('checks:status_loading', 'Loading checks...');
			try {
				const data = await this.callChecksApi('/webman/3rdparty/AV_ImgData/index.cgi/api/checks_dimension_mismatch_start', {
					source_mode: this.selectedChecksAction,
				});
				const items = data && data.data && Array.isArray(data.data.items) ? data.data.items : [];
				this.checksItems = items;
				this.checksCurrentIndex = 0;
				this.checksStatusMessage = items.length
					? this.$t('checks:status_loaded', '{count} entries loaded.', { count: items.length })
					: this.$t('checks:status_empty', 'No matching entries found.');
			} catch (err) {
				this.checksStatusMessage = `Error: ${err.message}`;
			} finally {
				this.checksLoading = false;
			}
		},
		nextChecksReview() {
			if (!this.hasNextChecksItem) {
				return;
			}
			this.checksCurrentIndex += 1;
			this.checksStatusMessage = this.$t('checks:status_entry', 'Entry {current} of {total}.', {
				current: this.checksCurrentIndex + 1,
				total: this.checksItems.length,
			});
		},
		extractPersonsFromPayload(payload) {
			const root = payload && typeof payload === 'object' ? payload : {};
			const data = root.data && typeof root.data === 'object' ? root.data : {};
			const personsSource = (data.persons && typeof data.persons === 'object')
				? data.persons
				: ((root.persons && typeof root.persons === 'object') ? root.persons : {});
			const total = Number(personsSource.total) || 0;
			const known = Number(personsSource.known) || 0;
			const unknownFromPayload = personsSource.unknown ?? personsSource.unkwown;
			const unknown = Number.isFinite(Number(unknownFromPayload))
				? Number(unknownFromPayload)
				: Math.max(total - known, 0);
			return {
				total: Math.max(total, 0),
				known: Math.max(known, 0),
				unknown: Math.max(unknown, 0),
				mappings: Math.max(Number(personsSource.mappings) || 0, 0),
			};
		},
		extractSystemFromPayload(payload) {
			const root = payload && typeof payload === "object" ? payload : {};
			const data = root.data && typeof root.data === "object" ? root.data : {};
			const systemSource = (data.system && typeof data.system === "object")
				? data.system
				: ((root.system && typeof root.system === "object") ? root.system : {});
			return {
				sharedFolder: String(systemSource.shared_folder || systemSource.sharedFolder || ""),
			};
		},
		getSynoToken() {
			return (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
		},
		getFaceMatchBBox(face) {
			if (!face || typeof face !== 'object') {
				return null;
			}

			if (face.bbox) {
				const topLeft = face.bbox.top_left;
				const bottomRight = face.bbox.bottom_right;
				const left = Number(topLeft && topLeft.x);
				const top = Number(topLeft && topLeft.y);
				const right = Number(bottomRight && bottomRight.x);
				const bottom = Number(bottomRight && bottomRight.y);

				if (![left, top, right, bottom].every(Number.isFinite)) {
					return null;
				}

				const width = right - left;
				const height = bottom - top;
				if (width <= 0 || height <= 0) {
					return null;
				}

				return { left, top, width, height };
			}

			const centerX = Number(face.x);
			const centerY = Number(face.y);
			const width = Number(face.w);
			const height = Number(face.h);

			if (![centerX, centerY, width, height].every(Number.isFinite)) {
				return null;
			}
			if (width <= 0 || height <= 0) {
				return null;
			}

			return {
				left: centerX - (width / 2),
				top: centerY - (height / 2),
				width,
				height,
			};
		},
		getFaceMatchBoxStyle(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return null;
			}

			return {
				left: `${bbox.left * 100}%`,
				top: `${bbox.top * 100}%`,
				width: `${bbox.width * 100}%`,
				height: `${bbox.height * 100}%`,
			};
		},
		getFaceMatchMaskStyles(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return [];
			}

			const left = Math.max(0, bbox.left);
			const top = Math.max(0, bbox.top);
			const right = Math.min(1, bbox.left + bbox.width);
			const bottom = Math.min(1, bbox.top + bbox.height);

			return [
				{ left: '0', top: '0', width: '100%', height: `${top * 100}%` },
				{ left: '0', top: `${top * 100}%`, width: `${left * 100}%`, height: `${Math.max(0, bottom - top) * 100}%` },
				{ left: `${right * 100}%`, top: `${top * 100}%`, width: `${Math.max(0, 1 - right) * 100}%`, height: `${Math.max(0, bottom - top) * 100}%` },
				{ left: '0', top: `${bottom * 100}%`, width: '100%', height: `${Math.max(0, 1 - bottom) * 100}%` },
			];
		},
		getFaceMatchCropStyle(face) {
			const bbox = this.getFaceMatchBBox(face);
			if (!bbox) {
				return null;
			}

			return {
				width: `${100 / bbox.width}%`,
				height: `${100 / bbox.height}%`,
				left: `-${(bbox.left / bbox.width) * 100}%`,
				top: `-${(bbox.top / bbox.height) * 100}%`,
			};
		},
		getRightFaceMatchFace() {
			if (!this.faceMatchResult || !this.faceMatchResult.match) {
				return null;
			}
			return this.faceMatchResult.metadata_face || null;
		},
		getPhotoThumbnailUrl(image) {
			const itemId = image && image.id;
			const thumbnail = (image && image.additional && image.additional.thumbnail)
				|| (image && image.thumbnail);
			const cacheKey = thumbnail && thumbnail.cache_key;
			const synoToken = this.getSynoToken();
			if (!itemId || !cacheKey || !synoToken) {
				return '';
			}

			const params = new URLSearchParams();
			params.set('id', String(itemId));
			params.set('cache_key', `"${cacheKey}"`);
			params.set('type', '"unit"');
			params.set('size', '"sm"');
			params.set('SynoToken', synoToken);
			return `/synofoto/api/v2/t/Thumbnail/get?${params.toString()}`;
		},
		getFaceMatchThumbnailUrl(image) {
			return this.getPhotoThumbnailUrl(image);
		},
		getFaceMatchPersonThumbnailUrl(person) {
			const personId = person && person.id;
			const thumbnail = (person && person.additional && person.additional.thumbnail)
				|| (person && person.thumbnail);
			const cacheKey = thumbnail && thumbnail.cache_key;
			const synoToken = this.getSynoToken();
			if (!personId || !cacheKey || !synoToken) {
				return '';
			}

			const params = new URLSearchParams();
			params.set('id', String(personId));
			params.set('cache_key', `"${cacheKey}"`);
			params.set('type', '"person"');
			params.set('size', '"sm"');
			params.set('SynoToken', synoToken);
			return `/synofoto/api/v2/t/Thumbnail/get?${params.toString()}`;
		},
		getFaceMatchPersonPreviewUrl(person) {
			return this.getFaceMatchPersonThumbnailUrl(person) || this.resolveLocalIconUrl('person_unknown.png');
		},
		getCurrentFaceMatchFaceId() {
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			return Number.isFinite(Number(faceId)) ? Number(faceId) : null;
		},
		getFaceMatchEditableNameDefault() {
			const metadataFace = this.faceMatchResult && this.faceMatchResult.metadata_face;
			const fallbackName = metadataFace && metadataFace.name ? String(metadataFace.name).trim() : '';
			return fallbackName || '';
		},
		normalizeFaceMatchName(name) {
			return String(name || '').trim().replace(/\s+/g, ' ').toLocaleLowerCase();
		},
		faceMatchEditableNameMatchesPerson(person) {
			if (!person || !person.name) {
				return false;
			}
			return this.normalizeFaceMatchName(this.faceMatchEditableName) === this.normalizeFaceMatchName(person.name);
		},
		captureFaceMatchProgressBase() {
			this.faceMatchProgressBase = { ...this.faceMatchDisplayedProgress };
		},
		syncFaceMatchEditableName() {
			const sourceName = this.getFaceMatchEditableNameDefault();
			const matchedPerson = this.faceMatchResult && this.faceMatchResult.matched_person;
			const matchedPersonName = matchedPerson && matchedPerson.name ? String(matchedPerson.name).trim() : '';
			this.faceMatchEditableName = matchedPersonName || sourceName;
			this.faceMatchInitialEditableName = sourceName;
			this.faceMatchSelectedPerson = matchedPerson && matchedPerson.id ? matchedPerson : null;
			this.faceMatchPersonSuggestions = [];
			this.faceMatchPersonSuggestLoading = false;
			this.faceMatchShowSuggestions = false;
		},
		handleFaceMatchNameFocus() {
			if (this.faceMatchPersonSuggestions.length) {
				this.faceMatchShowSuggestions = true;
			}
		},
		handleFaceMatchNameInput() {
			const selectedPerson = this.faceMatchSelectedPerson;
			if (selectedPerson && !this.faceMatchEditableNameMatchesPerson(selectedPerson)) {
				this.faceMatchSelectedPerson = null;
			}
			this.scheduleFaceMatchSuggestions();
		},
		scheduleFaceMatchSuggestions() {
			if (this.faceMatchSuggestTimer) {
				window.clearTimeout(this.faceMatchSuggestTimer);
				this.faceMatchSuggestTimer = null;
			}
			const query = this.faceMatchEditableName.trim();
			if (!query || query.length < 1) {
				this.faceMatchPersonSuggestions = [];
				this.faceMatchPersonSuggestLoading = false;
				this.faceMatchShowSuggestions = false;
				return;
			}
			this.faceMatchSuggestTimer = window.setTimeout(() => {
				this.fetchFaceMatchSuggestions(query);
			}, 200);
		},
		async fetchFaceMatchSuggestions(query) {
			const currentQuery = String(query || '').trim();
			if (!currentQuery) {
				this.faceMatchPersonSuggestions = [];
				this.faceMatchPersonSuggestLoading = false;
				this.faceMatchShowSuggestions = false;
				return;
			}
			const requestId = this.faceMatchSuggestRequestId + 1;
			this.faceMatchSuggestRequestId = requestId;
			this.faceMatchPersonSuggestLoading = true;
			this.faceMatchShowSuggestions = true;
			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error('kk_message could not be read from ResumeParams');
				}
				if (!synoToken) {
					throw new Error('SYNO.SDS.Session.SynoToken is empty');
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_person_suggest', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						name_prefix: currentQuery,
						limit: 10,
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}
				if (this.faceMatchSuggestRequestId !== requestId) {
					return;
				}
				this.faceMatchPersonSuggestions = Array.isArray(data && data.data && data.data.list) ? data.data.list : [];
				this.faceMatchShowSuggestions = this.faceMatchPersonSuggestions.length > 0;
			} catch (err) {
				if (this.faceMatchSuggestRequestId !== requestId) {
					return;
				}
				this.faceMatchPersonSuggestions = [];
				this.faceMatchShowSuggestions = false;
			} finally {
				if (this.faceMatchSuggestRequestId === requestId) {
					this.faceMatchPersonSuggestLoading = false;
				}
			}
		},
		selectFaceMatchSuggestion(person) {
			if (!person || !person.id) {
				return;
			}
			this.faceMatchSelectedPerson = person;
			this.faceMatchEditableName = person.name || '';
			this.faceMatchPersonSuggestions = [];
			this.faceMatchShowSuggestions = false;
			this.faceMatchPersonSuggestLoading = false;
		},
		resolveFaceMatchNameMappingPreference(targetName) {
			const sourceName = (this.faceMatchInitialEditableName || '').trim();
			const nextName = String(targetName || '').trim();
			if (!sourceName || !nextName) {
				return Promise.resolve({ saveMapping: false, sourceName: '' });
			}
			if (this.normalizeFaceMatchName(sourceName) === this.normalizeFaceMatchName(nextName)) {
				return Promise.resolve({ saveMapping: false, sourceName });
			}
			if (this.faceMatchHasStoredNameMapping) {
				return Promise.resolve({ saveMapping: false, sourceName });
			}
			return this.confirmFaceMatchNameMapping(sourceName, nextName).then((saveMapping) => ({ saveMapping, sourceName }));
		},
		confirmFaceMatchNameMapping(sourceName, targetName) {
			return new Promise((resolve) => {
				this.nameMappingConfirm.visible = true;
				this.nameMappingConfirm.message = this.$t(
					'face_match:confirm_save_mapping',
					'Should "{source}" always be mapped to "{target}"?',
					{ source: sourceName, target: targetName }
				);
				this.nameMappingConfirm.resolver = resolve;
			});
		},
		resolveNameMappingConfirm(value) {
			const resolver = this.nameMappingConfirm.resolver;
			this.nameMappingConfirm.visible = false;
			this.nameMappingConfirm.message = '';
			this.nameMappingConfirm.resolver = null;
			if (typeof resolver === 'function') {
				resolver(!!value);
			}
		},
		buildNextSkippedFaceIds() {
			const currentFaceId = this.getCurrentFaceMatchFaceId();
			if (!currentFaceId) {
				return this.faceMatchSkippedFaceIds.slice();
			}
			const nextIds = this.faceMatchSkippedFaceIds.slice();
			if (!nextIds.includes(currentFaceId)) {
				nextIds.push(currentFaceId);
			}
			return nextIds;
		},
		async fetchFaceMatchingProgress() {
			try {
				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_progress', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': this.getSynoToken(),
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken: this.getSynoToken(),
					}),
				});
				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					return;
				}
				this.faceMatchProgress = (data && data.data && typeof data.data === 'object') ? data.data : {};
			} catch (err) {
				return;
			}
		},
		startFaceMatchProgressPolling() {
			this.stopFaceMatchProgressPolling();
			this.fetchFaceMatchingProgress();
			this.faceMatchProgressTimer = window.setInterval(() => {
				this.fetchFaceMatchingProgress();
			}, 1000);
		},
		stopFaceMatchProgressPolling() {
			if (this.faceMatchProgressTimer) {
				window.clearInterval(this.faceMatchProgressTimer);
				this.faceMatchProgressTimer = null;
			}
		},
		async callStatusApi(apiPath, { auto = false, updatePersons = true } = {}) {
			this.statusLoading = true;
			if (!auto) {
				this.output = 'start synocredential resume flow...';
			}
			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch(apiPath, {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(backendError);
				}
				if (updatePersons) {
					this.persons = this.extractPersonsFromPayload(data);
					this.system = this.extractSystemFromPayload(data);
					this.statusLoaded = true;
				}
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				this.output = `Error: ${err.message}`;
			} finally {
				this.statusLoading = false;
			}
		},
		async getStatus(options = {}) {
			return this.callStatusApi('/webman/3rdparty/AV_ImgData/index.cgi/api/status', options);
		},
		async handleFilesAnalyze() {
			try {
				const current = this.isFileAnalysisRunning;
				if (current) {
					await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_stop');
					this.output = this.$t('status:analyze_stopping', 'Stopping file analysis...');
					await this.fetchFileAnalysisProgress();
					return;
				}
				const data = await this.callFileAnalysisApi('/webman/3rdparty/AV_ImgData/index.cgi/api/file_analysis_start');
				this.fileAnalysisProgress = (data && data.data && typeof data.data === 'object') ? data.data : {};
				this.startFileAnalysisProgressPolling();
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				this.output = `Error: ${err.message}`;
			}
		},
		async loadNextFaceMatch() {
			this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
			await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
		},
		async handlePrimaryFaceMatchButton() {
			if (this.faceMatchLoading) {
				await this.stopFaceMatchingAction();
				return;
			}
			await this.startFaceMatchingAction();
		},
		async stopFaceMatchingAction() {
			try {
			const synoToken = this.getSynoToken();
				await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_stop', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						cookies: this.collectDsmCookies(),
						synoToken,
					}),
				});
			} catch (err) {
				// Best effort; the in-flight search request is aborted below.
			}
			if (this.faceMatchAbortController) {
				this.faceMatchAbortController.abort();
				this.faceMatchAbortController = null;
			}
			this.faceMatchLoading = false;
			this.stopFaceMatchProgressPolling();
			this.output = this.$t('face_match:output_stopping', 'Stopping search...');
			await this.fetchFaceMatchingProgress();
		},
		async handleFaceMatchAction() {
			if (this.faceMatchActionMode === 'create') {
				await this.createFaceMatchPerson();
				return;
			}
			await this.assignFaceMatchToPerson();
		},
		async createFaceMatchPerson() {
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			const personName = (this.faceMatchEditableName || this.getFaceMatchEditableNameDefault()).trim();
			if (!faceId || !personName) {
				this.output = this.$t('face_match:error_missing_face_or_name', 'Error: Missing face ID or person name.');
				return;
			}
			const mappingPreference = await this.resolveFaceMatchNameMappingPreference(personName);

			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_create_match', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						face_id: faceId,
						person_name: personName,
						save_mapping: mappingPreference.saveMapping,
						source_name: mappingPreference.sourceName,
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}

				this.output = JSON.stringify(data, null, 2);
				this.faceMatchTransferredCount += 1;
				this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
				await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
			} catch (err) {
				this.output = `Error: ${err.message}`;
			}
		},
		async assignFaceMatchToPerson() {
			const matchedPersonId = this.faceMatchEffectivePerson && this.faceMatchEffectivePerson.id;
			const faceId = this.faceMatchResult && this.faceMatchResult.face && this.faceMatchResult.face.face_id;
			const matchedPersonName = (this.faceMatchEditableName || '').trim();
			if (!matchedPersonId || !faceId || !matchedPersonName) {
				this.output = this.$t('face_match:error_missing_known_person', 'Error: Missing known person ID, face ID, or person name.');
				return;
			}
			const mappingPreference = await this.resolveFaceMatchNameMappingPreference(matchedPersonName);

			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = this.getSynoToken();
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_assign_match', {
					method: 'POST',
					credentials: 'include',
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						face_id: faceId,
						person_id: matchedPersonId,
						person_name: matchedPersonName,
						save_mapping: mappingPreference.saveMapping,
						source_name: mappingPreference.sourceName,
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}

				this.output = JSON.stringify(data, null, 2);
				this.faceMatchTransferredCount += 1;
				this.faceMatchSkippedFaceIds = this.buildNextSkippedFaceIds();
				await this.startFaceMatchingAction({ resetSkippedFaceIds: false });
			} catch (err) {
				this.output = `Error: ${err.message}`;
			}
		},
		async startFaceMatchingAction(options = {}) {
			if (this.faceMatchLoading) {
				return;
			}
			const resetSkippedFaceIds = options.resetSkippedFaceIds !== false;
			if (resetSkippedFaceIds) {
				this.faceMatchSkippedFaceIds = [];
				this.faceMatchTransferredCount = 0;
				this.faceMatchProgressBase = {};
			} else {
				this.captureFaceMatchProgressBase();
			}

			this.faceMatchLoading = true;
			this.faceMatchProgress = {
				message: this.$t('face_match:status_starting', 'Search starting...'),
				persons_read: 0,
				images_read: 0,
				faces_read: 0,
			};
			this.faceMatchResult = null;
			this.faceMatchEditableName = '';
			this.faceMatchInitialEditableName = '';
			this.faceMatchSelectedPerson = null;
			this.faceMatchPersonSuggestions = [];
			this.faceMatchPersonSuggestLoading = false;
			this.faceMatchShowSuggestions = false;
			this.faceMatchAbortController = new AbortController();
			this.startFaceMatchProgressPolling();
			this.output = this.$t('face_match:output_start_action', 'Starting action: {action}', { action: this.selectedFaceMatchingAction });
			try {
				await synocredential._instance.Resume();

				const remote = synocredential._instance.GetRemoteKey();
				const params = synocredential._instance.GetResumeParams({}, remote) || {};
				const kk_message = params.kk_message || '';
				const synoToken = (SYNO && SYNO.SDS && SYNO.SDS.Session && SYNO.SDS.Session.SynoToken) || '';
				const cookies = this.collectDsmCookies();

				if (!kk_message) {
					throw new Error(this.$t('face_match:error_missing_resume_message', 'kk_message could not be read from ResumeParams'));
				}
				if (!synoToken) {
					throw new Error(this.$t('face_match:error_missing_synotoken', 'SYNO.SDS.Session.SynoToken is empty'));
				}

				const resp = await fetch('/webman/3rdparty/AV_ImgData/index.cgi/api/face_matching_action', {
					method: 'POST',
					credentials: 'include',
					signal: this.faceMatchAbortController.signal,
					headers: {
						'Content-Type': 'application/json',
						'X-SYNO-TOKEN': synoToken,
					},
					body: JSON.stringify({
						action: this.selectedFaceMatchingAction,
						auto: this.faceMatchAutoAssignKnown,
						skip_face_ids: this.faceMatchSkippedFaceIds,
						kk_message,
						synoToken,
						cookies,
					}),
				});

				const data = await resp.json().catch(() => ({}));
				if (!resp.ok || data.success === false) {
					const backendError = data.error || `HTTP ${resp.status}`;
					throw new Error(typeof backendError === 'string' ? backendError : JSON.stringify(backendError));
				}

				this.faceMatchResult = data.data && data.data.face_matches ? data.data.face_matches : null;
				this.syncFaceMatchEditableName();
				const transferredCount = Number(
					data && data.data && data.data.face_matches && data.data.face_matches.transferred_count
				) || 0;
				this.faceMatchTransferredCount += transferredCount;
				this.output = JSON.stringify(data, null, 2);
			} catch (err) {
				if (err && err.name === 'AbortError') {
					this.output = this.$t('face_match:output_stopped', 'Search stopped.');
					return;
				}
				this.faceMatchResult = null;
				this.faceMatchEditableName = '';
				this.faceMatchInitialEditableName = '';
				this.faceMatchSelectedPerson = null;
				this.faceMatchPersonSuggestions = [];
				this.faceMatchPersonSuggestLoading = false;
				this.faceMatchShowSuggestions = false;
				this.output = `Error: ${err.message}`;
			} finally {
				this.faceMatchAbortController = null;
				this.faceMatchLoading = false;
				this.stopFaceMatchProgressPolling();
				await this.fetchFaceMatchingProgress();
			}
		},
	},
};
</script>
